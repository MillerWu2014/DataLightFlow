from __future__ import annotations

import json
import re

from tqdm import tqdm

from datalight.llm import LLMClient, safe_generate
from datalight.pipeline.core import Operator, Record, limit_rows_per_chunk
from datalight.pipeline.language import normalize_target_language
from datalight.pipeline.prompts.text2qa import Text2QAAutoPromptTemplate, Text2QASeedPromptTemplate
from datalight.utils.json_parse import clean_json_block, extract_json_payload, parse_json_value


class Text2QAGeneratorOperator(Operator):
    """Two-stage Text2QA generator ported from dataflow Text2QAGenerator.

    Stage 1: generate dynamic extraction prompts per chunk.
    Stage 2: use each prompt with the chunk text to extract Q:/A: pairs.
    """

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
        self._auto_prompt = Text2QAAutoPromptTemplate()
        self._seed_prompt = Text2QASeedPromptTemplate()

    def run(self, rows: list[Record]) -> list[Record]:
        source_rows = [row for row in rows if str(row.get("chunk_text", "")).strip()]
        if not source_rows:
            return []

        auto_prompts = [
            self._auto_prompt.build_prompt(str(row["chunk_text"]), question_num=self.question_num)
            for row in source_rows
        ]
        auto_responses = safe_generate(self.llm_client, auto_prompts, system_prompt="")

        jobs: list[tuple[Record, str]] = []
        for row, response in zip(source_rows, auto_responses):
            prompt_list = parse_generated_prompt_list(response)
            for generated_prompt in prompt_list[: self.question_num]:
                jobs.append((dict(row), generated_prompt))

        if not jobs:
            return []

        seed_prompts = [
            self._seed_prompt.build_prompt(generated_prompt, str(row["chunk_text"]))
            for row, generated_prompt in jobs
        ]
        qa_responses = safe_generate(
            self.llm_client,
            seed_prompts,
            system_prompt=self.system_prompt,
        )

        expanded: list[Record] = []
        for (row, generated_prompt), response in tqdm(
            zip(jobs, qa_responses),
            total=len(jobs),
            desc="Generating QA pairs",
        ):
            pairs = parse_qa_response(response)
            if not pairs:
                question, answer = _parse_qa_line_response(response)
                if question and answer:
                    pairs = [(question, answer)]
            for question, answer in pairs:
                item = dict(row)
                item["question"] = question
                item["answer"] = answer
                item["generated_prompt"] = generated_prompt
                item["context"] = str(row.get("chunk_text", ""))
                item["hop_type"] = "singlehop"
                item["reasoning_steps"] = []
                item["supporting_facts"] = []
                item["qa_type"] = "text2qa_meta"
                expanded.append(item)
        return limit_rows_per_chunk(expanded, max_per_chunk=self.question_num)


def parse_generated_prompt_list(response: str) -> list[str]:
    parsed = parse_json_value(response)
    if isinstance(parsed, list):
        prompts = [str(item).strip() for item in parsed if str(item).strip()]
        if prompts:
            return prompts

    payload = clean_json_block(response)
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return _parse_prompt_list_fallback(payload)

    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return []


def _parse_prompt_list_fallback(text: str) -> list[str]:
    text = text.strip()
    if not text.startswith("[") or not text.endswith("]"):
        return []
    inner = text[1:-1].strip()
    if not inner:
        return []
    try:
        parsed = json.loads(f"[{inner}]")
    except json.JSONDecodeError:
        return [item.strip().strip('"').strip("'") for item in inner.split(",") if item.strip()]
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return []


def parse_qa_response(response: str) -> list[tuple[str, str]]:
    pairs = _parse_qa_json_response(response)
    if pairs:
        return pairs

    question, answer = _parse_qa_line_response(response)
    if question and answer:
        return [(question, answer)]
    return []


def _parse_qa_json_response(response: str) -> list[tuple[str, str]]:
    try:
        payload = extract_json_payload(response, error_context="qa response")
        data = json.loads(payload)
    except (ValueError, json.JSONDecodeError):
        return []

    if isinstance(data, list):
        qa_items = data
    elif isinstance(data, dict):
        qa_items = data.get("qa_pairs", [])
    else:
        return []

    if not isinstance(qa_items, list):
        return []

    pairs: list[tuple[str, str]] = []
    for item in qa_items:
        if not isinstance(item, dict):
            continue
        question = str(
            item.get("input") or item.get("question") or item.get("instruction") or "",
        ).strip()
        answer = str(item.get("output") or item.get("answer") or "").strip()
        if question and answer:
            pairs.append((question, answer))
    return pairs


def _parse_qa_line_response(response: str) -> tuple[str, str]:
    question = ""
    answer = ""
    for line in response.strip().splitlines():
        stripped = line.strip()
        if re.match(r"^q:\s*", stripped, flags=re.IGNORECASE):
            question = re.sub(r"^q:\s*", "", stripped, flags=re.IGNORECASE).strip()
        elif re.match(r"^a:\s*", stripped, flags=re.IGNORECASE):
            answer = re.sub(r"^a:\s*", "", stripped, flags=re.IGNORECASE).strip()
    return question, answer
