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
    error_detail: str | None = None

    def to_jsonl_line(self) -> str:
        return self.model_dump_json(exclude_none=False) + "\n"
