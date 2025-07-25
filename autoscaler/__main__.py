from typing import Any, Dict

import collections
import json
import logging

import autoscaler.k8s_manager as k8s_manager
import autoscaler.metrics_collector as metrics_collector
import autoscaler.util as util

logger = logging.getLogger(__name__)


def autoscale_resources() -> None:
    """Autoscales all resources in K8s"""
    logging.basicConfig(level=logging.INFO)
    config = util.Config("config.json")
    collector = metrics_collector.MetricsCollector(config)
    manager = k8s_manager.K8sManager(config)

    resources = manager.get_container_resources()
    metrics = collector.get_all_container_metrics()

    suggest_all_resources(resources, metrics)

    # suggestions = suggest_resources(data)
    # for suggestion in suggestions.values():
    #     manager.humanize_resources(suggestion)
    # print(json.dumps(suggestions, indent=2))


def suggest_all_resources(
    resources: Dict[
        util.K8sObject, Dict[util.Container, Dict | None]
    ],  # All container resources, grouped by their controller.
    metrics: Dict[util.Container, Dict[str, Any]],  # All container metrics.
) -> None:
    """Suggests resources for containers."""
    logger.info("Generating resource suggestions...")
    for controller, controller_resources in resources.items():
        controller_metrics = {
            container: metrics[container] for container in controller_resources
        }
        suggest_resources(controller, controller_resources, controller_metrics)


def suggest_resources(
    controller: util.K8sObject,  # The resource that controls the containers.
    resources: Dict[util.Container, Dict | None],  # The resources of each container.
    metrics: Dict[util.Container, Any],  # The metrics of each container
) -> Dict[util.Container, Any]:
    """Suggests resources for containers."""
    suggestion = collections.defaultdict(dict)

    # TODO: handle multiple containers

    # CPU requests
    if "cpu_usage" in metrics:
        suggestion["requests"]["cpu"] = 0.5 * (
            metrics["cpu_usage"]["25th%"] + metrics["cpu_usage"]["75th%"]
        )
    # Memory requests
    if "memory_usage" in metrics:
        suggestion["requests"]["memory"] = 0.5 * (
            metrics["memory_usage"]["25th%"] + metrics["memory_usage"]["75th%"]
        )
    for container, metric in metrics.items():
        print(controller, metric)
    # print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    autoscale_resources()
