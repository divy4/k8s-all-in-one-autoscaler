from typing import Any, Dict, Iterable

import collections
import json
import logging
import math
import numpy

import autoscaler.metrics_collector as metrics_collector
import autoscaler.util as util

logger = logging.getLogger(__name__)

PROMETHEUS_URL = "http://k8s.az1.danivy.com:8080/prometheus"
QUERY_RANGE_SECONDS = 86400
QUERY_STEP_SECONDS = 15
CPU_USAGE_PERCENTILE_LOW = 25
CPU_USAGE_PERCENTILE_HIGH = 75
MEMORY_USAGE_PERCENTILE_LOW = 25
MEMORY_USAGE_PERCENTILE_HIGH = 75
SUGGESTION_SIGNIFICANT_DIGITS = 2


def autoscale_resources() -> None:
    """Autoscales all resources in K8s"""
    logging.basicConfig(level=logging.INFO)
    collector = metrics_collector.MetricsCollector(
        PROMETHEUS_URL, QUERY_RANGE_SECONDS, QUERY_STEP_SECONDS
    )
    data = collect_metrics(collector)
    suggestions = suggest_resources(data)
    print(json.dumps(suggestions, indent=2))


# Suggestions


def suggest_resources(
    data: Dict[util.Container, Dict[str, float]],
) -> Dict[util.Container, Any]:
    """Suggests resources for containers."""
    logger.info("Generating resource suggestions...")
    suggestions = collections.defaultdict(lambda: collections.defaultdict(dict))
    for container, metrics in data.items():
        # Memory requests
        if "memory_usage_low" in metrics and "memory_usage_high" in metrics:
            suggestion = (
                metrics["memory_usage_low"] + metrics["memory_usage_low"]
            ) / 2.0
            suggestions[str(container)]["requests"]["memory"] = humanize_memory(
                suggestion
            )
    return suggestions


def humanize_memory(value: float) -> str:
    """Humanizes a memory value."""
    value = int(value)
    if value < 1024:
        return str(value)
    elif value < 1024**2:
        return f"{ceil_sigfig(value / 1024, SUGGESTION_SIGNIFICANT_DIGITS)}Ki"
    elif value < 1024**3:
        return f"{ceil_sigfig(value / 1024 ** 2, SUGGESTION_SIGNIFICANT_DIGITS)}Mi"
    else:
        return f"{ceil_sigfig(value / 1024 ** 3, SUGGESTION_SIGNIFICANT_DIGITS)}Gi"


def ceil_sigfig(x: float, sigfigs: int) -> str:
    """Computes ceil a number of significant digits."""
    # This function could handle non-positive values with some extra work.
    # But we shouldn't expect them anyway, so throw an error instead.
    if x <= 0:
        raise ValueError(f"Non-positive value '{valxue}' detected.")
    # 1 -> 1's place, 2 -> 10's place, -1 -> 10th's place
    first_sigfig_place = int(numpy.floor(numpy.log10(x)))
    # Convert number of significant digits to what precision to round on
    precision = sigfigs - 1 - first_sigfig_place
    # Numpy and math's ceil functions don't allow setting precision...
    # ...so we have to do it ourselves *shakes fist*
    x = numpy.true_divide(math.ceil(x * 10**precision), 10**precision)
    # Convert to int if there's no decimal places
    if first_sigfig_place + 1 >= sigfigs:
        x = int(x)
    return x


# Metrics


def collect_metrics(
    collector: metrics_collector.MetricsCollector,
) -> Dict[Any, Dict[str, float]]:
    """Collects metrics for all containers in a cluster."""
    # Collect data
    data = collections.defaultdict(dict)
    # CPU throttling
    metrics = collector.get_cpu_throttle_time()
    compute_max(data, "cpu_throttle_time", metrics)
    # CPU usage
    metrics = collector.get_cpu_usage()
    compute_percentile(
        data,
        ("cpu_usage_low", "cpu_usage_high"),
        (CPU_USAGE_PERCENTILE_LOW, CPU_USAGE_PERCENTILE_HIGH),
        metrics,
    )
    # Memory usage
    metrics = collector.get_memory_usage()
    compute_percentile(
        data,
        ("memory_usage_low", "memory_usage_high"),
        (MEMORY_USAGE_PERCENTILE_LOW, MEMORY_USAGE_PERCENTILE_HIGH),
        metrics,
    )
    # Out of memory kills
    metrics = collector.get_out_of_memory_kills()
    compute_max(data, "out_of_memory_kills", metrics)
    return data


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
        data[container][key] = max(metric)


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
            data[container][key] = value


if __name__ == "__main__":
    autoscale_resources()
