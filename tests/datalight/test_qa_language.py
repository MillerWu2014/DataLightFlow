import json

from datalight.pipeline.qa.llm import StaticLLMClient
from datalight.pipeline.qa.multihop import MultiHopQAGeneratorOperator, build_multihop_prompt
from datalight.pipeline.qa.operators import Text2QAEvaluatorOperator, Text2QAGeneratorOperator


def test_singlehop_generator_defaults_to_chinese_prompt():
    llm = StaticLLMClient(["Q: 什么是 OpenClaw？\nA: 一个开源自托管 AI Agent 系统。"])

    out = Text2QAGeneratorOperator(llm_client=llm).run(
        [{"chunk_text": "OpenClaw 是一个开源、自托管的 AI Agent 系统。"}],
    )

    assert "中文" in llm.prompts[0]
    assert out[0]["generated_question"] == "什么是 OpenClaw？"


def test_singlehop_evaluator_defaults_to_chinese_feedback_prompt():
    llm = StaticLLMClient(
        [
            "**Grading**: 5\n**Feedback**: 问题清晰",
            "**Grading**: 5\n**Feedback**: 答案匹配",
            "**Grading**: 5\n**Feedback**: 可从原文验证",
            "**Grading**: 5\n**Feedback**: 适合训练",
        ],
    )

    out = Text2QAEvaluatorOperator(llm_client=llm).run(
        [
            {
                "chunk_text": "OpenClaw 是一个开源、自托管的 AI Agent 系统。",
                "generated_question": "什么是 OpenClaw？",
                "generated_answer": "一个开源自托管 AI Agent 系统。",
            },
        ],
    )

    assert all("中文" in prompt for prompt in llm.prompts)
    assert out[0]["question_quality_feedback"] == "问题清晰"


def test_multihop_generator_defaults_to_chinese_prompt():
    llm = StaticLLMClient(
        [
            json.dumps(
                {
                    "question": "为什么 OpenClaw 有利于数据控制？",
                    "reasoning_steps": [{"step": "它是自托管，并且数据保存在本地"}],
                    "answer": "因为自托管让用户拥有本地数据控制权。",
                    "supporting_facts": ["OpenClaw 是自托管系统", "数据完全本地"],
                    "type": "数据控制",
                },
                ensure_ascii=False,
            ),
        ],
    )

    out = MultiHopQAGeneratorOperator(llm_client=llm).run(
        [{"multihop_context": "OpenClaw 是自托管系统。数据完全本地。用户拥有所有数据。"}],
    )

    assert "中文" in llm.prompts[0]
    assert out[0]["generated_question"] == "为什么 OpenClaw 有利于数据控制？"


def test_language_auto_uses_context_primary_language_instruction():
    prompt = build_multihop_prompt("OpenClaw is self-hosted.", target_language="auto")

    assert "Use the primary language of the context" in prompt
    assert "必须使用中文" not in prompt
