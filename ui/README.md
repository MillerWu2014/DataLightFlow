# DataLight QA 工作台（前端）

基于 [docs/前端设计需求说明.md](../docs/前端设计需求说明.md) 与 `ui/stitch_v1/` 设计稿实现的 **QA 数据工作台 + 设置** 桌面 UI。

| 项 | 说明 |
|----|------|
| 技术栈 | Vite + React 18 + TypeScript + React Router |
| 当前模式 | **Mock 演示**（`src/lib/api.ts` 中 `USE_MOCK = true`） |
| 数据持久化 | Mock 下任务 / 会话 / 设置存于浏览器 `localStorage` |
| 接口契约 | 见下文；完整规格见 [BACKEND_API.md](./BACKEND_API.md) |

---

## 运行与构建

```bash
cd ui
npm install
npm run dev      # 默认 http://localhost:5173
npm run build    # 产出 dist/
npm run preview  # 预览生产构建
```

建议视口宽度 ≥ 1280px。页面语言为中文；`index.html` 已设 `lang="zh-CN"`。

### 对接真实后端时的开发代理（可选）

在 `vite.config.ts` 中增加反向代理，避免跨域：

```ts
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
```

将 `src/lib/api.ts` 的 `USE_MOCK` 改为 `false` 后，所有 `fetch("/api/v1/…")` 会走上述代理。

---

## 目录结构

```text
ui/
├── src/
│   ├── lib/
│   │   ├── api.ts          # HTTP 封装（Mock / 真实切换点）
│   │   ├── storage.ts      # localStorage 读写与演示数据修复
│   │   ├── qa-utils.ts     # 评分、流水线阶段、Alpaca 导出
│   │   └── mock-data.ts    # Mock QA 样本
│   ├── pages/
│   │   ├── WorkspacePage.tsx   # 工作台（上传、任务、列表、详情）
│   │   └── SettingsPage.tsx    # 设置（LLM / 输出 / 分类体系）
│   ├── components/         # 顶栏、侧栏、QA 卡片、详情面板等
│   └── types/index.ts      # 与后端 JSON 对齐的 TypeScript 类型
├── stitch_v1/              # 静态设计稿（HTML + 截图）
├── BACKEND_API.md          # 后端 API 详细规格（实现参考）
└── README.md               # 本文档
```

---

## 路由与页面

| 路径 | 页面 | 功能 |
|------|------|------|
| `/` | 重定向 | → `/workspace` |
| `/workspace` | 工作台 | 历史任务、上传 Markdown、流水线配置、QA 列表与详情、导出 |
| `/settings` | 设置 | 大模型连接、输出目录、分类体系预览 |

---

## Mock 模式说明

`USE_MOCK = true` 时：

- **不上传**到服务器；`uploadMarkdown` 仅校验 `.md` 扩展名与非空
- **不调用** Job API；`createQaJob` 本地生成 `jobId`，`getJobStatus` 按阶段名模拟进度（约 800ms/阶段）
- **QA 数据**来自 `mock-data.ts`（按 `generator` / `multihop` 切换样本）
- **任务列表**来自 `localStorage` 键 `datalight-ui-tasks-v2`
- **会话**键 `datalight-ui-sessions-v2`；**设置**键 `datalight-ui-settings-v1`
- 文件名含 `fail` 时模拟 LLM 连接失败（用于演示错误态）

首次无任务时会自动 seed 演示任务（taxonomy 样本）。若列表有任务但 QA 为空，刷新后 `initWorkspaceData()` 会尝试修复会话。

---

## 后端 API 依赖总览

前端通过 `src/lib/api.ts` 统一访问后端。下表为 **P0（对接必需）** 与 **P1（规划能力）** 端点。

