from pathlib import Path
import tempfile

from datalight.contracts.ingest_record import IngestRecordRow

def test_jsonl_roundtrip():
    row = IngestRecordRow(
        source_path="/a/x.pdf", output_md_path="/out/x.md", status="ok"
    )
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "ingest_manifest.jsonl"
        p.write_text(row.model_dump_json() + "\n", encoding="utf-8")
        line = p.read_text(encoding="utf-8").strip()
        assert IngestRecordRow.model_validate_json(line).source_path == "/a/x.pdf"
