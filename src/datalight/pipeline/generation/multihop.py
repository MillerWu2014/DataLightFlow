from __future__ import annotations

import json
from typing import Any

from datalight.llm import LLMClient
from datalight.pipeline.core import Operator, Record
from datalight.pipeline.language import normalize_target_language
from datalight.pipeline.prompts.multihop import MultihopPromptTemplate


class MultiHopQAGeneratorOperator(Operator):
    """Generate multi-hop QA pairs using the original DataFlow prompt and parsing flow."""

    def __init__(
        self,
        llm_client: LLMClient,
        target_language: str = "zh",
        system_prompt: str | None = None,
        num_q: int = 5,
        strict_validation: bool = True,
    ):
        if num_q <= 0:
            raise ValueError("num_q must be positive")
        self.llm_client = llm_client
        self.target_language = _normalize_multihop_language(target_language)
        self.system_prompt = system_prompt
        self.num_q = num_q
        self.strict_validation = strict_validation
        self.prompt_template = MultihopPromptTemplate(lang=self.target_language)

    def run(self, rows: list[Record]) -> list[Record]:
        if not rows:
            return []

        prompts = [self.prompt_template.build_prompt(str(row["context"])) for row in rows]
        responses = self.llm_client.generate(
            prompts,
            system_prompt=build_multihop_system_prompt(
                prompt_template=self.prompt_template,
                extra_system_prompt=self.system_prompt,
            ),
        )

        grouped: dict[tuple[str, int], list[Record]] = {}
        for row, response in zip(rows, responses):
            qa_pairs = extract_multihop_qa_pairs(response, strict=self.strict_validation)
            if not qa_pairs:
                continue
            key = (str(row.get("source_md", "")), int(row.get("chunk_index", 0)))
            for qa in qa_pairs:
                item = dict(row)
                item["question"] = qa["question"]
                item["answer"] = qa["answer"]
                item["hop_type"] = "multihop"
                item["reasoning_steps"] = qa.get("reasoning_steps", [])
                item["supporting_facts"] = qa.get("supporting_facts", [])
                item["qa_type"] = qa.get("type", "")
                item["complexity"] = calculate_multihop_complexity([qa])
                grouped.setdefault(key, []).append(item)

        out: list[Record] = []
        for items in grouped.values():
            deduped = _dedupe_multihop_rows(items)
            out.extend(deduped[: self.num_q])
        return out


def build_multihop_system_prompt(
    *,
    prompt_template: MultihopPromptTemplate,
    extra_system_prompt: str | None = None,
) -> str:
    base_prompt = prompt_template.build_system_prompt()
    if extra_system_prompt and extra_system_prompt.strip():
        return f"{extra_system_prompt.strip()}\n\n{base_prompt}"
    return base_prompt


def build_multihop_prompt(context: str, *, target_language: str = "zh") -> str:
    return MultihopPromptTemplate(lang=_normalize_multihop_language(target_language)).build_prompt(context)


def parse_multihop_response(response: str, *, strict: bool = True) -> dict[str, Any]:
    qa_pairs = extract_multihop_qa_pairs(response, strict=strict)
    return qa_pairs[0] if qa_pairs else {}


def extract_multihop_qa_pairs(response: str, *, strict: bool = True) -> list[dict[str, Any]]:
    qa_pairs: list[dict[str, Any]] = []

    try:
        payload = json.loads(response)
        if isinstance(payload, dict) and "question" in payload:
            qa_pairs.append(_normalize_multihop_qa(payload, strict=strict))
        elif isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and "question" in item:
                    qa_pairs.append(_normalize_multihop_qa(item, strict=strict))
        qa_pairs = [qa for qa in qa_pairs if qa]
        if qa_pairs:
            return _dedupe_multihop_qa_pairs(qa_pairs)
    except json.JSONDecodeError:
        pass

    json_objects = _find_json_objects(response)
    for json_str in json_objects:
        try:
            qa_pair = json.loads(json_str)
        except json.JSONDecodeError:
            continue
        if not isinstance(qa_pair, dict):
            continue
        normalized = _normalize_multihop_qa(qa_pair, strict=strict)
        if normalized:
            qa_pairs.append(normalized)

    return _dedupe_multihop_qa_pairs(qa_pairs)


