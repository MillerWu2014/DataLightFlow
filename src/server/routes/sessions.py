from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from server.schemas import (
    ExpandQaBody,
    EvaluateQaBody,
    QAPatchBody,
    QaItemResponse,
    SessionSaveResponse,
    WorkspaceSessionBody,
)
from server.session_qa_service import SessionQaError, SessionQaService

router = APIRouter()


def _store(request: Request):
    return request.app.state.store


def _qa_service(request: Request) -> SessionQaService:
    return SessionQaService(request.app.state.store, request.app.state.settings.config_path)


def _item_response(item: dict[str, Any], updated_at: str | None = None) -> QaItemResponse:
    return QaItemResponse(
        id=item["id"],
        record=item.get("record") or {},
        local=item.get("local") or {},
        updatedAt=updated_at,
    )


def _handle_qa_error(exc: SessionQaError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/sessions/{session_id}")
def get_session(session_id: str, request: Request) -> dict:
    store = _store(request)
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在。")
    return session


@router.put("/sessions/{session_id}", response_model=SessionSaveResponse)
def save_session(session_id: str, body: WorkspaceSessionBody, request: Request) -> SessionSaveResponse:
    store = _store(request)
    payload = body.model_dump(by_alias=True)
    payload["id"] = session_id
    updated_at = store.save_session(session_id, payload)
    return SessionSaveResponse(updatedAt=updated_at)


@router.get("/sessions/{session_id}/export")
def export_session(
    session_id: str,
    request: Request,
    scope: str = Query(default="passed"),
    ids: str | None = Query(default=None),
) -> StreamingResponse:
    store = _store(request)
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在。")

    selected_ids = {item.strip() for item in (ids or "").split(",") if item.strip()}
    rows: list[dict] = []
    for item in session.get("items", []):
        local = item.get("local") or {}
        if local.get("deleted"):
            continue
        if scope == "passed" and local.get("filterPassed") is False:
            continue
        if scope == "selected" and selected_ids and item.get("id") not in selected_ids:
            continue
        record = item.get("record") or {}
        rows.append(_to_alpaca_row(record))

    def stream():
        for row in rows:
            yield json.dumps(row, ensure_ascii=False) + "\n"

    filename = (session.get("sourceFileName") or "export").replace(".md", "") + "_export.jsonl"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(stream(), media_type="application/jsonl", headers=headers)


@router.patch("/sessions/{session_id}/qa/{qa_id}", response_model=QaItemResponse)
def patch_qa_item(
    session_id: str,
    qa_id: str,
    body: QAPatchBody,
    request: Request,
) -> QaItemResponse:
    service = _qa_service(request)
    try:
        item = service.patch_item(
            session_id,
            qa_id,
            record_patch=body.record,
            local_patch=body.local,
        )
    except SessionQaError as exc:
        raise _handle_qa_error(exc) from exc
    session = _store(request).get_session(session_id)
    return _item_response(item, session.get("updatedAt") if session else None)


@router.post("/sessions/{session_id}/qa/{qa_id}/expand", response_model=QaItemResponse)
def expand_qa_item(
    session_id: str,
    qa_id: str,
    body: ExpandQaBody,
    request: Request,
) -> QaItemResponse:
    service = _qa_service(request)
    try:
        item = service.expand_item(
            session_id,
            qa_id,
            mode=body.mode,
            llm_model=body.model,
            timeout_sec=body.timeout_sec,
        )
    except SessionQaError as exc:
        raise _handle_qa_error(exc) from exc
    session = _store(request).get_session(session_id)
    return _item_response(item, session.get("updatedAt") if session else None)


@router.post("/sessions/{session_id}/qa/{qa_id}/evaluate", response_model=QaItemResponse)
def evaluate_qa_item(
    session_id: str,
    qa_id: str,
    body: EvaluateQaBody,
    request: Request,
) -> QaItemResponse:
    service = _qa_service(request)
    try:
        item = service.evaluate_item(
            session_id,
            qa_id,
            llm_model=body.model,
            timeout_sec=body.timeout_sec,
        )
    except SessionQaError as exc:
        raise _handle_qa_error(exc) from exc
    session = _store(request).get_session(session_id)
    return _item_response(item, session.get("updatedAt") if session else None)


@router.delete("/sessions/{session_id}/qa/{qa_id}")
def delete_qa_item(session_id: str, qa_id: str, request: Request) -> Response:
    service = _qa_service(request)
    try:
        service.delete_item(session_id, qa_id)
    except SessionQaError as exc:
        raise _handle_qa_error(exc) from exc
    return Response(status_code=204)


def _to_alpaca_row(record: dict) -> dict:
    question = record.get("expanded_question") or record.get("question") or ""
    answer = record.get("expanded_answer") or record.get("answer") or ""
    row = {
        "instruction": "根据给定上下文回答问题。",
        "input": question,
        "output": answer,
    }
    for key in ("source_md", "chunk_index", "think", "level1_name", "task_type", "hop_type"):
        if key in record and record[key] is not None:
            row[key] = record[key]
    return row
