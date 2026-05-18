import json

from datalight.pipeline.qa.agentic import DepthQAGeneratorOperator, WidthQAGeneratorOperator
from datalight.pipeline.qa.filters import QADedupFilterOperator
from datalight.pipeline.qa.formatters import QAExtractorOperator
from datalight.pipeline.qa.llm import StaticLLMClient
from datalight.pipeline.qa.multihop import MultiHopContextBuilderOperator
from datalight.pipeline.qa.operators import Text2QAEvaluatorOperator


def test_text2qa_evaluator_outputs_four_dataflow_dimensions():
    rows = [
        {
            "chunk_text": "OpenClaw is self-hosted and keeps user data local.",
            "generated_question": "What does OpenClaw do with user data?",
            "generated_answer": "It keeps user data local.",
        },
    ]
    llm = StaticLLMClient(
        [
            "**Grading**: 5\n**Feedback**: clear",
            "**Grading**: 4\n**Feedback**: aligned",
            "**Grading**: 5\n**Feedback**: verifiable",
            "**Grading**: 3\n**Feedback**: useful",
        ],
    )

    out = Text2QAEvaluatorOperator(llm_client=llm).run(rows)

    assert out[0]["question_quality_grade"] == 5
    assert out[0]["answer_alignment_grade"] == 4
    assert out[0]["answer_verifiability_grade"] == 5
    assert out[0]["downstream_value_grade"] == 3
    assert out[0]["downstream_value_feedback"] == "useful"


def test_multihop_context_builder_adds_information_pair_fields():
    rows = [
        {
            "source_md": "guide.md",
            "chunk_index": 0,
            "chunk_text": "A is true. B follows from A. C follows from B. D is related.",
        },
    ]

    out = MultiHopContextBuilderOperator(min_context_sentences=3).run(rows)

    assert out[0]["premise"] == "A is true."
    assert out[0]["intermediate"] == "B follows from A."
    assert out[0]["conclusion"] == "C follows from B."
    assert out[0]["related_contexts"] == ["D is related."]


def test_qa_extractor_flattens_nested_qa_pairs_to_alpaca():
    rows = [
        {
            "source_md": "guide.md",
            "chunk_index": 2,
            "qa_pairs": [
                {
                    "question": "Q1?",
                    "answer": "A1.",
                    "reasoning_steps": [{"step": "because"}],
                    "supporting_facts": ["fact"],
                },
            ],
        },
    ]

    out = QAExtractorOperator().run(rows)

    assert out == [
        {
            "instruction": "Please answer the following question based on the provided information.",
            "input": "Q1?",
            "output": "A1.",
            "source_md": "guide.md",
            "chunk_index": 2,
            "metadata": {
                "reasoning_steps": [{"step": "because"}],
                "supporting_facts": ["fact"],
                "type": "",
            },
        },
    ]


def test_dedup_filter_removes_duplicate_questions_and_near_duplicate_answers():
    rows = [
        {"generated_question": "What is OpenClaw?", "generated_answer": "A self hosted agent."},
        {"generated_question": "What is OpenClaw?", "generated_answer": "A self hosted agent."},
        {"generated_question": "How is data handled?", "generated_answer": "User data stays local."},
    ]

    out = QADedupFilterOperator().run(rows)

    assert [row["generated_question"] for row in out] == [
        "What is OpenClaw?",
        "How is data handled?",
    ]


def test_depth_and_width_generators_use_existing_qa_with_static_llm():
    rows = [
        {
            "generated_question": "What is OpenClaw?",
            "generated_answer": "A self-hosted AI agent system.",
            "identifier": "OpenClaw",
        },
        {
            "generated_question": "Where does OpenClaw keep data?",
            "generated_answer": "Locally.",
            "identifier": "data locality",
        },
    ]
    llm = StaticLLMClient(
        [
            json.dumps(
                {
                    "question": "Why does OpenClaw's self-hosting matter?",
                    "answer": "It helps users control local data.",
                    "identifier": "self-hosting privacy",
                    "relation": "privacy",
                },
            ),
            json.dumps(
                {
                    "question": "How do OpenClaw's architecture and data locality relate?",
                    "answer": "Self-hosting supports local data control.",
                    "index": [0, 1],
                    "content_identifier": "OpenClaw + data locality",
                },
            ),
        ],
    )

    depth = DepthQAGeneratorOperator(llm_client=llm).run(rows[:1])
    width = WidthQAGeneratorOperator(llm_client=llm).run(rows)

    assert depth[0]["generated_question"] == "Why does OpenClaw's self-hosting matter?"
    assert depth[0]["relation"] == "privacy"
    assert width[0]["generated_question"] == "How do OpenClaw's architecture and data locality relate?"
    assert width[0]["source_question_indices"] == [0, 1]
