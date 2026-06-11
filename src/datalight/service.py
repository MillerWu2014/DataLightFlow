from __future__ import annotations

from pathlib import Path
from typing import Optional

from datalight.config import DatalightConfig, LLMSettings
from datalight.ingest.runner import IngestConfig, ingest_dir, ingest_url
from datalight.llm import OpenAICompatibleLLMClient, StaticLLMClient
from datalight.pipeline.placeholder import echo_manifest_lines
from datalight.pipeline.generation.agentic import run_depth_qa_pipeline, run_width_qa_pipeline
from datalight.pipeline.generation.expansion import run_qa_expansion_pipeline
from datalight.pipeline.generation.thinking import run_qa_thinking_pipeline
from datalight.pipeline.runner import (
    run_markdown_multihop_qa_pipeline,
    run_markdown_qa_pipeline,
)
from datalight.version import __version__


class DatalightService:
    """DataLight 流水线统一入口，各方法委托至对应模块级函数。"""

    def __init__(self, config: Optional[Path] = None):
        """绑定默认 `datalight.yaml` 路径，供未显式传 config 的调用回退使用。"""
        self.config = config

    def ingest_directory(self, **kwargs) -> Path:
        """本地目录摄入：原始文件 → MinerU 转 Markdown → 写入 ingest manifest"""
        kwargs["config"] = kwargs.get("config") or self.config
        return ingest_directory(**kwargs)

    def ingest_url_to_markdown(self, **kwargs) -> Path:
        """单 URL 摄入：下载资源 → MinerU 转 Markdown → 写入 ingest manifest"""
        kwargs["config"] = kwargs.get("config") or self.config
        return ingest_url_to_markdown(**kwargs)

    def pipeline_noop(self, **kwargs) -> Path:
        """占位流水线：manifest 逐行回显到 export，用于 I/O 接线自检（无 LLM）"""
        return pipeline_noop(**kwargs)

    def pipeline_markdown_qa(self, **kwargs):
        """单跳 QA 主链路：Markdown → 切块 → 生成（default/atomic/taxonomy）→ 评分过滤 → 可选扩写/think → Alpaca 导出"""
        kwargs["config"] = kwargs.get("config") or self.config
        return pipeline_markdown_qa(**kwargs)

    def pipeline_markdown_multihop_qa(self, **kwargs):
        """多跳 QA 链路：Markdown → 语义切块 → 滑动窗口上下文 → 多跳 QA 生成 → 导出"""
        kwargs["config"] = kwargs.get("config") or self.config
        return pipeline_markdown_multihop_qa(**kwargs)

    def pipeline_expand_qa(self, **kwargs):
        """QA 后处理扩写：已有 QA JSONL → LLM 扩写变体 → 输出 enriched QA JSONL"""
        kwargs["config"] = kwargs.get("config") or self.config
        return pipeline_expand_qa(**kwargs)

    def pipeline_add_think(self, **kwargs):
        """QA 后处理推理：已有 QA JSONL → 生成 think 字段并重写 answer → 输出带推理链的 JSONL"""
        kwargs["config"] = kwargs.get("config") or self.config
        return pipeline_add_think(**kwargs)

    def pipeline_depth_qa(self, **kwargs):
        """Agentic Depth 链路：单跳 QA JSONL → 多轮深挖验证 → 输出更深层的 QA JSONL"""
        kwargs["config"] = kwargs.get("config") or self.config
        return pipeline_depth_qa(**kwargs)

    def pipeline_width_qa(self, **kwargs):
        """Agentic Width 链路：单跳 QA JSONL → 横向扩展与合并验证 → 输出更广覆盖的 QA JSONL"""
        kwargs["config"] = kwargs.get("config") or self.config
        return pipeline_width_qa(**kwargs)

    def version(self) -> str:
        """返回 DataLight 包版本号"""
        return version()


