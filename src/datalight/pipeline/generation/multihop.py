from __future__ import annotations

import json
from typing import Any

from datalight.llm import LLMClient
from datalight.pipeline.core import Operator, Record
from datalight.pipeline.language import language_instruction, normalize_target_language
from datalight.utils.json_payload import extract_json_payload


class MultiHopQAGeneratorOperator(Operator):
    """生成多跳QA对"""

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


def build_multihop_system_prompt(target_language: str = "zh", system_prompt: str | None = None) -> str:
    json_rule = "请只返回合法 JSON，不要使用 Markdown 代码块。"
    if system_prompt:
        return f"{system_prompt.strip()}\n{language_instruction(target_language)}\n{json_rule}"
    return (
        "你是民航领域多跳 QA 构造专家。"
        "围绕 Context 生成需串联 2-3 个事实、经多步推理才能回答的问答对。"
        f"{language_instruction(target_language)} "
        "答案须完整呈现推理依据与结论，不得一句话敷衍。"
        f"{json_rule}"
    )


def build_multihop_prompt(context: str, *, target_language: str = "zh") -> str:
    return (
        "根据 Context 生成 1 个多跳 QA 对：问题需串联至少 2 个事实，经多步推理后才能作答。\n"
        f"{language_instruction(target_language)}\n\n"
        "要求：\n"
        "- 问题、推理步骤、答案均须严格基于 Context，不得编造。\n"
        "- reasoning_steps 至少 2 步，体现「前提 → 中间推断 → 结论」思维链。\n"
        "- answer 须完整写出推理结论，交代关键条件与依据，禁止一句话敷衍作答。\n"
        "- supporting_facts 从 Context 原文摘录支撑事实。\n"
        "- 问题自含主体，禁止「上文」「该规范」等模糊指代。\n"
        "- Context 不足以构成多跳推理时，返回空对象 {}。\n\n"
        "请只返回如下 JSON，不要输出 Markdown 代码块：\n"
        "{\n"
        '  "question": "...",\n'
        '  "reasoning_steps": [{"step": "..."}, {"step": "..."}],\n'
        '  "answer": "完整答案，融合推理依据与最终结论...",\n'
        '  "supporting_facts": ["原文事实1", "原文事实2"],\n'
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
