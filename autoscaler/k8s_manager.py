from typing import Any, Dict, Iterable

import collections
import kubernetes
import json


import autoscaler.util as util

kubernetes.config.load_kube_config()

SUPPORTED_CONTROLLER_TYPES = {
    "DaemonSet",
    "Deployment",
    "StatefulSet",
}

SUPPORTED_PARENT_TYPES = {
    "CronJob",
    "DaemonSet",
    "Deployment",
    "Job",
    "Pod",
    "ReplicaSet",
    "StatefulSet",
}


class K8sManager:
    """A class for managing K8s resources."""

    def __init__(self, config: util.Config):
        self.__config = config
        self.__v1 = kubernetes.client.CoreV1Api()
        self.__apps_v1 = kubernetes.client.AppsV1Api()
        self.__batch_v1 = kubernetes.client.BatchV1Api()

    # Resources

    def get_container_resources(
        self,
    ) -> Dict[util.ContainerSpecLocation, Dict[util.Container, Dict | None]]:
        """Returns the resources of every container in the cluster."""
        item_functions = {
            "Pod": self.__v1.list_pod_for_all_namespaces,
            "ReplicaSet": self.__apps_v1.list_replica_set_for_all_namespaces,
            "Job": self.__batch_v1.list_job_for_all_namespaces,
        }

        direct_owners = {}
        direct_resources = {}

        # Build map of direct owners of resources
        for resource_kind, item_function in item_functions.items():
            for resource in item_function().items:
                # Ignore resources without owners and unsupported owner resources
                if (
                    resource.metadata.owner_references is None
                    or len(resource.metadata.owner_references) != 1
                ):
                    continue
                owner = resource.metadata.owner_references[0]
                if owner.kind not in SUPPORTED_PARENT_TYPES:
                    continue

                # Note what owns this resource
                resource_dto = util.K8sObject(
                    resource_kind, resource.metadata.namespace, resource.metadata.name
                )
                owner_dto = util.K8sObject(
                    owner.kind, resource.metadata.namespace, owner.name
                )
                direct_owners[resource_dto] = owner_dto

                # Note the owner and resources of each container
                if resource_kind == "Pod":
                    for container in resource.spec.containers:
                        container_dto = util.Container(
                            resource.metadata.namespace,
                            resource.metadata.name,
                            container.name,
                        )
                        direct_owners[container_dto] = resource_dto
                        direct_resources[container_dto] = container.resources

        resources = collections.defaultdict(dict)

        # Build map of containers to the top-level resource that controls them
        # Using tuple() to allow editing the dict during the loop
        for container in direct_resources.keys():
            # Follow direct owner up to controlling resource
            controller = container
            while controller in direct_owners:
                controller = direct_owners[controller]

            # Ignore this container if we don't support its controller
            if controller.kind not in SUPPORTED_CONTROLLER_TYPES:
                continue

            # Set container spec location
            spec_location = util.ContainerSpecLocation.from_parent(
                controller, container
            )

            # Note what resources are set for the container
            resources[spec_location][container] = direct_resources[container]

        return resources

    # Resource conversion

    def humanize_resources(
        self,
        resources: Dict[str, Dict[str, int | float]],  # The resources block of a pod.
    ) -> Dict[str, Dict[str, int | float | str]]:
        """Reformats resources into Kubernetes human-readable values, e.g. 10Mi,
        123m, 1.7Gi."""
        humanized = {}

        if "requests" in resources:
            humanized["requests"] = {}
            if "cpu" in resources["requests"]:
                humanized["requests"]["cpu"] = self.humanize_cpu(
                    resources["requests"]["cpu"]
                )
            if "memory" in resources["requests"]:
                humanized["requests"]["memory"] = self.humanize_memory(
                    resources["requests"]["memory"]
                )
        if "limits" in resources:
            humanized["limits"] = {}
            if "cpu" in resources["requests"]:
                humanized["requests"]["cpu"] = self.humanize_cpu(
                    resources["requests"]["cpu"]
                )
            if "memory" in resources["limits"]:
                humanized["limits"]["memory"] = self.humanize_memory(
                    resources["limits"]["memory"]
                )

        return humanized

    def humanize_cpu(self, x: float) -> str:
        """Reformats a raw cpu value to a human-readable K8s value, e.g. 123m."""
        if x <= 0:
            raise ValueError(f"Unable to convert '{x}' to a Kubernetes cpu value.")
        elif x < 0.001:
            return "1m"
        elif x < 1:
            return f"{util.advanced_ceil(x * 1000, self.__config.suggestion_significant_digits, 0)}m"
        else:
            return str(
                util.advanced_ceil(x, self.__config.suggestion_significant_digits)
            )

    def humanize_memory(self, x: float) -> str:
        """Reformats a raw memory value to a human-readable K8s value, e.g. 10Mi."""
        x = int(x)
        if x <= 0:
            raise ValueError(f"Unable to convert '{x}' to a Kubernetes memory value.")
        elif x < 1024:
            return str(
                util.advanced_ceil(x, self.__config.suggestion_significant_digits)
            )
        elif x < 1024**2:
            return f"{util.advanced_ceil(x / 1024, self.__config.suggestion_significant_digits)}Ki"
        elif x < 1024**3:
            return f"{util.advanced_ceil(x / 1024 ** 2, self.__config.suggestion_significant_digits)}Mi"
        else:
            return f"{util.advanced_ceil(x / 1024 ** 3, self.__config.suggestion_significant_digits)}Gi"
