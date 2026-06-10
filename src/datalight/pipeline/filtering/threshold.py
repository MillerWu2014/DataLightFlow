from __future__ import annotations

from datalight.pipeline.core import Operator, Record


class QAFilterOperator(Operator):
    def __init__(
        self,
        min_question_quality: float = 3.0,
        min_answer_alignment: float | None = None,
        min_answer_verifiability: float | None = None,
        min_downstream_value: float | None = None,
    ):
        self.min_question_quality = min_question_quality
        self.min_answer_alignment = min_answer_alignment
        self.min_answer_verifiability = min_answer_verifiability
        self.min_downstream_value = min_downstream_value

    def run(self, rows: list[Record]) -> list[Record]:
        return [row for row in rows if self._passes(row)]

    def _passes(self, row: Record) -> bool:
        checks = [
            ("question_quality_grade", self.min_question_quality),
            ("answer_alignment_grade", self.min_answer_alignment),
            ("answer_verifiability_grade", self.min_answer_verifiability),
            ("downstream_value_grade", self.min_downstream_value),
        ]
        for key, threshold in checks:
            if threshold is not None and float(row.get(key, 0)) < threshold:
                return False
        return True
