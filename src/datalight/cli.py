from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from datalight.config import DatalightConfig, LLMSettings
from datalight.ingest.runner import IngestConfig, ingest_dir, ingest_url
from datalight.pipeline.placeholder import echo_manifest_lines
from datalight.pipeline.qa.expansion import run_qa_expansion_pipeline
from datalight.pipeline.qa.llm import OpenAICompatibleLLMClient, StaticLLMClient
from datalight.pipeline.qa.runner import (
    run_markdown_multihop_qa_pipeline,
    run_markdown_qa_pipeline,
)
from datalight.pipeline.qa.thinking import run_qa_thinking_pipeline
from datalight.version import __version__

app = typer.Typer(help="DataLight — lightweight ingest (local MinerU) and pipeline placeholder.")
ingest_app = typer.Typer(help="Ingest documents to Markdown + ingest_manifest.jsonl")
app.add_typer(ingest_app, name="ingest")
pipeline_app = typer.Typer(help="Pipeline (noop placeholder in 0.1.x)")
app.add_typer(pipeline_app, name="pipeline")


@ingest_app.command("directory")
def ingest_directory(
        input_dir: Path = typer.Argument(..., exists=True, file_okay=False, help="Input directory of PDFs/images"),
        output_dir: Optional[Path] = typer.Argument(None, file_okay=False, help="Output directory root"),
        config: Optional[Path] = typer.Option(None, "--config", exists=True, dir_okay=False,
                                              help="DataLight config YAML"),
        backend: str = typer.Option("vlm-auto-engine", "--backend", "-b", help="MinerU -b backend"),
        timeout: int = typer.Option(3600, "--timeout", help="Per-file mineru timeout (seconds)"),
        keep_intermediate: bool = typer.Option(
            False, "--keep-intermediate", help="Keep .datalight/mineru_work after success",
        ),
        fail_fast: bool = typer.Option(False, "--fail-fast", help="Stop on first file failure"),
) -> None:
    """Mirror directory structure: PDFs/images -> .md under output_dir, write ingest_manifest.jsonl."""
    app_cfg = _load_config(config)
    resolved_output_dir = _required_path(output_dir, app_cfg.output.ingest_dir(), "output_dir")
    cfg = IngestConfig(
        backend=backend,
        timeout_sec=timeout,
        keep_intermediate=keep_intermediate,
        fail_fast=fail_fast,
    )
    if app_cfg.mineru.executable:
        cfg.mineru_executable = app_cfg.mineru.executable
    p = ingest_dir(input_dir, resolved_output_dir, cfg)
    typer.echo(f"Wrote manifest: {p}")


@ingest_app.command("url")
def ingest_url_cmd(
        output_dir: Optional[Path] = typer.Argument(None, file_okay=False, help="Output directory root"),
        url: str = typer.Option(..., "--url", help="Direct PDF URL (application/pdf)"),
        config: Optional[Path] = typer.Option(None, "--config", exists=True, dir_okay=False,
                                              help="DataLight config YAML"),
        backend: str = typer.Option("vlm-auto-engine", "--backend", "-b"),
        timeout: int = typer.Option(3600, "--timeout"),
        keep_intermediate: bool = typer.Option(False, "--keep-intermediate"),
) -> None:
    """Download PDF from URL and run local MinerU; output under urls/<host>/<fp16>/source.md."""
    app_cfg = _load_config(config)
    resolved_output_dir = _required_path(output_dir, app_cfg.output.ingest_dir(), "output_dir")
    cfg = IngestConfig(
        backend=backend,
        timeout_sec=timeout,
        keep_intermediate=keep_intermediate,
    )
    if app_cfg.mineru.executable:
        cfg.mineru_executable = app_cfg.mineru.executable
    p = ingest_url(url, resolved_output_dir, cfg)
    typer.echo(f"Wrote manifest: {p}")