| 优先级 | 方法 | 路径 | 前端函数 | 用途 |
|--------|------|------|----------|------|
| P0 | POST | `/api/v1/uploads` | `uploadMarkdown()` | 上传单个 `.md` |
| P0 | POST | `/api/v1/jobs/qa` | `createQaJob()` | 提交 QA 生成异步任务 |
| P0 | GET | `/api/v1/jobs` | `listJobs()` | 历史任务列表 |
| P0 | GET | `/api/v1/jobs/{jobId}` | `getJobStatus()` | 任务状态与阶段（轮询） |
| P0 | GET | `/api/v1/jobs/{jobId}/qa` | `fetchJobQa()` | 拉取 QA 记录数组 |
| P0 | PUT | `/api/v1/sessions/{sessionId}` | `saveSession()` | 批量保存编辑 / 软删除 |
| P0 | GET | `/api/v1/config` | `fetchConfig()` | 读取脱敏配置 |
| P0 | GET | `/api/v1/sessions/{sessionId}/export` | （可选，见导出） | 服务端 Alpaca JSONL 流 |
| P2 | PUT | `/api/v1/config` | `updateConfig()` | 写回可编辑配置项 |
| P1 | DELETE | `/api/v1/jobs/{jobId}` | — | 删除任务（侧栏归档/回收站） |
| P1 | PATCH | `/api/v1/sessions/{sessionId}/qa/{id}` | — | 单条 QA 更新 |
| P1 | POST | `/api/v1/sessions/.../expand` | — | 单条扩写 |
| P1 | POST | `/api/v1/sessions/.../evaluate` | — | 单条重评 |

