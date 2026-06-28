from __future__ import annotations

import threading
import traceback
import uuid
from pathlib import Path
from typing import Any

from datalight.service import DatalightService
from datalight.utils.jsonl import read_jsonl

from server.schemas import PipelineParamsBody
from server.storage import DataStore, JobRecord, _utc_now


def humanize_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()
    if any(token in lowered for token in ("connection", "connect", "timeout", "llm", "openai")):
        return "大模型连接失败。请在设置中检查 base_url 与 model。"
    return message


def passes_filter(record: dict[str, Any], min_score: float) -> bool:
    for key in (
        "question_quality_grade",
        "answer_alignment_grade",
        "answer_verifiability_grade",
        "downstream_value_grade",
    ):
        grade = record.get(key)
        if isinstance(grade, (int, float)) and grade < min_score:
            return False
    return True


def resolve_qa_jsonl_path(job: JobRecord, output_dir: Path) -> Path:
    if job.pipeline == "multihop":
        return output_dir / "qa_multihop_generated.jsonl"
    generator = job.generator or "default"
    gen_dir = output_dir / generator
    if generator == "atomic":
        return gen_dir / "qa_generated.jsonl"
    return gen_dir / "qa_scored.jsonl"


def build_session_payload(job: JobRecord, records: list[dict[str, Any]], params: PipelineParamsBody) -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    now = _utc_now()
    items = []
    for index, record in enumerate(records):
        items.append(
            {
                "id": f"qa-{index}",
                "record": record,
                "local": {
                    "deleted": False,
                    "dirty": False,
                    "selected": False,
                    "filterPassed": passes_filter(record, params.min_score),
                },
            },
        )
    return {
        "id": session_id,
        "sourceFileName": job.source_file_name,
        "pipeline": job.pipeline,
        "generator": job.generator,
        "params": params.model_dump(by_alias=True),
        "jobId": job.job_id,
        "items": items,
        "createdAt": now,
        "updatedAt": now,
    }


class JobRunner:
    def __init__(self, store: DataStore, config_path: Path) -> None:
        self.store = store
        self.config_path = config_path

    def start(self, job_id: str, *, llm_model: str | None = None, timeout_sec: int | None = None) -> None:
        thread = threading.Thread(
            target=self._run,
            args=(job_id, llm_model, timeout_sec),
            name=f"qa-job-{job_id}",
            daemon=True,
        )
        thread.start()

    def _run(self, job_id: str, llm_model: str | None, timeout_sec: int | None) -> None:
        job = self.store.get_job(job_id)
        if job is None:
            return
        params = PipelineParamsBody.model_validate(job.params)
        service = DatalightService(config=self.config_path)
        output_dir = self.store.job_output_dir(job_id)
        markdown_path = self.store.upload_markdown_path(job.upload_id)
        lmstudio = True

        try:
            self.store.update_job(job_id, status="running", stage="切块")
            result_paths: dict[str, str] = {}

            if job.pipeline == "multihop":
                self.store.update_job(job_id, stage="上下文构建")
                result = service.pipeline_markdown_multihop_qa(
                    markdown=[markdown_path],
                    output_dir=output_dir,
                    chunk_words=params.chunk_words or 800,
                    language=params.language,
                    num_q=params.question_num,
                    llm_model=llm_model,
                    llm_timeout=timeout_sec,
                    lmstudio=lmstudio,
                )
                result_paths = {
                    "chunks": str(result.chunks_path),
                    "contexts": str(result.contexts_path),
                    "generated": str(result.generated_path),
                    "export": str(result.export_path),
                }
                qa_path = result.generated_path
            else:
                generator = job.generator or "default"
                self.store.update_job(job_id, stage="生成")
                result = service.pipeline_markdown_qa(
                    markdown=[markdown_path],
                    output_dir=output_dir,
                    generator=generator,
                    chunk_words=params.chunk_words,
                    overlap_words=params.overlap_words,
                    question_num=params.question_num,
                    min_score=params.min_score,
                    language=params.language,
                    expand_qa=params.expand_qa,
                    expand_mode=params.expand_mode,
                    add_think=params.add_think,
                    atomic_max_per_task=params.atomic_max_per_task,
                    llm_model=llm_model,
                    llm_timeout=timeout_sec,
                    lmstudio=lmstudio,
                )
                gen_dir = output_dir / generator
                result_paths = {
                    "chunks": str(result.chunks_path),
                    "generated": str(result.generated_path),
                    "scored": str(result.scored_path),
                    "export": str(result.export_path),
                }
                if result.expanded_path:
                    result_paths["expanded"] = str(result.expanded_path)
                if result.think_path:
                    result_paths["think"] = str(result.think_path)

                qa_path = resolve_qa_jsonl_path(job, output_dir)

                if params.add_depth_qa:
                    self.store.update_job(job_id, stage="深挖")
                    depth_input = gen_dir / "qa_generated.jsonl"
                    service.pipeline_depth_qa(
                        input_path=depth_input,
                        output_path=gen_dir / "qa_depth.jsonl",
                        n_rounds=params.depth_rounds,
                        llm_model=llm_model,
                        llm_timeout=timeout_sec,
                        lmstudio=lmstudio,
                    )
                    result_paths["depth"] = str(gen_dir / "qa_depth.jsonl")

                if params.add_width_qa:
                    self.store.update_job(job_id, stage="扩宽")
                    width_input = gen_dir / "qa_generated.jsonl"
                    service.pipeline_width_qa(
                        input_path=width_input,
                        output_path=gen_dir / "qa_width.jsonl",
                        llm_model=llm_model,
                        llm_timeout=timeout_sec,
                        lmstudio=lmstudio,
                    )
                    result_paths["width"] = str(gen_dir / "qa_width.jsonl")

            self.store.update_job(job_id, stage="导出")
            records = read_jsonl(qa_path) if qa_path.is_file() else []
            session_payload = build_session_payload(job, records, params)
            self.store.save_session(session_payload["id"], session_payload)

            self.store.update_job(
                job_id,
                status="succeeded",
                stage="导出",
                session_id=session_payload["id"],
                qa_count=len(records),
                finished_at=_utc_now(),
                error_message=None,
                result_paths=result_paths,
            )
        except Exception as exc:
            traceback.print_exc()
            self.store.update_job(
                job_id,
                status="failed",
                finished_at=_utc_now(),
                error_message=humanize_error(exc),
            )
