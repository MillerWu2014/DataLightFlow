# DataLight HTTP API Server

基于 FastAPI 的 QA 工作台后端，接口契约见 [ui/BACKEND_API.md](../../ui/BACKEND_API.md)。

## 启动

开发（uvicorn）：

```bash
cd /path/to/DataLightFlow
pip install -e ".[server]"
export PYTHONPATH=src
uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
```

生产（gunicorn + uvicorn worker）：

```bash
gunicorn server.main:app \
  -k uvicorn.workers.UvicornWorker \
  -b 0.0.0.0:8000 \
  --workers 2 \
  --timeout 3600
```

## 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `DATALIGHT_CONFIG` | `datalight.yaml` 路径 | `configs/datalight.yaml` |
| `DATALIGHT_SERVER_DATA` | 上传/任务/会话数据目录 | `{output.root}/.datalight-server` |
| `DATALIGHT_MAX_UPLOAD_MB` | 上传大小上限（MB） | `32` |
| `DATALIGHT_CORS_ORIGINS` | 逗号分隔 CORS 源 | `http://localhost:5173,…` |

## 已实现端点（P0）

- `POST /api/v1/uploads`
- `POST /api/v1/jobs/qa`
- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{jobId}`
- `DELETE /api/v1/jobs/{jobId}`（P1）
- `PATCH /api/v1/sessions/{sessionId}/qa/{id}`（P1）
- `POST /api/v1/sessions/{sessionId}/qa/{id}/expand`（P1）
- `POST /api/v1/sessions/{sessionId}/qa/{id}/evaluate`（P1）
- `DELETE /api/v1/sessions/{sessionId}/qa/{id}`（P1）
- `GET /api/v1/jobs/{jobId}/qa`
- `GET /api/v1/sessions/{sessionId}`
- `PUT /api/v1/sessions/{sessionId}`
- `GET /api/v1/sessions/{sessionId}/export`
- `GET /api/v1/config`
- `PUT /api/v1/config`
- `GET /health`

Job 在后台线程中调用 `DatalightService.pipeline_markdown_qa` / `pipeline_markdown_multihop_qa`，可选串联 `pipeline_depth_qa` / `pipeline_width_qa`。

## 前端联调

1. 启动本服务（端口 8000）
2. `ui/vite.config.ts` 配置 `/api` 代理
3. `ui/src/lib/api.ts` 设置 `USE_MOCK = false`

## 测试

```bash
PYTHONPATH=src pytest tests/server/test_api.py -q
```
