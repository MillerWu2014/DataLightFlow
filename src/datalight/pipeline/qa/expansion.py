from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datalight.pipeline.core import Operator, Record
from datalight.pipeline.qa.language import language_instruction, normalize_target_language
from datalight.pipeline.qa.llm import LLMClient

EXPANSION_MODES = {"detail", "contextual", "reasoning"}


@dataclass
class QAExpansionPipelineResult:
    input_path: Path
    output_path: Path


class QAExpansionOperator(Operator):
    """Optional QA expansion stage that preserves original QA fields."""

    def __init__(
        self,
        llm_client: LLMClient,
        mode: str = "detail",
        target_language: str = "zh",
        keep_failed: bool = True,
        system_prompt: str | None = None,
    ):
        if mode not in EXPANSION_MODES:
            raise ValueError("mode must be one of: detail, contextual, reasoning")
        self.llm_client = llm_client
        self.mode = mode
        self.target_language = normalize_target_language(target_language)
        self.keep_failed = keep_failed
        self.system_prompt = system_prompt

    def run(self, rows: list[Record]) -> list[Record]:
        prompts = [
            build_expansion_prompt(row, mode=self.mode, target_language=self.target_language)
            for row in rows
        ]
        responses = self.llm_client.generate(
            prompts,
            system_prompt=build_expansion_system_prompt(
                target_language=self.target_language,
                system_prompt=self.system_prompt,
            ),
        )
        out: list[Record] = []
        for row, response in zip(rows, responses):
            item = dict(row)
            try:
                expansion = parse_expansion_response(response)
            except (json.JSONDecodeError, ValueError) as exc:
                if self.keep_failed:
                    item["expansion_status"] = "failed"
                    item["expansion_error"] = str(exc)
                    out.append(item)
                continue
            item["expanded_question"] = expansion["expanded_question"]
            item["expanded_answer"] = expansion["expanded_answer"]
            item["expansion_type"] = expansion.get("expansion_type") or self.mode
            item["expansion_notes"] = expansion.get("expansion_notes", "")
            item["expansion_status"] = "ok"
            out.append(item)
        return out


def run_qa_expansion_pipeline(
    *,
    input_path: Path,
    output_path: Path,
    llm_client: LLMClient,
    mode: str = "detail",
    target_language: str = "zh",
    system_prompt: str | None = None,
) -> QAExpansionPipelineResult:
    rows = _read_jsonl(input_path)
    expanded = QAExpansionOperator(
        llm_client=llm_client,
        mode=mode,
        target_language=target_language,
        system_prompt=system_prompt,
    ).run(rows)
    _write_jsonl(output_path, expanded)
    return QAExpansionPipelineResult(input_path=input_path, output_path=output_path)


def build_expansion_system_prompt(target_language: str = "zh", system_prompt: str | None = None) -> str:
    if system_prompt:
        return f"{system_prompt.strip()} {language_instruction(target_language)} Return only valid JSON."
    return (
        "You expand QA pairs for training and RAG data. "
        f"{language_instruction(target_language)} "
        "Do not add facts that are not supported by the provided context. "
        "Return only valid JSON."
    )


def build_expansion_prompt(row: Record, *, mode: str = "detail", target_language: str = "zh") -> str:
    mode_hint = {
        "detail": "Expand the answer with useful context, boundaries, and explanation.",
        "contextual": "Rewrite the question to sound more natural and context-rich, then refine the answer.",
        "reasoning": "Add concise reasoning while keeping the final answer grounded.",
    }[mode]
    context = str(row.get("chunk_text") or row.get("multihop_context") or "")
    question = str(row.get("generated_question") or row.get("question") or row.get("input") or "")
    answer = str(row.get("generated_answer") or row.get("answer") or row.get("output") or "")
    return (
        "Expand this QA pair without changing its core meaning.\n"
        f"{language_instruction(target_language)}\n"
        f"Mode: {mode}\n"
        f"Mode guidance: {mode_hint}\n"
        "Return only this JSON object:\n"
        "{\n"
        '  "expanded_question": "...",\n'
        '  "expanded_answer": "...",\n'
        '  "expansion_type": "detail|contextual|reasoning",\n'
        '  "expansion_notes": "short note"\n'
        "}\n\n"
        f"Context:\n{context}\n\n"
        f"Original question:\n{question}\n\n"
        f"Original answer:\n{answer}"
    )


def parse_expansion_response(response: str) -> dict[str, str]:
    payload = _extract_json_payload(response)
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Expansion response must be a JSON object")
    question = str(data.get("expanded_question", "")).strip()
    answer = str(data.get("expanded_answer", "")).strip()
    if not question or not answer:
        raise ValueError("Expansion response must include expanded_question and expanded_answer")
    return {
        "expanded_question": question,
        "expanded_answer": answer,
        "expansion_type": str(data.get("expansion_type", "")).strip(),
        "expansion_notes": str(data.get("expansion_notes", "")).strip(),
    }


def _extract_json_payload(response: str) -> str:
    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    if text.startswith("{"):
        return text
    start = text.find("{")
    if start < 0:
        raise ValueError("No JSON object found in expansion response")
    return text[start:]


def _read_jsonl(path: Path) -> list[Record]:
    rows: list[Record] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            data: Any = json.loads(line)
            if isinstance(data, dict):
                rows.append(data)
    return rows


def _write_jsonl(path: Path, rows: list[Record]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
