from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from typing import Any

Record = dict[str, Any]


def limit_rows_per_chunk(rows: list[Record], *, max_per_chunk: int) -> list[Record]:
    if max_per_chunk <= 0:
        raise ValueError("max_per_chunk must be positive")

    grouped: dict[tuple[str, int], list[Record]] = {}
    for row in rows:
        key = (str(row.get("source_md", "")), int(row.get("chunk_index", 0)))
        grouped.setdefault(key, []).append(row)
    limited: list[Record] = []
    for items in grouped.values():
        limited.extend(items[:max_per_chunk])
        
    return limited


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
