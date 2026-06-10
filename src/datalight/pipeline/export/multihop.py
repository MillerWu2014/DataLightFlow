from __future__ import annotations

import json
from pathlib import Path

from datalight.pipeline.core import Operator, Record

MULTIHOP_INSTRUCTION = "Answer the multi-hop question using the provided supporting facts."


class MultiHopAlpacaExportOperator(Operator):
    def __init__(self, output_path: Path, instruction: str = MULTIHOP_INSTRUCTION):
        self.output_path = output_path
        self.instruction = instruction

    def run(self, rows: list[Record]) -> list[Record]:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("w", encoding="utf-8") as f:
            for row in rows:
                item = {
                    "instruction": self.instruction,
                    "input": row["question"],
                    "output": row["answer"],
                    "source_md": row["source_md"],
                    "chunk_index": row["chunk_index"],
                    "metadata": {
                        "reasoning_steps": row.get("reasoning_steps", []),
                        "supporting_facts": row.get("supporting_facts", []),
                        "type": row.get("qa_type", ""),
                    },
                }
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return rows
