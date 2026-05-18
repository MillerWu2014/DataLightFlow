import json

from datalight.pipeline.qa.llm import StaticLLMClient
from datalight.pipeline.qa.runner import run_markdown_qa_pipeline
from datalight.pipeline.qa.thinking import QAThinkOperator, run_qa_thinking_pipeline


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_qa_think_operator_adds_think_and_rebuilds_answer():
    llm = StaticLLMClient(
        [
            json.dumps(
                {
                    "think": "先确认 OpenClaw 是自托管系统，再说明数据保存在本地。",
                    "answer": "OpenClaw 是自托管系统，因此数据保存在本地，用户拥有控制权。",
                },
                ensure_ascii=False,
            ),
        ],
    )

    out = QAThinkOperator(llm_client=llm).run(
        [
            {
                "chunk_text": "OpenClaw 是自托管系统，数据完全本地。",
                "generated_question": "OpenClaw 如何控制数据？",
                "generated_answer": "数据完全本地。",
            },
        ],
    )

    assert "中文" in llm.prompts[0]
    assert "OpenClaw 如何控制数据？" in llm.prompts[0]
    assert out[0]["original_generated_answer"] == "数据完全本地。"
    assert out[0]["generated_answer"] == "OpenClaw 是自托管系统，因此数据保存在本地，用户拥有控制权。"
    assert out[0]["think"] == "先确认 OpenClaw 是自托管系统，再说明数据保存在本地。"
    assert out[0]["think_status"] == "ok"


def test_qa_think_operator_defaults_empty_think_when_missing():
    llm = StaticLLMClient(
        [
            json.dumps(
                {"answer": "OpenClaw 是开源、自托管的 AI Agent 系统。"},
                ensure_ascii=False,
            ),
        ],
    )

    out = QAThinkOperator(llm_client=llm).run(
        [
            {
                "generated_question": "什么是 OpenClaw？",
                "generated_answer": "一个开源自托管 AI Agent 系统。",
            },
        ],
    )

    assert out[0]["think"] == ""
    assert out[0]["generated_answer"] == "OpenClaw 是开源、自托管的 AI Agent 系统。"


def test_qa_think_operator_updates_expanded_answer_when_present():
    llm = StaticLLMClient(
        [
            json.dumps(
                {
                    "think": "先解释系统类型，再补充自托管特征。",
                    "answer": "OpenClaw 是开源 AI Agent 系统，并且支持用户自托管部署。",
                },
                ensure_ascii=False,
            ),
        ],
    )

    out = QAThinkOperator(llm_client=llm).run(
        [
            {
                "generated_question": "什么是 OpenClaw？",
                "generated_answer": "一个 AI Agent 系统。",
                "expanded_question": "OpenClaw 是什么类型的系统？",
                "expanded_answer": "OpenClaw 是开源 AI Agent 系统。",
            },
        ],
    )

    assert out[0]["original_expanded_answer"] == "OpenClaw 是开源 AI Agent 系统。"
    assert out[0]["expanded_answer"] == "OpenClaw 是开源 AI Agent 系统，并且支持用户自托管部署。"


def test_run_qa_thinking_pipeline_reads_and_writes_jsonl(tmp_path):
    input_path = tmp_path / "qa_expanded.jsonl"
    output_path = tmp_path / "qa_with_think.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "generated_question": "什么是 OpenClaw？",
                "generated_answer": "一个开源自托管 AI Agent 系统。",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    llm = StaticLLMClient(
        [
            json.dumps(
                {
                    "think": "根据问题识别系统定义。",
                    "answer": "OpenClaw 是一个开源、自托管的 AI Agent 系统。",
                },
                ensure_ascii=False,
            ),
        ],
    )

    result = run_qa_thinking_pipeline(
        input_path=input_path,
        output_path=output_path,
        llm_client=llm,
    )

    assert result.output_path == output_path
    assert read_jsonl(output_path)[0]["think"] == "根据问题识别系统定义。"


def test_markdown_qa_pipeline_can_optionally_add_think_after_expansion(tmp_path):
    md = tmp_path / "guide.md"
    md.write_text("OpenClaw 是一个开源、自托管的 AI Agent 系统。", encoding="utf-8")
    llm = StaticLLMClient(
        [
            "Q: 什么是 OpenClaw？\nA: 一个开源自托管 AI Agent 系统。",
            "**Grading**: 5\n**Feedback**: 问题清晰",
            "**Grading**: 5\n**Feedback**: 答案匹配",
            "**Grading**: 5\n**Feedback**: 可验证",
            "**Grading**: 5\n**Feedback**: 有训练价值",
            json.dumps(
                {
                    "expanded_question": "OpenClaw 是什么类型的系统？",
                    "expanded_answer": "OpenClaw 是一个开源、自托管的 AI Agent 系统。",
                    "expansion_type": "detail",
                    "expansion_notes": "补充系统类型。",
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "think": "先定位系统定义，再说明开源和自托管特征。",
                    "answer": "OpenClaw 是一个开源的 AI Agent 系统，支持用户自托管部署和控制。",
                },
                ensure_ascii=False,
            ),
        ],
    )

    result = run_markdown_qa_pipeline(
        markdown_paths=[md],
        output_dir=tmp_path / "out",
        llm_client=llm,
        chunk_words=30,
        min_question_quality=4,
        min_answer_alignment=4,
        min_answer_verifiability=4,
        min_downstream_value=4,
        expand_qa=True,
        add_think=True,
    )

    assert result.think_path is not None
    assert read_jsonl(result.think_path)[0]["think"] == "先定位系统定义，再说明开源和自托管特征。"
    exported = read_jsonl(result.export_path)[0]
    assert exported["input"] == "OpenClaw 是什么类型的系统？"
    assert exported["output"] == "OpenClaw 是一个开源的 AI Agent 系统，支持用户自托管部署和控制。"
    assert exported["think"] == "先定位系统定义，再说明开源和自托管特征。"
