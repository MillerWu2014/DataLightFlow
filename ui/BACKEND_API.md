# DataLight 前端 — 后端 API 依赖清单

> 本文档列出 `ui/` 演示前端对接生产后端所需的 **HTTP API**，与 `DatalightService`（`src/datalight/service.py`）一一对应。  
> 前端实现位置：`src/lib/api.ts`（当前 `USE_MOCK = true`）。

---

## 1. 架构概览

```text
浏览器 (ui/)
    │  REST / WebSocket
    ▼
HTTP 封装层（待建设，建议 FastAPI）
    │  同步/异步 Job 调度
    ▼
DatalightService / pipeline runners
    │  JSONL 产物
    ▼
{output.root}/…
```

**原则**：
- LLM 密钥与 `configs/datalight.yaml` 仅服务端持有
- 前端 Session 编辑态与服务端 JSONL 通过 Session API 同步
- Job 异步执行，前端轮询或 WebSocket 获取阶段进度

---

## 2. API 端点总表

| # | 方法 | 路径 | 前端调用方 | 后端应对齐的 Service 能力 | 优先级 |
|---|------|------|-----------|--------------------------|--------|
| 1 | POST | `/api/v1/uploads` | `uploadMarkdown()` | 文件存储（隔离目录） | P0 |
| 2 | POST | `/api/v1/jobs/qa` | `createQaJob()` | `pipeline_markdown_qa` / `pipeline_markdown_multihop_qa` | P0 |
| 3 | GET | `/api/v1/jobs` | `listJobs()` | Job 索引持久化 | P0 |
| 4 | GET | `/api/v1/jobs/{jobId}` | `getJobStatus()` | Job 状态 + 阶段 | P0 |
| 5 | GET | `/api/v1/jobs/{jobId}/qa` | `fetchJobQa()` | 读取 `qa_scored.jsonl` 或等价 | P0 |
| 6 | DELETE | `/api/v1/jobs/{jobId}` | （P1 历史删除） | 删除 Job 索引与 Session | P1 |
| 7 | GET | `/api/v1/sessions/{sessionId}` | Session 加载 | 会话元数据 | P0 |
| 8 | PUT | `/api/v1/sessions/{sessionId}` | `saveSession()` | 批量保存编辑后 JSONL | P0 |
| 9 | PATCH | `/api/v1/sessions/{sessionId}/qa/{id}` | 单条更新（可选） | 行级 PATCH | P1 |
| 10 | POST | `/api/v1/sessions/{sessionId}/qa/{id}/expand` | 单条扩写（P1） | `pipeline_expand_qa`（单行） | P1 |
| 11 | POST | `/api/v1/sessions/{sessionId}/qa/{id}/evaluate` | 单条重评（P1） | `Text2QAEvaluatorOperator` | P1 |
| 12 | DELETE | `/api/v1/sessions/{sessionId}/qa/{id}` | 单条删除（可选） | Session 行删除 | P1 |
| 13 | GET | `/api/v1/sessions/{sessionId}/export` | 服务端导出（可选） | `AlpacaExportOperator` | P0 |
| 14 | GET | `/api/v1/config` | `fetchConfig()` | `DatalightConfig.from_file()` 脱敏 | P0 |
| 15 | PUT | `/api/v1/config` | `updateConfig()` | 写回可编辑 YAML 字段 | P2 |

---

## 3. 端点详细规格

### 3.1 POST `/api/v1/uploads`

**用途**：上传单个 `.md` 文件。

**Request**：`multipart/form-data`，字段 `file`

**Response** `200`：
```json
{
  "uploadId": "uuid",
  "path": "/data/uploads/{uploadId}/doc.md",
  "fileName": "客舱运行管理.md",
  "size": 12345
}
```

**错误**：
| 状态 | 场景 | message 示例 |
|------|------|-------------|
| 400 | 非 `.md` | 仅支持 .md 文件。请选择 Markdown 文件后重试。 |
| 400 | 空文件 | 文件为空。请选择包含内容的 Markdown 文件。 |
| 413 | 超大 | 文件超过上限 {N} MB。请拆分文档或联系管理员。 |

**后端实现要点**：
- 存储至隔离目录，禁止路径遍历
- 校验 UTF-8 编码
- 返回 `uploadId` 供 Job 创建引用