def calculate_multihop_complexity(qa_pairs: list[dict[str, Any]]) -> float:
    if not qa_pairs:
        return 0.0

    complexities: list[float] = []
    for qa in qa_pairs:
        reasoning_steps_count = len(qa.get("reasoning_steps", []))
        supporting_facts_count = len(qa.get("supporting_facts", []))
        question_length = len(str(qa.get("question", "")).split())
        answer_length = len(str(qa.get("answer", "")).split())
        complexities.append(
            min(reasoning_steps_count / 3, 1.0) * 0.4
            + min(supporting_facts_count / 3, 1.0) * 0.3
            + min(question_length / 20, 1.0) * 0.15
            + min(answer_length / 50, 1.0) * 0.15,
        )
    return sum(complexities) / len(complexities)


def _normalize_multihop_language(target_language: str) -> str:
    language = normalize_target_language(target_language)
    return "zh" if language == "auto" else language


def _normalize_multihop_qa(data: dict[str, Any], *, strict: bool) -> dict[str, Any]:
    question = str(data.get("question", "")).strip()
    answer = str(data.get("answer", "")).strip()
    qa_type = str(data.get("type", "")).strip()
    reasoning_steps = _normalize_reasoning_steps(data.get("reasoning_steps", []))
    supporting_facts = _normalize_supporting_facts(data.get("supporting_facts", []))

    if not question or not answer:
        return {}
    if strict:
        if not qa_type:
            return {}
        if len(reasoning_steps) < 2:
            return {}
        if len(supporting_facts) < 2:
            return {}
        if not _has_required_multihop_fields(data):
            return {}

    return {
        "question": question,
        "reasoning_steps": reasoning_steps,
        "answer": answer,
        "supporting_facts": supporting_facts,
        "type": qa_type,
    }


def _has_required_multihop_fields(data: dict[str, Any]) -> bool:
    return all(
        key in data
        for key in ("question", "reasoning_steps", "answer", "supporting_facts", "type")
    )


def _normalize_reasoning_steps(raw_steps: Any) -> list[dict[str, str]]:
    if not isinstance(raw_steps, list):
        return []
    steps: list[dict[str, str]] = []
    for step in raw_steps:
        if isinstance(step, dict):
            text = str(step.get("step", "")).strip()
        else:
            text = str(step).strip()
        if text:
            steps.append({"step": text})
    return steps


def _normalize_supporting_facts(raw_facts: Any) -> list[str]:
    if not isinstance(raw_facts, list):
        return []
    return [str(fact).strip() for fact in raw_facts if str(fact).strip()]


def _find_json_objects(response: str) -> list[str]:
    json_objects: list[str] = []
    brace_count = 0
    start_pos = -1
    for index, char in enumerate(response):
        if char == "{":
            if brace_count == 0:
                start_pos = index
            brace_count += 1
        elif char == "}":
            brace_count -= 1
            if brace_count == 0 and start_pos != -1:
                json_objects.append(response[start_pos : index + 1])
                start_pos = -1
    return json_objects


def _dedupe_multihop_qa_pairs(qa_pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_questions: set[str] = set()
    unique_pairs: list[dict[str, Any]] = []
    for qa_pair in qa_pairs:
        question = qa_pair.get("question", "").strip().lower()
        if question and question not in seen_questions:
            seen_questions.add(question)
            unique_pairs.append(qa_pair)
    return unique_pairs


def _dedupe_multihop_rows(rows: list[Record]) -> list[Record]:
    seen_questions: set[str] = set()
    unique_rows: list[Record] = []
    for row in rows:
        question = str(row.get("question", "")).strip().lower()
        if question and question not in seen_questions:
            seen_questions.add(question)
            unique_rows.append(row)
    return unique_rows
