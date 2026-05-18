from __future__ import annotations

import json
import re
from typing import Any

from datalight.pipeline.core import Operator, Record
from datalight.pipeline.qa.llm import LLMClient


class DepthQAGeneratorOperator(Operator):
    """Generate deeper follow-up QA pairs from existing single-hop QA records."""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def run(self, rows: list[Record]) -> list[Record]:
        prompts = [_build_depth_prompt(row) for row in rows]
        responses = self.llm_client.generate(prompts, system_prompt=_system_prompt())
        out: list[Record] = []
        for row, response in zip(rows, responses):
            qa = _parse_agentic_response(response)
            if not qa:
                continue
            item = dict(row)
            item["generated_question"] = qa["question"]
            item["generated_answer"] = qa["answer"]
            item["identifier"] = qa.get("identifier", row.get("identifier", ""))
            item["relation"] = qa.get("relation", "")
            item["qa_type"] = "depth"
            out.append(item)
        return out


class WidthQAGeneratorOperator(Operator):
    """Generate breadth QA pairs by connecting neighboring existing QA records."""

    def __init__(self, llm_client: LLMClient, window_size: int = 2):
        if window_size < 2:
            raise ValueError("window_size must be at least 2")
        self.llm_client = llm_client
        self.window_size = window_size

    def run(self, rows: list[Record]) -> list[Record]:
        windows = [rows[index : index + self.window_size] for index in range(0, max(len(rows) - 1, 0))]
        windows = [window for window in windows if len(window) >= 2]
        prompts = [_build_width_prompt(window) for window in windows]
        responses = self.llm_client.generate(prompts, system_prompt=_system_prompt())
        out: list[Record] = []
        for window, response in zip(windows, responses):
            qa = _parse_agentic_response(response)
            if not qa:
                continue
            source_indices = qa.get("index", list(range(len(window))))
            if not isinstance(source_indices, list):
                source_indices = list(range(len(window)))
            out.append(
                {
                    "generated_question": qa["question"],
                    "generated_answer": qa["answer"],
                    "source_question_indices": source_indices,
                    "content_identifier": qa.get("content_identifier", ""),
                    "qa_type": "width",
                    "source_rows": window,
                },
            )
        return out


def _system_prompt() -> str:
    return "You create concise QA pairs for training data. Return only valid JSON."


def _build_depth_prompt(row: Record) -> str:
    return (
        "Create one deeper follow-up QA pair from this existing QA.\n"
        "Return JSON with question, answer, identifier, and relation.\n\n"
        f"Question: {row.get('generated_question', '')}\n"
        f"Answer: {row.get('generated_answer', '')}\n"
        f"Identifier: {row.get('identifier', '')}"
    )


def _build_width_prompt(rows: list[Record]) -> str:
    items = []
    for index, row in enumerate(rows):
        items.append(
            f"[{index}] Question: {row.get('generated_question', '')}\n"
            f"[{index}] Answer: {row.get('generated_answer', '')}\n"
            f"[{index}] Identifier: {row.get('identifier', '')}"
        )
    return (
        "Create one breadth QA pair that connects these QA records.\n"
        "Return JSON with question, answer, index, and content_identifier.\n\n"
        + "\n\n".join(items)
    )


def _parse_agentic_response(response: str) -> dict[str, Any]:
    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        return {}
    question = str(data.get("question", "")).strip()
    answer = str(data.get("answer", "")).strip()
    if not question or not answer:
        return {}
    data["question"] = question
    data["answer"] = answer
    return data
