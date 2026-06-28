from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from server.db.qa_mapping import qa_item_row_values
from server.util import utc_now


def import_legacy_json_store(conn: sqlite3.Connection, data_dir: Path) -> None:
    marker = data_dir / ".legacy-json-imported"
    if marker.is_file():
        return

    uploads_dir = data_dir / "uploads"
    jobs_dir = data_dir / "jobs"
    sessions_dir = data_dir / "sessions"
    if not jobs_dir.is_dir() and not sessions_dir.is_dir():
        return

    with conn:
        _import_uploads(conn, uploads_dir)
        _import_jobs(conn, jobs_dir)
        _import_sessions(conn, sessions_dir)

    marker.write_text(utc_now(), encoding="utf-8")


def _import_uploads(conn: sqlite3.Connection, uploads_dir: Path) -> None:
    if not uploads_dir.is_dir():
        return
    for upload_dir in uploads_dir.iterdir():
        if not upload_dir.is_dir():
            continue
        upload_id = upload_dir.name
        exists = conn.execute("SELECT 1 FROM uploads WHERE id = ?", (upload_id,)).fetchone()
        if exists:
            continue
        meta_path = upload_dir / "meta.json"
        file_name = "document.md"
        size = 0
        created_at = utc_now()
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            file_name = str(meta.get("fileName") or file_name)
            size = int(meta.get("size") or 0)
            created_at = str(meta.get("createdAt") or created_at)
        storage_path = f"uploads/{upload_id}/doc.md"
        conn.execute(
            """
            INSERT INTO uploads(id, file_name, storage_path, size_bytes, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (upload_id, file_name, storage_path, size, created_at),
        )


def _import_jobs(conn: sqlite3.Connection, jobs_dir: Path) -> None:
    if not jobs_dir.is_dir():
        return
    for job_dir in jobs_dir.iterdir():
        meta_path = job_dir / "meta.json"
        if not meta_path.is_file():
            continue
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        job_id = data["job_id"]
        exists = conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if exists:
            continue
        upload_id = data["upload_id"]
        if not conn.execute("SELECT 1 FROM uploads WHERE id = ?", (upload_id,)).fetchone():
            conn.execute(
                """
                INSERT INTO uploads(id, file_name, storage_path, size_bytes, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    upload_id,
                    data.get("source_file_name") or "document.md",
                    f"uploads/{upload_id}/doc.md",
                    0,
                    data.get("created_at") or utc_now(),
                ),
            )
        conn.execute(
            """
            INSERT INTO jobs(
                id, upload_id, session_id, source_file_name, pipeline, generator,
                status, stage, params_json, qa_count, error_message, result_paths_json,
                created_at, finished_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                upload_id,
                data.get("session_id"),
                data["source_file_name"],
                data["pipeline"],
                data.get("generator"),
                data["status"],
                data.get("stage"),
                json.dumps(data.get("params") or {}, ensure_ascii=False),
                data.get("qa_count"),
                data.get("error_message"),
                json.dumps(data.get("result_paths") or {}, ensure_ascii=False),
                data["created_at"],
                data.get("finished_at"),
                data.get("finished_at") or data["created_at"],
            ),
        )


def _import_sessions(conn: sqlite3.Connection, sessions_dir: Path) -> None:
    if not sessions_dir.is_dir():
        return
    for path in sessions_dir.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        session_id = payload.get("id") or path.stem
        exists = conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if exists:
            continue
        job_id = payload.get("jobId")
        if not job_id:
            continue
        if not conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone():
            continue
        created_at = str(payload.get("createdAt") or utc_now())
        updated_at = str(payload.get("updatedAt") or created_at)
        conn.execute(
            """
            INSERT INTO sessions(
                id, job_id, source_file_name, pipeline, generator,
                params_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                job_id,
                payload.get("sourceFileName") or "document.md",
                payload.get("pipeline") or "singlehop",
                payload.get("generator"),
                json.dumps(payload.get("params") or {}, ensure_ascii=False),
                created_at,
                updated_at,
            ),
        )
        conn.execute(
            "UPDATE jobs SET session_id = ? WHERE id = ?",
            (session_id, job_id),
        )
        _replace_qa_items(conn, session_id, payload.get("items") or [], created_at)


def _replace_qa_items(
    conn: sqlite3.Connection,
    session_id: str,
    items: list[dict[str, Any]],
    now: str,
) -> None:
    conn.execute("DELETE FROM qa_items WHERE session_id = ?", (session_id,))
    for index, item in enumerate(items):
        row = qa_item_row_values(session_id, item, index, now)
        conn.execute(
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
