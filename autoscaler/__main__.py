from typing import Any, Dict

import collections
import json
import logging
import numpy

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
    suggestions = suggest_all_resources(resources, metrics)
    for location, suggestion in suggestions.items():
        suggestion = manager.humanize_resources(suggestion)
        print(f"\n{location}:\n{json.dumps(suggestion)}")


def suggest_all_resources(
    resources: Dict[
        util.ContainerSpecLocation, Dict[util.Container, Dict | None]
    ],  # All container resources, grouped by their controller.
    metrics: Dict[util.Container, Dict[str, float]],  # All container metrics.
) -> None:
    """Suggests resources for containers."""
    logger.info("Generating resource suggestions...")

    # Generate suggestions for each container spec
    suggestions = {}
    for spec_location, container_resources in resources.items():
        container_metrics = {
            container: metrics[container] for container in container_resources
        }
        suggestions[spec_location] = suggest_resources(
            spec_location, container_resources, container_metrics
        )
    return suggestions


def suggest_resources(
    spec_location: util.ContainerSpecLocation,  # The location of the container spec.
    container_resources: Dict[
        util.Container, Dict | None
    ],  # The resources of each container.
    container_metrics: Dict[util.Container, Any],  # The metrics of each container
) -> Dict[util.Container, Any]:
    """Suggests resources for containers."""
    suggestion = collections.defaultdict(lambda: collections.defaultdict(lambda: 0))

    for container, resources in container_resources.items():
        metrics = container_metrics[container]

        # CPU requests
        if "cpu_usage" in metrics:
            suggestion["requests"]["cpu"] = max(
                suggestion["requests"]["cpu"],
                numpy.average(
                    (metrics["cpu_usage"]["25th%"], metrics["cpu_usage"]["75th%"])
                ),
            )
        # Memory requests
        if "memory_usage" in metrics:
            suggestion["requests"]["memory"] = max(
                suggestion["requests"]["memory"],
                numpy.average(
                    (metrics["memory_usage"]["25th%"], metrics["memory_usage"]["75th%"])
                ),
            )

    return suggestion


if __name__ == "__main__":
    autoscale_resources()