**架构原则**（详见 [BACKEND_API.md §1](./BACKEND_API.md#1-架构概览)）：

- LLM API Key 与完整 `datalight.yaml` **仅服务端**持有；前端配置页不含密钥字段
- Job **异步**执行；前端在 `WorkspacePage` 中每 **600ms** 轮询 `getJobStatus`，成功后调用 `fetchJobQa`
- 深挖 / 扩宽（`addDepthQa` / `addWidthQa`）在 Job 编排层于主流水线之后调用 `pipeline_depth_qa` / `pipeline_width_qa`

---

## 接口详细说明（P0）

### 1. POST `/api/v1/uploads`

**Content-Type**：`multipart/form-data`，字段名 `file`

**成功 200**：

```json
{
  "uploadId": "uuid",
  "path": "/data/uploads/{uploadId}/doc.md",
  "fileName": "客舱运行管理.md",
  "size": 12345
}
```

**错误**：

| HTTP | 场景 | message 示例 |
|------|------|--------------|
| 400 | 非 `.md` | 仅支持 .md 文件。请选择 Markdown 文件后重试。 |
| 400 | 空文件 | 文件为空。请选择包含内容的 Markdown 文件。 |
| 413 | 超大 | 文件超过上限 {N} MB。 |

---

### 2. POST `/api/v1/jobs/qa`

**Headers**：`Content-Type: application/json`；可选 `Idempotency-Key: uuid`

**请求体**（camelCase，与 `PipelineParamsSnapshot` + 任务元数据对齐）：

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

| 字段 | 说明 | 后端映射 |
|------|------|----------|
| `pipeline` | `singlehop` \| `multihop` | 选择主流水线 |
| `generator` | `default` \| `atomic` \| `taxonomy` | 仅单跳；多跳可省略 |
| `language` | `zh` \| `en` \| `auto` | `language` / `target_language` |
| `chunkWords` | 切块词数 | `chunk_words`（多跳默认 800） |
| `overlapWords` | 重叠词数 | `overlap_words`（多跳语义切块未使用） |
| `questionNum` | 每 chunk QA 数 | `question_num` / 多跳 `num_q` |
| `minScore` | 过滤阈值 1–5 | `min_score`（atomic / 多跳无四维时可忽略） |
| `atomicMaxPerTask` | atomic 每块上限 | `atomic_max_per_task` |
| `expandQa` / `expandMode` | 后处理扩写 | `expand_qa` / `expand_mode` |
| `addThink` | 生成 Think | `add_think` |
| `addDepthQa` / `depthRounds` | Agentic 深挖 | Job 编排 `pipeline_depth_qa` |
| `addWidthQa` | Agentic 扩宽 | Job 编排 `pipeline_width_qa` |
| `model` / `timeoutSec` | 可选覆盖 | 覆盖 `datalight.yaml` 中 LLM 配置 |

**成功 202**：

```json
{
  "jobId": "uuid",
  "sessionId": null,
  "status": "queued"
}
```

**Job 阶段 `stage` 枚举**（写入任务元数据，前端进度条直接展示）：

- 单跳 default / taxonomy：`切块` → `生成` → `评估` → `过滤` → [`扩写`] → [`Think`] → [`深挖`] → [`扩宽`] → `导出`
- 单跳 atomic：`切块` → `生成` → [`扩写`] → [`Think`] → [`深挖`] → [`扩宽`] → `导出`
- 多跳：`切块` → `上下文构建` → `生成` → `导出`

**实现注意**：当前 Mock 版 `createQaJob` 的 TypeScript 参数含 `fileName`、`uploadContent`（仅本地演示用）。对接真实后端时，`api.ts` 应只提交上表 JSON，**不要**把文件内容放入 body。

---

### 3. GET `/api/v1/jobs`

**Query**（均可选）：`q`, `status`, `generator`, `from`, `to`, `limit`, `offset`

**成功 200**：`TaskHistoryEntry[]`

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
    "errorMessage": null,
    "params": { "language": "zh", "chunkWords": 512, "minScore": 3.0 }
  }
]
```

`status` 枚举：`queued` | `running` | `succeeded` | `failed` | `cancelled`

---

### 4. GET `/api/v1/jobs/{jobId}`

**成功 200（运行中）**：

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

**失败**：

```json
{
  "status": "failed",
  "stage": "评估",
  "error": {
    "code": "LLM_UNAVAILABLE",
    "message": "大模型连接失败。请在设置中检查 base_url 与 model。"
  }
}
```

前端 `JobStatusResult` 当前使用扁平 `error?: string`；对接时可统一为 `error.message` 字符串。

**可选**：WebSocket `GET /api/v1/jobs/{jobId}/stream` 推送阶段，替代轮询。

---

### 5. GET `/api/v1/jobs/{jobId}/qa`

**Query**：`scored=true`（默认）、`limit`, `offset`

**成功 200**：`QARecord[]`（JSON 数组，与流水线 JSONL 行结构一致）

**按流水线读取的文件**：

| 流水线 | 目录 | 数据源文件 |
|--------|------|------------|
| 单跳 default | `{job_dir}/default/` | `qa_scored.jsonl` |
| 单跳 taxonomy | `{job_dir}/taxonomy/` | `qa_scored.jsonl` |
| 单跳 atomic | `{job_dir}/atomic/` | `qa_generated.jsonl`（无四维评分） |
| 多跳 | `{job_dir}/` | `qa_multihop_generated.jsonl` |

**`QARecord` 主要字段**：

| 分组 | 字段 |
|------|------|
| 定位 | `source_md`, `chunk_index` |
| 核心 | `question`, `answer`, `chunk_text`, `context` |
| 类型 | `hop_type`, `qa_type` |
| Taxonomy | `level1_name`, `level2_name`, `task_type`, `reasoning_style` |
| 四维评分 | `question_quality_grade`, `question_quality_feedback`, `answer_alignment_*`, `answer_verifiability_*`, `downstream_value_*` |
| 多跳 | `reasoning_steps`, `supporting_facts` |
| 扩写 | `expanded_question`, `expanded_answer`, `expansion_status` |
| Think | `think`, `think_status`, `think_error` |
| 编辑 | `user_modified` |

前端收到数组后，由 `buildSessionFromRecords()` 转为 `WorkspaceSession`（含 `items[].local.filterPassed` 等 UI 状态）。

---

### 6. PUT `/api/v1/sessions/{sessionId}`

**用途**：保存用户在详情面板中的编辑与软删除。

**请求体**：

```json
{
  "sourceFileName": "客舱运行管理.md",
  "pipeline": "singlehop",
  "generator": "taxonomy",
  "params": { "minScore": 3.0 },
  "jobId": "uuid",
  "items": [
    {
      "id": "qa-0",
      "record": {
        "question": "…",
        "answer": "…",
        "user_modified": true
      },
      "local": {
        "deleted": false,
        "dirty": false,
        "selected": false,
        "filterPassed": true
      }
    }
  ],
  "updatedAt": "2026-06-27T10:10:00Z"
}
```

**成功 200**：`{ "updatedAt": "ISO8601" }`

服务端可只持久化 `record` + `deleted` 标志；`local.dirty` 等为前端 ephemeral 状态。

---

### 7. GET `/api/v1/config`

**成功 200**：`AppSettings`（**脱敏**，无 API Key）

```json
{
  "llm": {
    "provider": "lmstudio",
    "baseUrl": "http://127.0.0.1:1234/v1",
    "model": "qwen/qwen3.6-35b-a3b",
    "timeoutSec": 180,
    "temperature": 0.5
  },
  "output": {
    "root": ".output",
    "autoArchive": false
  },
  "taxonomy": {
    "complete": true,
    "topic": "民航领域",
    "level1Count": 3,
    "taskTypeCount": 9,
    "nodes": [
      { "level": "01", "label": "root/民航领域", "indent": 0 },
      { "level": "02", "label": "运行推理类", "indent": 1 }
    ]
  }
}
```

`taxonomy.nodes` 用于设置页「分类体系预览」表格；可由 `configs/datalight.yaml` 的 `taxonomy` 段展开生成。

---

### 8. PUT `/api/v1/config`

**可写字段**：`llm.model`, `llm.baseUrl`, `llm.provider`, `llm.timeoutSec`, `llm.temperature`, `output.root`, `output.autoArchive` 等**非密钥**项。

**成功 200** 或 **204**。失败时返回可读中文 `message`。

---

### 9. 导出（当前实现 vs 可选 API）

**当前（Mock / 客户端导出）**：工作台顶栏「导出」→ `ExportDialog` → `toAlpacaRow()` + `downloadJsonl()`，范围：

- `passed`：仅 `filterPassed !== false` 且未删除
- `all`：全部未删除
- `selected`：当前选中一条

**Alpaca 行结构**：

```json
{
  "instruction": "根据给定上下文回答问题。",
  "input": "expanded_question 或 question",
  "output": "expanded_answer 或 answer",
  "source_md": "…",
  "chunk_index": 0,
  "think": "…",
  "level1_name": "…",
  "task_type": "…",
  "hop_type": "…"
}
```

**可选服务端**：`GET /api/v1/sessions/{sessionId}/export?scope=passed|all|selected&ids=qa-1,qa-2`  
返回 `application/jsonl` 文件流，逻辑对齐 `AlpacaExportOperator`。

---

## 前端调用流程

```text
上传 Markdown
  uploadMarkdown(file)  →  POST /api/v1/uploads  →  uploadId

