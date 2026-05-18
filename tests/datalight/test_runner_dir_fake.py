import os
import stat
from pathlib import Path

import pytest

from datalight.ingest.runner import IngestConfig, ingest_dir

@pytest.fixture
def fake_mineru() -> str:
    root = Path(__file__).resolve().parent / "fixtures" / "fake_mineru"
    os.chmod(root, os.stat(root).st_mode | stat.S_IXUSR)
    return str(root)

def test_ingest_dir_with_fake_mineru(fake_mineru, tmp_path: Path) -> None:
    ind = tmp_path / "in"
    out = tmp_path / "out"
    ind.mkdir()
    (ind / "a.pdf").write_bytes(b"%PDF-1.4\n")
    cfg = IngestConfig(mineru_executable=fake_mineru, backend="t-b")
    mpath = ingest_dir(ind, out, cfg)
    assert mpath.is_file()
    assert (out / "a.md").is_file()
    text = mpath.read_text(encoding="utf-8")
    assert "ok" in text or "a.pdf" in text
