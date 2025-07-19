from typing import Any, Hashable, Tuple


class SortableDTO:
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
    def __init__(self, namespace: str, pod: str, container: str):
        super(Container, self).__init__((namespace, pod, container))
        self.namespace = namespace
        self.pod = pod
        self.container = container