---

### 3.2 POST `/api/v1/jobs/qa`

**用途**：提交 QA 生成异步任务。

**Headers**：`Idempotency-Key`（可选，防双提交）

**Request body**：
```json
{
  "uploadId": "uuid",
  "pipeline": "singlehop",
  "generator": "default",
  "language": "zh",
  "chunkWords": 512,
  "overlapWords": 0,
  "questionNum": 1,
  "minScore": 3.0,
  "atomicMaxPerTask": 10,
  "expandQa": false,
  "expandMode": "detail",
  "addThink": false,
  "addDepthQa": false,
  "depthRounds": 2,
  "addWidthQa": false,
  "model": null,
  "timeoutSec": null
}
```

| 字段 | 映射 Service 参数 |
|------|------------------|
| `pipeline=singlehop` + `generator` | `pipeline_markdown_qa(generator=…)` |
| `pipeline=multihop` | `pipeline_markdown_multihop_qa` |
| `language` | `language` / `target_language` |
| `chunkWords` | `chunk_words`（多跳默认 800） |
| `overlapWords` | `overlap_words`（多跳语义切块未使用） |
| `questionNum` | `question_num`（多跳 `num_q`） |
| `minScore` | `min_score` |
| `atomicMaxPerTask` | `atomic_max_per_task` |
| `expandQa` / `expandMode` | `expand_qa` / `expand_mode` |
| `addThink` | `add_think` |
| `addDepthQa` / `depthRounds` | Job 编排：`pipeline_depth_qa(n_rounds=…)` |
| `addWidthQa` | Job 编排：`pipeline_width_qa` |

**Response** `202`：
```json
{
  "jobId": "uuid",
  "sessionId": null,
  "status": "queued"
}
```

**后端实现要点**：
```python
# 单跳
service.pipeline_markdown_qa(
    markdown=[upload_path],
    output_dir=job_output_dir,
    generator=body.generator,
    chunk_words=body.chunkWords,
    overlap_words=body.overlapWords,
    question_num=body.questionNum,
    min_score=body.minScore,
    expand_qa=body.expandQa,
    expand_mode=body.expandMode,
    add_think=body.addThink,
    language=body.language,
)
# 可选后处理（单跳，在 qa_generated / qa_scored 之后）
gen_dir = job_output_dir / body.generator
if body.addDepthQa:
    service.pipeline_depth_qa(
        input_path=gen_dir / "qa_generated.jsonl",
        output_path=gen_dir / "qa_depth.jsonl",
        n_rounds=body.depthRounds,
    )
if body.addWidthQa:
    service.pipeline_width_qa(
        input_path=gen_dir / "qa_generated.jsonl",
        output_path=gen_dir / "qa_width.jsonl",
    )
# 产物：{output_dir}/{generator}/qa_scored.jsonl, qa_export.jsonl, …

# 多跳
service.pipeline_markdown_multihop_qa(
    markdown=[upload_path],
    output_dir=job_output_dir,
    chunk_words=body.chunkWords,
    num_q=body.questionNum,
    language=body.language,
)
# 产物：qa_multihop_generated.jsonl, qa_multihop_export.jsonl
```

**Job 阶段枚举**（写入 `stage` 字段）：
- 单跳 default/taxonomy：`切块` → `生成` → `评估` → `过滤` → [`扩写`] → [`Think`] → [`深挖`] → [`扩宽`] → `导出`
- 单跳 atomic：`切块` → `生成` → [`扩写`] → [`Think`] → [`深挖`] → [`扩宽`] → `导出`
- 多跳：`切块` → `上下文构建` → `生成` → `导出`

---

### 3.3 GET `/api/v1/jobs`

**Query**：`q`, `status`, `generator`, `from`, `to`, `limit`, `offset`

**Response**：
```json
[
  {
    "jobId": "uuid",
    "sessionId": "uuid",
    "sourceFileName": "客舱运行管理.md",
    "pipeline": "singlehop",
    "generator": "taxonomy",
    "status": "succeeded",
    "stage": "导出",
    "qaCount": 42,
    "createdAt": "2026-06-27T10:00:00Z",
    "finishedAt": "2026-06-27T10:05:00Z",
    "errorMessage": null
  }
]
```

