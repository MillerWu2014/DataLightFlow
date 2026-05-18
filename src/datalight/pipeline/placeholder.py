from __future__ import annotations

import json
from pathlib import Path

def echo_manifest_lines(manifest: Path, export_dir: Path) -> Path:
    """Read `ingest_manifest.jsonl` lines, append `stage: noop` as JSON, write `export_dir/.placeholder.jsonl`."""
    export_dir.mkdir(parents=True, exist_ok=True)
    out = export_dir / ".placeholder.jsonl"
    with manifest.open(encoding="utf-8") as fin, out.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            obj: dict = json.loads(line)
            obj["stage"] = "noop"
            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return out
