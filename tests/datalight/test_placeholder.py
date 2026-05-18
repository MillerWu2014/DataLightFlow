import json
from pathlib import Path

from datalight.pipeline.placeholder import echo_manifest_lines
from datalight.contracts.ingest_record import IngestRecordRow

def test_echo_placeholder(tmp_path: Path) -> None:
    man = tmp_path / "ingest_manifest.jsonl"
    r = IngestRecordRow(
        source_path="x", output_md_path="y", status="ok", parser="mineru_local",
    )
    man.write_text(r.model_dump_json() + "\n", encoding="utf-8")
    out = echo_manifest_lines(man, tmp_path / "export")
    assert out.is_file()
    line = out.read_text(encoding="utf-8").strip()
    o = json.loads(line)
    assert o.get("stage") == "noop"
