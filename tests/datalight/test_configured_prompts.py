import json

from datalight.config import PromptConfig
from datalight.pipeline.qa.expansion import QAExpansionOperator
from datalight.pipeline.qa.llm import StaticLLMClient
from datalight.pipeline.qa.multihop import MultiHopQAGeneratorOperator
from datalight.pipeline.qa.operators import Text2QAEvaluatorOperator, Text2QAGeneratorOperator
from datalight.pipeline.qa.thinking import QAThinkOperator


class SpyLLMClient(StaticLLMClient):
    def __init__(self, responses):
        super().__init__(responses)
        self.system_prompts: list[str] = []

    def generate(self, prompts: list[str], *, system_prompt: str = "") -> list[str]:
        self.system_prompts.append(system_prompt)
        return super().generate(prompts, system_prompt=system_prompt)


def test_singlehop_and_evaluator_use_configured_system_prompts_with_topic():
    prompt_config = PromptConfig(
        topic="OpenClaw 安全",
        singlehop_system="只围绕 Topic 生成 QA：{topic}",
        evaluator_system="只评估 Topic 相关 QA：{topic}",
    )
    llm = SpyLLMClient(
        [
            "Q: OpenClaw 如何控制数据？\nA: 数据完全本地。",
            "**Grading**: 5\n**Feedback**: 问题清晰",
            "**Grading**: 5\n**Feedback**: 答案匹配",
            "**Grading**: 5\n**Feedback**: 可验证",
            "**Grading**: 5\n**Feedback**: 有价值",
        ],
    )

    generated = Text2QAGeneratorOperator(
        llm_client=llm,
        system_prompt=prompt_config.render("singlehop", ""),
    ).run([{"chunk_text": "OpenClaw 数据完全本地。"}])
    Text2QAEvaluatorOperator(
        llm_client=llm,
        system_prompt=prompt_config.render("evaluator", ""),
    ).run(generated)

    assert "OpenClaw 安全" in llm.system_prompts[0]
    assert all("OpenClaw 安全" in prompt for prompt in llm.system_prompts[1:])


def test_multihop_expansion_and_thinking_use_configured_system_prompts_with_topic():
    prompt_config = PromptConfig(
        topic="OpenClaw 部署",
        multihop_system="只生成 Topic 多跳 QA：{topic}",
        expansion_system="只扩写 Topic QA：{topic}",
        thinking_system="只为 Topic QA 添加 think：{topic}",
    )
    llm = SpyLLMClient(
        [
            json.dumps(
                {
                    "question": "为什么 OpenClaw 适合自托管？",
                    "reasoning_steps": [{"step": "它支持自托管并保持数据本地"}],
                    "answer": "因为它可以部署在自己的服务器上。",
                    "supporting_facts": ["自托管服务器", "数据完全本地"],
                    "type": "部署",
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "expanded_question": "OpenClaw 为什么适合自托管部署？",
                    "expanded_answer": "OpenClaw 可部署在自己的服务器上，并保持数据本地。",
                    "expansion_type": "detail",
                    "expansion_notes": "补充部署特征。",
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "think": "先确认部署方式，再说明数据本地。",
                    "answer": "OpenClaw 支持自托管部署，并能保持数据本地。",
                },
                ensure_ascii=False,
            ),
        ],
    )

    MultiHopQAGeneratorOperator(
        llm_client=llm,
        system_prompt=prompt_config.render("multihop", ""),
    ).run([{"multihop_context": "OpenClaw 使用自托管服务器。数据完全本地。"}])
    expanded = QAExpansionOperator(
        llm_client=llm,
        system_prompt=prompt_config.render("expansion", ""),
    ).run([{"generated_question": "为什么适合部署？", "generated_answer": "可自托管。"}])
    QAThinkOperator(
        llm_client=llm,
        system_prompt=prompt_config.render("thinking", ""),
    ).run(expanded)

    assert all("OpenClaw 部署" in prompt for prompt in llm.system_prompts)
