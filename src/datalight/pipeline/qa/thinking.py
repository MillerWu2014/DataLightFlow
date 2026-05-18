from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datalight.pipeline.core import Operator, Record
from datalight.pipeline.qa.language import language_instruction, normalize_target_language
from datalight.pipeline.qa.llm import LLMClient


@dataclass
class QAThinkingPipelineResult:
    input_path: Path
    output_path: Path


class QAThinkOperator(Operator):
    """Ask an LLM to add a think field and rebuild the answer from it."""

    def __init__(
        self,
        llm_client: LLMClient,
        target_language: str = "zh",
        keep_failed: bool = True,
        system_prompt: str | None = None,
    ):
        self.llm_client = llm_client
        self.target_language = normalize_target_language(target_language)
        self.keep_failed = keep_failed
        self.system_prompt = system_prompt

    def run(self, rows: list[Record]) -> list[Record]:
        prompts = [build_think_prompt(row, target_language=self.target_language) for row in rows]
        responses = self.llm_client.generate(
            prompts,
            system_prompt=build_think_system_prompt(
                target_language=self.target_language,
                system_prompt=self.system_prompt,
            ),
        )
        out: list[Record] = []
        for row, response in zip(rows, responses):
            item = dict(row)
            question_key, answer_key = _final_qa_keys(item)
            original_answer = str(item.get(answer_key, ""))
            try:
                think, rebuilt_answer = parse_think_response(response)
            except (json.JSONDecodeError, ValueError) as exc:
                if self.keep_failed:
                    item["think"] = ""
                    item["think_status"] = "failed"
                    item["think_error"] = str(exc)
                    out.append(item)
                continue

            item["think"] = think
            item["think_status"] = "ok"
            if answer_key == "expanded_answer":
                item.setdefault("original_expanded_answer", original_answer)
            else:
                item.setdefault("original_generated_answer", original_answer)
            if rebuilt_answer:
                item[answer_key] = rebuilt_answer
            elif answer_key not in item:
                item[answer_key] = original_answer
            # Keep generated_question access explicit even when the final question is expanded.
            if question_key not in item:
                item[question_key] = ""
            out.append(item)
        return out


def run_qa_thinking_pipeline(
    *,
    input_path: Path,
    output_path: Path,
    llm_client: LLMClient,
    target_language: str = "zh",
    system_prompt: str | None = None,
) -> QAThinkingPipelineResult:
    rows = _read_jsonl(input_path)
    thought = QAThinkOperator(
        llm_client=llm_client,
        target_language=target_language,
        system_prompt=system_prompt,
    ).run(rows)
    _write_jsonl(output_path, thought)
    return QAThinkingPipelineResult(input_path=input_path, output_path=output_path)


def build_think_system_prompt(target_language: str = "zh", system_prompt: str | None = None) -> str:
    if system_prompt:
        return f"{system_prompt.strip()} {language_instruction(target_language)} Return only valid JSON."
    return (
        "You add a concise think field to QA data and rebuild the answer from that think field. "
        f"{language_instruction(target_language)} "
        "Only use facts supported by the provided context and original QA. "
        "Return only valid JSON."
    )


def build_think_prompt(row: Record, *, target_language: str = "zh") -> str:
    question_key, answer_key = _final_qa_keys(row)
    question = str(row.get(question_key, ""))
    answer = str(row.get(answer_key, ""))
    context = str(row.get("chunk_text") or row.get("multihop_context") or "")
    return (
        "Given the same question, produce a concise think field and rebuild the answer from it.\n"
        f"{language_instruction(target_language)}\n"
        "If no think is needed or available, return an empty string for think.\n"
        "The answer must follow the think process and remain grounded in the context.\n"
        "Return only this JSON object:\n"
        "{\n"
        '  "think": "...",\n'
        '  "answer": "..."\n'
        "}\n\n"
        f"Context:\n{context}\n\n"
        f"Question:\n{question}\n\n"
        f"Original answer:\n{answer}"
    )


def parse_think_response(response: str) -> tuple[str, str]:
    payload = _extract_json_payload(response)
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Think response must be a JSON object")
    think = str(data.get("think", "") or "").strip()
    answer = str(data.get("answer", "") or "").strip()
    return think, answer


def _final_qa_keys(row: Record) -> tuple[str, str]:
    if row.get("expanded_question") or row.get("expanded_answer"):
        return "expanded_question", "expanded_answer"
    return "generated_question", "generated_answer"


def _extract_json_payload(response: str) -> str:
    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    if text.startswith("{"):
        return text
    start = text.find("{")
    if start < 0:
        raise ValueError("No JSON object found in think response")
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
