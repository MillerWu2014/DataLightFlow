from __future__ import annotations

import json
import re
from pathlib import Path

from datalight.llm import LLMClient
from datalight.pipeline.core import Operator, Record
from datalight.pipeline.qa.language import language_instruction, normalize_target_language

DEFAULT_INSTRUCTION = "Please answer the following question based on the provided information."


class MarkdownChunkOperator(Operator):
    def __init__(self, chunk_words: int = 512, overlap_words: int = 0):
        if chunk_words <= 0:
            raise ValueError("chunk_words must be positive")
        if overlap_words < 0:
            raise ValueError("overlap_words must be non-negative")
        if overlap_words >= chunk_words:
            raise ValueError("overlap_words must be smaller than chunk_words")
        self.chunk_words = chunk_words
        self.overlap_words = overlap_words

    def run(self, rows: list[Record]) -> list[Record]:
        chunks: list[Record] = []
        for row in rows:
            if row.get("status", "ok") != "ok":
                continue
            md_path = Path(str(row.get("output_md_path") or row.get("source_path")))
            if not md_path.is_file():
                continue
            words = md_path.read_text(encoding="utf-8").split()
            if not words:
                continue
            step = self.chunk_words - self.overlap_words
            for idx, start in enumerate(range(0, len(words), step)):
                part = words[start : start + self.chunk_words]
                if not part:
                    continue
                chunks.append(
                    {
                        "source_md": str(md_path),
                        "chunk_index": idx,
                        "chunk_text": " ".join(part),
                    },
                )
                if start + self.chunk_words >= len(words):
                    break
        return chunks


class Text2QAGeneratorOperator(Operator):
    def __init__(
        self,
        llm_client: LLMClient,
        question_num: int = 1,
        target_language: str = "zh",
        system_prompt: str = "",
    ):
        if question_num <= 0:
            raise ValueError("question_num must be positive")
        self.llm_client = llm_client
        self.question_num = question_num
        self.target_language = normalize_target_language(target_language)
        self.system_prompt = system_prompt

    def run(self, rows: list[Record]) -> list[Record]:
        prompts = [
            self._build_prompt(row["chunk_text"], target_language=self.target_language)
            for row in rows
            for _ in range(self.question_num)
        ]
        responses = self.llm_client.generate(prompts, system_prompt=self.system_prompt)
        expanded: list[Record] = []
        response_index = 0
        for row in rows:
            for _ in range(self.question_num):
                question, answer = parse_qa_response(responses[response_index])
                response_index += 1
                if not question or not answer:
                    continue
                item = dict(row)
                item["question"] = question
                item["answer"] = answer
                item["context"] = str(row.get("chunk_text", ""))
                item["hop_type"] = "singlehop"
                item["reasoning_steps"] = []
                item["supporting_facts"] = []
                item["qa_type"] = "singlehop"
                expanded.append(item)
        return expanded

    @staticmethod
    def _build_prompt(chunk_text: str, *, target_language: str = "zh") -> str:
        return (
            "Generate one high-quality question-answer pair from the context.\n"
            f"{language_instruction(target_language)}\n"
            "Return exactly two lines:\n"
            "Q: <question>\n"
            "A: <answer>\n\n"
            f"Context:\n{chunk_text}"
        )


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
        for row in rows:
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


class AlpacaExportOperator(Operator):
    def __init__(self, output_path: Path, instruction: str = DEFAULT_INSTRUCTION):
        self.output_path = output_path
        self.instruction = instruction

    def run(self, rows: list[Record]) -> list[Record]:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("w", encoding="utf-8") as f:
            for row in rows:
                item = {
                    "instruction": self.instruction,
                    "input": row.get("expanded_question") or row["question"],
                    "output": row.get("expanded_answer") or row["answer"],
                    "source_md": row["source_md"],
                    "chunk_index": row["chunk_index"],
                }
                if "think" in row:
                    item["think"] = row.get("think", "")
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return rows


def parse_qa_response(response: str) -> tuple[str, str]:
    question = ""
    answer = ""
    for line in response.strip().splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("q:"):
            question = stripped[2:].strip()
        elif stripped.lower().startswith("a:"):
            answer = stripped[2:].strip()
    return question, answer


def parse_grade_and_feedback(response: str) -> tuple[float, str]:
    grade_match = re.search(r"\*\*Grading\*\*:\s*(\d+(?:\.\d+)?)", response)
    feedback_match = re.search(r"\*\*Feedback\*\*:\s*(.+)", response, re.DOTALL)
    grade = float(grade_match.group(1)) if grade_match else 0.0
    if grade.is_integer():
        grade = int(grade)
    feedback = feedback_match.group(1).strip() if feedback_match else ""
    return grade, feedback
