import json

from datalight.pipeline.core import Pipeline
from datalight.pipeline.qa.llm import StaticLLMClient
from datalight.pipeline.qa.multihop import (
    MultiHopAlpacaExportOperator,
    MultiHopContextBuilderOperator,
    MultiHopQAGeneratorOperator,
    parse_multihop_response,
)
from datalight.pipeline.qa.runner import run_markdown_multihop_qa_pipeline


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_multihop_context_builder_uses_three_sentences():
    rows = [
        {
            "source_md": "guide.md",
            "chunk_index": 0,
            "chunk_text": (
                "OpenClaw is self-hosted. It keeps user data local. "
                "Local control improves privacy. Short."
            ),
        },
    ]

    contexts = MultiHopContextBuilderOperator(min_context_sentences=3).run(rows)

    assert len(contexts) == 1
    assert contexts[0]["multihop_context"] == (
        "OpenClaw is self-hosted. It keeps user data local. Local control improves privacy."
    )
    assert contexts[0]["supporting_sentence_count"] == 3


def test_parse_multihop_response_accepts_json_object():
    response = json.dumps(
        {
            "question": "How does self-hosting improve privacy?",
            "reasoning_steps": [{"step": "OpenClaw is self-hosted"}],
            "answer": "It keeps user data local.",
            "supporting_facts": ["OpenClaw is self-hosted", "It keeps user data local"],
            "type": "privacy",
        },
    )

    qa = parse_multihop_response(response)

    assert qa["question"] == "How does self-hosting improve privacy?"
    assert qa["answer"] == "It keeps user data local."
    assert qa["supporting_facts"][1] == "It keeps user data local"


def test_multihop_pipeline_generates_and_exports_alpaca(tmp_path):
    export_path = tmp_path / "qa_multihop_export.jsonl"
    llm = StaticLLMClient(
        [
            json.dumps(
                {
                    "question": "Why does local data control improve privacy?",
                    "reasoning_steps": [
                        {"step": "Self-hosting keeps data on user infrastructure"},
                        {"step": "Keeping data local reduces third-party exposure"},
                    ],
                    "answer": "Because self-hosting keeps data local and reduces third-party exposure.",
                    "supporting_facts": [
                        "OpenClaw is self-hosted",
                        "It keeps user data local",
                    ],
                    "type": "privacy",
                },
            ),
        ],
    )
    rows = [
        {
            "source_md": "guide.md",
            "chunk_index": 0,
            "chunk_text": (
                "OpenClaw is self-hosted. It keeps user data local. "
                "Local control improves privacy."
            ),
        },
    ]

    pipeline = Pipeline(
        [
            MultiHopContextBuilderOperator(min_context_sentences=3),
            MultiHopQAGeneratorOperator(llm_client=llm),
            MultiHopAlpacaExportOperator(output_path=export_path),
        ],
    )
    generated = pipeline.run(rows)

    exported = read_jsonl(export_path)
    assert generated[0]["generated_question"] == "Why does local data control improve privacy?"
    assert generated[0]["reasoning_steps"][0]["step"].startswith("Self-hosting")
    assert exported[0]["input"] == "Why does local data control improve privacy?"
    assert exported[0]["metadata"]["supporting_facts"] == [
        "OpenClaw is self-hosted",
        "It keeps user data local",
    ]


def test_multihop_runner_writes_intermediate_files(tmp_path):
    md = tmp_path / "guide.md"
    md.write_text(
        "OpenClaw is self-hosted. It keeps user data local. Local control improves privacy.",
        encoding="utf-8",
    )
    llm = StaticLLMClient(
        [
            json.dumps(
                {
                    "question": "Why is OpenClaw privacy-friendly?",
                    "reasoning_steps": [{"step": "It is self-hosted and keeps data local"}],
                    "answer": "Because it is self-hosted and keeps user data local.",
                    "supporting_facts": ["OpenClaw is self-hosted", "It keeps user data local"],
                    "type": "privacy",
                },
            ),
        ],
    )

    result = run_markdown_multihop_qa_pipeline(
        markdown_paths=[md],
        output_dir=tmp_path / "out",
        llm_client=llm,
        chunk_words=80,
        min_context_sentences=3,
    )

    assert result.contexts_path.is_file()
    assert result.generated_path.is_file()
    assert result.export_path.is_file()
    assert read_jsonl(result.export_path)[0]["output"].startswith("Because")
