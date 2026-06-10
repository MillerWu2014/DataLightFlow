from __future__ import annotations

import re

from datalight.pipeline.core import Operator, Record


class QADedupFilterOperator(Operator):
    """Remove exact and near-duplicate QA records with cheap text similarity."""

    def __init__(self, similarity_threshold: float = 0.92):
        if not 0 <= similarity_threshold <= 1:
            raise ValueError("similarity_threshold must be between 0 and 1")
        self.similarity_threshold = similarity_threshold

    def run(self, rows: list[Record]) -> list[Record]:
        out: list[Record] = []
        seen_keys: set[tuple[str, str]] = set()
        seen_texts: list[str] = []
        for row in rows:
            question = _get_text(row, "question")
            answer = _get_text(row, "answer")
            key = (_normalize(question), _normalize(answer))
            if key in seen_keys:
                continue
            joined = f"{question} {answer}"
            if any(_jaccard_words(joined, seen) >= self.similarity_threshold for seen in seen_texts):
                continue
            seen_keys.add(key)
            seen_texts.append(joined)
            out.append(row)
        return out


def _get_text(row: Record, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value:
            return str(value)
    return ""


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.lower()))


def _jaccard_words(left: str, right: str) -> float:
    left_words = set(_normalize(left).split())
    right_words = set(_normalize(right).split())
    if not left_words and not right_words:
        return 1.0
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / len(left_words | right_words)
