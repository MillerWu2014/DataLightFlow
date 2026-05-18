import json

from datalight.pipeline.qa.expansion import QAExpansionOperator, run_qa_expansion_pipeline
from datalight.pipeline.qa.llm import StaticLLMClient
from datalight.pipeline.qa.runner import run_markdown_qa_pipeline


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_qa_expansion_operator_preserves_original_and_adds_expanded_fields():
    llm = StaticLLMClient(
        [
            json.dumps(
                {
                    "expanded_question": "OpenClaw 与 ChatGPT 在数据控制方面有什么关键区别？",
                    "expanded_answer": "OpenClaw 将数据保存在本地，用户拥有数据控制权；ChatGPT 的数据由 OpenAI 托管。",
                    "expansion_type": "detail",
                    "expansion_notes": "补充了数据归属和托管差异。",
                },
                ensure_ascii=False,
            ),
        ],
    )

    out = QAExpansionOperator(llm_client=llm).run(
        [
            {
                "chunk_text": "OpenClaw 数据完全本地，ChatGPT 数据在 OpenAI。",
                "generated_question": "两者数据控制有什么区别？",
                "generated_answer": "OpenClaw 本地，ChatGPT 在 OpenAI。",
            },
        ],
    )

    assert "中文" in llm.prompts[0]
    assert out[0]["generated_question"] == "两者数据控制有什么区别？"
    assert out[0]["expanded_question"] == "OpenClaw 与 ChatGPT 在数据控制方面有什么关键区别？"
    assert out[0]["expanded_answer"].startswith("OpenClaw 将数据保存在本地")
    assert out[0]["expansion_type"] == "detail"


def test_qa_expansion_operator_keeps_original_on_invalid_json():
    llm = StaticLLMClient(["not json"])
    row = {
        "generated_question": "什么是 OpenClaw？",
        "generated_answer": "一个开源自托管 AI Agent 系统。",
    }

    out = QAExpansionOperator(llm_client=llm).run([row])

    assert out[0]["generated_question"] == row["generated_question"]
    assert out[0]["expansion_status"] == "failed"
    assert "expanded_question" not in out[0]


def test_run_qa_expansion_pipeline_reads_and_writes_jsonl(tmp_path):
    input_path = tmp_path / "qa_scored.jsonl"
    output_path = tmp_path / "qa_expanded.jsonl"
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
                    "expanded_question": "OpenClaw 是什么类型的系统？",
                    "expanded_answer": "OpenClaw 是一个开源、自托管的 AI Agent 系统。",
                    "expansion_type": "contextual",
                    "expansion_notes": "使问题更自然。",
                },
                ensure_ascii=False,
            ),
        ],
    )

    result = run_qa_expansion_pipeline(
        input_path=input_path,
        output_path=output_path,
        llm_client=llm,
        mode="contextual",
    )

    assert result.output_path == output_path
    assert read_jsonl(output_path)[0]["expanded_question"] == "OpenClaw 是什么类型的系统？"


def test_markdown_qa_pipeline_can_optionally_expand_after_filtering(tmp_path):
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
                    "expanded_question": "OpenClaw 是什么，它的部署特征是什么？",
                    "expanded_answer": "OpenClaw 是一个开源、自托管的 AI Agent 系统，强调用户可自行部署和控制。",
                    "expansion_type": "detail",
                    "expansion_notes": "补充部署特征。",
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
    )

    assert result.expanded_path is not None
    assert read_jsonl(result.expanded_path)[0]["expanded_answer"].startswith("OpenClaw 是一个开源")
    assert read_jsonl(result.export_path)[0]["input"] == "OpenClaw 是什么，它的部署特征是什么？"
