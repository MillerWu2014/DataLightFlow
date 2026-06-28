from __future__ import annotations

import json
from typing import Any

HOT_RECORD_KEYS = frozenset(
    {
        "question",
        "answer",
        "chunk_text",
        "expanded_question",
        "expanded_answer",
        "hop_type",
        "level1_name",
        "level2_name",
        "task_type",
        "question_quality_grade",
        "answer_alignment_grade",
        "answer_verifiability_grade",
        "downstream_value_grade",
    },
)


def split_record(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    overflow = {k: v for k, v in record.items() if k not in HOT_RECORD_KEYS}
    hot = {k: record.get(k) for k in HOT_RECORD_KEYS if k in record}
    return hot, overflow


def merge_record(hot: dict[str, Any], record_json: str) -> dict[str, Any]:
    base = json.loads(record_json) if record_json else {}
    merged = dict(base)
    for key, value in hot.items():
        if value is not None:
            merged[key] = value
    return merged


def workspace_item_from_row(row: Any) -> dict[str, Any]:
    record = merge_record(
        {
            "question": row["question"],
            "answer": row["answer"],
            "chunk_text": row["chunk_text"],
            "expanded_question": row["expanded_question"],
            "expanded_answer": row["expanded_answer"],
            "hop_type": row["hop_type"],
            "level1_name": row["level1_name"],
            "level2_name": row["level2_name"],
            "task_type": row["task_type"],
            "question_quality_grade": row["question_quality_grade"],
            "answer_alignment_grade": row["answer_alignment_grade"],
            "answer_verifiability_grade": row["answer_verifiability_grade"],
            "downstream_value_grade": row["downstream_value_grade"],
        },
        row["record_json"],
    )
    filter_passed = row["filter_passed"]
    local: dict[str, Any] = {
        "deleted": bool(row["deleted"]),
        "dirty": bool(row["dirty"]),
        "selected": bool(row["selected"]),
    }
    if filter_passed is not None:
        local["filterPassed"] = bool(filter_passed)
    return {
        "id": row["id"],
        "record": record,
        "local": local,
    }


def qa_item_row_values(
    session_id: str,
    item: dict[str, Any],
    sort_index: int,
    now: str,
) -> dict[str, Any]:
    record = dict(item.get("record") or {})
    local = item.get("local") or {}
    hot, _ = split_record(record)
    record_json = json.dumps(record, ensure_ascii=False)
    filter_passed = local.get("filterPassed")
    return {
        "id": item["id"],
        "session_id": session_id,
        "sort_index": sort_index,
        "question": hot.get("question"),
        "answer": hot.get("answer"),
        "chunk_text": hot.get("chunk_text"),
        "expanded_question": hot.get("expanded_question"),
        "expanded_answer": hot.get("expanded_answer"),
        "hop_type": hot.get("hop_type"),
        "level1_name": hot.get("level1_name"),
        "level2_name": hot.get("level2_name"),
        "task_type": hot.get("task_type"),
        "question_quality_grade": hot.get("question_quality_grade"),
        "answer_alignment_grade": hot.get("answer_alignment_grade"),
        "answer_verifiability_grade": hot.get("answer_verifiability_grade"),
        "downstream_value_grade": hot.get("downstream_value_grade"),
        "deleted": 1 if local.get("deleted") else 0,
        "dirty": 1 if local.get("dirty") else 0,
        "selected": 1 if local.get("selected") else 0,
        "filter_passed": 1 if filter_passed else (0 if filter_passed is False else None),
        "user_modified": 1 if record.get("user_modified") else 0,
        "record_json": record_json,
        "created_at": now,
        "updated_at": now,
    }


def record_to_jsonl_row(item: dict[str, Any]) -> dict[str, Any]:
    return dict(item.get("record") or {})