@pipeline_app.command("noop")
def pipeline_noop(
        manifest: Path = typer.Argument(..., exists=True, help="ingest_manifest.jsonl path"),
        export_dir: Path = typer.Option(
            None,
            "--export-dir",
            help="Default: <parent of manifest>/export",
        ),
) -> None:
    """Pass-through each manifest line and add stage=noop to .placeholder.jsonl."""
    ex = export_dir
    if ex is None:
        ex = manifest.parent / "export"
    out = echo_manifest_lines(manifest, ex)
    typer.echo(f"Wrote: {out}")


@pipeline_app.command("info")
def pipeline_info() -> None:
    typer.echo("DataLight pipeline: full SFT/RAG stages are planned; use `noop` for 0.1.x.")


@pipeline_app.command("markdown-qa")
def pipeline_markdown_qa(
        markdown: list[Path] = typer.Option(
            ...,
            "--markdown",
            exists=True,
            dir_okay=False,
            help="Markdown file. Repeat for multiple files.",
        ),
        output_dir: Optional[Path] = typer.Option(None, "--output-dir", file_okay=False),
        config: Optional[Path] = typer.Option(None, "--config", exists=True, dir_okay=False,
                                              help="DataLight config YAML"),
        responses_file: Path = typer.Option(
            None,
            "--responses-file",
            dir_okay=False,
            help="Static test responses separated by a line containing ---.",
        ),
        lmstudio: bool = typer.Option(
            False,
            "--lmstudio",
            help="Use local LM Studio OpenAI-compatible server.",
        ),
        llm_base_url: Optional[str] = typer.Option(
            None,
            "--llm-base-url",
            help="OpenAI-compatible base URL. LM Studio default: http://127.0.0.1:1234/v1",
        ),
        llm_model: Optional[str] = typer.Option(
            None,
            "--llm-model",
            help="OpenAI-compatible model name. LM Studio target: gemma-4-31b-it",
        ),
        llm_timeout: Optional[int] = typer.Option(None, "--llm-timeout", help="LLM request timeout seconds"),
        chunk_words: int = typer.Option(512, "--chunk-words"),
        overlap_words: int = typer.Option(0, "--overlap-words"),
        question_num: int = typer.Option(1, "--question-num"),
        min_score: float = typer.Option(3.0, "--min-score"),
        language: str = typer.Option("zh", "--language", help="QA language: zh, en, or auto"),
        expand_qa: bool = typer.Option(False, "--expand-qa", help="Expand filtered QA pairs before export"),
        expand_mode: str = typer.Option("detail", "--expand-mode",
                                        help="Expansion mode: detail, contextual, reasoning"),
        add_think: bool = typer.Option(False, "--add-think", help="Add LLM-supplied think field before export"),
) -> None:
    """Run lightweight Markdown -> single-hop QA pipeline."""
    app_cfg = _load_config(config)
    resolved_output_dir = _required_path(output_dir, app_cfg.output.qa_dir(), "output_dir")
    llm_client = _build_qa_llm_client(
        responses_file=responses_file,
        lmstudio=lmstudio,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        llm_timeout=llm_timeout,
        llm_config=app_cfg.llm,
    )
    result = run_markdown_qa_pipeline(
        markdown_paths=markdown,
        output_dir=resolved_output_dir,
        llm_client=llm_client,
        chunk_words=chunk_words,
        overlap_words=overlap_words,
        question_num=question_num,
        min_question_quality=min_score,
        min_answer_alignment=min_score,
        min_answer_verifiability=min_score,
        min_downstream_value=min_score,
        target_language=language,
        expand_qa=expand_qa,
        expand_mode=expand_mode,
        add_think=add_think,
        prompt_config=app_cfg.prompt_config(),
    )
    typer.echo(f"Wrote export: {result.export_path}")
    if result.expanded_path is not None:
        typer.echo(f"Wrote expanded QA: {result.expanded_path}")
    if result.think_path is not None:
        typer.echo(f"Wrote QA with think: {result.think_path}")


