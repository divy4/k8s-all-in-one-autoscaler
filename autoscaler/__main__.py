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

# The period and step size, in seconds, to lookup metrics data on
QUERY_RANGE_SECONDS = 86400 * 7
QUERY_STEP_SECONDS = 60

# Collection settings
CPU_PERCENTILES = (25, 75, 100)
MEMORY_PERCENTILES = (25, 75, 100)

# Algorithm settings
MEMORY_REQUEST_TARGET_PERCENTAGE = 100
SUGGESTION_SIGNIFICANT_DIGITS = 2


def autoscale_resources() -> None:
    """Autoscales all resources in K8s"""
    logging.basicConfig(level=logging.INFO)
    collector = metrics_collector.MetricsCollector(
        PROMETHEUS_URL, QUERY_RANGE_SECONDS, QUERY_STEP_SECONDS
    )
    data = collect_metrics(collector)
    suggestions = suggest_resources(data)
    humanize_suggestions(suggestions)
    print(json.dumps(suggestions, indent=2))


# Suggestions


def suggest_resources(
    data: Dict[util.Container, Dict[str, float]],
) -> Dict[util.Container, Any]:
    """Suggests resources for containers."""
    logger.info("Generating resource suggestions...")
    suggestions = collections.defaultdict(lambda: collections.defaultdict(dict))
    for container, metrics in data.items():
        # CPU requests
        if "cpu_usage_percentile" in metrics:
            suggestions[str(container)]["requests"]["cpu"] = (
                metrics["cpu_usage_percentile"][25]
                + metrics["cpu_usage_percentile"][75]
            ) / 2
        # Memory requests
        if "memory_usage_percentile" in metrics:
            suggestions[str(container)]["requests"]["memory"] = (
                metrics["memory_usage_percentile"][25]
                + metrics["memory_usage_percentile"][75]
            ) / 2
    return suggestions


def humanize_suggestions(
    suggestions: Dict[util.Container, Any],
) -> Dict[util.Container, Any]:
    """Reformats suggestions into Kubernetes human-readable values, e.g. 10Mi,
    123m, 1.7Gi."""
    for suggestion in suggestions.values():
        if "requests" in suggestion:
            if "cpu" in suggestion["requests"]:
                suggestion["requests"]["cpu"] = humanize_cpu(
                    suggestion["requests"]["cpu"]
                )
            if "memory" in suggestion["requests"]:
                suggestion["requests"]["memory"] = humanize_memory(
                    suggestion["requests"]["memory"]
                )
        if "limits" in suggestion:
            if "cpu" in suggestion["requests"]:
                suggestion["requests"]["cpu"] = humanize_cpu(
                    suggestion["requests"]["cpu"]
                )
            if "memory" in suggestion["limits"]:
                suggestion["limits"]["memory"] = humanize_memory(
                    suggestion["limits"]["memory"]
                )


def humanize_cpu(x: float) -> str:
    """Humanizes a cpu value."""
    if x <= 0:
        raise ValueError(f"Unable to convert '{x}' to a Kubernetes cpu value.")
    elif x < 0.001:
        return "1m"
    elif x < 1:
        return f"{advanced_ceil(x * 1000, SUGGESTION_SIGNIFICANT_DIGITS, 0)}m"
    else:
        return str(advanced_ceil(x, SUGGESTION_SIGNIFICANT_DIGITS))


def humanize_memory(x: float) -> str:
    """Humanizes a memory value."""
    x = int(x)
    if x <= 0:
        raise ValueError(f"Unable to convert '{x}' to a Kubernetes memory value.")
    elif x < 1024:
        return str(advanced_ceil(x, SUGGESTION_SIGNIFICANT_DIGITS))
    elif x < 1024**2:
        return f"{advanced_ceil(x / 1024, SUGGESTION_SIGNIFICANT_DIGITS)}Ki"
    elif x < 1024**3:
        return f"{advanced_ceil(x / 1024 ** 2, SUGGESTION_SIGNIFICANT_DIGITS)}Mi"
    else:
        return f"{advanced_ceil(x / 1024 ** 3, SUGGESTION_SIGNIFICANT_DIGITS)}Gi"


def advanced_ceil(x: float, sigfigs: int, decimals: int = None) -> int | float:
    """Computes ceil a number of significant digits."""
    # This function could handle non-positive values with some extra work.
    # But we shouldn't expect them anyway, so throw an error instead.
    if x <= 0:
        raise ValueError(f"Non-positive value '{valxue}' detected.")
    # 1 -> 1's place, 2 -> 10's place, -1 -> 10th's place
    first_sigfig_place = int(numpy.floor(numpy.log10(x)))
    # Convert number of significant digits to what precision to round on
    precision = sigfigs - 1 - first_sigfig_place
    # If decimals would be less precise than significant figures, use it instead.
    if decimals is not None and decimals < precision:
        precision = decimals
    # Numpy and math's ceil functions don't allow setting precision...
    # ...so we have to do it ourselves *shakes fist*
    x = numpy.true_divide(math.ceil(x * 10**precision), 10**precision)
    # Convert to int if there's no decimal places
    if precision <= 0:
        x = int(x)
    return x


# Metrics


def collect_metrics(
    collector: metrics_collector.MetricsCollector,
) -> Dict[Any, Dict[str, Any]]:
    """Collects metrics for all containers in a cluster."""
    # Collect data
    data = collections.defaultdict(dict)
    # CPU throttling
    metrics = collector.get_cpu_throttle_time()
    compute_max(data, "cpu_throttle_time", metrics)
    # CPU usage
    metrics = collector.get_cpu_usage()
    compute_percentile(data, "cpu_usage_percentile", CPU_PERCENTILES, metrics)
    # Memory usage
    metrics = collector.get_memory_usage()
    compute_percentile(data, "memory_usage_percentile", MEMORY_PERCENTILES, metrics)
    # Out of memory kills
    metrics = collector.get_out_of_memory_kills()
    compute_max(data, "out_of_memory_kills", metrics)
    return data


def compute_max(
    data: Dict[
        Any, Dict[str, Dict[int, Any]]
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
        Any, Dict[str, Dict[int, Any]]
    ],  # The collection of all metrics to append data to.
    key: str,  # The subkey to store the metrics in.
    percentiles: Iterable[int],  # What percentiles to collect.
    metrics: metrics_collector.ContainerMetrics,  # A set of container metrics to evaluate.
) -> None:
    """Compute a set of percentiles on a set of metrics and add them to
    data[container][key][percentile]."""
    for container, metric in metrics.items():
        # Ensure dict exists under the key
        data[container][key] = collections.defaultdict(dict)
        # Compute all percentiles
        values = numpy.percentile(metric, percentiles)
        for percentile, value in zip(percentiles, values):
            data[container][key][percentile] = value


if __name__ == "__main__":
    autoscale_resources()
