import os
import stat
import tempfile
from pathlib import Path

import pytest

from datalight.ingest.mineru_local import run_mineru_on_file

@pytest.fixture
def fake_mineru() -> str:
    root = Path(__file__).resolve().parent / "fixtures" / "fake_mineru"
    os.chmod(root, os.stat(root).st_mode | stat.S_IXUSR)
    return str(root)

def test_fake_mineru_produces_markdown(fake_mineru, tmp_path: Path) -> None:
    src = tmp_path / "source.pdf"
    src.write_bytes(b"%PDF-1.4\n")
    work = tmp_path / "work"
    res = run_mineru_on_file(
        executable=fake_mineru,
        source=src,
        work_root=work,
        backend="b1",
        timeout_sec=30,
    )
    assert res.ok, res.stderr_tail
    assert res.md_path is not None
    assert res.md_path.is_file()
    assert "fake" in res.md_path.read_text(encoding="utf-8").lower() or res.md_path.read_text()
