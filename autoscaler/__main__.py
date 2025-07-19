from typing import Any, Dict, Iterable

import collections
import json
import logging
import numpy

import autoscaler.metrics_collector as metrics_collector

logger = logging.getLogger(__name__)

PROMETHEUS_URL = "http://k8s.az1.danivy.com:8080/prometheus"
QUERY_RANGE_SECONDS = 86400
QUERY_STEP_SECONDS = 15
CPU_USAGE_PERCENTILE_LOW = 25
CPU_USAGE_PERCENTILE_HIGH = 75
MEMORY_USAGE_PERCENTILE_LOW = 25
MEMORY_USAGE_PERCENTILE_HIGH = 75

CPU_USAGE_PERCENTILES = (CPU_USAGE_PERCENTILE_LOW, CPU_USAGE_PERCENTILE_HIGH)
MEMORY_USAGE_PERCENTILES = (MEMORY_USAGE_PERCENTILE_LOW, MEMORY_USAGE_PERCENTILE_HIGH)


def autoscale_resources() -> None:
    """Autoscales all resources in K8s"""
    logging.basicConfig(level=logging.INFO)
    collector = metrics_collector.MetricsCollector(
        PROMETHEUS_URL, QUERY_RANGE_SECONDS, QUERY_STEP_SECONDS
    )

    data = collections.defaultdict(dict)

    # CPU throttling
    metrics = collector.get_container_cpu_throttle_time()
    compute_max(data, "cpu_throttle_time", metrics)
    # CPU usage
    metrics = collector.get_container_cpu_usage()
    compute_percentile(
        data,
        ("cpu_usage_low", "cpu_usage_high"),
        (CPU_USAGE_PERCENTILE_LOW, CPU_USAGE_PERCENTILE_HIGH),
        metrics,
    )
    # Memory usage
    metrics = collector.get_container_memory_usage()
    compute_percentile(
        data,
        ("memory_usage_low", "memory_usage_high"),
        (MEMORY_USAGE_PERCENTILE_LOW, MEMORY_USAGE_PERCENTILE_HIGH),
        metrics,
    )
    # Out of memory kills
    metrics = collector.get_container_out_of_memory_kills()
    compute_max(data, "out_of_memory_kills", metrics)

    print(json.dumps(data, indent=2))


def compute_max(
    data: Dict[
        Any, Dict[str, Dict[int, float]]
    ],  # The collection of all metrics to append data to.
    key: str,  # The subkey to store the metrics in.
    metrics: metrics_collector.ContainerMetrics,  # A set of container metrics to evaluate.
) -> None:
    """Compute the maximum on a set of metrics and add them to
    data[container][key]."""
    for container, metric in metrics.items():
        data[str(container)][key] = max(metric)


def compute_percentile(
    data: Dict[
        Any, Dict[str, Dict[int, float]]
    ],  # The collection of all metrics to append data to.
    keys: Iterable[str],  # The subkeys to store the metrics in.
    percentiles: Iterable[int],  # What percentiles to collect.
    metrics: metrics_collector.ContainerMetrics,  # A set of container metrics to evaluate.
) -> None:
    """Compute a set of percentiles on a set of metrics and add them to
    data[container][key]."""
    for container, metric in metrics.items():
        values = numpy.percentile(metric, percentiles)
        for key, value in zip(keys, values):
            data[str(container)][key] = value


if __name__ == "__main__":
    autoscale_resources()
