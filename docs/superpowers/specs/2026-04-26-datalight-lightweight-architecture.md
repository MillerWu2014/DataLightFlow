# DataLight 轻量化技术方案（新仓库 + 分模块，完全重构）

**版本**：1.0  
**日期**：2026-04-26  
**状态**：设计稿（待评审后进入实现计划）  
**与上游关系**：不延续 monolithic `open-dataflow` 包结构；**方案 C — 新独立仓库**承载全部代码，仅将原 DataFlow 作行为与算子**参考**（不强制 fork 保历史）。

**本轮明确排除**：**Word（.doc/.docx）** 作为语料或转换输入；若未来需要，以单独 ADR 扩展摄取层，不阻塞当前架构。

---

## 1. 目标与成功标准

### 1.1 产品目标

构建 **DataLight**：一条从 **源文档（URL 或本地 PDF 目录）** 到 **「可用于 SFT 或 RAG 的、经生成 / 精炼 / 评估 / 过滤」** 的流水线，在 **依赖、部署与认知负担** 上显著轻于全量 DataFlow。

### 1.2 成功标准（可验证）

- **摄取层**：对 **HTTP(S) URL** 与 **目录下 PDF** 产出 **Markdown**；**目录输入时输出目录与相对结构一致**（见 §3.2）。  
- **数据层**：仅消费 **已生成的 `.md` 树** 或等价的清单索引；各阶段 **可独立运行、可复现**（记录模型名、提示词版本、配置哈希）。  
- **工程**：核心依赖清晰；`pip install` 分 **minimal / llm / mineru** 等 **extras**；**无** 对 WebUI、Ray、全量 `dataflow` 的硬依赖。  
- **可测试**：摄取与流水线核心逻辑可在 **无 GPU、可选无网络（fixture）** 下跑通单元测试。

---

## 2. 范围边界

| 包含 | 不包含（本设计稿） |
|------|-------------------|
| URL → Markdown（以 HTML/文本提取为主，见 §4） | Word、PPT、扫描件专用 OCR 管线（可后续加模块） |
| 目录中 PDF → Markdown | 原库全部算子、Agent、ECO、RayOrch |
| 基于 MD 的生成 / 精炼 / 评估 / 过滤 | 与上游仓库的 import 或 git 子模块耦合 |
| 统一清单（manifest）与错误策略 | 生产级多租户、权限与计费 |

---

## 3. 系统分解（分模块）

建议新仓库包名（示例，可替换）：`datalight`；顶层分三个 **可安装子包或命名空间**。

```
datalight/
  ingest/        # 仅「源 → Markdown + manifest」
  pipeline/     # 仅「Markdown/清单 → JSONL 各阶段」
  contracts/   # 共享：manifest schema、jsonl 记录 schema、错误码
  cli/          # 单入口，薄封装
```

### 3.1 模块 `datalight.contracts`

- **职责**：**唯一** 的跨模块类型与 **JSON Schema**（或 Pydantic 模型）定义，避免 `ingest` 与 `pipeline` 各写各的。  
- **交付物**：`IngestManifest`、`PipelineRunManifest`、`Record`（单条训练/RAG 样本 + metadata）的稳定字段集。

### 3.2 模块 `datalight.ingest`

**输入（二选一，互斥语义写死）：**

- **模式 A — 目录**：`ingest <input_dir> <output_dir>`。递归扫描，仅处理 **`.pdf`**；对每个 PDF 在 `output_dir` 下写 **与 `input_dir` 相对路径一致** 的 `*.md`（与源文件**同词干**，扩展名由 `.pdf` 变为 `.md`）。  
- **模式 B — URL**：`ingest --url <url> <output_dir>`。在 `output_dir` 下写 **约定子树**，例如 `urls/<slug_or_hash>/source.md`（**无法**与模式 A 的「镜像目录」用同一套路径规则，必须在 CLI 与文档中说明；manifest 中标注 `source_kind: "url"`）。

**不处理**：本阶段 **不** 解析 Word；若目录中出现 `.docx` 可 **记录 skip** 并写入 manifest，不失败整批（可配置为 strict）。

**输出**：  
- **Markdown 文件树**（符合上述规则）。  
- **`ingest_manifest.json`**（或 JSONL 一行一条文件）：`source_path`、`output_md_path`、`status`（ok / skipped / failed）、`error_code`、`sha256`（对源文件或拉取体）、`backend`（见 §4）。

**依赖控制**：`trafilatura`（URL/HTML）与 **可插拔的 PDF 后端**（见 §4）分别放入 extras。

### 3.3 模块 `datalight.pipeline`

- **输入**：`ingest` 产出的根目录 + `ingest_manifest.json`（**推荐** 总是带清单，避免扫盘歧义）。  
- **四阶段**（**顺序**固定；每阶段读写独立子目录，便于删除重跑）：  
  1. **generate**：`md/` → `generated/`（如 chunk + 问题生成，JSONL）  
  2. **refine**：`generated/` → `refined/`  
  3. **eval**：`refined/` → `scored/`（每样本有分数/理由）  
  4. **filter**：`scored/` → `export/`（阈值与规则，**最终** SFT / RAG 用 JSONL）  
