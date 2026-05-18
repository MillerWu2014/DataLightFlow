# DataLight Ingest MVP + `remote/` Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use **superpowers:subagent-driven-development** (recommended) or **superpowers:executing-plans** to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Spec:** [docs/superpowers/specs/2026-04-26-datalight-lightweight-architecture.md](../specs/2026-04-26-datalight-lightweight-architecture.md) (v1.2)

**Goal:** Ship an installable `**datalight`** package with **ingest MVP** (local MinerU only, `ingest_manifest.jsonl`, directory mirror + PDF URL with host-based paths), a **pipeline noop/echo** placeholder, and move legacy `**dataflow/`** under `**remote/dataflow/`** so new code is isolated per spec.

**Architecture:** `src/datalight/` with `contracts` (Pydantic + error codes), `ingest` (URL layout helpers, `MineruLocalBackend` subprocess, orchestration), `pipeline` (read JSONL → write placeholder), `cli` (Typer, `datalight` console script). Root `**pyproject.toml`** publishes **only** `datalight`; `**remote/dataflow/`** is reference-only (not listed in `packages`).

**Tech Stack:** Python 3.10+, Typer, Pydantic v2, `httpx` or `urllib.request` for URL HEAD/GET (stdlib acceptable for MVP), `subprocess` for `mineru`, `pytest`, **optional** real `mineru` in CI/manual integration.

**Dependency note (YAGNI):** New `datalight` **does not** depend on `trafilatura` for ingest. HTML URL → `E_URL_HTML_NOT_SUPPORTED` in manifest.

---

## Target file map (new)


| Path                                       | Responsibility                                          |
| ------------------------------------------ | ------------------------------------------------------- |
| `src/datalight/__init__.py`                | Public version `__version__`                            |
| `src/datalight/contracts/errors.py`        | `ErrorCode` str literals / enum                         |
| `src/datalight/contracts/constants.py`     | `URL_FINGERPRINT_HEX_LEN = 16`                          |
| `src/datalight/contracts/ingest_record.py` | Pydantic `IngestRecordRow` (one JSONL line)             |
| `src/datalight/ingest/url_layout.py`       | `host_sanitized`, `fingerprint16`, `url_output_relpath` |
| `src/datalight/ingest/mineru_local.py`     | `resolve_output_md_path`, `run_mineru` subprocess       |
| `src/datalight/ingest/runner.py`           | `IngestConfig`, `ingest_dir`, `ingest_url`              |
| `src/datalight/pipeline/placeholder.py`    | `echo_manifest` → `export/.placeholder.jsonl`           |
| `src/datalight/cli.py`                     | Typer app, `ingest` / `pipeline`                        |
| `tests/`                                   | New tests for `datalight` (not legacy `dataflow`)       |


**Migration (modify existing repo layout):**


| Action                            | Result                                                                                                              |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `git mv dataflow remote/dataflow` | Legacy tree under `remote/`                                                                                         |
| `remote/README.md` (create)       | Explains non-installable reference; `PYTHONPATH=remote` to import `dataflow`                                        |
| `pyproject.toml` (replace/merge)  | `name = "datalight"`, `packages` = only `datalight` from `src`, script `datalight`                                  |
| `test/` (legacy)                  | Move to `remote/tests-legacy/` **or** add `conftest.py` skip unless `DATALIGHT_RUN_LEGACY=1` — **Task 7** picks one |


---

## Self-review (plan vs spec)


| Spec section                          | Task      |
| ------------------------------------- | --------- |
| JSONL manifest                        | Task 1, 4 |
| URL `urls/<host>/<fp16>/source.md`    | Task 1, 4 |
| Local MinerU only, §4.2               | Task 2    |
| No cloud API / no trafilature default | Task 2, 4 |
| `remote/` + DataLightFlow             | Task 7    |
| Pipeline placeholder                  | Task 5    |
| CLI `mineru` flags                    | Task 3    |


---

### Task 1: Contracts + URL layout (TDD)

**Files:**

- Create: `src/datalight/__init__.py`
- Create: `src/datalight/contracts/__init__.py`
- Create: `src/datalight/contracts/constants.py`
- Create: `src/datalight/contracts/errors.py`
- Create: `src/datalight/contracts/ingest_record.py`
- Create: `src/datalight/ingest/__init__.py`
- Create: `src/datalight/ingest/url_layout.py`
- Test: `tests/datalight/test_url_layout.py`
- **Step 1: Write the failing test**

