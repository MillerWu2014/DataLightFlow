from __future__ import annotations

import json
from typing import Any
from tqdm import tqdm

from datalight.config import TaxonomyCategory, TaxonomySettings
from datalight.llm import LLMClient, safe_generate
from datalight.pipeline.core import Operator, Record
from datalight.pipeline.language import language_instruction, normalize_target_language
from datalight.pipeline.prompts.taxonomy import (
    TaxonomyAnswerPromptTemplate,
    TaxonomyQuestionPromptTemplate,
    TaxonomyTagPromptTemplate,
)
from datalight.utils.json_parse import extract_json_payload

TAG_JSON_SUFFIX = "Return valid JSON only. Do not wrap the response in Markdown code fences."
QUESTION_JSON_SUFFIX = "Return valid JSON only. Do not wrap the response in Markdown code fences."
ANSWER_JSON_SUFFIX = 'Return a JSON object only:\n{"answer":"..."}\n'


def build_taxonomy_catalog(taxonomy: TaxonomySettings) -> str:
    lines = ["## Categories (level1_name / level2_name)"]
    for category in taxonomy.categories:
        lines.append(
            f"- {category.level1_name} / {category.level2_name}: "
            f"focus={category.focus}; prompt_hint={category.prompt_hint}",
        )
    lines.append("\n## task_type")
    for key, description in taxonomy.task_type.items():
        lines.append(f"- {key}: {description}")
    lines.append("\n## reasoning_style")
    for key, description in taxonomy.reasoning_style.items():
        lines.append(f"- {key}: {description}")
    return "\n".join(lines)


def _taxonomy_system_prompt(base_prompt: str, json_suffix: str) -> str:
    if base_prompt:
        return f"{base_prompt.rstrip()}\n\n{json_suffix}"
    return json_suffix


class ChunkTaxonomyTaggerOperator(Operator):
    def __init__(
        self,
        llm_client: LLMClient,
        taxonomy: TaxonomySettings,
        target_language: str = "zh",
        system_prompt: str = "",
    ):
        self.llm_client = llm_client
        self.taxonomy = taxonomy
        self.target_language = normalize_target_language(target_language)
        self.system_prompt = system_prompt
        self.catalog = build_taxonomy_catalog(taxonomy)
        self._tag_prompt_template = TaxonomyTagPromptTemplate()
        self._category_lookup = {
            (category.level1_name, category.level2_name): category
            for category in taxonomy.categories
        }

    def run(self, rows: list[Record]) -> list[Record]:
        prompts = [
            self._build_tag_prompt(str(row.get("chunk_text", "")))
            for row in rows
        ]
        responses = safe_generate(
            self.llm_client,
            prompts,
            system_prompt=_taxonomy_system_prompt(self.system_prompt, TAG_JSON_SUFFIX),
        )
        out: list[Record] = []
        for row, response in tqdm(
            zip(rows, responses),
            total=len(rows),
            desc="Tagging taxonomy chunks",
        ):
            item = dict(row)
            item["taxonomy_tags"] = self._parse_tags(response)
            out.append(item)
        return out

    def _build_tag_prompt(self, chunk_text: str) -> str:
        if not chunk_text.strip():
            return '上下文为空，无法分类。请返回：{"tags":[]}'

        return self._tag_prompt_template.build_prompt(
            chunk_text=chunk_text,
            catalog=self.catalog,
            taxonomy=self.taxonomy,
            language_line=language_instruction(self.target_language),
        )

    def _parse_tags(self, response: str) -> list[dict[str, str]]:
        payload = _load_json_object(response, error_context="taxonomy tags")
        raw_tags = payload.get("tags", [])
        if not isinstance(raw_tags, list):
            return []

        tags: list[dict[str, str]] = []
        for raw_tag in raw_tags:
            if not isinstance(raw_tag, dict):
                continue
            tag = _normalize_tag(raw_tag, self.taxonomy, self._category_lookup)
            if tag is not None:
                tags.append(tag)
        return tags


class TaxonomyQuestionGeneratorOperator(Operator):
    def __init__(
        self,
        llm_client: LLMClient,
        taxonomy: TaxonomySettings,
        target_language: str = "zh",
        system_prompt: str = "",
    ):
        self.llm_client = llm_client
        self.taxonomy = taxonomy
        self.target_language = normalize_target_language(target_language)
        self.system_prompt = system_prompt
        self._question_prompt_template = TaxonomyQuestionPromptTemplate()

    def run(self, rows: list[Record]) -> list[Record]:
        jobs: list[tuple[Record, dict[str, str]]] = []
        for row in rows:
            for tag in row.get("taxonomy_tags", []):
                if isinstance(tag, dict):
                    jobs.append((row, tag))

        if not jobs:
            return []

        prompts = [
            self._build_question_prompt(str(row.get("chunk_text", "")), tag)
            for row, tag in jobs
        ]
        responses = safe_generate(
            self.llm_client,
            prompts,
            system_prompt=_taxonomy_system_prompt(self.system_prompt, QUESTION_JSON_SUFFIX),
        )

        out: list[Record] = []
        for (row, tag), response in tqdm(
            zip(jobs, responses),
            total=len(jobs),
            desc="Generating taxonomy questions",
        ):
            question = _parse_question(response)
            if not question:
                continue
            item = _base_taxonomy_record(row, tag)
            item["question"] = question
            out.append(item)
        return out

    def _build_question_prompt(self, chunk_text: str, tag: dict[str, str]) -> str:
        return self._question_prompt_template.build_prompt(
            chunk_text=chunk_text,
            level1_name=tag["level1_name"],
            level2_name=tag["level2_name"],
            task_type=tag["task_type"],
            task_description=self.taxonomy.task_type.get(tag["task_type"], ""),
            reasoning_style=tag["reasoning_style"],
            reasoning_description=self.taxonomy.reasoning_style.get(tag["reasoning_style"], ""),
            focus=str(tag.get("focus", "")),
            prompt_hint=str(tag.get("prompt_hint", "")),
            taxonomy=self.taxonomy,
            language_line=language_instruction(self.target_language),
        )


