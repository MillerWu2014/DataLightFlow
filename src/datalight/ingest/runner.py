from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from datalight.contracts.errors import ErrorCode
from datalight.contracts.ingest_record import IngestRecordRow
from datalight.ingest.mineru_local import copy_markdown_to_dest, run_mineru_on_file
from datalight.ingest.url_layout import build_url_storage_paths

INGEST_EXTENSIONS = frozenset(
    {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"},
)

def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()

def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _mineru_version(executable: str) -> str | None:
    for args in ((executable, "--version"), (executable, "-V")):
        try:
            proc = subprocess.run(
                list(args), capture_output=True, text=True, timeout=8,
            )
            out = (proc.stdout or proc.stderr or "").strip()
            if out:
                return out.splitlines()[0][:500]
        except (OSError, subprocess.SubprocessError):
            continue
    return None

def _resolve_mineru_executable() -> str:
    import os
    return os.environ.get("MINERU_EXECUTABLE", "mineru")

@dataclass
class IngestConfig:
    mineru_executable: str = field(default_factory=_resolve_mineru_executable)
    backend: str = "vlm-auto-engine"
    timeout_sec: int = 3600
    keep_intermediate: bool = False
    fail_fast: bool = False
    on_progress: Callable[[str], None] | None = None

def _write_manifest(output_dir: Path, rows: list[IngestRecordRow]) -> Path:
    path = output_dir / "ingest_manifest.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(r.to_jsonl_line())
    return path

def _ensure_mineru_exists(executable: str) -> bool:
    p = Path(executable)
    if p.is_file():
        return True
    return shutil.which(executable) is not None

def ingest_dir(
    input_dir: Path,
    output_dir: Path,
    cfg: IngestConfig,
) -> Path:
    if not _ensure_mineru_exists(cfg.mineru_executable):
        row = IngestRecordRow(
            source_path=str(input_dir),
            output_md_path="",
            status="failed",
            error_code=ErrorCode.E_MINERU_NOT_FOUND,
            error_detail="mineru not found; set MINERU_EXECUTABLE or install MinerU",
        )
        return _write_manifest(output_dir, [row])

    mver = _mineru_version(cfg.mineru_executable)
    base_work = output_dir / ".datalight" / "mineru_work"
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()
    rows: list[IngestRecordRow] = []
    job = 0

    for path in sorted(input_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(input_dir)
        ext = path.suffix.lower()
        if ext in (".docx", ".doc") or ext in {".ppt", ".pptx"}:
            rows.append(
                IngestRecordRow(
                    source_path=str(path),
                    output_md_path="",
                    status="skipped",
                    error_code=ErrorCode.E_UNSUPPORTED_EXT,
                    parser="mineru_local",
                ),
            )
            continue
        if ext not in INGEST_EXTENSIONS:
            continue

        job += 1
        out_md = (output_dir / rel).with_suffix(".md")
        stem = path.stem
        work_root = base_work / f"job_{job:05d}_{stem}"
        t0 = time.perf_counter()
        res = run_mineru_on_file(
            executable=cfg.mineru_executable,
            source=path,
            work_root=work_root,
            backend=cfg.backend,
            timeout_sec=cfg.timeout_sec,
        )
        duration_ms = int((time.perf_counter() - t0) * 1000) if not res.ok else res.duration_ms

        if not res.ok:
            rows.append(
                IngestRecordRow(
                    source_path=str(path),
                    output_md_path="",
                    status="failed",
                    error_code=ErrorCode.E_MINERU_FAILED
                    if res.returncode
                    else ErrorCode.E_MINERU_OUTPUT_MISSING,
                    sha256=_sha256_path(path),
                    mineru_version=mver,
                    mineru_backend=cfg.backend,
                    source_kind="file",
                    duration_ms=duration_ms,
                    stderr_tail=res.stderr_tail,
                ),
            )
            if not cfg.keep_intermediate and work_root.exists():
                shutil.rmtree(work_root, ignore_errors=True)
            if cfg.fail_fast:
                return _write_manifest(output_dir, rows)
            continue

        try:
            copy_markdown_to_dest(res.md_path, out_md)  # type: ignore[arg-type]
        except OSError as e:
            rows.append(
                IngestRecordRow(
                    source_path=str(path),
                    output_md_path="",
                    status="failed",
                    error_code=ErrorCode.E_MINERU_FAILED,
                    error_detail=str(e)[:2000],
                    sha256=_sha256_path(path),
                ),
            )
            continue
        if not cfg.keep_intermediate and work_root.exists():
            shutil.rmtree(work_root, ignore_errors=True)

        rows.append(
            IngestRecordRow(
                source_path=str(path),
                output_md_path=str(out_md),
                status="ok",
                sha256=_sha256_path(path),
                mineru_version=mver,
                mineru_backend=cfg.backend,
                source_kind="file",
                duration_ms=duration_ms,
            ),
        )

    return _write_manifest(output_dir, rows)

def _head_content_type(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "datalight/0.1"})
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
            return r.headers.get("Content-Type", "").split(";")[0].strip().lower() or None
    except (urllib.error.URLError, OSError, ValueError):
        return None

def _is_pdf_type(ct: str | None) -> bool:
    if not ct:
        return False
    return "application/pdf" in ct

def _sniff_is_pdf(data: bytes) -> bool:
    return len(data) >= 4 and data[:4] == b"%PDF"

def _fetch_url_bytes(url: str) -> tuple[bytes, str | None]:
    req = urllib.request.Request(url, headers={"User-Agent": "datalight/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310
        ct = r.headers.get("Content-Type", "").split(";")[0].strip().lower() or None
        return r.read(), ct

def ingest_url(
    url: str,
    output_dir: Path,
    cfg: IngestConfig,
) -> Path:
    if not _ensure_mineru_exists(cfg.mineru_executable):
        row = IngestRecordRow(
            source_path=url,
            output_md_path="",
            status="failed",
            error_code=ErrorCode.E_MINERU_NOT_FOUND,
            source_kind="url",
        )
        return _write_manifest(output_dir, [row])

    mver = _mineru_version(cfg.mineru_executable)
    out_dir = output_dir.resolve()
    rel, host_raw, fp = build_url_storage_paths(url)
    out_md = out_dir / rel / "source.md"

    ct_head = _head_content_type(url)
    if ct_head and "text/html" in ct_head and not _is_pdf_type(ct_head):
        row = IngestRecordRow(
            source_path=url,
            output_md_path="",
            status="failed",
            error_code=ErrorCode.E_URL_HTML_NOT_SUPPORTED,
            source_kind="url",
            url_host=host_raw,
            url_fingerprint=fp,
        )
        return _write_manifest(out_dir, [row])

    try:
        data, ct_get = _fetch_url_bytes(url)
    except (urllib.error.URLError, OSError):
        row = IngestRecordRow(
            source_path=url,
            output_md_path="",
            status="failed",
            error_code=ErrorCode.E_MINERU_FAILED,
            source_kind="url",
            url_host=host_raw,
            url_fingerprint=fp,
        )
        return _write_manifest(out_dir, [row])

    if not _is_pdf_type(ct_get) and not _is_pdf_type(ct_head) and not _sniff_is_pdf(data):
        row = IngestRecordRow(
            source_path=url,
            output_md_path="",
            status="failed",
            error_code=ErrorCode.E_URL_NOT_PDF,
            source_kind="url",
            url_host=host_raw,
            url_fingerprint=fp,
        )
        return _write_manifest(out_dir, [row])

    data_sha = _sha256_bytes(data)
    tdir = Path(tempfile.mkdtemp())
    src_pdf = tdir / "source.pdf"
    try:
        src_pdf.write_bytes(data)
    except OSError:
        shutil.rmtree(tdir, ignore_errors=True)
        row = IngestRecordRow(
            source_path=url,
            output_md_path="",
            status="failed",
            error_code=ErrorCode.E_MINERU_FAILED,
            source_kind="url",
            url_host=host_raw,
            url_fingerprint=fp,
        )
        return _write_manifest(out_dir, [row])

    base_work = out_dir / ".datalight" / "mineru_work" / f"url_{fp}"
    try:
        res = run_mineru_on_file(
            executable=cfg.mineru_executable,
            source=src_pdf,
            work_root=base_work,
            backend=cfg.backend,
            timeout_sec=cfg.timeout_sec,
        )
    finally:
        shutil.rmtree(tdir, ignore_errors=True)

    if not res.ok:
        r = IngestRecordRow(
            source_path=url,
            output_md_path="",
            status="failed",
            error_code=ErrorCode.E_MINERU_OUTPUT_MISSING
            if res.returncode == 0
            else ErrorCode.E_MINERU_FAILED,
            sha256=data_sha,
            mineru_version=mver,
            mineru_backend=cfg.backend,
            source_kind="url",
            url_host=host_raw,
            url_fingerprint=fp,
            duration_ms=res.duration_ms,
            stderr_tail=res.stderr_tail,
        )
        if not cfg.keep_intermediate and base_work.exists():
            shutil.rmtree(base_work, ignore_errors=True)
        return _write_manifest(out_dir, [r])

    try:
        copy_markdown_to_dest(res.md_path, out_md)  # type: ignore[arg-type]
    except OSError as e:
        r = IngestRecordRow(
            source_path=url,
            output_md_path="",
            status="failed",
            error_code=ErrorCode.E_MINERU_FAILED,
            error_detail=str(e)[:2000],
            sha256=data_sha,
            source_kind="url",
            url_host=host_raw,
            url_fingerprint=fp,
        )
        if not cfg.keep_intermediate and base_work.exists():
            shutil.rmtree(base_work, ignore_errors=True)
        return _write_manifest(out_dir, [r])

    if not cfg.keep_intermediate and base_work.exists():
        shutil.rmtree(base_work, ignore_errors=True)

    ok = IngestRecordRow(
        source_path=url,
        output_md_path=str(out_md),
        status="ok",
        sha256=data_sha,
        mineru_version=mver,
        mineru_backend=cfg.backend,
        source_kind="url",
        url_host=host_raw,
        url_fingerprint=fp,
        duration_ms=res.duration_ms,
    )
    return _write_manifest(out_dir, [ok])