def ingest_directory(
    *,
    input_dir: Path,
    output_dir: Optional[Path] = None,
    config: Optional[Path] = None,
    backend: str = "vlm-auto-engine",
    timeout: int = 3600,
    keep_intermediate: bool = False,
    fail_fast: bool = False,
) -> Path:
    """Ingest a local directory and convert documents to Markdown.

    Args:
        input_dir: Source directory containing files to ingest.
        output_dir: Output directory for converted markdown files.
            If not provided, falls back to `output.ingest_dir()` in config.
        config: Optional config file path (`datalight.yaml`).
        backend: MinerU backend name.
        timeout: Per-file timeout in seconds.
        keep_intermediate: Whether to keep intermediate MinerU artifacts.
        fail_fast: Stop immediately when a file fails if set to True.

    Returns:
        Path to the generated ingest manifest.

    Raises:
        ValueError: If `input_dir` is not an existing directory, or no output
            path can be resolved from args/config.
    """
    if not input_dir.exists() or not input_dir.is_dir():
        raise ValueError("input_dir must exist and be a directory")
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
    return ingest_dir(input_dir, resolved_output_dir, cfg)


def ingest_url_to_markdown(
    *,
    url: str,
    output_dir: Optional[Path] = None,
    config: Optional[Path] = None,
    backend: str = "vlm-auto-engine",
    timeout: int = 3600,
    keep_intermediate: bool = False,
) -> Path:
    """Download a single URL and convert it to Markdown.

    Args:
        url: Target URL for ingestion.
        output_dir: Output directory for converted markdown files.
            If not provided, falls back to `output.ingest_dir()` in config.
        config: Optional config file path (`datalight.yaml`).
        backend: MinerU backend name.
        timeout: Request/processing timeout in seconds.
        keep_intermediate: Whether to keep intermediate MinerU artifacts.

    Returns:
        Path to the generated ingest manifest.

    Raises:
        ValueError: If `url` is empty, or no output path can be resolved from
            args/config.
    """
    if not url.strip():
        raise ValueError("url must not be empty")
    app_cfg = _load_config(config)
    resolved_output_dir = _required_path(output_dir, app_cfg.output.ingest_dir(), "output_dir")
    cfg = IngestConfig(
        backend=backend,
        timeout_sec=timeout,
        keep_intermediate=keep_intermediate,
    )
    if app_cfg.mineru.executable:
        cfg.mineru_executable = app_cfg.mineru.executable
    return ingest_url(url, resolved_output_dir, cfg)


def pipeline_noop(*, manifest: Path, export_dir: Optional[Path] = None) -> Path:
    """Run the placeholder pipeline and echo manifest lines to export files.

    This is a lightweight sanity-check pipeline for verifying file I/O wiring
    without invoking QA/LLM stages.

    Args:
        manifest: Input manifest file path.
        export_dir: Optional export directory. Defaults to
            `<manifest.parent>/export`.

    Returns:
        Path to the generated export artifact.

    Raises:
        ValueError: If `manifest` is not an existing file.
    """
    if not manifest.exists() or not manifest.is_file():
        raise ValueError("manifest must exist and be a file")
    resolved_export_dir = export_dir or (manifest.parent / "export")
    return echo_manifest_lines(manifest, resolved_export_dir)


