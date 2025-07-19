from typing import Any, Dict, Iterable, List, Tuple, TypeAlias

import collections
import logging
import re
import requests
import time

import autoscaler.util as util

EpochTime: TypeAlias = int
ContainerMetrics: TypeAlias = Dict[util.Container, Iterable[float]]

NEWLINE_WITH_WHITESPACE = re.compile("\s*\n\s*")


class MetricsCollector:
    """An object that collects metrics for the autoscaler."""

    __BY_CONTAINER = "by(namespace, pod, container)"
    __FILTER = '{namespace!="", pod!="", container!=""}'

    def __init__(
        self,
        prometheus_url: str,  # The prometheus URL to collect metrics from.
        query_range_seconds: int,  # The timeframe, in seconds, every query should collect data from.
        query_step_seconds: int,  # The distance between each measurement in every query.
    ):
        self.__logger = logging.getLogger("MetricsCollector")
        self.__prometheus_url = prometheus_url
        self.__query_range_seconds = query_range_seconds
        self.__query_step_seconds = query_step_seconds

    # Typed queries

    def get_cpu_throttle_time(self) -> ContainerMetrics:
        """Returns the CPU throttle time metrics of all containers."""
        self.__logger.info("Fetching container cpu throttle time metrics...")
        results = self.query_range(
            f"""max {self.__BY_CONTAINER} (
                    irate(container_cpu_cfs_throttled_seconds_total{self.__FILTER}[5m])
                )"""
        )
        return self.__reduce_time_series_data(results, "cpu throttle time")

    def get_cpu_usage(self) -> ContainerMetrics:
        """Returns the CPU usage of all containers."""
        self.__logger.info("Fetching container cpu usage metrics...")
        results = self.query_range(
            f"""max {self.__BY_CONTAINER} (
                    rate(container_cpu_usage_seconds_total{self.__FILTER}[5m])
                ) != 0"""
        )
        return self.__reduce_time_series_data(results, "cpu usage")

    def get_memory_usage(self) -> ContainerMetrics:
        """Returns the memory usage metrics of all containers."""
        self.__logger.info("Fetching container memory usage metrics...")
        results = self.query_range(
            f"""max {self.__BY_CONTAINER} (
                    container_memory_working_set_bytes{self.__FILTER}
                )"""
        )
        return self.__reduce_time_series_data(results, "memory usage")

    def get_out_of_memory_kills(self) -> ContainerMetrics:
        """Returns the number of out of memory errors of all containers."""
        self.__logger.info("Fetching container out of memory metrics...")
        results = self.query_range(
            f"""max {self.__BY_CONTAINER} (
                    rate(container_oom_events_total{self.__FILTER}[5m])
                )"""
        )
        return self.__reduce_time_series_data(results, "out of memory")

    # Low level queries

    def query(self, query: str) -> Any:  # The query to send to prometheus.
        """Query prometheus."""
        query = self.__normalize_query(query)
        self.__logger.info(f"Sending query to prometheus: {query}")
        response = requests.get(
            f"{self.__prometheus_url}/api/v1/query", params={"query": query}
        )
        response.raise_for_status()
        return response.json()

    def query_range(
        self,  # This object.
        query: str,  # The query to send to prometheus.
    ) -> Any:
        """Query prometheus over the range from now - range_seconds to now."""
        query = self.__normalize_query(query)
        self.__logger.debug(f"Sending query to prometheus: {query}")
        now = int(time.time())
        response = requests.get(
            f"{self.__prometheus_url}/api/v1/query_range",
            params={
                "query": query,
                "start": now - self.__query_range_seconds,
                "end": now,
                "step": self.__query_step_seconds,
            },
        )
        response.raise_for_status()
        return response.json()

    # Common data wrangling

    def __normalize_query(self, query: str) -> str:
        """Normalizes a query string."""
        return NEWLINE_WITH_WHITESPACE.sub("", query)

    def __reduce_time_series_data(
        self,
        results: Any,  # The results returned from a query.
        description: str,  # A human-readable description of the kind of metrics being reduced. e.g. "memory usage".
    ) -> Dict[util.Container, List[float]]:
        """Reduces time series data from prometheus to a dict of lists."""
        metrics = collections.defaultdict(list)
        containers = 0
        data_points = 0
        for result in results["data"]["result"]:
            container = util.Container(**result["metric"])
            containers += 1
            for epoch, value in result["values"]:
                metrics[container].append(float(value))
                data_points += 1
        self.__logger.info(
            f"Collected {data_points} {description} metrics for {containers} containers."
        )
        return metrics