class TaxonomyAnswerGeneratorOperator(Operator):
    def __init__(
        self,
        llm_client: LLMClient,
        taxonomy: TaxonomySettings,
        target_language: str = "zh",
        system_prompt: str = "",
    ):
        self.llm_client = llm_client
        self.taxonomy = taxonomy
        self.target_language = normalize_target_language(target_language)
        self.system_prompt = system_prompt
        self._answer_prompt_template = TaxonomyAnswerPromptTemplate()

    def run(self, rows: list[Record]) -> list[Record]:
        if not rows:
            return []

        prompts = [
            self._build_answer_prompt(
                str(row.get("chunk_text", "")),
                str(row.get("question", "")),
                row,
            )
            for row in rows
        ]
        responses = safe_generate(
            self.llm_client,
            prompts,
            system_prompt=_taxonomy_system_prompt(self.system_prompt, ANSWER_JSON_SUFFIX),
        )

        out: list[Record] = []
        for row, response in tqdm(
            zip(rows, responses),
            total=len(rows),
            desc="Generating taxonomy answers",
        ):
            answer = _parse_answer(response)
            if not answer:
                continue
            item = dict(row)
            item["answer"] = answer
            out.append(item)
        return out

    def _build_answer_prompt(self, chunk_text: str, question: str, row: Record) -> str:
        return self._answer_prompt_template.build_prompt(
            chunk_text=chunk_text,
            question=question,
            level1_name=str(row.get("level1_name", "")),
            level2_name=str(row.get("level2_name", "")),
            task_type=str(row.get("task_type", "")),
            reasoning_style=str(row.get("reasoning_style", "")),
            taxonomy=self.taxonomy,
            language_line=language_instruction(self.target_language),
        )


def _base_taxonomy_record(row: Record, tag: dict[str, str]) -> Record:
    return {
        "source_md": row["source_md"],
        "chunk_index": row["chunk_index"],
        "chunk_text": row["chunk_text"],
        "context": str(row.get("chunk_text", "")),
        "level1_name": tag["level1_name"],
        "level2_name": tag["level2_name"],
        "task_type": tag["task_type"],
        "reasoning_style": tag["reasoning_style"],
        "focus": tag.get("focus", ""),
        "prompt_hint": tag.get("prompt_hint", ""),
        "hop_type": "singlehop",
        "reasoning_steps": [],
        "supporting_facts": [],
        "qa_type": tag["task_type"],
    }


def _normalize_tag(
    raw_tag: dict[str, Any],
    taxonomy: TaxonomySettings,
    category_lookup: dict[tuple[str, str], TaxonomyCategory],
) -> dict[str, str] | None:
    level1_name = str(raw_tag.get("level1_name") or "").strip()
    level2_name = str(raw_tag.get("level2_name") or "").strip()
    task_type = str(raw_tag.get("task_type") or "").strip()
    reasoning_style = str(raw_tag.get("reasoning_style") or "").strip()
    if not level1_name or not level2_name or not task_type or not reasoning_style:
        return None
    if task_type not in taxonomy.task_type or reasoning_style not in taxonomy.reasoning_style:
        return None

    category = category_lookup.get((level1_name, level2_name))
    if category is None:
        return None

    return {
        "level1_name": category.level1_name,
        "level2_name": category.level2_name,
        "task_type": task_type,
        "reasoning_style": reasoning_style,
        "focus": category.focus,
        "prompt_hint": category.prompt_hint,
    }


def _load_json_object(response: str, *, error_context: str) -> dict[str, Any]:
    payload = extract_json_payload(response, error_context=error_context)
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError(f"{error_context} must be a JSON object")
    return data


def _parse_question(response: str) -> str:
    try:
        payload = _load_json_object(response, error_context="taxonomy question")
    except (ValueError, json.JSONDecodeError):
        return ""
    return str(payload.get("question") or "").strip()


def _parse_answer(response: str) -> str:
    try:
        payload = _load_json_object(response, error_context="taxonomy answer")
    except (ValueError, json.JSONDecodeError):
        return ""
    return str(payload.get("answer") or "").strip()