- **实现约束**：每阶段 = **一个明确 CLI 子命令** + 共享「读上阶段、写下阶段」的 I/O 助手；**不** 引入原仓库的全局 `OPERATOR_REGISTRY` 除非有充分理由；若保留「算子」概念，则 **新 registry 仅服务本包**。

### 3.4 模块 `datalight.cli`

- 单入口，例如 `datalight ingest ...`、`datalight pipeline run --stage all|generate|...`。  
- 配置：优先 **YAML/ TOML 文件** + 环境变量（API key），**不** 依赖原 WebUI。

---

## 4. 摄取技术选型（无 Word）

### 4.1 URL

- 默认：若响应为 `text/html`，**trafilatura** `fetch_url` + `extract(..., output_format="markdown")`。  
- 若响应为 `application/pdf`：下载至临时或目标目录，再走 **与本地 PDF 相同** 的 PDF 后端。  
- 网络错误、非 HTML 非 PDF：写入 manifest `failed` + 错误码，不阻断（除非 `--fail-fast`）。

### 4.2 PDF

- **主路径**：**MinerU** 作为 **可选 extra**（API、本地 CLI 或受支持的后端三选一在配置中指定）—— 行为对齐原 `mineru_operators` 思想，**实现为新仓库内独立适配器类**，不复制原 `DataFlowStorage` 依赖。  
- **可选回退**（可后续迭代）：**仅** 在文档中写明的轻量回退（如纯文本 `pypdf`）用于无 GPU/无 MinerU 环境；**默认质量策略以 MinerU 为准。**

本设计 **不** 在首版强制图片类 PDF 的完美公式还原；以「结构良好的 Markdown + manifest」为交付。

---

## 5. 数据流与可复现性

- **ingest** 的 manifest 与 **pipeline** 的每阶段运行日志（`run_manifest.json`）应包含：工具版本、配置哈希、时间戳。  
- **filter** 输出的每条记录至少含：`source_md`、各阶段模型名、**prompt 模板版本 id**、分数、是否进入 export。

---

## 6. 错误与退出约定

- **批处理默认**：单文件失败不导致进程码非 0 除非 `--fail-fast`；汇总在 manifest 中。  
- **CI 建议**：`--fail-fast` 用于小数据集回归。

---

## 7. 与 DataFlow 的关系（方案 C）

- **代码**：**新仓库**；不保留原 `dataflow` 包名作为主入口。  
- **知识迁移**：**人工** 从 `dataflow/operators/knowledge_cleaning/generate/mineru_operators.py` 等文件 **借鉴** URL/PDF/MinerU 调用与边界条件；**不** 通过 `git subtree` 拉取整条历史，除非项目维护者另有决定。  
- **许可证**：新仓库**沿用** Apache-2.0 或与上游及依赖（MinerU 等）兼容的协议；在 `NOTICE` 中致谢 OpenDCAI/DataFlow。

---

## 8. 测试策略

- **ingest**：fixture 小 PDF、录制的 `responses` HTML、mock MinerU API（或 CLI dry-run 接口若存在）。  
- **pipeline**：每阶段用 **固定** 小 JSONL 输入/黄金输出；LLM 调用 **mock** 或 vcr。  
- **合同**：`contracts` 的 schema **契约测试**（反序列化、必填字段）。

---

## 9. 风险与未决项（首版不阻塞，仅登记）

- MinerU 商业 API 的速率与费用：需在 README 中提示。  
- 仅 PDF + URL 时，**学术 PDF** 与 **网页** 的「引用、脚注」在 MD 中表现差异大；RAG 切分策略放在 **pipeline generate/refine** 中调参。  
- Word 若将来支持：新 ADR，独立 `ingest.backends.word`，默认 extra。

---

## 10. 发布与版本

- **SemVer**；`0.1.0` = ingest 目录+URL + 四阶段 pipeline 骨架 + 可跑通假数据/ mock。  
- **Changelog** 中区分 **breaking**（manifest/JSONL 字段）与实现细节。

---

## 11. 文档自审（本稿）

- 已消除 Word 作为语料的要求；**明确** 目录镜像仅针对 PDF。  
- URL 与目录两种输入的路径规则**无歧义**（单 URL 使用单独子树）。  
- 范围与全量 DataFlow 的**切割**在 §7 写清。  
- 无遗留「TBD」阻塞实现；**未决项** 已归入 §9，不混进硬性需求。

**下一步（按 brainstorming 工作流）**：你审阅本稿；通过后由 **writing-plans** 生成 `docs/superpowers/plans/` 下的分任务实现计划，并在 **独立 worktree/新仓** 中执行。
