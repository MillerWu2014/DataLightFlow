from __future__ import annotations

from pathlib import Path

from datalight.config import PromptConfig
from datalight.llm import LLMClient
from datalight.pipeline.core import Pipeline
from datalight.pipeline.qa.models import MarkdownMultiHopQAPipelineResult, MarkdownQAPipelineResult
from datalight.pipeline.qa.expansion import QAExpansionOperator
from datalight.pipeline.qa.thinking import QAThinkOperator
from datalight.pipeline.qa.operators import (
    AlpacaExportOperator,
    MarkdownChunkOperator,
    QAFilterOperator,
    Text2QAEvaluatorOperator,
    Text2QAGeneratorOperator,
)
from datalight.pipeline.qa.multihop import (
    MultiHopAlpacaExportOperator,
    MultiHopContextBuilderOperator,
    MultiHopQAGeneratorOperator,
)
from datalight.utils.jsonl import write_jsonl


def run_markdown_qa_pipeline(
    *,
    markdown_paths: list[Path],
    output_dir: Path,
    llm_client: LLMClient,
    chunk_words: int = 512,
    overlap_words: int = 0,
    question_num: int = 1,
    min_question_quality: float = 3.0,
    min_answer_alignment: float | None = None,
    min_answer_verifiability: float | None = None,
    min_downstream_value: float | None = None,
    target_language: str = "zh",
    expand_qa: bool = False,
    expand_mode: str = "detail",
    add_think: bool = False,
    prompt_config: PromptConfig | None = None,
) -> MarkdownQAPipelineResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        {"source_path": str(path), "output_md_path": str(path), "status": "ok"}
        for path in markdown_paths
    ]

    chunks = MarkdownChunkOperator(chunk_words=chunk_words, overlap_words=overlap_words).run(rows)
    chunks_path = output_dir / "chunks.jsonl"
    write_jsonl(chunks_path, chunks)

    generated = Text2QAGeneratorOperator(
        llm_client=llm_client,
        question_num=question_num,
        target_language=target_language,
        system_prompt=prompt_config.render("singlehop", "") if prompt_config else "",
    ).run(chunks)
    generated_path = output_dir / "qa_generated.jsonl"
    write_jsonl(generated_path, generated)

    scored = Text2QAEvaluatorOperator(
        llm_client=llm_client,
        target_language=target_language,
        system_prompt=prompt_config.render("evaluator", "") if prompt_config else "",
    ).run(generated)
    scored_path = output_dir / "qa_scored.jsonl"
    write_jsonl(scored_path, scored)

    filtered = QAFilterOperator(
        min_question_quality=min_question_quality,
        min_answer_alignment=min_answer_alignment,
        min_answer_verifiability=min_answer_verifiability,
        min_downstream_value=min_downstream_value,
    ).run(scored)

    expanded_path: Path | None = None
    rows_to_export = filtered
    if expand_qa:
        rows_to_export = QAExpansionOperator(
            llm_client=llm_client,
            mode=expand_mode,
            target_language=target_language,
            system_prompt=prompt_config.render("expansion", "") if prompt_config else None,
        ).run(filtered)
        expanded_path = output_dir / "qa_expanded.jsonl"
        write_jsonl(expanded_path, rows_to_export)

    think_path: Path | None = None
    if add_think:
        rows_to_export = QAThinkOperator(
            llm_client=llm_client,
            target_language=target_language,
            system_prompt=prompt_config.render("thinking", "") if prompt_config else None,
        ).run(rows_to_export)
        think_path = output_dir / "qa_with_think.jsonl"
        write_jsonl(think_path, rows_to_export)

    export_path = output_dir / "qa_export.jsonl"
    Pipeline(
        [
            AlpacaExportOperator(output_path=export_path),
        ],
    ).run(rows_to_export)

    return MarkdownQAPipelineResult(
        chunks_path=chunks_path,
        generated_path=generated_path,
        scored_path=scored_path,
        export_path=export_path,
        expanded_path=expanded_path,
        think_path=think_path,
    )


def run_markdown_multihop_qa_pipeline(
    *,
    markdown_paths: list[Path],
    output_dir: Path,
    llm_client: LLMClient,
    chunk_words: int = 800,
    overlap_words: int = 0,
    min_context_sentences: int = 3,
    target_language: str = "zh",
    prompt_config: PromptConfig | None = None,
) -> MarkdownMultiHopQAPipelineResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        {"source_path": str(path), "output_md_path": str(path), "status": "ok"}
        for path in markdown_paths
    ]

    chunks = MarkdownChunkOperator(chunk_words=chunk_words, overlap_words=overlap_words).run(rows)
    chunks_path = output_dir / "chunks.jsonl"
    write_jsonl(chunks_path, chunks)

    contexts = MultiHopContextBuilderOperator(min_context_sentences=min_context_sentences).run(chunks)
    contexts_path = output_dir / "multihop_contexts.jsonl"
    write_jsonl(contexts_path, contexts)

    generated = MultiHopQAGeneratorOperator(
        llm_client=llm_client,
        target_language=target_language,
        system_prompt=prompt_config.render("multihop", "") if prompt_config else None,
    ).run(contexts)
    generated_path = output_dir / "qa_multihop_generated.jsonl"
    write_jsonl(generated_path, generated)

    export_path = output_dir / "qa_multihop_export.jsonl"
    MultiHopAlpacaExportOperator(output_path=export_path).run(generated)

    return MarkdownMultiHopQAPipelineResult(
        chunks_path=chunks_path,
        contexts_path=contexts_path,
        generated_path=generated_path,
        export_path=export_path,
    )
