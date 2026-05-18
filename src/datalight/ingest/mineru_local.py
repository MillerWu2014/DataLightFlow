from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

@dataclass
class MineruResult:
    ok: bool
    returncode: int
    md_path: Path | None
    stderr_tail: str
    duration_ms: int
    stdout_tail: str = ""

def expected_mineru_markdown(work_root: Path, stem: str, backend: str) -> Path:
    return work_root / stem / backend / f"{stem}.md"

def find_mineru_markdown(work_root: Path, stem: str, backend: str) -> Path | None:
    expected = expected_mineru_markdown(work_root, stem, backend)
    if expected.is_file():
        return expected

    stem_dir = work_root / stem
    if not stem_dir.is_dir():
        return None

    matches = sorted(stem_dir.glob(f"*/{stem}.md"))
    if len(matches) == 1:
        return matches[0]
    for candidate in matches:
        if candidate.parent.name == "auto":
            return candidate
    return None

def run_mineru_on_file(
    *,
    executable: str,
    source: Path,
    work_root: Path,
    backend: str,
    timeout_sec: int = 3600,
) -> MineruResult:
    work_root.mkdir(parents=True, exist_ok=True)
    stem = source.stem
    cmd = [
        executable,
        "-p",
        str(source),
        "-o",
        str(work_root),
        "-b",
        backend,
        "--source",
        "local",
    ]
    t0 = time.perf_counter()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    duration_ms = int((time.perf_counter() - t0) * 1000)
    md = find_mineru_markdown(work_root, stem, backend)
    ok = proc.returncode == 0 and md is not None
    stderr_tail = (proc.stderr or "")[-4000:]
    stdout_tail = (proc.stdout or "")[-4000:]
    return MineruResult(
        ok=ok,
        returncode=proc.returncode,
        md_path=md if ok else None,
        stderr_tail=stderr_tail,
        duration_ms=duration_ms,
        stdout_tail=stdout_tail,
    )

def copy_markdown_to_dest(md_src: Path, dest_md: Path) -> None:
    dest_md.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(md_src, dest_md)
