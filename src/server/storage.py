from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from server.schemas import PipelineParamsBody


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class JobRecord:
    job_id: str
    upload_id: str
    source_file_name: str
    pipeline: Literal["singlehop", "multihop"]
    generator: Literal["default", "atomic", "taxonomy"] | None
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    params: dict[str, Any]
    created_at: str
    stage: str | None = None
    session_id: str | None = None
    qa_count: int | None = None
    finished_at: str | None = None
    error_message: str | None = None
    result_paths: dict[str, str] = field(default_factory=dict)

    def to_summary(self) -> dict[str, Any]:
        params = PipelineParamsBody.model_validate(self.params)
        return {
            "jobId": self.job_id,
            "sessionId": self.session_id,
            "sourceFileName": self.source_file_name,
            "pipeline": self.pipeline,
            "generator": self.generator,
            "status": self.status,
            "stage": self.stage,
            "qaCount": self.qa_count,
            "createdAt": self.created_at,
            "finishedAt": self.finished_at,
            "errorMessage": self.error_message,
            "params": params.model_dump(by_alias=True),
        }


class DataStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.uploads_dir = data_dir / "uploads"
        self.jobs_dir = data_dir / "jobs"
        self.sessions_dir = data_dir / "sessions"
        self._lock = threading.RLock()
        for path in (self.uploads_dir, self.jobs_dir, self.sessions_dir):
            path.mkdir(parents=True, exist_ok=True)

    def save_upload(self, file_name: str, content: bytes) -> tuple[str, Path, int]:
        upload_id = str(uuid.uuid4())
        upload_dir = self.uploads_dir / upload_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / "doc.md"
        target.write_bytes(content)
        meta = {"fileName": file_name, "size": len(content), "createdAt": _utc_now()}
        (upload_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return upload_id, target, len(content)

    def upload_markdown_path(self, upload_id: str) -> Path:
        path = self.uploads_dir / upload_id / "doc.md"
        if not path.is_file():
            raise FileNotFoundError(f"upload not found: {upload_id}")
        return path

    def upload_file_name(self, upload_id: str) -> str:
        meta_path = self.uploads_dir / upload_id / "meta.json"
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return str(meta.get("fileName") or "document.md")
        return "document.md"

    def job_output_dir(self, job_id: str) -> Path:
        path = self.jobs_dir / job_id / "output"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def create_job(
        self,
        *,
        upload_id: str,
        source_file_name: str,
        pipeline: Literal["singlehop", "multihop"],
        generator: Literal["default", "atomic", "taxonomy"] | None,
        params: PipelineParamsBody,
    ) -> JobRecord:
        job_id = str(uuid.uuid4())
        record = JobRecord(
            job_id=job_id,
            upload_id=upload_id,
            source_file_name=source_file_name,
            pipeline=pipeline,
            generator=generator,
            status="queued",
            params=params.model_dump(by_alias=True),
            created_at=_utc_now(),
        )
        self._write_job(record)
        return record

    def get_job(self, job_id: str) -> JobRecord | None:
        path = self._job_meta_path(job_id)
        if not path.is_file():
            return None
        with self._lock:
            data = json.loads(path.read_text(encoding="utf-8"))
        return JobRecord(**data)

    def list_jobs(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[JobRecord]:
        jobs: list[JobRecord] = []
        for meta in sorted(self.jobs_dir.glob("*/meta.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            record = JobRecord(**json.loads(meta.read_text(encoding="utf-8")))
            if status and record.status != status:
                continue
            jobs.append(record)
        return jobs[offset : offset + limit]

    def update_job(self, job_id: str, **fields: Any) -> JobRecord:
        with self._lock:
            record = self.get_job(job_id)
            if record is None:
                raise KeyError(job_id)
            data = asdict(record)
            data.update(fields)
            updated = JobRecord(**data)
            self._write_job(updated)
            return updated

    def delete_job(self, job_id: str) -> bool:
        job_dir = self.jobs_dir / job_id
        if not job_dir.exists():
            return False
        import shutil

        shutil.rmtree(job_dir, ignore_errors=True)
        return True

    def save_session(self, session_id: str, payload: dict[str, Any]) -> str:
        path = self.sessions_dir / f"{session_id}.json"
        payload = {**payload, "updatedAt": _utc_now()}
        with self._lock:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload["updatedAt"]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        path = self.sessions_dir / f"{session_id}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def delete_session(self, session_id: str) -> bool:
        path = self.sessions_dir / f"{session_id}.json"
        if path.is_file():
            path.unlink()
            return True
        return False

    def _job_meta_path(self, job_id: str) -> Path:
        return self.jobs_dir / job_id / "meta.json"

    def _write_job(self, record: JobRecord) -> None:
        job_dir = self.jobs_dir / record.job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        self._job_meta_path(record.job_id).write_text(
            json.dumps(asdict(record), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