@pipeline_app.command("markdown-multihop-qa")
def pipeline_markdown_multihop_qa(
        markdown: list[Path] = typer.Option(
            ...,
            "--markdown",
            exists=True,
            dir_okay=False,
            help="Markdown file. Repeat for multiple files.",
        ),
        output_dir: Optional[Path] = typer.Option(None, "--output-dir", file_okay=False),
        config: Optional[Path] = typer.Option(None, "--config", exists=True, dir_okay=False,
                                              help="DataLight config YAML"),
        responses_file: Path = typer.Option(
            None,
            "--responses-file",
            dir_okay=False,
            help="Static test responses separated by a line containing ---.",
        ),
        lmstudio: bool = typer.Option(
            False,
            "--lmstudio",
            help="Use local LM Studio OpenAI-compatible server.",
        ),
        llm_base_url: Optional[str] = typer.Option(None, "--llm-base-url"),
        llm_model: Optional[str] = typer.Option(None, "--llm-model"),
        llm_timeout: Optional[int] = typer.Option(None, "--llm-timeout"),
        chunk_words: int = typer.Option(800, "--chunk-words"),
        overlap_words: int = typer.Option(0, "--overlap-words"),
        min_context_sentences: int = typer.Option(3, "--min-context-sentences"),
        language: str = typer.Option("zh", "--language", help="QA language: zh, en, or auto"),
) -> None:
    """Run lightweight Markdown -> multi-hop QA pipeline."""
    app_cfg = _load_config(config)
    resolved_output_dir = _required_path(output_dir, app_cfg.output.multihop_dir(), "output_dir")
    llm_client = _build_qa_llm_client(
        responses_file=responses_file,
        lmstudio=lmstudio,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        llm_timeout=llm_timeout,
        llm_config=app_cfg.llm,
    )
    result = run_markdown_multihop_qa_pipeline(
        markdown_paths=markdown,
        output_dir=resolved_output_dir,
        llm_client=llm_client,
        chunk_words=chunk_words,
        overlap_words=overlap_words,
        min_context_sentences=min_context_sentences,
        target_language=language,
        prompt_config=app_cfg.prompt_config(),
    )
    typer.echo(f"Wrote export: {result.export_path}")


@pipeline_app.command("expand-qa")
def pipeline_expand_qa(
        input_path: Path = typer.Option(..., "--input", exists=True, dir_okay=False, help="Input QA JSONL"),
        output_path: Optional[Path] = typer.Option(None, "--output", dir_okay=False, help="Output expanded QA JSONL"),
        config: Optional[Path] = typer.Option(None, "--config", exists=True, dir_okay=False,
                                              help="DataLight config YAML"),
        responses_file: Path = typer.Option(
            None,
            "--responses-file",
            dir_okay=False,
            help="Static test responses separated by a line containing ---.",
        ),
        lmstudio: bool = typer.Option(False, "--lmstudio", help="Use local LM Studio OpenAI-compatible server."),
        llm_base_url: Optional[str] = typer.Option(None, "--llm-base-url"),
        llm_model: Optional[str] = typer.Option(None, "--llm-model"),
        llm_timeout: Optional[int] = typer.Option(None, "--llm-timeout"),
        mode: str = typer.Option("detail", "--mode", help="Expansion mode: detail, contextual, reasoning"),
        language: str = typer.Option("zh", "--language", help="QA language: zh, en, or auto"),
) -> None:
    """Expand existing QA JSONL without running the Markdown generation pipeline."""
    app_cfg = _load_config(config)
    resolved_output_path = _required_path(output_path, app_cfg.output.expansion_path(), "output")
    llm_client = _build_qa_llm_client(
        responses_file=responses_file,
        lmstudio=lmstudio,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        llm_timeout=llm_timeout,
        llm_config=app_cfg.llm,
    )
    result = run_qa_expansion_pipeline(
        input_path=input_path,
        output_path=resolved_output_path,
        llm_client=llm_client,
        mode=mode,
        target_language=language,
        system_prompt=app_cfg.prompt_config().render("expansion", ""),
    )
    typer.echo(f"Wrote expanded QA: {result.output_path}")


