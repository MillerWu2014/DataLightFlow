from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from typing import Any

Record = dict[str, Any]


class Operator(ABC):
    """Minimal DataFlow-style operator: records in, records out."""

    @abstractmethod
    def run(self, rows: list[Record]) -> list[Record]:
        raise NotImplementedError


class Pipeline:
    """Simple sequential pipeline without DataFlowStorage or compile graph."""

    def __init__(self, operators: Sequence[Operator]):
        self.operators = list(operators)

    def run(self, rows: Iterable[Record]) -> list[Record]:
        current = list(rows)
        for operator in self.operators:
            current = operator.run(current)
        return current