**后端实现要点**：Job 元数据持久化（SQLite / JSON 索引），排序默认 `createdAt` 降序。

---

### 3.4 GET `/api/v1/jobs/{jobId}`

**Response**：
```json
{
  "status": "running",
  "stage": "评估",
  "progress": { "current": 12, "total": 48 },
  "error": null,
  "sessionId": null,
  "resultPaths": {
    "chunks": "…/chunks.jsonl",
    "generated": "…/qa_generated.jsonl",
    "scored": "…/qa_scored.jsonl",
    "export": "…/qa_export.jsonl"
  }
}
```

**失败 Response**：
```json
{
  "status": "failed",
  "stage": "评估",
  "error": {
    "code": "LLM_UNAVAILABLE",
    "message": "LLM 连接失败。请检查 base_url 与 model 配置后重试。"
  }
}
```

**后端实现要点**：
- 长任务后台线程 / Celery / asyncio task
- LLM 不可用时返回可读错误，不 500 白屏
- 可选 WebSocket `/api/v1/jobs/{jobId}/stream` 推送阶段

---

### 3.5 GET `/api/v1/jobs/{jobId}/qa`

**Query**：`scored=true`, `limit`, `offset`

**Response**：`QARecord[]`（与 `qa_scored.jsonl` 行结构一致）

**Record 字段**（参见 `pipeline/models.py`）：

| 字段组 | 字段 |
|--------|------|
| 定位 | `source_md`, `chunk_index` |
| 核心 | `question`, `answer`, `chunk_text` / `context` |
| 类型 | `hop_type`, `qa_type` |
| Taxonomy | `level1_name`, `level2_name`, `task_type`, `reasoning_style` |
| 四维评分 | `question_quality_grade`, `*_feedback`, … |
| 多跳 | `reasoning_steps`, `supporting_facts` |
| 扩写 | `expanded_question`, `expanded_answer`, `expansion_status` |
| Think | `think`, `think_status`, `think_error` |

**数据源选择**：
| 模式 | 读取文件 |
|------|---------|
| singlehop default/taxonomy | `qa_scored.jsonl`（含四维；过滤已在 runner 完成） |
| singlehop atomic | `qa_generated.jsonl`（无四维） |
| multihop | `qa_multihop_generated.jsonl` |

**分页**：单文档可能数百条，必须支持 `limit`/`offset`。

---

### 3.6 PUT `/api/v1/sessions/{sessionId}`

**用途**：批量保存用户编辑（含软删除）。

**Request body**：
```json
{
  "items": [
    {
      "id": "qa-0",
      "record": { "question": "…", "answer": "…", "user_modified": true },
      "deleted": false
    }
  ]
}
```

**Response** `200`：`{ "updatedAt": "…" }`

**后端实现要点**：
- 写入 Session 专用 JSONL 或覆盖 Job 产物副本
- 保留 `jobId` 关联，不修改原始 Job 快照（可选策略）

---

### 3.7 GET `/api/v1/sessions/{sessionId}/export`

**Query**：`scope=passed|all|selected`, `ids=…`

**Response**：`application/jsonl` 文件流（Alpaca 格式）

**Alpaca 字段**（`AlpacaExportOperator`）：
```json
{
  "instruction": "…",
  "input": "expanded_question 或 question",
  "output": "expanded_answer 或 answer",
  "source_md": "…",
  "chunk_index": 0,
  "think": "…",
  "level1_name": "…",
  "task_type": "…"
}
```

**后端实现**：对 Session 数据运行 `AlpacaExportOperator`，或等价逻辑。

---

### 3.8 GET / PUT `/api/v1/config`

**GET Response**（脱敏，无 API Key）：
```json
{
  "llm": {
    "provider": "lmstudio",
    "baseUrl": "http://127.0.0.1:1234/v1",
    "model": "qwen/…",
    "timeoutSec": 180,
    "temperature": 0.5
  },
  "output": { "root": ".output" },
  "taxonomy": {
    "complete": true,
    "topic": "民航领域",
    "level1Count": 3,
    "taskTypeCount": 9
  }
}
```

**PUT**：仅允许修改非密钥项（`model`, `timeoutSec`, `temperature`, `output.root` 等）。

**后端实现**：
```python
config = DatalightConfig.from_file("configs/datalight.yaml")
# GET: config.llm, config.output, config.taxonomy.is_complete(), …
# PUT: 写回 YAML 或运行时覆盖
```

