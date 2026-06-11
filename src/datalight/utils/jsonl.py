from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datalight.pipeline.core import Record

QA_CONTEXT_OMIT_KEYS = frozenset({"chunk_text", "context"})


def read_jsonl(path: Path) -> list[Record]:
    rows: list[Record] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            data: Any = json.loads(line)
            if isinstance(data, dict):
                rows.append(data)
    return rows


def write_jsonl(path: Path, rows: list[Record], *, omit_keys: frozenset[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            payload = row
            if omit_keys:
                payload = {key: value for key, value in row.items() if key not in omit_keys}
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