def pipeline_markdown_qa(
    *,
    markdown: list[Path],
    output_dir: Optional[Path] = None,
    config: Optional[Path] = None,
    responses_file: Optional[Path] = None,
    lmstudio: bool = False,
    llm_model: Optional[str] = None,
    llm_timeout: Optional[int] = None,
    chunk_words: int = 512,
    overlap_words: int = 0,
    question_num: int = 1,
    min_score: float = 3.0,
    language: str = "zh",
    expand_qa: bool = False,
    expand_mode: str = "detail",
    add_think: bool = False,
    generator: str = "default",
    atomic_max_per_task: int = 10,
):
    """Run the single-hop markdown QA pipeline.

    Pipeline stages: chunking -> QA generation -> scoring/filtering ->
    optional expansion -> optional think augmentation -> Alpaca export.

    `generator` options:
    - `default`: two-stage Text2QA meta-prompt generation (AutoPrompt -> Q:/A:)
    - `atomic`: AgenticRAG atomic task pipeline (high-quality verified QA;
      skips the four-dimension evaluator to avoid duplicate LLM calls)
    - `taxonomy`: taxonomy tag -> question -> answer

    LLM source options:
    1) `responses_file` for deterministic static responses.
    2) configured provider in `config`.
    3) `lmstudio=True` to force runtime LLM path (still reads config URL/model
       defaults when needed).

    Args:
        markdown: Markdown file paths to process.
        output_dir: Base output directory for generated artifacts.
            Actual files are written to ``output_dir / generator`` so runs with
            different generators do not overwrite each other.
            If not provided, falls back to ``output.qa_dir()`` in config.
        config: Optional config file path (`datalight.yaml`).
        responses_file: Optional static responses file (split by `---`).
        lmstudio: Whether to use online LLM mode instead of static responses.
        llm_model: Optional LLM model override.
        llm_timeout: Optional LLM timeout override in seconds.
        chunk_words: Max words per chunk.
        overlap_words: Overlap words between adjacent chunks.
        question_num: Max QA pairs to keep per chunk (applies to default, atomic,
            and taxonomy generators).
        min_score: Unified threshold for all QA quality score dimensions.
        language: Target language (e.g. `zh`, `en`).
        expand_qa: Whether to run expansion stage.
        expand_mode: Expansion mode (`detail` / other supported modes).
        add_think: Whether to run think augmentation stage.
        generator: QA generator mode (`default`, `atomic`, `taxonomy`).
        atomic_max_per_task: Max conclusion candidates per chunk for atomic mode.

    Returns:
        `MarkdownQAPipelineResult` containing paths for intermediate/final
        artifacts.

    Raises:
        ValueError: If input markdown list is empty, files are missing, output
            directory cannot be resolved, or LLM config is invalid.
    """
    if not markdown:
        raise ValueError("markdown must not be empty")
    _ensure_files(markdown, "markdown")
    app_cfg = _load_config(config)
    base_output_dir = _required_path(output_dir, app_cfg.output.qa_dir(), "output_dir")
    resolved_output_dir = base_output_dir / generator
    llm_client = _build_qa_llm_client(
        responses_file=responses_file,
        lmstudio=lmstudio,
        llm_model=llm_model,
        llm_timeout=llm_timeout,
        llm_config=app_cfg.llm,
    )
    return run_markdown_qa_pipeline(
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
        taxonomy=app_cfg.taxonomy_data(),
        generator=generator,
        atomic_max_per_task=atomic_max_per_task,
    )


def pipeline_markdown_multihop_qa(
    *,
    markdown: list[Path],
    output_dir: Optional[Path] = None,
    config: Optional[Path] = None,
    responses_file: Optional[Path] = None,
    lmstudio: bool = False,
    llm_model: Optional[str] = None,
    llm_timeout: Optional[int] = None,
    chunk_words: int = 800,
    overlap_words: int = 0,
    min_context_sentences: int = 3,
    num_q: int = 5,
    language: str = "zh",
):
    """Run the multi-hop markdown QA pipeline.

    Pipeline stages: semantic chunking -> info-pair context extraction (original
    DataFlow sliding window) -> multi-hop QA generation -> Alpaca export.

    Notes:
    - This function only runs multi-hop generation/export.
    - To add expansion/think after multi-hop generation, call
      `pipeline_expand_qa` and `pipeline_add_think` on `generated_path`.

    Args:
        markdown: Markdown file paths to process.
        output_dir: Output directory for all generated artifacts.
            If not provided, falls back to `output.multihop_dir()` in config.
        config: Optional config file path (`datalight.yaml`).
        responses_file: Optional static responses file (split by `---`).
        lmstudio: Whether to use online LLM mode instead of static responses.
        llm_model: Optional LLM model override.
        llm_timeout: Optional LLM timeout override in seconds.
        chunk_words: Approximate chunk size budget; mapped to
            ``max_chunk_chars = chunk_words * 4`` for semantic chunking.
        overlap_words: Ignored for multi-hop semantic chunking.
        min_context_sentences: Minimum sentence count required before extracting
            multi-hop info pairs from a chunk.
        num_q: Maximum multi-hop QA pairs to keep per source chunk.
        language: Target language (e.g. `zh`, `en`).

    Returns:
        `MarkdownMultiHopQAPipelineResult` containing paths for intermediate
        and final artifacts.

    Raises:
        ValueError: If input markdown list is empty, files are missing, output
            directory cannot be resolved, or LLM config is invalid.
    """
    if not markdown:
        raise ValueError("markdown must not be empty")
    _ensure_files(markdown, "markdown")
    app_cfg = _load_config(config)
    resolved_output_dir = _required_path(output_dir, app_cfg.output.multihop_dir(), "output_dir")
    llm_client = _build_qa_llm_client(
        responses_file=responses_file,
        lmstudio=lmstudio,
        llm_model=llm_model,
        llm_timeout=llm_timeout,
        llm_config=app_cfg.llm,
    )
    return run_markdown_multihop_qa_pipeline(
        markdown_paths=markdown,
        output_dir=resolved_output_dir,
        llm_client=llm_client,
        chunk_words=chunk_words,
        overlap_words=overlap_words,
        min_context_sentences=min_context_sentences,
        num_q=num_q,
        target_language=language,
    )


