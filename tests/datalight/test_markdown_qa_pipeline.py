import json

from datalight.pipeline.core import Pipeline
from datalight.pipeline.qa.llm import OpenAICompatibleLLMClient, StaticLLMClient
from datalight.pipeline.qa.operators import (
    AlpacaExportOperator,
    MarkdownChunkOperator,
    QAFilterOperator,
    Text2QAEvaluatorOperator,
    Text2QAGeneratorOperator,
)
from datalight.pipeline.qa.runner import run_markdown_qa_pipeline


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_markdown_chunk_operator_splits_text_with_overlap(tmp_path):
    md = tmp_path / "guide.md"
    md.write_text("# Title\n\none two three four five six seven eight nine", encoding="utf-8")

    rows = MarkdownChunkOperator(chunk_words=5, overlap_words=1).run(
        [{"source_path": str(md), "output_md_path": str(md), "status": "ok"}],
    )

    assert [row["chunk_text"] for row in rows] == [
        "# Title one two three",
        "three four five six seven",
        "seven eight nine",
    ]
    assert rows[0]["source_md"] == str(md)
    assert rows[1]["chunk_index"] == 1


def test_pipeline_generates_scores_filters_and_exports_alpaca(tmp_path):
    md = tmp_path / "guide.md"
    md.write_text("OpenClaw lets agents execute tasks inside workspaces.", encoding="utf-8")
    export_path = tmp_path / "qa_export.jsonl"
    llm = StaticLLMClient(
        responses=[
            "Q: What does OpenClaw let agents do?\nA: Execute tasks inside workspaces.",
            "**Grading**: 5\n**Feedback**: grounded and clear",
            "**Grading**: 5\n**Feedback**: aligned",
            "**Grading**: 5\n**Feedback**: verifiable",
            "**Grading**: 4\n**Feedback**: useful",
        ],
    )

    pipeline = Pipeline(
        [
            MarkdownChunkOperator(chunk_words=20),
            Text2QAGeneratorOperator(llm_client=llm, question_num=1),
            Text2QAEvaluatorOperator(llm_client=llm),
            QAFilterOperator(min_question_quality=4),
            AlpacaExportOperator(output_path=export_path),
        ],
    )
    rows = pipeline.run([{"source_path": str(md), "output_md_path": str(md), "status": "ok"}])

    exported = read_jsonl(export_path)
    assert len(rows) == 1
    assert rows[0]["generated_question"] == "What does OpenClaw let agents do?"
    assert rows[0]["question_quality_grade"] == 5
    assert rows[0]["answer_alignment_grade"] == 5
    assert exported == [
        {
            "instruction": "Please answer the following question based on the provided information.",
            "input": "What does OpenClaw let agents do?",
            "output": "Execute tasks inside workspaces.",
            "source_md": str(md),
            "chunk_index": 0,
        },
    ]


def test_runner_writes_intermediate_jsonl_files(tmp_path):
    md = tmp_path / "guide.md"
    md.write_text("OpenClaw is an open-source self-hosted AI agent system.", encoding="utf-8")
    llm = StaticLLMClient(
        responses=[
            "Q: What is OpenClaw?\nA: An open-source self-hosted AI agent system.",
            "**Grading**: 4\n**Feedback**: acceptable",
            "**Grading**: 4\n**Feedback**: aligned",
            "**Grading**: 4\n**Feedback**: verifiable",
            "**Grading**: 4\n**Feedback**: useful",
        ],
    )

    result = run_markdown_qa_pipeline(
        markdown_paths=[md],
        output_dir=tmp_path / "out",
        llm_client=llm,
        chunk_words=30,
        min_question_quality=3,
    )

    assert result.export_path.name == "qa_export.jsonl"
    assert result.generated_path.is_file()
    assert result.scored_path.is_file()
    assert read_jsonl(result.export_path)[0]["input"] == "What is OpenClaw?"


def test_openai_compatible_client_posts_lmstudio_chat_requests():
    requests = []

    def fake_transport(url, payload, timeout):
        requests.append((url, payload, timeout))
        return {"choices": [{"message": {"content": "Q: hi\nA: there"}}]}

    client = OpenAICompatibleLLMClient(
        base_url="http://127.0.0.1:1234/v1",
        model="gemma-4-31b-it",
        timeout_sec=7,
        transport=fake_transport,
    )

    assert client.generate(["hello"], system_prompt="sys") == ["Q: hi\nA: there"]
    url, payload, timeout = requests[0]
    assert url == "http://127.0.0.1:1234/v1/chat/completions"
    assert payload["model"] == "gemma-4-31b-it"
    assert payload["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]
    assert timeout == 7
