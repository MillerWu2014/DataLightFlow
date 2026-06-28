from __future__ import annotations

import sqlite3

MIGRATIONS: list[tuple[str, str]] = [
    (
        "001_uploads_jobs",
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS uploads (
            id            TEXT PRIMARY KEY,
            file_name     TEXT NOT NULL,
            storage_path  TEXT NOT NULL,
            size_bytes    INTEGER NOT NULL,
            sha256        TEXT,
            created_at    TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_uploads_created ON uploads(created_at DESC);

        CREATE TABLE IF NOT EXISTS jobs (
            id                TEXT PRIMARY KEY,
            upload_id         TEXT NOT NULL REFERENCES uploads(id),
            session_id        TEXT,
            source_file_name  TEXT NOT NULL,
            pipeline          TEXT NOT NULL CHECK (pipeline IN ('singlehop', 'multihop')),
            generator         TEXT CHECK (generator IN ('default', 'atomic', 'taxonomy')),
            status            TEXT NOT NULL,
            stage             TEXT,
            params_json       TEXT NOT NULL,
            qa_count          INTEGER,
            error_message     TEXT,
            result_paths_json TEXT,
            idempotency_key   TEXT UNIQUE,
            created_at        TEXT NOT NULL,
            finished_at       TEXT,
            updated_at        TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_jobs_upload ON jobs(upload_id);
        CREATE INDEX IF NOT EXISTS idx_jobs_session ON jobs(session_id);
        """,
    ),
    (
        "002_sessions_qa_items",
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id               TEXT PRIMARY KEY,
            job_id           TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
            source_file_name TEXT NOT NULL,
            pipeline         TEXT NOT NULL,
            generator        TEXT,
            params_json      TEXT NOT NULL,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qa_items (
            id            TEXT NOT NULL,
            session_id    TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            sort_index    INTEGER NOT NULL,
            question      TEXT,
            answer        TEXT,
            chunk_text    TEXT,
            expanded_question TEXT,
            expanded_answer   TEXT,
            hop_type      TEXT,
            level1_name   TEXT,
            level2_name   TEXT,
            task_type     TEXT,
            question_quality_grade       REAL,
            answer_alignment_grade       REAL,
            answer_verifiability_grade   REAL,
            downstream_value_grade       REAL,
            deleted       INTEGER NOT NULL DEFAULT 0,
            dirty         INTEGER NOT NULL DEFAULT 0,
            selected      INTEGER NOT NULL DEFAULT 0,
            filter_passed INTEGER,
            user_modified INTEGER NOT NULL DEFAULT 0,
            record_json   TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            PRIMARY KEY (session_id, id)
        );

        CREATE INDEX IF NOT EXISTS idx_qa_session_sort ON qa_items(session_id, sort_index);
        CREATE INDEX IF NOT EXISTS idx_qa_session_deleted ON qa_items(session_id, deleted);
        CREATE INDEX IF NOT EXISTS idx_qa_session_filter ON qa_items(session_id, filter_passed);
        CREATE INDEX IF NOT EXISTS idx_qa_session_modified ON qa_items(session_id, user_modified);
        """,
    ),
    (
        "003_events_settings_fts",
        """
        CREATE TABLE IF NOT EXISTS job_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id     TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            stage      TEXT,
            message    TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id, created_at);

        CREATE TABLE IF NOT EXISTS settings_overrides (
            key         TEXT PRIMARY KEY,
            value_json  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS qa_items_fts USING fts5(
            session_id UNINDEXED,
            item_id UNINDEXED,
            question,
            answer,
            expanded_question,
            tokenize='unicode61'
        );
        """,
    ),
]


def apply_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)",
    )
    applied = {
        row["version"]
        for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    from server.util import utc_now

    for version, sql in MIGRATIONS:
        if version in applied:
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, utc_now()),
        )
    conn.commit()
