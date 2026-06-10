from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datalight.pipeline.core import Record


def read_jsonl(path: Path) -> list[Record]:
    rows: list[Record] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            data: Any = json.loads(line)
            if isinstance(data, dict):
                rows.append(data)
    return rows


def write_jsonl(path: Path, rows: list[Record]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
