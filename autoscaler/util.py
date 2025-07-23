from typing import Any, Hashable, Tuple

import json
import logging
import math
import numpy

logger = logging.getLogger(__name__)

# Objects


class Config:
    """Reads/monitors configuration in a file"""

    def __init__(self, config_file: str):
        self.__logger = logging.getLogger(type(self).__name__)

        self.__logger.info(f"Loading config from {config_file}...")
        with open(config_file, "r") as file:
            config = json.load(file)

        self.connections_prometheus_url = config["connections_prometheus_url"]
        self.data_cpu_usage_percentiles = config["data_cpu_usage_percentiles"]
        self.data_memory_usage_percentiles = config["data_memory_usage_percentiles"]
        self.query_range_seconds = config["query_range_days"] * 86400
        self.query_step_seconds = config["query_step_seconds"]
        self.suggestion_cpu_request_target_percentage = config[
            "suggestion_cpu_request_target_percentage"
        ]
        self.suggestion_memory_request_target_percentage = config[
            "suggestion_memory_request_target_percentage"
        ]
        self.suggestion_significant_digits = config["suggestion_significant_digits"]


class SortableDTO:
    """A sortable/hashable data transfer object based on tuples."""

    def __init__(self, t: Tuple[Hashable], separator="/"):
        self.__separator = separator
        self.tuple = t

    def __repr__(self) -> str:
        return self.__separator.join(self.tuple)

    def __hash__(self) -> int:
        return hash(self.tuple)

    def __eq__(self, other: Any) -> bool:
        if type(self) != type(other):
            return False
        return self.tuple == other.tuple

    def __lt__(self, other: Any) -> bool:
        if type(self) != type(other):
            return False
        return self.tuple < other.tuple


class Container(SortableDTO):
    """A DTO that uniquely identifies a container."""

    def __init__(self, namespace: str, pod: str, container: str):
        super(Container, self).__init__((namespace, pod, container))
        self.namespace = namespace
        self.pod = pod
        self.container = container


# Math


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
