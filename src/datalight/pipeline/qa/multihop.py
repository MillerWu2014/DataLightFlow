from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from datalight.pipeline.core import Operator, Record
from datalight.llm import LLMClient
from datalight.pipeline.qa.language import language_instruction, normalize_target_language
from datalight.utils.json_payload import extract_json_payload

MULTIHOP_INSTRUCTION = "Answer the multi-hop question using the provided supporting facts."


class MultiHopContextBuilderOperator(Operator):
    def __init__(self, min_context_sentences: int = 3):
        if min_context_sentences < 2:
            raise ValueError("min_context_sentences must be at least 2")
        self.min_context_sentences = min_context_sentences

    def run(self, rows: list[Record]) -> list[Record]:
        out: list[Record] = []
        for row in rows:
            sentences = _split_sentences(str(row.get("chunk_text", "")))
            if len(sentences) < self.min_context_sentences:
                continue
            context_sentences = sentences[: self.min_context_sentences]
            item = dict(row)
            item["premise"] = context_sentences[0]
            item["intermediate"] = context_sentences[1]
            item["conclusion"] = context_sentences[2] if len(context_sentences) > 2 else context_sentences[-1]
            item["related_contexts"] = sentences[self.min_context_sentences :]
            item["context"] = " ".join(context_sentences)
            item["supporting_sentence_count"] = len(context_sentences)
            out.append(item)
        return out


class MultiHopQAGeneratorOperator(Operator):
    def __init__(
        self,
        llm_client: LLMClient,
        target_language: str = "zh",
        system_prompt: str | None = None,
    ):
        self.llm_client = llm_client
        self.target_language = normalize_target_language(target_language)
        self.system_prompt = system_prompt

    def run(self, rows: list[Record]) -> list[Record]:
        prompts = [
            build_multihop_prompt(str(row["context"]), target_language=self.target_language)
            for row in rows
        ]
        responses = self.llm_client.generate(
            prompts,
            system_prompt=build_multihop_system_prompt(
                target_language=self.target_language,
                system_prompt=self.system_prompt,
            ),
        )
        out: list[Record] = []
        for row, response in zip(rows, responses):
            qa = parse_multihop_response(response)
            if not qa:
                continue
            item = dict(row)
            item["question"] = qa["question"]
            item["answer"] = qa["answer"]
            item["hop_type"] = "multihop"
            item["reasoning_steps"] = qa.get("reasoning_steps", [])
            item["supporting_facts"] = qa.get("supporting_facts", [])
            item["qa_type"] = qa.get("type", "")
            out.append(item)
        return out


class MultiHopAlpacaExportOperator(Operator):
    def __init__(self, output_path: Path, instruction: str = MULTIHOP_INSTRUCTION):
        self.output_path = output_path
        self.instruction = instruction

    def run(self, rows: list[Record]) -> list[Record]:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("w", encoding="utf-8") as f:
            for row in rows:
                item = {
                    "instruction": self.instruction,
                    "input": row["question"],
                    "output": row["answer"],
                    "source_md": row["source_md"],
                    "chunk_index": row["chunk_index"],
                    "metadata": {
                        "reasoning_steps": row.get("reasoning_steps", []),
                        "supporting_facts": row.get("supporting_facts", []),
                        "type": row.get("qa_type", ""),
                    },
                }
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return rows


def build_multihop_system_prompt(target_language: str = "zh", system_prompt: str | None = None) -> str:
    if system_prompt:
        return f"{system_prompt.strip()} {language_instruction(target_language)} Return only valid JSON."
    return (
        "You are a professional multi-hop QA specialist. "
        "Generate questions that require connecting 2-3 facts. "
        f"{language_instruction(target_language)} "
        "Return only valid JSON."
    )


def build_multihop_prompt(context: str, *, target_language: str = "zh") -> str:
    return (
        "Create one multi-hop QA pair from the context below.\n"
        f"{language_instruction(target_language)}\n"
        "The question must require reasoning across at least two facts.\n"
        "Prefer a premise -> intermediate -> conclusion reasoning chain.\n"
        "Return only this JSON object:\n"
        "{\n"
        '  "question": "...",\n'
        '  "reasoning_steps": [{"step": "..."}],\n'
        '  "answer": "...",\n'
        '  "supporting_facts": ["verbatim fact 1", "verbatim fact 2"],\n'
        '  "type": "domain_tag"\n'
        "}\n\n"
        f"Context:\n{context}"
    )


def parse_multihop_response(response: str) -> dict[str, Any]:
    payload = extract_json_payload(response, allow_array=True, error_context="multi-hop response")
    data = json.loads(payload)
    if isinstance(data, list):
        if not data:
            return {}
        data = data[0]
    if not isinstance(data, dict):
        return {}
    question = str(data.get("question", "")).strip()
    answer = str(data.get("answer", "")).strip()
    if not question or not answer:
        return {}
    steps = data.get("reasoning_steps", [])
    if not isinstance(steps, list):
        steps = []
    facts = data.get("supporting_facts", [])
    if not isinstance(facts, list):
        facts = []
    return {
        "question": question,
        "reasoning_steps": steps,
        "answer": answer,
        "supporting_facts": facts,
        "type": str(data.get("type", "")).strip(),
    }


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？.!?])\s+", text.strip())
    return [part.strip() for part in parts if len(part.strip()) > 2]
