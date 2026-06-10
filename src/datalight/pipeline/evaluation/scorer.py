from __future__ import annotations

import re

from tqdm import tqdm

from datalight.llm import LLMClient
from datalight.pipeline.core import Operator, Record
from datalight.pipeline.language import language_instruction, normalize_target_language


class Text2QAEvaluatorOperator(Operator):
    def __init__(self, llm_client: LLMClient, target_language: str = "zh", system_prompt: str = ""):
        self.llm_client = llm_client
        self.target_language = normalize_target_language(target_language)
        self.system_prompt = system_prompt

    def run(self, rows: list[Record]) -> list[Record]:
        out: list[Record] = []
        dimensions = [
            ("question_quality", self._build_question_quality_prompt),
            ("answer_alignment", self._build_answer_alignment_prompt),
            ("answer_verifiability", self._build_answer_verifiability_prompt),
            ("downstream_value", self._build_downstream_value_prompt),
        ]
        for row in tqdm(rows, desc="Evaluating QA pairs"):
            item = dict(row)
            for name, builder in dimensions:
                response = self.llm_client.generate([builder(row)], system_prompt=self.system_prompt)[0]
                grade, feedback = parse_grade_and_feedback(response)
                item[f"{name}_grade"] = grade
                item[f"{name}_feedback"] = feedback
            out.append(item)
        return out

    @staticmethod
    def _qa_block(row: Record) -> str:
        return (
            f"Context: {row['chunk_text']}\n"
            f"Question: {row['question']}\n"
            f"Answer: {row['answer']}"
        )

    def _build_question_quality_prompt(self, row: Record) -> str:
        return (
            "Score the question clarity and meaningfulness from 1 to 5.\n"
            f"{language_instruction(self.target_language)}\n"
            "Return:\n"
            "**Grading**: <integer>\n"
            "**Feedback**: <short feedback>\n\n"
            f"{self._qa_block(row)}"
        )

    def _build_answer_alignment_prompt(self, row: Record) -> str:
        return (
            "Score how directly the answer addresses the question from 1 to 5.\n"
            f"{language_instruction(self.target_language)}\n"
            "Return:\n**Grading**: <integer>\n**Feedback**: <short feedback>\n\n"
            f"{self._qa_block(row)}"
        )

    def _build_answer_verifiability_prompt(self, row: Record) -> str:
        return (
            "Score how objectively verifiable the answer is from the context from 1 to 5.\n"
            f"{language_instruction(self.target_language)}\n"
            "Return:\n**Grading**: <integer>\n**Feedback**: <short feedback>\n\n"
            f"{self._qa_block(row)}"
        )

    def _build_downstream_value_prompt(self, row: Record) -> str:
        return (
            "Score how useful this QA pair is for downstream training or RAG from 1 to 5.\n"
            f"{language_instruction(self.target_language)}\n"
            "Return:\n**Grading**: <integer>\n**Feedback**: <short feedback>\n\n"
            f"{self._qa_block(row)}"
        )

def parse_grade_and_feedback(response: str) -> tuple[float, str]:
    grade_match = re.search(r"\*\*Grading\*\*:\s*(\d+(?:\.\d+)?)", response)
    feedback_match = re.search(r"\*\*Feedback\*\*:\s*(.+)", response, re.DOTALL)
    grade = float(grade_match.group(1)) if grade_match else 0.0
    if grade.is_integer():
        grade = int(grade)
    feedback = feedback_match.group(1).strip() if feedback_match else ""
    return grade, feedback

