import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

import datalight.cli as cli_module
from datalight.cli import app

def test_cli_version():
    runner = CliRunner()
    r = runner.invoke(app, ["version"])
    assert r.exit_code == 0
    assert len(r.output.strip()) > 0

def test_ingest_directory_smoke(tmp_path, monkeypatch):
    fake = Path(__file__).resolve().parent / "fixtures" / "fake_mineru"
    os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
    ind = tmp_path / "i"
    out = tmp_path / "o"
    ind.mkdir()
    (ind / "a.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setenv("MINERU_EXECUTABLE", str(fake))
    runner = CliRunner()
    r = runner.invoke(
        app,
        ["ingest", "directory", str(ind), str(out), "--backend", "bb", "--timeout", "10"],
    )
    assert r.exit_code == 0, r.output

def test_pipeline_markdown_qa_cli_with_static_responses(tmp_path):
    md = tmp_path / "guide.md"
    md.write_text("OpenClaw is an open-source AI agent system.", encoding="utf-8")
    responses = tmp_path / "responses.txt"
    responses.write_text(
        "Q: What is OpenClaw?\\nA: An open-source AI agent system.\\n---\\n"
        "**Grading**: 5\\n**Feedback**: clear\\n---\\n"
        "**Grading**: 5\\n**Feedback**: aligned\\n---\\n"
        "**Grading**: 5\\n**Feedback**: verifiable\\n---\\n"
        "**Grading**: 5\\n**Feedback**: useful\\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"

    runner = CliRunner()
    r = runner.invoke(
        app,
        [
            "pipeline",
            "markdown-qa",
            "--markdown",
            str(md),
            "--output-dir",
            str(out),
            "--responses-file",
            str(responses),
            "--chunk-words",
            "30",
            "--min-score",
            "4",
            "--language",
            "zh",
        ],
    )

    assert r.exit_code == 0, r.output
    assert (out / "qa_export.jsonl").is_file()

def test_pipeline_markdown_qa_requires_one_llm_source(tmp_path):
    md = tmp_path / "guide.md"
    md.write_text("OpenClaw is an AI agent system.", encoding="utf-8")

    runner = CliRunner()
    r = runner.invoke(
        app,
        [
            "pipeline",
            "markdown-qa",
            "--markdown",
            str(md),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert r.exit_code != 0
    assert "Provide either --responses-file for deterministic tests or --lmstudio" in r.output

def test_pipeline_markdown_multihop_qa_cli_with_static_responses(tmp_path):
    md = tmp_path / "guide.md"
    md.write_text(
        "OpenClaw is self-hosted. It keeps user data local. Local control improves privacy.",
        encoding="utf-8",
    )
    responses = tmp_path / "responses.txt"
    responses.write_text(
        '{"question":"Why is OpenClaw privacy-friendly?",'
        '"reasoning_steps":[{"step":"It is self-hosted and keeps data local"}],'
        '"answer":"Because it is self-hosted and keeps user data local.",'
        '"supporting_facts":["OpenClaw is self-hosted","It keeps user data local"],'
        '"type":"privacy"}',
        encoding="utf-8",
    )
    out = tmp_path / "out"

    runner = CliRunner()
    r = runner.invoke(
        app,
        [
            "pipeline",
            "markdown-multihop-qa",
            "--markdown",
            str(md),
            "--output-dir",
            str(out),
            "--responses-file",
            str(responses),
            "--chunk-words",
            "80",
            "--min-context-sentences",
            "3",
            "--language",
            "zh",
        ],
    )

    assert r.exit_code == 0, r.output
    assert (out / "qa_multihop_export.jsonl").is_file()

def test_pipeline_expand_qa_cli_with_static_responses(tmp_path):
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
    responses = tmp_path / "responses.txt"
    responses.write_text(
        json.dumps(
            {
                "expanded_question": "OpenClaw 是什么类型的系统？",
                "expanded_answer": "OpenClaw 是一个开源、自托管的 AI Agent 系统。",
                "expansion_type": "detail",
                "expansion_notes": "补充了系统类型。",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    r = runner.invoke(
        app,
        [
            "pipeline",
            "expand-qa",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--responses-file",
            str(responses),
            "--language",
            "zh",
        ],
    )

    assert r.exit_code == 0, r.output
    assert output_path.is_file()

def test_pipeline_add_think_cli_with_static_responses(tmp_path):
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
    responses = tmp_path / "responses.txt"
    responses.write_text(
        json.dumps(
            {
                "think": "先识别系统定义，再组织答案。",
                "answer": "OpenClaw 是一个开源、自托管的 AI Agent 系统。",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    r = runner.invoke(
        app,
        [
            "pipeline",
            "add-think",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--responses-file",
            str(responses),
            "--language",
            "zh",
        ],
    )

    assert r.exit_code == 0, r.output
    assert output_path.is_file()

def test_pipeline_markdown_qa_can_use_llm_from_config(tmp_path, monkeypatch):
    md = tmp_path / "guide.md"
    md.write_text("OpenClaw 是一个自托管系统。", encoding="utf-8")
    cfg = tmp_path / "datalight.yaml"
    cfg.write_text(
        f"""
output:
  root: {tmp_path / "out"}
llm:
  provider: lmstudio
  base_url: http://127.0.0.1:1234/v1
  model: config-model
  timeout_sec: 77
  temperature: 0.05
""",
        encoding="utf-8",
    )
    seen = {}

    def fake_run_markdown_qa_pipeline(**kwargs):
        seen["llm_client"] = kwargs["llm_client"]
        export_path = kwargs["output_dir"] / "qa_export.jsonl"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text("", encoding="utf-8")
        return SimpleNamespace(export_path=export_path, expanded_path=None, think_path=None)

    monkeypatch.setattr(cli_module, "run_markdown_qa_pipeline", fake_run_markdown_qa_pipeline)

    r = CliRunner().invoke(
        app,
        ["pipeline", "markdown-qa", "--config", str(cfg), "--markdown", str(md)],
    )

    assert r.exit_code == 0, r.output
    assert seen["llm_client"].model == "config-model"
    assert seen["llm_client"].timeout_sec == 77
    assert seen["llm_client"].temperature == 0.05

def test_pipeline_markdown_qa_cli_model_overrides_config_llm(tmp_path, monkeypatch):
    md = tmp_path / "guide.md"
    md.write_text("OpenClaw 是一个自托管系统。", encoding="utf-8")
    cfg = tmp_path / "datalight.yaml"
    cfg.write_text(
        f"""
output:
  root: {tmp_path / "out"}
llm:
  provider: lmstudio
  model: config-model
""",
        encoding="utf-8",
    )
    seen = {}

    def fake_run_markdown_qa_pipeline(**kwargs):
        seen["llm_client"] = kwargs["llm_client"]
        export_path = kwargs["output_dir"] / "qa_export.jsonl"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text("", encoding="utf-8")
        return SimpleNamespace(export_path=export_path, expanded_path=None, think_path=None)

    monkeypatch.setattr(cli_module, "run_markdown_qa_pipeline", fake_run_markdown_qa_pipeline)

    r = CliRunner().invoke(
        app,
        [
            "pipeline",
            "markdown-qa",
            "--config",
            str(cfg),
            "--markdown",
            str(md),
            "--llm-model",
            "cli-model",
        ],
    )

    assert r.exit_code == 0, r.output
    assert seen["llm_client"].model == "cli-model"