@pipeline_app.command("add-think")
def pipeline_add_think(
        input_path: Path = typer.Option(..., "--input", exists=True, dir_okay=False, help="Input QA JSONL"),
        output_path: Optional[Path] = typer.Option(None, "--output", dir_okay=False, help="Output QA JSONL with think"),
        config: Optional[Path] = typer.Option(None, "--config", exists=True, dir_okay=False,
                                              help="DataLight config YAML"),
        responses_file: Path = typer.Option(
            None,
            "--responses-file",
            dir_okay=False,
            help="Static test responses separated by a line containing ---.",
        ),
        lmstudio: bool = typer.Option(False, "--lmstudio", help="Use local LM Studio OpenAI-compatible server."),
        llm_base_url: Optional[str] = typer.Option(None, "--llm-base-url"),
        llm_model: Optional[str] = typer.Option(None, "--llm-model"),
        llm_timeout: Optional[int] = typer.Option(None, "--llm-timeout"),
        language: str = typer.Option("zh", "--language", help="QA language: zh, en, or auto"),
) -> None:
    """Add an LLM-supplied think field and rebuild answers for existing QA JSONL."""
    app_cfg = _load_config(config)
    resolved_output_path = _required_path(output_path, app_cfg.output.think_path(), "output")
    llm_client = _build_qa_llm_client(
        responses_file=responses_file,
        lmstudio=lmstudio,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        llm_timeout=llm_timeout,
        llm_config=app_cfg.llm,
    )
    result = run_qa_thinking_pipeline(
        input_path=input_path,
        output_path=resolved_output_path,
        llm_client=llm_client,
        target_language=language,
        system_prompt=app_cfg.prompt_config().render("thinking", ""),
    )
    typer.echo(f"Wrote QA with think: {result.output_path}")


def _load_static_responses(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [part.strip() for part in text.split("\n---\n") if part.strip()]


def _load_config(path: Path | None) -> DatalightConfig:
    if path is None:
        return DatalightConfig()
    return DatalightConfig.from_file(path)


def _required_path(value: Path | None, fallback: Path | None, name: str) -> Path:
    if value is not None:
        return value
    if fallback is not None:
        return fallback
    raise typer.BadParameter(f"Provide --{name.replace('_', '-')} or set output.root in --config")


def _build_qa_llm_client(
        *,
        responses_file: Path | None,
        lmstudio: bool,
        llm_base_url: str | None,
        llm_model: str | None,
        llm_timeout: int | None,
        llm_config: LLMSettings,
):
    if responses_file is not None and lmstudio:
        raise typer.BadParameter("Use only one of --responses-file or --lmstudio")
    if responses_file is None and not lmstudio and not llm_config.is_configured():
        raise typer.BadParameter(
            "Provide --responses-file, --lmstudio, or llm.provider in --config",
        )
    if responses_file is not None:
        return StaticLLMClient(_load_static_responses(responses_file))
    _validate_llm_provider(llm_config.provider)
    return OpenAICompatibleLLMClient(
        base_url=llm_base_url or llm_config.base_url or "http://127.0.0.1:1234/v1",
        model=llm_model or llm_config.model or "gemma-4-31b-it",
        timeout_sec=llm_timeout or llm_config.timeout_sec or 120,
        temperature=llm_config.temperature if llm_config.temperature is not None else 0.2,
    )


def _validate_llm_provider(provider: str | None) -> None:
    if provider is None:
        return
    if provider not in {"lmstudio", "openai-compatible"}:
        raise typer.BadParameter("llm.provider must be one of: lmstudio, openai-compatible")


def _version() -> None:
    typer.echo(__version__)


@app.command("version")
def version() -> None:
    _version()


def run() -> None:
    app()


if __name__ == "__main__":
    app()