开始生成
  createQaJob({ uploadId, pipeline, generator, params })
    →  POST /api/v1/jobs/qa  →  jobId

轮询（WorkspacePage.pollJob，间隔 ~600ms）
  getJobStatus(jobId)  →  GET /api/v1/jobs/{jobId}
  status === succeeded 时：
    fetchJobQa(jobId)  →  GET /api/v1/jobs/{jobId}/qa
    buildSessionFromRecords()  →  写入 sessions 状态

保存编辑
  saveSession(session)  →  PUT /api/v1/sessions/{sessionId}

设置页
  fetchConfig()   →  GET /api/v1/config
  updateConfig()  →  PUT /api/v1/config

（对接后）历史任务
  listJobs()  →  GET /api/v1/jobs   # 当前 Mock 仍读 localStorage
```

---

## 对接 checklist

1. ~~实现 [BACKEND_API.md](./BACKEND_API.md) 中 P0 端点~~ → 见 [`src/server/`](../src/server/)
2. ~~`ui/vite.config.ts` 配置 `/api` 代理~~（已默认指向 `8000`）
3. `src/lib/api.ts`：`USE_MOCK = false`
4. ~~`createQaJob` 请求体已与后端对齐~~
5. `WorkspacePage`：可选在 mount 时调用 `listJobs()` 替代仅读 `localStorage`
6. ~~Job 失败错误格式~~（`getJobStatus` 已解析 `error.message`）
7. ~~`GET /api/v1/config` 返回 `taxonomy.nodes`~~

---

## 当前 UI 能力（Mock）

- 左栏历史任务（运行中 / 已完成 / 失败）、新建任务
- 上传 `.md`、流水线类型（单跳通用 / 原子 / 分类体系、多跳）、高级参数（扩写、Think、深挖、扩宽）
- QA 列表、四维评分条、筛选（全部 / 已通过 / 待复核）、搜索
- 右侧详情：编辑 Q/A、软删除、标记已审核、来源上下文
- 顶栏保存会话、导出 JSONL；未保存切换任务时确认对话框
- 设置页：大模型连接（含温度滑块）、输出目录、分类体系预览
- 快捷键：`Ctrl/Cmd+S` 保存；`J` / `K` 切换选中 QA

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [BACKEND_API.md](./BACKEND_API.md) | 后端 API 完整规格、Job Runner 伪代码、产物路径 |
| [src/server/README.md](../src/server/README.md) | FastAPI 服务启动与 gunicorn 配置 |
| [docs/前端设计需求说明.md](../docs/前端设计需求说明.md) | 产品需求与交互说明 |
| [docs/技术实现方案.md](../docs/技术实现方案.md) | 流水线与 Service 能力 |
| `src/datalight/service.py` | Python 侧 `DatalightService` 入口 |

---

*文档版本：与 `ui/src/lib/api.ts`、`ui/src/types/index.ts` 及中文 UI（2026-06）对齐。*
