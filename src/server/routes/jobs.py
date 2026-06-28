from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response

from server.config_service import apply_config_update, config_to_response
from server.schemas import (
    AppConfigUpdate,
    CreateJobBody,
    CreateJobResponse,
    JobStatusResponse,
    JobSummary,
    SessionSaveResponse,
    UploadResponse,
    WorkspaceSessionBody,
)
from server.storage import DataStore
from datalight.utils.jsonl import read_jsonl

router = APIRouter()


def _store(request: Request) -> DataStore:
    return request.app.state.store


@router.post("/uploads", response_model=UploadResponse)
async def upload_markdown(request: Request) -> UploadResponse:
    form = await request.form()
    upload = form.get("file")
    if upload is None:
        raise HTTPException(status_code=400, detail="缺少 file 字段。")
    file_name = getattr(upload, "filename", None) or "document.md"
    if not str(file_name).lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="仅支持 .md 文件。请选择 Markdown 文件后重试。")
    content = await upload.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件为空。请选择包含内容的 Markdown 文件。")
    max_bytes = request.app.state.settings.max_upload_bytes
    if len(content) > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"文件超过上限 {limit_mb} MB。请拆分文档或联系管理员。")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="文件必须为 UTF-8 编码。") from exc

    store = _store(request)
    upload_id, path, size = store.save_upload(file_name, content)
    return UploadResponse(uploadId=upload_id, path=str(path), fileName=file_name, size=size)


@router.post("/jobs/qa", response_model=CreateJobResponse, status_code=202)
def create_qa_job(body: CreateJobBody, request: Request) -> CreateJobResponse:
    store = _store(request)
    try:
        store.upload_markdown_path(body.upload_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="uploadId 不存在。") from exc

    params = body.resolved_params()
    generator = body.generator if body.pipeline == "singlehop" else None
    source_file_name = store.upload_file_name(body.upload_id)
    job = store.create_job(
        upload_id=body.upload_id,
        source_file_name=source_file_name,
        pipeline=body.pipeline,
        generator=generator,
        params=params,
    )
    request.app.state.job_runner.start(
        job.job_id,
        llm_model=body.model,
        timeout_sec=body.timeout_sec,
    )
    return CreateJobResponse(jobId=job.job_id, sessionId=None, status="queued")


@router.get("/jobs", response_model=list[JobSummary])
def list_jobs(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[JobSummary]:
    store = _store(request)
    records = store.list_jobs(status=status, limit=limit, offset=offset)
    return [JobSummary.model_validate(record.to_summary()) for record in records]


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str, request: Request) -> JobStatusResponse:
    store = _store(request)
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在。")
    error: str | None = job.error_message
    if job.status == "failed" and error:
        error = {"code": "JOB_FAILED", "message": error}
    return JobStatusResponse(
        status=job.status,
        stage=job.stage,
        sessionId=job.session_id,
        qaCount=job.qa_count,
        resultPaths=job.result_paths or None,
        error=error,
    )


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, request: Request) -> Response:
    store = _store(request)
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在。")
    if job.session_id:
        store.delete_session(job.session_id)
    store.delete_job(job_id)
    return Response(status_code=204)


@router.get("/jobs/{job_id}/qa")
def fetch_job_qa(
    job_id: str,
    request: Request,
    scored: bool = Query(default=True),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    del scored
    store = _store(request)
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在。")
    if job.status != "succeeded":
        raise HTTPException(status_code=409, detail="任务尚未完成。")

    session = store.get_session(job.session_id) if job.session_id else None
    if session and session.get("items"):
        records = [
            item["record"]
            for item in session["items"]
            if not item.get("local", {}).get("deleted")
        ]
        return records[offset : offset + limit]

    from server.job_runner import resolve_qa_jsonl_path

    qa_path = resolve_qa_jsonl_path(job, store.job_output_dir(job_id))
    if not qa_path.is_file():
        return []
    records = read_jsonl(qa_path)
    return records[offset : offset + limit]