`tests/datalight/test_url_layout.py`:

```python
from datalight.ingest.url_layout import build_url_storage_paths, URL_FINGERPRINT_HEX_LEN
import hashlib

def test_host_sanitized_port_replaces_colon():
    rel, host, fp = build_url_storage_paths("https://example.com:8443/a/b/c.pdf?x=1")
    assert host == "example.com:8443"  # raw netloc for manifest
    assert rel.parts[0] == "urls"
    assert rel.parts[1] == "example.com_8443"  # filesystem-safe
    assert len(rel.parts[2]) == URL_FINGERPRINT_HEX_LEN
    assert (rel / "source.md").as_posix().endswith("/source.md")

def test_fingerprint_is_prefix_of_sha256():
    u = "https://x.example.org/p.pdf"
    rel, host, fp = build_url_storage_paths(u)
    want = hashlib.sha256(u.encode("utf-8")).hexdigest()[:16]
    assert rel.parts[2] == want
    assert fp == want
```

- **Step 2: Run test (expect fail)**

```bash
cd /path/to/DataLightFlow
export PYTHONPATH=src
python -m pytest tests/datalight/test_url_layout.py -v
```

Expected: `ModuleNotFoundError: datalight` or import errors.

- **Step 3: Minimal `pyproject` slice so `datalight` is importable**

Add minimal `[project]` and `[tool.setuptools.packages.find] where = ["src"]` **or** set `PYTHONPATH=src` only until Task 7. Implement:

`src/datalight/contracts/constants.py`:

```python
URL_FINGERPRINT_HEX_LEN = 16
```

`src/datalight/ingest/url_layout.py`:

```python
from __future__ import annotations
import hashlib
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from datalight.contracts.constants import URL_FINGERPRINT_HEX_LEN

def sanitize_host_for_fs(netloc: str) -> str:
    s = netloc.lower()
    if ":" in s:
        host_part, port_part = s.rsplit(":", 1) if s.count(":") == 1 else (s, "")
        # IPv6 in brackets [::1] — handle minimally: replace all ":" except bracket case
        if s.startswith("["):
            return s.replace(":", "_")  # rough; add tests for IPv6 if needed
        return f"{host_part}_{port_part}" if port_part else host_part
    return s

def build_url_storage_paths(url: str) -> tuple[PurePosixPath, str, str]:
    """Returns (relative path under output_dir, url_host netloc, fingerprint hex)."""
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        raise ValueError("URL must be absolute with netloc")
    host_raw = p.netloc
    host_fs = sanitize_host_for_fs(host_raw)
    fp = hashlib.sha256(url.encode("utf-8")).hexdigest()[:URL_FINGERPRINT_HEX_LEN]
    rel = PurePosixPath("urls") / host_fs / fp
    return rel, host_raw, fp
```

- **Step 4: Run test (expect pass)**

```bash
PYTHONPATH=src python -m pytest tests/datalight/test_url_layout.py -v
```

- **Step 5: Commit**

```bash
git add src/datalight tests/datalight
git commit -m "feat(datalight): add URL layout helpers and constants"
```

**Note:** If IPv6 URL support is required later, add tests and fix `sanitize_host_for_fs` in a follow-up; spec allows punycode ASCII which `urlparse` provides.

---

### Task 2: `MineruLocalBackend` (subprocess + path resolve)

**Files:**

- Create: `src/datalight/ingest/mineru_local.py`
- Test: `tests/datalight/test_mineru_local_resolve.py` (no real `mineru`)
- Test fixture: `tests/datalight/fixtures/fake_mineru` (shell script, executable)
- **Step 1: Test resolve path (pure)**

`tests/datalight/test_mineru_local_resolve.py`:

```python
from pathlib import Path
from datalight.ingest.mineru_local import expected_mineru_markdown

def test_expected_path_matches_spec():
    intermediate = Path("/tmp/w")
    stem = "doc"
    backend = "vlm-x"
    md = expected_mineru_markdown(intermediate, stem, backend)
    assert md == intermediate / stem / backend / f"{stem}.md"
```

- **Step 2: Implement `expected_mineru_markdown`**

`src/datalight/ingest/mineru_local.py`:

```python
from __future__ import annotations
import os
import subprocess
import shutil
from dataclasses import dataclass
from pathlib import Path

@dataclass
class MineruResult:
    ok: bool
    returncode: int
    md_path: Path | None
    stderr_tail: str
    duration_ms: int

def expected_mineru_markdown(work_root: Path, stem: str, backend: str) -> Path:
    return work_root / stem / backend / f"{stem}.md"

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
        executable, "-p", str(source), "-o", str(work_root),
        "-b", backend, "--source", "local",
    ]
    t0 = __import__("time").perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    ms = int((__import__("time").perf_counter() - t0) * 1000)
    md = expected_mineru_markdown(work_root, stem, backend)
    ok = proc.returncode == 0 and md.is_file()
    tail = (proc.stderr or "")[-4000:]
    return MineruResult(ok=ok, returncode=proc.returncode, md_path=md if ok else None, stderr_tail=tail, duration_ms=ms)
```

In the **same commit**, add the **fake** `mineru` executable (see Step 3) that creates the expected `.md` so `ok` is true; add a test that runs `run_mineru_on_file` with `MINERU_EXECUTABLE` pointing to the fake script.

- **Step 3: Fake `mineru` script** (`tests/datalight/fixtures/fake_mineru`):

```bash
#!/usr/bin/env bash
# Parses -p IN -o OUT -b B — creates OUT/$(basename IN .ext)/B/$(basename IN .ext).md
set -e
# minimal argparse loop omitted in plan: implement in repo with while loop
```

Implement arg parsing in the real script; test sets `MINERU_EXECUTABLE=tests/.../fake_mineru`.

- **Step 4: `pytest` + commit**

```bash
git add src/datalight/ingest/mineru_local.py tests/datalight
git commit -m "feat(datalight): MinerU local backend subprocess and path resolve"
```

---

### Task 3: `IngestRecordRow` (Pydantic) + line JSONL I/O

**Files:**

- Create: `src/datalight/contracts/ingest_record.py`
- Test: `tests/datalight/test_ingest_record.py`
- **Step 1: Define model matching spec (minimum fields)**

`src/datalight/contracts/ingest_record.py`:

```python
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field

class IngestRecordRow(BaseModel, extra="allow"):
    source_path: str
    output_md_path: str
    status: Literal["ok", "failed", "skipped"]
    parser: str = "mineru_local"
    error_code: str | None = None
    sha256: str | None = None
    mineru_version: str | None = None
    mineru_backend: str | None = None
    source_kind: Literal["file", "url"] = "file"
    url_host: str | None = None
    url_fingerprint: str | None = None
    duration_ms: int | None = None
    stderr_tail: str | None = None
```

- **Step 2: Test round-trip JSONL**

```python
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
```

- **Step 3: Add `pydantic>=2` to new `pyproject` dependencies in Task 7 or add `requirements-datalight.txt` now** — YAGNI: add in Task 6 when `pyproject` is finalized.
- **Step 4: Commit** after pydantic is installable in dev env.

---

### Task 4: Ingest runner (directory + URL)

**Files:**

- Create: `src/datalight/ingest/runner.py`
- Test: `tests/datalight/test_ingest_dir.py` (uses fake MinerU + tiny PDF or empty file if fake accepts)

**Behavior:**

- `ingest_dir(input_dir, output_dir, cfg)`: walk `input_dir` for exts in `{.pdf, .png, .jpg, .jpeg, .webp, .gif}` (copy list from spec README); for each, compute `rel = relative path`, `stem.md` under `output_dir / rel` with same parent structure; `sha256` of source; call `run_mineru_on_file` then `copy` md to `output` path; append `IngestRecordRow`.
- Skip `.docx` with `status=skipped` and `error_code` or a dedicated `E_UNSUPPORTED_EXT` (define in `errors.py`).
- `ingest_url(url, output_dir, cfg)`: if HEAD/GET not `application/pdf` → one failed row `E_URL_HTML_NOT_SUPPORTED` (or if not pdf); if pdf, download to temp, run mineru, copy to `output_dir / build_url_storage_paths` / `source.md`.
- **Step 1: Integration test with fake MinerU + temp dirs** — one PDF path string.
- **Step 2: Write `ingest_dir` and `ingest_url`**; write `ingest_manifest.jsonl` to `output_dir/ingest_manifest.jsonl` at end.
- **Step 3: `pytest` + commit** `feat(datalight): ingest directory and URL flows`