def pipeline_expand_qa(
    *,
    input_path: Path,
    output_path: Optional[Path] = None,
    config: Optional[Path] = None,
    responses_file: Optional[Path] = None,
    lmstudio: bool = False,
    llm_model: Optional[str] = None,
    llm_timeout: Optional[int] = None,
    mode: str = "detail",
    language: str = "zh",
):
    """Expand existing QA records into richer question/answer variants.

    Args:
        input_path: Source QA JSONL file path.
        output_path: Expanded QA JSONL output path.
            If not provided, falls back to `output.expansion_path()` in config.
        config: Optional config file path (`datalight.yaml`).
        responses_file: Optional static responses file (split by `---`).
        lmstudio: Whether to use online LLM mode instead of static responses.
        llm_model: Optional LLM model override.
        llm_timeout: Optional LLM timeout override in seconds.
        mode: Expansion mode (`detail`, `contextual`, `reasoning`, etc.).
        language: Target language (e.g. `zh`, `en`).

    Returns:
        `QAExpansionPipelineResult` with input/output paths.

    Raises:
        ValueError: If `input_path` is missing, output path cannot be resolved,
            or LLM config is invalid.
    """
    _ensure_file(input_path, "input_path")
    app_cfg = _load_config(config)
    resolved_output_path = _required_path(output_path, app_cfg.output.expansion_path(), "output")
    llm_client = _build_qa_llm_client(
        responses_file=responses_file,
        lmstudio=lmstudio,
        llm_model=llm_model,
        llm_timeout=llm_timeout,
        llm_config=app_cfg.llm,
    )
    return run_qa_expansion_pipeline(
        input_path=input_path,
        output_path=resolved_output_path,
        llm_client=llm_client,
        mode=mode,
        target_language=language,
        system_prompt=None,
    )


def pipeline_add_think(
    *,
    input_path: Path,
    output_path: Optional[Path] = None,
    config: Optional[Path] = None,
    responses_file: Optional[Path] = None,
    lmstudio: bool = False,
    llm_model: Optional[str] = None,
    llm_timeout: Optional[int] = None,
    language: str = "zh",
):
    """Add `think` fields and rebuild answers for existing QA records.

    Args:
        input_path: Source QA JSONL file path.
        output_path: Think-augmented QA JSONL output path.
            If not provided, falls back to `output.think_path()` in config.
        config: Optional config file path (`datalight.yaml`).
        responses_file: Optional static responses file (split by `---`).
        lmstudio: Whether to use online LLM mode instead of static responses.
        llm_model: Optional LLM model override.
        llm_timeout: Optional LLM timeout override in seconds.
        language: Target language (e.g. `zh`, `en`).

    Returns:
        `QAThinkingPipelineResult` with input/output paths.

    Raises:
        ValueError: If `input_path` is missing, output path cannot be resolved,
            or LLM config is invalid.
    """
    _ensure_file(input_path, "input_path")
    app_cfg = _load_config(config)
    resolved_output_path = _required_path(output_path, app_cfg.output.think_path(), "output")
    llm_client = _build_qa_llm_client(
        responses_file=responses_file,
        lmstudio=lmstudio,
        llm_model=llm_model,
        llm_timeout=llm_timeout,
        llm_config=app_cfg.llm,
    )
    return run_qa_thinking_pipeline(
        input_path=input_path,
        output_path=resolved_output_path,
        llm_client=llm_client,
        target_language=language,
        system_prompt=None,
    )


