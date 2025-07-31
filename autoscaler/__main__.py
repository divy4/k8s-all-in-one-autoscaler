from typing import Any, Dict

import collections
import json
import logging
import numpy
import tabulate

import autoscaler.k8s_manager as k8s_manager
import autoscaler.metrics_collector as metrics_collector
import autoscaler.util as util

logger = logging.getLogger(__name__)


def autoscale_resources() -> None:
    """Autoscales all resources in K8s"""
    # Setup
    logging.basicConfig(level=logging.INFO)
    config = util.Config("config.json")
    collector = metrics_collector.MetricsCollector(config)
    manager = k8s_manager.K8sManager(config)
    # Gather metrics
    # TODO: continuously gather resources because pods/containers that belong a
    # deployment don't always exist/have different requests/limits.
    resources = manager.get_container_resources()
    metrics = collector.get_all_container_metrics()
    # Suggest resources
    suggestions = suggest_all_resources(manager, resources, metrics)


def suggest_all_resources(
    manager: k8s_manager.K8sManager,  # The K8sManager object.
    resources: Dict[
        util.ContainerSpecLocation, Dict[util.Container, Dict | None]
    ],  # All container resources, grouped by their controller.
    metrics: Dict[util.Container, Dict[str, float]],  # All container metrics.
) -> Dict[util.ContainerSpecLocation, Dict[str, Dict[str, int | float | str]]]:
    """Suggests resources for containers."""
    logger.info("Generating resource suggestions...")

    spec_suggestions = {}
    if logger.parent.level <= logging.DEBUG:
        debug_table_data = []

    # Generate suggestions for each container spec
    for spec, resources in resources.items():
        # Get metrics for containers specific to this spec
        container_metrics = {container: metrics[container] for container in resources}
        # Generate suggestions for each container and the spec itself
        container_suggestions = suggest_resources(spec, resources, container_metrics)
        # Log the metrics for each container
        if logger.parent.level <= logging.DEBUG:
            for container, suggestion in container_suggestions.items():
                if container is None:
                    continue
                debug_table_data.append(
                    (
                        container.namespace,
                        container.pod,
                        container.container,
                        manager.humanize_resources(suggestion),
                    )
                )
        # Set the suggestion for the spec
        spec_suggestions[spec] = manager.humanize_resources(container_suggestions[None])

    # Print the results of every pod's container
    if logger.parent.level <= logging.DEBUG:
        table = tabulate.tabulate(
            sorted(debug_table_data),
            headers=("Namespace", "Pod", "Container", "Suggestion"),
        )
        logger.debug(f"Specific container suggestions:\n{table}")

    # Print the results of the specs
    table = tabulate.tabulate(
        sorted(
            (spec.namespace, f"{spec.kind}/{spec.name}", spec.container, suggestion)
            for spec, suggestion in spec_suggestions.items()
        ),
        headers=("Namespace", "Object", "Container", "Suggestion"),
    )
    logger.info(f"Object suggestions:\n{table}")
    return spec_suggestions


def suggest_resources(
    spec_location: util.ContainerSpecLocation,  # The location of the container spec.
    container_resources: Dict[
        util.Container, Dict | None
    ],  # The resources of each container.
    container_metrics: Dict[util.Container, Any],  # The metrics of each container
) -> Dict[util.Container | None, Dict[str, int | float | str]]:
    """Suggests resources for containers in a location + for the container spec
    in general."""
    suggestions = collections.defaultdict(
        lambda: collections.defaultdict(lambda: collections.defaultdict(lambda: 0))
    )
    for container, resources in container_resources.items():
        metrics = container_metrics[container]
        # CPU request
        if "cpu_usage" in metrics:
            suggestions[container]["requests"]["cpu"] = numpy.average(
                (metrics["cpu_usage"]["25th%"], metrics["cpu_usage"]["75th%"])
            )
        # Memory request
        if "memory_usage" in metrics:
            suggestions[container]["requests"]["memory"] = numpy.average(
                (metrics["memory_usage"]["25th%"], metrics["memory_usage"]["75th%"])
            )

    # Suggest the maximum of each individual container's suggestion
    suggestions[None] = util.dict_max(*suggestions.values())

    return suggestions


if __name__ == "__main__":
    autoscale_resources()
