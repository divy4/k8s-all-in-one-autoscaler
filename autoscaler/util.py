from typing import Any, Dict, Hashable, Generator, Iterable, Set, Tuple

import functools
import json
import logging
import math
import numpy
import operator

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
        self.metrics = config["metrics"]
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


class K8sObject(SortableDTO):
    """A DTO that uniquely identifies a generic K8s object."""

    def __init__(self, kind: str, namespace: str, name: str):
        super(K8sObject, self).__init__((kind, namespace, name))
        self.kind = kind
        self.namespace = namespace
        self.name = name


class Container(SortableDTO):
    """A DTO that uniquely identifies a container."""

    def __init__(self, namespace: str, pod: str, container: str):
        super(Container, self).__init__((namespace, pod, container))
        self.namespace = namespace
        self.pod = pod
        self.container = container


class ContainerSpecLocation(SortableDTO):
    """A DTO that uniquely identifies the location of a container spec."""

    def __init__(self, kind: str, namespace: str, name: str, container: str):
        super(ContainerSpecLocation, self).__init__((kind, namespace, name, container))
        self.kind = kind
        self.namespace = namespace
        self.name = name
        self.container = container

    def from_parent(parent_object: K8sObject, container: Container):
        return ContainerSpecLocation(
            parent_object.kind,
            parent_object.namespace,
            parent_object.name,
            container.container,
        )


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


def dict_max(*dicts: Iterable[Dict]) -> Dict:
    """Returns the merged result of a set of dicts, but with all keys set to
    the maximum value for each key."""
    # Flatten each dict into a dict of paths
    flattened_dicts = list(flatten_dict(x) for x in dicts)
    # Compute the set of all paths in every dict
    paths = set(path for d in flattened_dicts for path in d.keys())
    assert_no_prefix_paths(paths)
    # Compute the max for each path
    result = {path: max(d[path] for d in flattened_dicts) for path in paths}
    # Convert the final result back into a nested dict
    return inflate_dict(result)


def flatten_dict(d: Dict) -> Dict:
    """Flatten a multi-layer dict into a single-layer dict with tuples for keys."""
    result = {}
    unexplored = list(((k,), v) for k, v in d.items())
    while len(unexplored) > 0:
        keys, value = unexplored.pop()
        # If the value is also a dict...
        if not isinstance(value, dict):
            result[keys] = value
            continue
        # ...or add it's subkeys if it is a dict
        for subkey, subvalue in value.items():
            unexplored.append(((*keys, subkey), subvalue))
    return result


def inflate_dict(d: Dict[Tuple, Any]) -> Dict:
    """The inverse of flatten_dict(), inflates a single-layer dict of tuple keys
    back into a multi-layer dict."""
    result = {}
    for keys, value in d.items():
        curr_dict = result
        # Drill down to the dict where the value should be added
        for key in keys[:-1]:
            # Add missing subkeys
            if key not in curr_dict:
                curr_dict[key] = {}
            curr_dict = curr_dict[key]
        # Add the value
        curr_dict[keys[-1]] = value
    return result


def assert_no_prefix_paths(paths: Set[Tuple]) -> None:
    """Given a set of "paths" that are tuples of objects, asserts that no path
    is a prefix of another path in the set."""
    previous = None
    for path in sorted(paths):
        if previous is not None and path[: len(previous)] == previous:
            raise ValueError(
                "Unable to compute max of all paths in dicts."
                " One or more dicts contain values at"
                f" {'.'.join(str(x) for x in path)}"
                " while one or more dicts contain values in the prefix path"
                f" {'.'.join(str(x) for x in previous)}"
            )
        previous = path