---

### Task 5: Pipeline placeholder

**Files:**

- Create: `src/datalight/pipeline/__init__.py`
- Create: `src/datalight/pipeline/placeholder.py`
- Test: `tests/datalight/test_pipeline_placeholder.py`
- **Step 1: Implement `echo_placeholders(manifest: Path, export_dir: Path) -> None`**

Reads JSONL, writes `export_dir / ".placeholder.jsonl"` with each line + `"stage": "noop"`.

- **Step 2: Test** + **commit** `feat(datalight): pipeline noop echo JSONL`

---

### Task 6: CLI (Typer)

**Files:**

- Create: `src/datalight/cli.py`
- Test: `tests/datalight/test_cli.py` (click.testing / typer can use `typer.testing.CliRunner` if available)

**Commands:**

- `datalight ingest directory <in> <out> [--backend ...] [--timeout ...]`
- `datalight ingest url --url <u> <out> [...]`
- `datalight pipeline noop <manifest> [--export-dir <d>]`
- **Step 1: Typer app wiring** to `runner` and `echo_placeholders`.
- **Step 2: `CliRunner` smoke test** + **commit** `feat(datalight): Typer CLI for ingest and pipeline noop`

---

### Task 7: `remote/` migration + `pyproject` for `datalight` only

**Prerequisite:** Tasks 1–6 code exists under `src/datalight/`.

- **Step 1: Create `remote/README.md`**

```markdown
# Legacy DataFlow (reference)

This tree is the former `dataflow/` package, kept for **reference** only. It is **not** an install dependency of `datalight`.

To run legacy imports: `PYTHONPATH=remote` python -c "import dataflow"`.
```

- **Step 2: `git mv dataflow remote/dataflow`**

```bash
git mv dataflow remote/dataflow
```

- **Step 3: Replace root `pyproject.toml` `[project]`** so:
  - `name = "datalight"` (or keep dual publishing — spec says `datalight` is the new product; **YAGNI:** single name `datalight`)
  - `readme = { file = "README.md", content-type = "text/markdown" }` — ensure **root `README.md`** exists or points to a short DataLight-first description (merge a **DataLight** section with a **Legacy** pointer to `remote/README.md`)
  - `version` from `datalight.version` in `src/datalight/version.py` (e.g. `0.1.0`)
  - `dependencies` = `typer`, `pydantic>=2` (minimal set for ingest)
  - `[project.scripts]` `datalight = "datalight.cli:app"`
  - `[tool.setuptools.packages.find] where = ["src"]`
  - Remove `packages = ["dataflow"]` and **do not** include `remote`
- **Step 4: Legacy tests** — if `test/` imports `dataflow`, either:
  - `git mv test remote/test-legacy` and document run with `PYTHONPATH=remote` + `cd remote`, **or**
  - keep `test/` and add `pytest.ini` with `markers = legacy` and skip.

Pick **move to `remote/test-legacy/`** to keep root `tests/` = `datalight` only (clearest).

- **Step 5: `pip install -e ".[dev]"` and `datalight --help`**

```bash
pip install -e "."
datalight --help
python -m pytest tests/datalight -q
```

- **Step 6: Commit** `chore: move dataflow to remote/, publish datalight package`

---

### Task 8: README + CI stub

**Files:**

- Create or update: `README.datalight.md` **or** top `README.md` section “DataLight (datalight)”
- **Step 1: Document** MinerU install (link OpenDataLab), `datalight ingest` examples, `ingest_manifest.jsonl` path.
- **Step 2: `.github/workflows/datalight.yml` (optional)** — run `pytest tests/datalight` on 3.10/3.11, **no** `mineru` in CI (unit tests only) unless self-hosted runner available.
- **Step 3: Commit** `docs: add datalight README and CI for unit tests`

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-26-datalight-ingest-mvp-and-remote-migration.md`.

**Note:** The Cursor command `/execute-plan` is deprecated; use the **executing-plans** skill to run tasks in order with checkpoints, or **subagent-driven-development** for one task per subagent.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration. **REQUIRED SUB-SKILL:** `superpowers:subagent-driven-development`.
2. **Inline execution** — run tasks in the same session using **executing-plans** with batch checkpoints. **REQUIRED SUB-SKILL:** `superpowers:executing-plans`.

Which approach do you want to use for implementation?