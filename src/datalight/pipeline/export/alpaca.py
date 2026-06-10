from __future__ import annotations

import json
from pathlib import Path

from tqdm import tqdm

from datalight.pipeline.core import Operator, Record

DEFAULT_INSTRUCTION = "Please answer the following question based on the provided information."


class AlpacaExportOperator(Operator):
    def __init__(self, output_path: Path, instruction: str = DEFAULT_INSTRUCTION):
        self.output_path = output_path
        self.instruction = instruction

    def run(self, rows: list[Record]) -> list[Record]:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("w", encoding="utf-8") as f:
            for row in tqdm(rows, desc="Exporting QA pairs"):
                item = {
                    "instruction": self.instruction,
                    "input": row.get("expanded_question") or row["question"],
                    "output": row.get("expanded_answer") or row["answer"],
                    "source_md": row["source_md"],
                    "chunk_index": row["chunk_index"],
                }
                if "think" in row:
                    item["think"] = row.get("think", "")
                for key in ("level1_name", "level2_name", "task_type", "reasoning_style"):
                    if key in row:
                        item[key] = row[key]
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return rows
