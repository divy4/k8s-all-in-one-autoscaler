from typing import Any, Dict

import kubernetes

import autoscaler.util as util


class K8sManager:
    """A class for managing K8s resources."""

    def __init__(self, config: util.Config):
        self.__config = config

    # Resource conversion

    def humanize_resources(
        self,
        resources: Dict[str, Dict[str, int | float]],  # The resources block of a pod.
    ) -> Dict[util.Container, Any]:
        """Reformats resources into Kubernetes human-readable values, e.g. 10Mi,
        123m, 1.7Gi."""
        if "requests" in resources:
            if "cpu" in resources["requests"]:
                resources["requests"]["cpu"] = self.humanize_cpu(
                    resources["requests"]["cpu"]
                )
            if "memory" in resources["requests"]:
                resources["requests"]["memory"] = self.humanize_memory(
                    resources["requests"]["memory"]
                )
        if "limits" in resources:
            if "cpu" in resources["requests"]:
                resources["requests"]["cpu"] = self.humanize_cpu(
                    resources["requests"]["cpu"]
                )
            if "memory" in resources["limits"]:
                resources["limits"]["memory"] = self.humanize_memory(
                    resources["limits"]["memory"]
                )

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
