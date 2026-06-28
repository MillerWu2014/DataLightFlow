from __future__ import annotations

from pathlib import Path

import pytest
from datalight.llm import StaticLLMClient
from fastapi.testclient import TestClient

from server.app import create_app
from server.settings import ServerSettings


def _sample_session(session_id: str = "sess-1", qa_id: str = "qa-0") -> dict:
    return {
        "id": session_id,
        "sourceFileName": "demo.md",
        "pipeline": "singlehop",
        "generator": "default",
        "params": {
            "language": "zh",
            "chunkWords": 512,
            "overlapWords": 0,
            "questionNum": 1,
            "minScore": 3.0,
            "expandQa": False,
            "expandMode": "detail",
            "addThink": False,
            "addDepthQa": False,
            "depthRounds": 2,
            "addWidthQa": False,
        },
        "jobId": "job-1",
        "items": [
            {
                "id": qa_id,
                "record": {
                    "question": "什么是客舱？",
                    "answer": "飞机载客区域。",
                    "chunk_text": "客舱是飞机内载客的区域。",
                },
                "local": {
                    "deleted": False,
                    "dirty": False,
                    "selected": False,
                    "filterPassed": True,
                },
            },
        ],
        "createdAt": "2026-06-27T10:00:00Z",
        "updatedAt": "2026-06-27T10:00:00Z",
    }


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    config_path = tmp_path / "datalight.yaml"
    config_path.write_text(
        "output:\n  root: .output\nllm:\n  provider: lmstudio\n  base_url: http://127.0.0.1:1234/v1\n  model: test\n  timeout_sec: 60\n  temperature: 0.5\n",
        encoding="utf-8",
    )
    settings = ServerSettings(
        config_path=config_path,
        data_dir=tmp_path / "data",
        max_upload_bytes=1024 * 1024,
        cors_origins=["http://localhost:5173"],
    )
    app = create_app(settings)
    store = app.state.store
    store.save_session("sess-1", _sample_session())
    return TestClient(app)


def test_patch_qa_item(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/sessions/sess-1/qa/qa-0",
        json={"record": {"question": "客舱指什么？", "answer": "载客舱室。"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["record"]["question"] == "客舱指什么？"
    assert body["record"]["user_modified"] is True
    assert body["local"]["dirty"] is True


def test_delete_qa_item_soft(client: TestClient) -> None:
    response = client.delete("/api/v1/sessions/sess-1/qa/qa-0")
    assert response.status_code == 204
    session = client.get("/api/v1/sessions/sess-1").json()
    assert session["items"][0]["local"]["deleted"] is True


def test_expand_qa_item(client: TestClient) -> None:
    expand_json = (
        '{"expanded_question":"请说明客舱的定义。",'
        '"expanded_answer":"客舱是飞机内部用于搭载乘客的区域。",'
        '"expansion_type":"detail","expansion_notes":"ok"}'
    )
    client.app.state._expand_llm = StaticLLMClient([expand_json])  # type: ignore[attr-defined]

    from server.session_qa_service import SessionQaService

    def _mock_llm(self, *, llm_model, timeout_sec):  # noqa: ANN001
        return client.app.state._expand_llm

    SessionQaService._build_llm_client = _mock_llm  # type: ignore[method-assign]

    response = client.post(
        "/api/v1/sessions/sess-1/qa/qa-0/expand",
        json={"mode": "detail"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["record"]["expanded_question"] == "请说明客舱的定义。"
    assert body["record"]["expansion_status"] == "ok"


def test_evaluate_qa_item(client: TestClient) -> None:
    grade_block = "**Grading**: 4\n**Feedback**: 清晰"
    client.app.state._eval_llm = StaticLLMClient([grade_block, grade_block, grade_block, grade_block])  # type: ignore[attr-defined]

    from server.session_qa_service import SessionQaService

    def _mock_llm(self, *, llm_model, timeout_sec):  # noqa: ANN001
        return client.app.state._eval_llm

    SessionQaService._build_llm_client = _mock_llm  # type: ignore[method-assign]

    response = client.post("/api/v1/sessions/sess-1/qa/qa-0/evaluate", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["record"]["question_quality_grade"] == 4
    assert body["local"]["filterPassed"] is True


def test_delete_job(client: TestClient) -> None:
    upload = client.post(
        "/api/v1/uploads",
        files={"file": ("job.md", b"# doc\n", "text/markdown")},
    ).json()
    job = client.post(
        "/api/v1/jobs/qa",
        json={
            "uploadId": upload["uploadId"],
            "pipeline": "singlehop",
            "generator": "default",
            "language": "zh",
            "chunkWords": 256,
            "minScore": 3,
        },
    ).json()
    job_id = job["jobId"]
    assert client.delete(f"/api/v1/jobs/{job_id}").status_code == 204
    assert client.get(f"/api/v1/jobs/{job_id}").status_code == 404
