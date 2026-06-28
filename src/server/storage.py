from __future__ import annotations

import json
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from server.db.connection import init_database, transaction
from server.db.qa_mapping import qa_item_row_values, record_to_jsonl_row, workspace_item_from_row
from server.schemas import PipelineParamsBody
from server.util import utc_now


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


def _utc_now() -> str:
    return utc_now()


class DataStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.uploads_dir = data_dir / "uploads"
        self.jobs_dir = data_dir / "jobs"
        self.sessions_dir = data_dir / "sessions"
        self.db_path = data_dir / "datalight.db"
        self._lock = threading.RLock()
        for path in (self.uploads_dir, self.jobs_dir, self.sessions_dir):
            path.mkdir(parents=True, exist_ok=True)
        self._conn = init_database(self.db_path, data_dir)

    def save_upload(self, file_name: str, content: bytes) -> tuple[str, Path, int]:
        upload_id = str(uuid.uuid4())
        upload_dir = self.uploads_dir / upload_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / "doc.md"
        target.write_bytes(content)
        storage_path = f"uploads/{upload_id}/doc.md"
        now = _utc_now()
        with self._lock, transaction(self._conn):
            self._conn.execute(
                """
                INSERT INTO uploads(id, file_name, storage_path, size_bytes, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (upload_id, file_name, storage_path, len(content), now),
            )
        return upload_id, target, len(content)

    def upload_markdown_path(self, upload_id: str) -> Path:
        path = self.uploads_dir / upload_id / "doc.md"
        if not path.is_file():
            raise FileNotFoundError(f"upload not found: {upload_id}")
        return path

    def upload_file_name(self, upload_id: str) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT file_name FROM uploads WHERE id = ?",
                (upload_id,),
            ).fetchone()
        if row is None:
            return "document.md"
        return str(row["file_name"])

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
        idempotency_key: str | None = None,
    ) -> JobRecord:
        if idempotency_key:
            with self._lock:
                existing = self._conn.execute(
                    "SELECT id FROM jobs WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
            if existing:
                job = self.get_job(existing["id"])
                if job is not None:
                    return job

        job_id = str(uuid.uuid4())
        now = _utc_now()
        record = JobRecord(
            job_id=job_id,
            upload_id=upload_id,
            source_file_name=source_file_name,
            pipeline=pipeline,
            generator=generator,
            status="queued",
            params=params.model_dump(by_alias=True),
            created_at=now,
        )
        with self._lock, transaction(self._conn):
            self._conn.execute(
                """
                INSERT INTO jobs(
                    id, upload_id, session_id, source_file_name, pipeline, generator,
                    status, stage, params_json, qa_count, error_message, result_paths_json,
                    idempotency_key, created_at, finished_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    upload_id,
                    None,
                    source_file_name,
                    pipeline,
                    generator,
                    "queued",
                    None,
                    json.dumps(record.params, ensure_ascii=False),
                    None,
                    None,
                    None,
                    idempotency_key,
                    now,
                    None,
                    now,
                ),
            )
        return record

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    def list_jobs(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[JobRecord]:
        query = "SELECT * FROM jobs"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_job(row) for row in rows]

    def update_job(self, job_id: str, **fields: Any) -> JobRecord:
        with self._lock, transaction(self._conn):
            record = self.get_job(job_id)
            if record is None:
                raise KeyError(job_id)
            if "params" in fields and isinstance(fields["params"], dict):
                fields["params_json"] = json.dumps(fields.pop("params"), ensure_ascii=False)
            if "result_paths" in fields:
                fields["result_paths_json"] = json.dumps(
                    fields.pop("result_paths") or {},
                    ensure_ascii=False,
                )
            column_map = {
                "session_id": "session_id",
                "status": "status",
                "stage": "stage",
                "qa_count": "qa_count",
                "finished_at": "finished_at",
                "error_message": "error_message",
                "params_json": "params_json",
                "result_paths_json": "result_paths_json",
            }
            updates: list[str] = []
            values: list[Any] = []
            for key, column in column_map.items():
                if key in fields:
                    updates.append(f"{column} = ?")
                    values.append(fields[key])
            updates.append("updated_at = ?")
            values.append(_utc_now())
            values.append(job_id)
            self._conn.execute(
                f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?",
                values,
            )
        updated = self.get_job(job_id)
        if updated is None:
            raise KeyError(job_id)
        return updated

    def delete_job(self, job_id: str) -> bool:
        with self._lock, transaction(self._conn):
            row = self._conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return False
            self._conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        job_dir = self.jobs_dir / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
        return True

    def log_job_event(self, job_id: str, stage: str | None, message: str | None = None) -> None:
        with self._lock, transaction(self._conn):
            self._conn.execute(
                """
                INSERT INTO job_events(job_id, stage, message, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (job_id, stage, message, _utc_now()),
            )

    def save_session(self, session_id: str, payload: dict[str, Any]) -> str:
        now = _utc_now()
        payload = {**payload, "updatedAt": now}
        job_id = payload.get("jobId")
        if not job_id:
            raise ValueError("session payload requires jobId")

        with self._lock, transaction(self._conn):
            existing = self._conn.execute(
                "SELECT created_at FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            created_at = str(existing["created_at"]) if existing else str(payload.get("createdAt") or now)
            self._conn.execute(
                """
                INSERT INTO sessions(
                    id, job_id, source_file_name, pipeline, generator,
                    params_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source_file_name = excluded.source_file_name,
                    pipeline = excluded.pipeline,
                    generator = excluded.generator,
                    params_json = excluded.params_json,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    job_id,
                    payload.get("sourceFileName") or "document.md",
                    payload.get("pipeline") or "singlehop",
                    payload.get("generator"),
                    json.dumps(payload.get("params") or {}, ensure_ascii=False),
                    created_at,
                    now,
                ),
            )
            self._conn.execute(
                "UPDATE jobs SET session_id = ?, updated_at = ? WHERE id = ?",
                (session_id, now, job_id),
            )
            self._replace_qa_items(session_id, payload.get("items") or [], now, created_at)
        return now

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                return None
            items = self._load_session_items(session_id)
        return {
            "id": session_id,
            "sourceFileName": row["source_file_name"],
            "pipeline": row["pipeline"],
            "generator": row["generator"],
            "params": json.loads(row["params_json"]),
            "jobId": row["job_id"],
            "items": items,
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def delete_session(self, session_id: str) -> bool:
        with self._lock, transaction(self._conn):
            row = self._conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                return False
            self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        legacy = self.sessions_dir / f"{session_id}.json"
        if legacy.is_file():
            legacy.unlink()
        return True

    def get_session_item(self, session_id: str, qa_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM qa_items WHERE session_id = ? AND id = ?",
                (session_id, qa_id),
            ).fetchone()
        if row is None:
            return None
        return workspace_item_from_row(row)

    def save_session_item(self, session_id: str, item: dict[str, Any], sort_index: int | None = None) -> str:
        now = _utc_now()
        with self._lock, transaction(self._conn):
            if sort_index is None:
                row = self._conn.execute(
                    "SELECT sort_index FROM qa_items WHERE session_id = ? AND id = ?",
                    (session_id, item["id"]),
                ).fetchone()
                sort_index = int(row["sort_index"]) if row else 0
            values = qa_item_row_values(session_id, item, sort_index, now)
            self._conn.execute(
                """
                INSERT INTO qa_items(
                    id, session_id, sort_index, question, answer, chunk_text,
                    expanded_question, expanded_answer, hop_type, level1_name, level2_name,
                    task_type, question_quality_grade, answer_alignment_grade,
                    answer_verifiability_grade, downstream_value_grade,
                    deleted, dirty, selected, filter_passed, user_modified,
                    record_json, created_at, updated_at
                ) VALUES (
                    :id, :session_id, :sort_index, :question, :answer, :chunk_text,
                    :expanded_question, :expanded_answer, :hop_type, :level1_name, :level2_name,
                    :task_type, :question_quality_grade, :answer_alignment_grade,
                    :answer_verifiability_grade, :downstream_value_grade,
                    :deleted, :dirty, :selected, :filter_passed, :user_modified,
                    :record_json, :created_at, :updated_at
                )
                ON CONFLICT(session_id, id) DO UPDATE SET
                    sort_index = excluded.sort_index,
                    question = excluded.question,
                    answer = excluded.answer,
                    chunk_text = excluded.chunk_text,
                    expanded_question = excluded.expanded_question,
                    expanded_answer = excluded.expanded_answer,
                    hop_type = excluded.hop_type,
                    level1_name = excluded.level1_name,
                    level2_name = excluded.level2_name,
                    task_type = excluded.task_type,
                    question_quality_grade = excluded.question_quality_grade,
                    answer_alignment_grade = excluded.answer_alignment_grade,
                    answer_verifiability_grade = excluded.answer_verifiability_grade,
                    downstream_value_grade = excluded.downstream_value_grade,
                    deleted = excluded.deleted,
                    dirty = excluded.dirty,
                    selected = excluded.selected,
                    filter_passed = excluded.filter_passed,
                    user_modified = excluded.user_modified,
                    record_json = excluded.record_json,
                    updated_at = excluded.updated_at
                """,
                values,
            )
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
        return now

    def list_qa_records(
        self,
        session_id: str,
        *,
        limit: int = 500,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM qa_items WHERE session_id = ?"
        params: list[Any] = [session_id]
        if not include_deleted:
            query += " AND deleted = 0"
        query += " ORDER BY sort_index LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        items = [workspace_item_from_row(row) for row in rows]
        return [record_to_jsonl_row(item) for item in items]

    def _replace_qa_items(
        self,
        session_id: str,
        items: list[dict[str, Any]],
        now: str,
        created_at: str,
    ) -> None:
        self._conn.execute("DELETE FROM qa_items WHERE session_id = ?", (session_id,))
        for index, item in enumerate(items):
            row = qa_item_row_values(session_id, item, index, now)
            row["created_at"] = created_at
            self._conn.execute(
                """
                INSERT INTO qa_items(
                    id, session_id, sort_index, question, answer, chunk_text,
                    expanded_question, expanded_answer, hop_type, level1_name, level2_name,
                    task_type, question_quality_grade, answer_alignment_grade,
                    answer_verifiability_grade, downstream_value_grade,
                    deleted, dirty, selected, filter_passed, user_modified,
                    record_json, created_at, updated_at
                ) VALUES (
                    :id, :session_id, :sort_index, :question, :answer, :chunk_text,
                    :expanded_question, :expanded_answer, :hop_type, :level1_name, :level2_name,
                    :task_type, :question_quality_grade, :answer_alignment_grade,
                    :answer_verifiability_grade, :downstream_value_grade,
                    :deleted, :dirty, :selected, :filter_passed, :user_modified,
                    :record_json, :created_at, :updated_at
                )
                """,
                row,
            )

    def _load_session_items(self, session_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM qa_items WHERE session_id = ? ORDER BY sort_index",
            (session_id,),
        ).fetchall()
        return [workspace_item_from_row(row) for row in rows]

    def _row_to_job(self, row: Any) -> JobRecord:
        result_paths_raw = row["result_paths_json"]
        result_paths = json.loads(result_paths_raw) if result_paths_raw else {}
        return JobRecord(
            job_id=row["id"],
            upload_id=row["upload_id"],
            source_file_name=row["source_file_name"],
            pipeline=row["pipeline"],
            generator=row["generator"],
            status=row["status"],
            params=json.loads(row["params_json"]),
            created_at=row["created_at"],
            stage=row["stage"],
            session_id=row["session_id"],
            qa_count=row["qa_count"],
            finished_at=row["finished_at"],
            error_message=row["error_message"],
            result_paths=result_paths,
        )