def pipeline_depth_qa(
    *,
    input_path: Path,
    output_path: Path,
    config: Optional[Path] = None,
    responses_file: Optional[Path] = None,
    lmstudio: bool = False,
    llm_model: Optional[str] = None,
    llm_timeout: Optional[int] = None,
    n_rounds: int = 2,
):
    """Run AgenticRAG depth QA generation on existing single-hop QA records."""
    _ensure_file(input_path, "input_path")
    app_cfg = _load_config(config)
    llm_client = _build_qa_llm_client(
        responses_file=responses_file,
        lmstudio=lmstudio,
        llm_model=llm_model,
        llm_timeout=llm_timeout,
        llm_config=app_cfg.llm,
    )
    return run_depth_qa_pipeline(
        input_path=input_path,
        output_path=output_path,
        llm_client=llm_client,
        n_rounds=n_rounds,
    )


def pipeline_width_qa(
    *,
    input_path: Path,
    output_path: Path,
    config: Optional[Path] = None,
    responses_file: Optional[Path] = None,
    lmstudio: bool = False,
    llm_model: Optional[str] = None,
    llm_timeout: Optional[int] = None,
):
    """Run AgenticRAG width QA generation on existing single-hop QA records."""
    _ensure_file(input_path, "input_path")
    app_cfg = _load_config(config)
    llm_client = _build_qa_llm_client(
        responses_file=responses_file,
        lmstudio=lmstudio,
        llm_model=llm_model,
        llm_timeout=llm_timeout,
        llm_config=app_cfg.llm,
    )
    return run_width_qa_pipeline(
        input_path=input_path,
        output_path=output_path,
        llm_client=llm_client,
    )


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
    raise ValueError(f"Provide {name} or set output.root in config")


def _build_qa_llm_client(
    *,
    responses_file: Path | None,
    lmstudio: bool,
    llm_model: str | None,
    llm_timeout: int | None,
    llm_config: LLMSettings,
):
    if responses_file is not None and lmstudio:
        raise ValueError("Use only one of responses_file or lmstudio")
    if responses_file is None and not lmstudio and not llm_config.is_configured():
        raise ValueError(
            "Provide responses_file, set lmstudio=True, or configure llm.provider in config",
        )
    if responses_file is not None:
        _ensure_file(responses_file, "responses_file")
        return StaticLLMClient(_load_static_responses(responses_file))
    _validate_llm_provider(llm_config.provider)
    if llm_config.base_url is None:
        raise ValueError("Set llm.base_url in config (for example: configs/datalight.yaml)")
    return OpenAICompatibleLLMClient(
        base_url=llm_config.base_url,
        model=llm_model or llm_config.model or "gemma-4-31b-it",
        timeout_sec=llm_timeout or llm_config.timeout_sec or 120,
        temperature=llm_config.temperature if llm_config.temperature is not None else 0.2,
    )


def _validate_llm_provider(provider: str | None) -> None:
    if provider is None:
        return
    if provider not in {"lmstudio", "openai-compatible"}:
        raise ValueError("llm.provider must be one of: lmstudio, openai-compatible")


def _ensure_file(path: Path, name: str) -> None:
    if not path.exists() or not path.is_file():
        raise ValueError(f"{name} must exist and be a file")


def _ensure_files(paths: list[Path], name: str) -> None:
    for path in paths:
        _ensure_file(path, name)


def version() -> str:
    return __version__
