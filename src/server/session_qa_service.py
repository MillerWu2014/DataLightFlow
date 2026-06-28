from __future__ import annotations

from pathlib import Path
from typing import Any

from datalight.config import DatalightConfig
from datalight.pipeline.evaluation import Text2QAEvaluatorOperator
from datalight.pipeline.generation.expansion import QAExpansionOperator
from datalight.service import _build_qa_llm_client

from server.job_runner import humanize_error, passes_filter
from server.schemas import PipelineParamsBody
from server.storage import DataStore


class SessionQaError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class SessionQaService:
    def __init__(self, store: DataStore, config_path: Path) -> None:
        self.store = store
        self.config_path = config_path

    def patch_item(
        self,
        session_id: str,
        qa_id: str,
        *,
        record_patch: dict[str, Any] | None,
        local_patch: dict[str, Any] | None,
    ) -> dict[str, Any]:
        session, item = self._require_item(session_id, qa_id)
        if record_patch:
            merged = {**(item.get("record") or {}), **record_patch}
            merged["user_modified"] = True
            item["record"] = merged
        if local_patch:
            item["local"] = {**(item.get("local") or {}), **local_patch}
        item["local"]["dirty"] = True
        self.store.save_session(session_id, session)
        return item

    def delete_item(self, session_id: str, qa_id: str) -> None:
        session, item = self._require_item(session_id, qa_id)
        local = item.get("local") or {}
        local["deleted"] = True
        local["dirty"] = True
        item["local"] = local
        self.store.save_session(session_id, session)

    def expand_item(
        self,
        session_id: str,
        qa_id: str,
        *,
        mode: str = "detail",
        llm_model: str | None = None,
        timeout_sec: int | None = None,
    ) -> dict[str, Any]:
        session, item = self._require_item(session_id, qa_id, allow_deleted=False)
        record = dict(item.get("record") or {})
        params = PipelineParamsBody.model_validate(session.get("params") or {})
        language = params.language

        try:
            llm_client = self._build_llm_client(llm_model=llm_model, timeout_sec=timeout_sec)
            expanded_rows = QAExpansionOperator(
                llm_client=llm_client,
                mode=mode,
                target_language=language,
            ).run([record])
        except Exception as exc:
            raise SessionQaError(humanize_error(exc), status_code=503) from exc

        if not expanded_rows:
            raise SessionQaError("扩写未返回结果。", status_code=500)

        updated_record = expanded_rows[0]
        item["record"] = updated_record
        local = item.get("local") or {}
        local["dirty"] = True
        item["local"] = local
        self.store.save_session(session_id, session)
        return item

    def evaluate_item(
        self,
        session_id: str,
        qa_id: str,
        *,
        llm_model: str | None = None,
        timeout_sec: int | None = None,
    ) -> dict[str, Any]:
        session, item = self._require_item(session_id, qa_id, allow_deleted=False)
        record = dict(item.get("record") or {})
        if not record.get("chunk_text") and record.get("context"):
            record["chunk_text"] = record["context"]
        params = PipelineParamsBody.model_validate(session.get("params") or {})
        language = params.language

        try:
            llm_client = self._build_llm_client(llm_model=llm_model, timeout_sec=timeout_sec)
            scored_rows = Text2QAEvaluatorOperator(
                llm_client=llm_client,
                target_language=language,
            ).run([record])
        except Exception as exc:
            raise SessionQaError(humanize_error(exc), status_code=503) from exc

        if not scored_rows:
            raise SessionQaError("重评未返回结果。", status_code=500)

        updated_record = scored_rows[0]
        item["record"] = updated_record
        local = item.get("local") or {}
        local["dirty"] = True
        local["filterPassed"] = passes_filter(updated_record, params.min_score)
        item["local"] = local
        self.store.save_session(session_id, session)
        return item

    def _require_item(
        self,
        session_id: str,
        qa_id: str,
        *,
        allow_deleted: bool = True,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        session = self.store.get_session(session_id)
        if session is None:
            raise SessionQaError("会话不存在。", status_code=404)
        for item in session.get("items", []):
            if item.get("id") == qa_id:
                if not allow_deleted and (item.get("local") or {}).get("deleted"):
                    raise SessionQaError("该 QA 已删除，无法操作。", status_code=409)
                return session, item
        raise SessionQaError("QA 记录不存在。", status_code=404)

    def _build_llm_client(self, *, llm_model: str | None, timeout_sec: int | None):
        app_cfg = DatalightConfig.from_file(self.config_path)
        return _build_qa_llm_client(
            responses_file=None,
            lmstudio=True,
            llm_model=llm_model,
            llm_timeout=timeout_sec,
            llm_config=app_cfg.llm,
        )
