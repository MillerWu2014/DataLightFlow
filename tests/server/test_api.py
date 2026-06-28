from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.settings import ServerSettings


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
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_upload_rejects_non_md(client: TestClient) -> None:
    response = client.post(
        "/api/v1/uploads",
        files={"file": ("doc.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_upload_and_config(client: TestClient) -> None:
    content = "# Title\n\nhello world\n"
    upload = client.post(
        "/api/v1/uploads",
        files={"file": ("demo.md", content.encode("utf-8"), "text/markdown")},
    )
    assert upload.status_code == 200
    body = upload.json()
    assert body["uploadId"]
    assert body["fileName"] == "demo.md"

    config = client.get("/api/v1/config")
    assert config.status_code == 200
    cfg = config.json()
    assert cfg["llm"]["provider"] == "lmstudio"
    assert cfg["taxonomy"]["nodes"]

    updated = client.put(
        "/api/v1/config",
        json={"llm": {**cfg["llm"], "temperature": 0.7}},
    )
    assert updated.status_code == 200
    assert updated.json()["llm"]["temperature"] == 0.7


def test_create_job_accept_nested_params(client: TestClient) -> None:
    upload = client.post(
        "/api/v1/uploads",
        files={"file": ("job.md", b"# doc\n", "text/markdown")},
    ).json()

    response = client.post(
        "/api/v1/jobs/qa",
        json={
            "uploadId": upload["uploadId"],
            "pipeline": "singlehop",
            "generator": "default",
            "params": {
                "language": "zh",
                "chunkWords": 256,
                "overlapWords": 0,
                "questionNum": 1,
                "minScore": 3,
                "expandQa": False,
                "expandMode": "detail",
                "addThink": False,
                "addDepthQa": False,
                "depthRounds": 2,
                "addWidthQa": False,
            },
        },
    )
    assert response.status_code == 202
    job_id = response.json()["jobId"]
    status = client.get(f"/api/v1/jobs/{job_id}")
    assert status.status_code == 200
    assert status.json()["status"] in {"queued", "running", "failed", "succeeded"}
