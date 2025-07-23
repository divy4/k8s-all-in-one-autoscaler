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

    data = collector.get_all_container_metrics()
    suggestions = suggest_resources(data)
    for suggestion in suggestions.values():
        manager.humanize_resources(suggestion)
    print(json.dumps(suggestions, indent=2))


def suggest_resources(
    data: Dict[util.Container, Dict[str, float]],
) -> Dict[util.Container, Any]:
    """Suggests resources for containers."""
    logger.info("Generating resource suggestions...")
    suggestions = collections.defaultdict(lambda: collections.defaultdict(dict))
    for container, metrics in data.items():
        # CPU requests
        if "cpu_usage" in metrics:
            suggestions[str(container)]["requests"]["cpu"] = 0.5 * (
                metrics["cpu_usage"]["25th%"] + metrics["cpu_usage"]["75th%"]
            )
        # Memory requests
        if "memory_usage" in metrics:
            suggestions[str(container)]["requests"]["memory"] = 0.5 * (
                metrics["memory_usage"]["25th%"] + metrics["memory_usage"]["75th%"]
            )
    return suggestions


if __name__ == "__main__":
    autoscale_resources()