---

## 4. P1 扩展端点

### 4.1 POST `/api/v1/sessions/{sessionId}/qa/{id}/expand`

**后端**：对单行调用 `pipeline_expand_qa` 或 `QAExpansionOperator`。

| 参数 | 默认 |
|------|------|
| `mode` | `detail` / `contextual` / `reasoning` |

### 4.2 POST `/api/v1/sessions/{sessionId}/qa/{id}/evaluate`

**后端**：对编辑后 Q/A 调用 `Text2QAEvaluatorOperator`，返回更新后的四维分数。

### 4.3 DELETE `/api/v1/jobs/{jobId}`

**后端**：删除 Job 索引、Session；磁盘 JSONL 删除策略可配置。

---

## 5. 前端替换指南

| 前端模块 | 文件 | 替换为 |
|---------|------|--------|
| 上传 | `lib/api.ts` → `uploadMarkdown` | `POST /api/v1/uploads` |
| 创建 Job | `WorkspacePage` → `handleStartGenerate` | `POST /api/v1/jobs/qa` |
| 轮询进度 | `WorkspacePage` → `pollJob` | `GET /api/v1/jobs/{id}` 或 WebSocket |
| 加载 QA | `fetchJobQa` | `GET /api/v1/jobs/{id}/qa` |
| 历史列表 | `lib/storage.ts` → `loadTasks` | `GET /api/v1/jobs` |
| 保存会话 | `saveSession` | `PUT /api/v1/sessions/{id}` |
| 导出 | `handleExport` | `GET /api/v1/sessions/{id}/export` 或继续客户端 `toAlpacaRow` |
| 设置 | `SettingsPage` | `GET/PUT /api/v1/config` |

将 `lib/api.ts` 中 `USE_MOCK` 设为 `false` 即可切换。

---

## 6. 建议的后端项目结构

```text
src/datalight_http/
├── main.py              # FastAPI app
├── routes/
│   ├── uploads.py
│   ├── jobs.py
│   ├── sessions.py
│   └── config.py
├── services/
│   ├── job_runner.py    # 包装 DatalightService + 阶段回调
│   └── session_store.py
└── models/
    └── schemas.py       # Pydantic 请求/响应
```

**Job Runner 伪代码**：
```python
async def run_qa_job(job_id: str, spec: JobSpec):
    update_job(job_id, status="running", stage="切块")
    svc = DatalightService(config=CONFIG_PATH)
    try:
        if spec.pipeline == "singlehop":
            result = svc.pipeline_markdown_qa(
                markdown=[spec.upload_path],
                output_dir=job_dir(job_id),
                generator=spec.generator,
                **spec.to_service_kwargs(),
            )
            qa_path = result.scored_path or result.generated_path
        else:
            result = svc.pipeline_markdown_multihop_qa(...)
            qa_path = result.generated_path
        session = init_session_from_jsonl(job_id, qa_path)
        update_job(job_id, status="succeeded", session_id=session.id, qa_count=…)
    except Exception as e:
        update_job(job_id, status="failed", error=humanize(e))
```

---

## 7. 与流水线产物路径对照

| 流水线 | 输出目录 | 前端 QA 列表数据源 |
|--------|---------|-------------------|
| 单跳 default | `{job_dir}/default/` | `qa_scored.jsonl` |
| 单跳 atomic | `{job_dir}/atomic/` | `qa_generated.jsonl` |
| 单跳 taxonomy | `{job_dir}/taxonomy/` | `qa_scored.jsonl` |
| 多跳 | `{job_dir}/` | `qa_multihop_generated.jsonl` |

---

## 8. 非功能需求（后端）

| 类别 | 要求 |
|------|------|
| CORS | 允许前端 dev origin `http://localhost:5173` |
| 认证 | 首版可内网无鉴权；生产加 API Key / SSO |
| 文件安全 | 上传隔离、扩展名校验、大小限制 |
| 并发 | Job 队列，避免 LLM 并发过载 |
| 可观测 | Job 日志关联 `jobId`，阶段耗时 |

---

*文档版本：v1.0 · 与 `docs/前端设计需求说明.md` §7 及 `ui/src/lib/api.ts` 对齐*
