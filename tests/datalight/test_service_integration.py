from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from datalight.service import DatalightService


MARKDOWN_PATH = Path(
    "/Users/miller/Workspace/BJBN/project/aviation-llm-finetuning/data/markdown/标准规范/飞机地面勤务/飞机地面勤务.md",
)
CONFIG_PATH = Path(
    "/Users/miller/Workspace/BJBN/project/aviation-llm-finetuning/thirdparty/DataLightFlow/configs/datalight.yaml",
)
OUTPUT_ROOT = PROJECT_ROOT / "outputs"


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _require_inputs() -> None:
    if not MARKDOWN_PATH.is_file():
        raise FileNotFoundError(f"Markdown file not found: {MARKDOWN_PATH}")
    if not CONFIG_PATH.is_file():
        raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")


def _print_file_stats(title: str, path: Path) -> None:
    rows = _read_jsonl(path)
    print(f"{title}: {path} (rows={len(rows)})")
    if rows:
        first = rows[0]
        print(f"  first_keys={sorted(first.keys())}")


def run_singlehop(service: DatalightService, base_dir: Path, *, generator: str) -> None:
    output_dir = base_dir / "singlehop" / f"{MARKDOWN_PATH.stem}"
    output_dir.mkdir(parents=True, exist_ok=True)
    result = service.pipeline_markdown_qa(
        markdown=[MARKDOWN_PATH],
        output_dir=output_dir,
        chunk_words=640,
        overlap_words=64,
        expand_qa=True,
        add_think=True,
        question_num=5,
        generator=generator,
        atomic_max_per_task=10,
    )
    print(f"\n[singlehop/{generator}] generated artifacts")
    print(f"  output_dir={output_dir / generator}")
    _print_file_stats("generated", result.generated_path)
    _print_file_stats("scored", result.scored_path)
    if result.expanded_path is not None:
        _print_file_stats("expanded", result.expanded_path)
    if result.think_path is not None:
        _print_file_stats("with_think", result.think_path)
    _print_file_stats("alpaca_export", result.export_path)


def run_multihop(service: DatalightService, base_dir: Path) -> None:
    output_dir = base_dir / "multihop" / f"{MARKDOWN_PATH.stem}"
    output_dir.mkdir(parents=True, exist_ok=True)
    result = service.pipeline_markdown_multihop_qa(
        markdown=[MARKDOWN_PATH],
        output_dir=output_dir,
        chunk_words=640,
        overlap_words=64,
    )
    expanded_path = output_dir / "qa_multihop_expanded.jsonl"
    expanded = service.pipeline_expand_qa(
        input_path=result.generated_path,
        output_path=expanded_path,
    )
    think_path = output_dir / "qa_multihop_with_think.jsonl"
    think = service.pipeline_add_think(
        input_path=expanded.output_path,
        output_path=think_path,
    )

    print("\n[multihop] generated artifacts")
    _print_file_stats("contexts", result.contexts_path)
    _print_file_stats("generated", result.generated_path)
    _print_file_stats("expanded", expanded.output_path)
    _print_file_stats("with_think", think.output_path)
    _print_file_stats("alpaca_export", result.export_path)


def main() -> None:
    _require_inputs()
    service = DatalightService(config=CONFIG_PATH)
    base_dir = OUTPUT_ROOT
    base_dir.mkdir(parents=True, exist_ok=True)

    print(f"markdown={MARKDOWN_PATH}")
    print(f"config={CONFIG_PATH}")
    print(f"output_root={base_dir}")
    print("params: chunk_words=640 overlap_words=128")
    # run_singlehop(service, base_dir, generator="taxonomy")
    run_multihop(service, base_dir)
    print("\nDone. Please manually review generated jsonl files.")


if __name__ == "__main__":
    main()
