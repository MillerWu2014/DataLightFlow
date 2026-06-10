from __future__ import annotations

import json
from textwrap import dedent

from tqdm import tqdm

from datalight.llm import LLMClient
from datalight.pipeline.core import Operator, Record
from datalight.pipeline.language import language_instruction, normalize_target_language
from datalight.utils.json_payload import extract_json_payload


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
        for row in tqdm(rows, desc="Generating QA pairs"):
            for _ in range(self.question_num):
                qa_pairs = parse_qa_response(responses[response_index])
                response_index += 1
                for question, answer in qa_pairs:
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
        return dedent(f"""
        请阅读文档内容，并根据其内容生成一对高质量的问答对(QA), 这些QA对将用于大模型SFT的微调，必须满足以下标准：
                - **准确性**：答案必须严格依据原文，需要对问题描述清楚不得包含幻觉信息，将模糊指代转为具体实体名称。
                - **专业性**：术语使用需符合民航领域的业务规范，避免口语化。
                - **多样性**：涵盖事实问答、逻辑推理、规则、流程说明及异常处理等多种类型，不要针对图生成QA对。
                - **格式规范**：采用标准的JSON格式存储，包含 instruction、input（可选）、output。
                - **完备性**：QA 需覆盖文档核心知识点，避免遗漏关键参数或流程，包括关键参数（数值、阈值、时限）、完整流程（不省略中间步骤）、所有例外条款与特殊情形。
                - **自解释性（Self-Explanatory）**：问题必须包含必要的实体定义，使其脱离原文上下文后仍可独立理解，严禁使用“该项目”、“上文提到的”等模糊代词。
                - **原子性**：一个 QA 对只描述一个核心知识点，避免过于复杂的复合问题。如: 术语、单一流程、异常处理、单一指标、单一定义、单一规则等。
                - **禁止引用**：问题中不能出现引用，如“根据xx规范”；答案中不得包含“如上图所示”、“根据表2”、“根据附图2-1”等对文档其他部分的引用。
                - **写作规范**：答案直接陈述知识内容，禁止以"根据XX文件"、"依据XX规定"等引用句式开头。
        语言要求: {language_instruction(target_language)}
        请输出纯JSON格式，不要包含Markdown代码块标记（如 ```json ... ```）。
        JSON 结构必须如下：
        {{
            "qa_pairs": [
                {{
                    "input": "问题内容...",
                    "output": "答案内容..."
                }},
                ...
            ]
        }}
        
        文档内容：
        <content>
        {chunk_text}
        </content>
        """)

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
        if stripped.lower().startswith("q:"):
            question = stripped[2:].strip()
        elif stripped.lower().startswith("a:"):
            answer = stripped[2:].strip()
    return question, answer

