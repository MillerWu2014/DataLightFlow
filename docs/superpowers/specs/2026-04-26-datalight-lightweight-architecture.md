# DataLight 轻量化技术方案（新仓库 + 分模块，完全重构）

**版本**：1.2  
**日期**：2026-04-26  
**状态**：设计稿（已部分冻结决策，可进入 **ingest MVP** 实现计划）  
**与上游关系**：不延续 monolithic `open-dataflow` 包结构；**方案 C**；新代码以独立包 `datalight` 为主。 **工程落点：仓库名 `DataLightFlow`；** 原 open-dataflow/DataFlow 形态代码**迁**至本仓 `**remote/`** 子目录，与 `datalight` 新实现**物理隔离**（仅作参考或迁移对照，不随新包发布）。

**1.1 变更摘要（相对 1.0）**：**摄取层文档解析仅采用本地 MinerU**；**禁止** MinerU **商业/云端 API** 路径；删除「pypdf 等回退与 API 三选一」表述；**§4** 扩写为可落地的实现规格（CLI、目录布局、配置与错误处理）。

**1.2 变更摘要（相对 1.1）** — **已确认决策**：(1) **首版实施范围 = 选项 A**：先交付 **ingest MVP**（目录 + 直链 PDF URL → Markdown + 清单），**pipeline 四阶段** 仅占位/薄封装/简单 echo，**全量 SFT/RAG 流水线** 放第二迭代。(2) **清单格式**：`ingest_manifest` **仅使用 JSONL**（**一条输入/一次 URL 落盘 = 一行 JSON 记录**；文件名建议 `ingest_manifest.jsonl`）。(3) **URL 模式输出子树**：路径 **含原始 host**（经 **文件系统安全化**），见 **§3.2.1**。(4) **MinerU 基线**：开发与 CI **对齐当前 PyPI/官方最新的 MinerU 稳定版**（实现 README 中写明「安装最新」并**在 `manifest` 中记录**实际 `mineru_version`；若后续需钉死，再改 lockfile/约束）。

**本轮明确排除**：**Word（.doc/.docx）** 作为语料或转换输入；若未来需要，以单独 ADR 扩展摄取层，不阻塞当前架构。

---

## 1. 目标与成功标准

### 1.1 产品目标

构建 **DataLight**：一条从 **源文档（URL 或本地 PDF 目录）** 到 **「可用于 SFT 或 RAG 的、经生成 / 精炼 / 评估 / 过滤」** 的流水线，在 **依赖、部署与认知负担** 上显著轻于全量 DataFlow。

### 1.2 成功标准（可验证）

- **摄取层**：在 **仅使用本地 MinerU** 作版面/文档→Markdown 解析（见 **§4**）的前提下，对 **可解析输入** 产出 **Markdown**；**目录输入时输出目录与相对结构一致**（见 §3.2）。  
- **数据层（第二迭代）**：仅消费 **已生成的 `.md` 树** 与 `**ingest_manifest.jsonl`**；各阶段 **可独立运行、可复现**（记录模型名、提示词版本、配置哈希）。**首版（选项 A）** 不验收完整四阶段，仅可验收 **ingest 输出 + pipeline 占位**。  
- **工程**：核心依赖清晰；`pip install` 分 **minimal / llm / ingest-mineru-local** 等 **extras**；**无** 对 WebUI、Ray、全量 `dataflow` 的硬依赖。  
- **可测试**：摄取与流水线核心逻辑可分层测试；**MinerU 路径** 以 **进程级/录制日志** 或 **集成环境（安装 mineru 的小 CI job）** 为主（见 §8）。

---

## 2. 范围边界


| 包含                                                                                                                                                | 不包含（本设计稿）                                                                    |
| ------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| **本地 MinerU** 将 **PDF 与 MinerU 本地支持的图片**（如 `.png/.jpg/.jpeg/.webp/.gif` 等，以 **MinerU 官方 CLI 能力** 为准）转为 Markdown；**直链 PDF 的 URL** 下载后走同一套本地 MinerU | **MinerU 云/商业 API**、**FlashMinerU / Ray 分布式** 等非「单机本地 `mineru` 进程」路径         |
| **HTML 为首页的普通网页 URL** 的**正文提取**                                                                                                                   | **首版不纳入**（其不是 MinerU 输入；若未来需要，单独 ADR，可用 trafilatura 等，与「MinerU 文档解析层」**解耦**） |
| 目录中 **PDF/图片** → Markdown + `**ingest_manifest.jsonl`**                                                                                           | Word、PPT、专用 OCR 管线（可后续加模块）                                                   |
| **首版（选项 A）**：**ingest MVP** 完整可验收；`datalight.pipeline` **仅占位/echo**                                                                               | **首版不验收** 业务级 **generate / refine / eval / filter**（第二迭代再实现，见 §3.3）          |
| 仓内 `**datalight/`** 新包与 `**remote/**` 中 **原 DataFlow 形态参考代码** 物理分野                                                                                | 新包 **运行时** import `remote/` 为硬依赖；与上游 **git 子模块** 强绑定                         |
| 统一清单行级字段与错误码（JSONL）                                                                                                                               | 生产级多租户、权限与计费；原库全部 Agent/ECO/RayOrch                                          |


---

## 3. 系统分解（分模块）

建议新仓库包名（示例，可替换）：`datalight`；顶层分 **可安装子包或命名空间**。

```
datalight/
  contracts/    # 共享：manifest schema、jsonl 记录 schema、错误码
  ingest/       # 仅「源 → Markdown + manifest」；核心为 miners.local 适配器
  pipeline/     # 仅「Markdown/清单 → JSONL 各阶段」
  cli/          # 单入口，薄封装
```

### 3.1 模块 `datalight.contracts`

- **职责**：**唯一** 的跨模块类型与 **JSON Schema**（或 Pydantic 模型）定义。  
- **交付物**：`IngestManifest`、`PipelineRunManifest`、`Record` 的稳定字段集。  
- **摄取元数据**：`parser` 固定为 `mineru_local`；**附加** `mineru_version`（`mineru --version` 或 importlib 可读）、`mineru_backend`（如 `vlm-auto-engine`）、`cli_invocation_id`（可选，便于对日志）。

### 3.2 模块 `datalight.ingest`

**输入：**

- **模式 A — 目录**：`ingest <input_dir> <output_dir>`。递归扫描，对扩展名属于 **白名单** 的文件处理（**至少** `.pdf` 与 **MinerU CLI 所支持的图片扩展**；白名单在实现中与 MinerU 发行版**对齐并写进 README**）。对每个匹配文件在 `output_dir` 下写 **与 `input_dir` 相对路径一致** 的 `*.md`（**与源文件同主文件名**，扩展名改为 `.md`）。  
- **模式 B — URL**：`ingest --url <url> <output_dir>`。**首版只保证**：  
  - **Content-Type 为 `application/pdf`（经 HEAD/GET 判断）** 时：下载为临时/缓存文件后，走 **与模式 A 相同** 的 **本地 MinerU** 单文件解析，再在 `output_dir` 的 **§3.2.1** 约定子树中落盘（主 Markdown 文件名为 `source.md`），`source_kind: "url"`。  
  - **纯 HTML 响应**：**不解析**，manifest 记 `failed` + 错误码 `E_URL_HTML_NOT_SUPPORTED`（或 `skipped` + 原因），除非后续 ADR 增加「非 MinerU 的 HTML 旁路」。

**不处理**：Word；若目录出现 `.docx` 可 **记录 skip**（可配置 strict）。

**输出**：**Markdown 文件树** + **`ingest_manifest.jsonl`（每行一条 JSON 记录，UTF-8）**；字段含 `source_path`、`output_md_path`、`status`、`error_code`、`sha256`（对源/下载体）、`parser: "mineru_local"`、以及 §4.4 的 **结构化解码字段**。**末行** 是否写 **可选** 汇总行由实现定；**首版** 以「**每输入文件/URL 一行**」为最低要求。

**依赖控制**：**摄取核心** 的「文档→MD」**仅** 依赖 **本机可执行的 `mineru` CLI**（由 `mineru` PyPI/发行说明安装）；**不** 将 **trafilatura** 列入 ingest 的**默认/硬依赖**（与 HTML 未纳入 v1.1 一致）。

#### 3.2.1 URL 模式下的输出子目录规则（**含原 host**）

- **根**：`urls/` 位于 `output_dir` 下。  
- **第一级子目录 = 原始 URL 的 host，经文件系统安全化**：对 `urlparse(url).netloc` 作变换，例如转小写、**端口保留但将 `:` 改为 `_`**（如 `example.com:8443` → `example.com_8443`）、**禁止** 出现路径分隔符；若需 **punycode** 则使用 ASCII 形式，避免跨 OS 问题。  
- **第二级子目录**：对 **完整 URL 字符串** 计算短指纹，以防同 host 多 PDF 互相覆盖，例如 **SHA-256 十六进制前 16 位**；目录名 = 该指纹（具体宽度在 `contracts` 或 README 中定 **唯一常量**）。  
- **落盘主文件**：`<output_dir>/urls/<host_sanitized>/<url_fingerprint>/source.md`。  
- **manifest 行** 中除通用字段外，建议带 `url_host`（原始 netloc 明文）、`url_fingerprint`（与目录名一致），便于人读与对账。

#### 3.2.2 仓库名与 `remote/` 布局

- **实施与发布仓库名**：**`DataLightFlow`**。  
- **原 open-dataflow / DataFlow 形态参考代码** 置于 **`remote/`** 子目录，**不** 作为 `datalight` 安装分发的**运行时**依赖；**仅** 作对照、许可证或迁移期查阅。新实现位于 **`datalight/` 包**（**具体子路径** 在实现计划的 writing-plans 中固定）。

### 3.3 模块 `datalight.pipeline`（首版 **选项 A**）

- **首版**：**不实现** 业务级 generate / refine / eval / filter；**允许** `pipeline noop` / 说明性入口，**或** **echo/占位**（如读 `ingest_manifest.jsonl` 行并写出到 `export/.placeholder.jsonl`）**仅** 为验证 I/O 与 `contracts` 解析。  
- **第二迭代**：**输入** = `ingest` 根目录 + `ingest_manifest.jsonl`；**四阶段** = generate → refine → eval → **filter** → `export/` 下**最终** JSONL。

### 3.4 模块 `datalight.cli`

- 单入口，`datalight ingest` **必须** 暴露与本地 MinerU 相关的 **显式配置**（见 §4.3），例如：  
`mineru-backend`、`mineru-source=local`（写死为 local，不提供 cloud）、`intermediate-base`、`timeout-seconds` 等。  
- **禁止**：从 CLI/环境变量读取 **MinerU 云 API Key** 作为**默认解析路径**（首版**不提供**该代码路径；若出现遗留参数，**拒绝启动** 或**明确报 deprecated**）。

---

## 4. 摄取层：仅本地 MinerU（实现规格）

本节为 **v1.1+ 硬性约定**（v1.2 在清单格式与仓库布局上**补充** §3.2，不改动 §4.2 子进程契约）：**所有 PDF/图片/直链 PDF 的版面解析，仅通过本机 `mineru` 子进程完成**；**不使用** [MinerU Net API](https://mineru.net/) 等 **商业/托管 API**；**不实现** 基于 HTTP 的 `MinerUBatchExtractorViaAPI` 等同类逻辑。

### 4.1 总原则

1. **单一后端**：`datalight.ingest.backends.mineru_local`（类名可调整）是 **唯一** 的「版式文档 → Markdown」实现；**不** 提供 pypdf / pdfplumber 等**替代解析链**作为回退。
2. **可观测**：每次子进程**必须** 捕获 **stdout/stderr**（可配置截断长度），失败时写入 manifest 的 `error_detail`（脱敏后）。
3. **可复现**：manifest 中记录 `mineru` **版本**、**`-b` backend**、**`--source local`**，以及**输出目录的规范化路径**（见 4.2）。

### 4.2 子进程调用契约（与 DataFlow 参考实现对齐）

实现应 **参考**（非复制 `DataFrame` 逻辑）`FileOrURLToMarkdownConverterLocal._batch_parse_pdf_with_mineru` 的调用形态，并 **固定** 以下契约：

- **可执行体**：`mineru` 必须在 `PATH` 中，或通过配置项 `MINERU_EXECUTABLE` 指定。启动前执行**存在性检查**，缺失则 **FATAL**（错误码 `E_MINERU_NOT_FOUND`），并打印安装指引（链向 MinerU 官方文档）。  
- **每文件**（或受控的**小批**，若后续优化）一次调用，**推荐** 参数形态：
  ```text
  mineru -p <absolute_source_path> -o <intermediate_dir> -b <backend> --source local
  ```
  其中：  
  - `**-p**`：单文件，本地路径，**PDF 或 MinerU 支持的图片**。  
  - `**-o`**：`intermediate_dir`：**本次 ingest 可配置的中间根**（如 `<output_dir>/.datalight/mineru_work` 或用户指定），**必须** 对并发/多次运行**安全**（每文件可再分子目录避免冲突，见 4.5）。  
  - `**-b`**：backend 字符串，**默认** 与 MinerU 当前发行版推荐一致（如 `vlm-auto-engine` 等，**以配置为准**，文档中列出**受支持枚举**）。  
  - `**--source local`**：写死，表明 **仅本地** 资源与模型路径模式。
- **成功输出路径（解码规则）**：在参考实现中，Markdown 主文件路径形态为：  
  `os.path.join(intermediate_dir, <stem>, <backend_value>, f"{<stem>}.md")`  
  即：**第一级子目录 = 无扩展名的文件名**；**第二级 = backend 名**；**其下为同主名 `.md`**。  
  **DataLight 实现** 应用 **相同解码规则** 从 `intermediate_dir` 定位产出的 `*.md`，再 **复制或移动** 到**用户可见**的**镜像输出路径**（与 §3.2 的 `output_dir` 相对结构一致）。若 MinerU 小版本**变更了目录树**，**适配器** 应 **单点** 更新（`resolve_mineru_markdown_path(intermediate, stem, backend) -> Path`）。
- **失败判定**：`subprocess` **returncode != 0** 视为该文件 **failed**；**returncode == 0** 但 **未找到** 期望的 `.md` 视为 **failed**（`E_MINERU_OUTPUT_MISSING`），并将 stderr 摘要写入 manifest。
- **超时**：每文件**必须** 可配置超时（如默认 1h 或按页数估计，**具体数值在实现时写入模块常量并允许 CLI 覆盖**），超时**终止**子进程，记 `E_MINERU_TIMEOUT`。

### 4.3 模型与运行环境

- **模型来源**：**仅** [MinerU 官方「本地 / `--source local`」文档](https://opendatalab.github.io/MinerU/) 所述方式（如 `mineru-models-download`、本地 cache 目录）。  
- **MinerU 版本基线**（**已确认**）：开发与文档 **以当前时期 PyPI / 官方** **最新稳定版** `mineru` 为准；`ingest_manifest.jsonl` 每行**必须** 记录**实际** `mineru_version`（`mineru --version` 等）。**不在 spec 中钉死** 某具体版本号，防滞后；**CI** 上可用 `pip install -U mineru` 或固定「上周最新」——由 **实现计划** 定是否 pin。  
- **配置项**（在 ingest 侧暴露，**与 `remote/` 中历史 DataFlow 的** `mineru_model_path` 等**概念可对齐** 但**独立** 命名空间）：  
  - `model_path` / `model_cache`：与 MinerU 环境变量或 CLI 约定**一致**（实现时列一张表，避免两套魔法字符串）。  
  - **GPU**：不强制在 ingest 内管理 CUDA 可见性；**文档** 说明需与 MinerU 后端要求一致（VLM 后端常需 **GPU/显存**）。**无 GPU 机器** 上的行为以 MinerU 官方能力为准，DataLight **如实** 记录失败原因。

### 4.4 Manifest 中建议增加的 MinerU 专用字段

除通用字段外，**每条成功记录** 建议含：

- `mineru_version`  
- `mineru_backend`  
- `intermediate_relpath`（相对 work root，便于排障；可选）  
- `duration_ms`（子进程墙钟时间）

**失败记录** 建议含：截断的 `stderr_tail`、`returncode`（若有）。

### 4.5 并发与中间文件

- **默认串行** 每文件一个 `mineru` 进程，避免 GPU 显存打满；**可选** `MAX_PARALLEL`（>1 时**文档** 警告显存与 MinerU 行为）。  
- **清理策略**：`--keep-intermediate` 保留中间树；否则在成功落盘**用户 md** 后**可删除**该文件对应 `intermediate` 子树（**失败时保留** 便于查 log）。

### 4.6 URL 下载（仍仅服务 MinerU）

- **HEAD/GET** 检测 `Content-Type`；**仅**当判定为 **PDF** 时 **GET** 保存到**唯一临时路径** 或 `cache` 后调用 **4.2** 的同一适配器。  
- **不** 对 HTML 做正文提取；见 §2 / §3.2 错误码。

---

## 5. 数据流与可复现性

- **ingest** 使用 **`ingest_manifest.jsonl`**，每行需含：**MinerU 版本**、**backend**、**配置哈希/时间**（可放在每行或运行级单独文件，**首版** 以每行+CLI 起止时间戳为**最低** 要求）。  
- **pipeline 第二迭代** 的 `run_manifest.json` 等另行规定；**首版** 不强制。

---

## 6. 错误与退出约定

- **批处理默认** / `**--fail-fast`**（同 1.0）。  
- **建议错误码表**（实现时落在 `contracts`）：`E_MINERU_NOT_FOUND`、`E_MINERU_FAILED`、`E_MINERU_OUTPUT_MISSING`、`E_MINERU_TIMEOUT`、`E_URL_HTML_NOT_SUPPORTED`、**Word skip** 等。

---

## 7. 与 DataFlow 的关系（方案 C + **DataLightFlow**）

- **代码**：在 **`DataLightFlow`** 仓内，**`datalight`** 为**新主包**；**原** DataFlow 形态参考代码置于 **`remote/`**（**已确认** 布局），不替代 `datalight` 入口。  
- **知识迁移**：**人工** 自 `remote/.../mineru_operators.py`（或迁档前之 `dataflow/operators/knowledge_cleaning/generate/mineru_operators.py`）中 **`FileOrURLToMarkdownConverterLocal`** 分支 **只借鉴** 本地子进程与输出路径解码；**不** 迁 API 版、**不** 直接依赖原 `DataFlowStorage` 的 `run`。  
- **许可证**（同 1.0）；`remote/` 内第三方头文件/许可 **保留** 原样。

---

## 8. 测试策略

- **ingest + MinerU**：**单元** 用 **子进程 mock**（注入假 `mineru` 可执行，验证参数与路径解码）；**集成** 在具备 **真实** **当前最新** `mineru` + 小 PDF 的环境跑 **一条 golden**：产出 `.md` 与 **`ingest_manifest.jsonl`** 行级字段。  
- **不** 以「Mock 商业 API」作为摄取主测试（该路径**已删除**）。  
- **URL 输出路径**：**单元** 测 **URL → `urls/<host_sanitized>/<fingerprint>/source.md`** 的规范化（不下载）。  
- **pipeline**：**首版** 可 **仅** 测 `noop`/占位 JSONL 写入；**第二迭代** 再扩。  
- **contracts**：`ingest` 行与 **url 字段** 反序列化、必填字段；**fingerprint 宽度** 常量与文档一致。

---

## 9. 风险与未决项

- **本机显存/依赖**：VLM 类 backend 对 GPU 与**磁盘**（模型包）有要求，需在 README **前置说明**。  
- **MinerU 小版本** 变更输出目录结构的风险：由 **4.2 单点解析函数** + **一条集成测试** 缓解。  
- **HTML URL 需求**若出现：**单独 ADR**，**不得** 与 `mineru_local` 混为同一套「单一后端」故事，避免依赖膨胀。  
- Word：未来独立 ADR。

---

## 10. 发布与版本

- **SemVer**；**1.1**：摄取语义（仅本地 MinerU、去 API、HTML URL 不纳入）。**1.2**：**选项 A**、**`ingest_manifest.jsonl`**、**URL 含 host 子目录**、**DataLightFlow + `remote/`**、**MinerU 用最新**、**pipeline 首版占位**。  
- **Changelog** 中区分 **breaking**（如 JSONL 与 URL 子树相对单 JSON 的迁移）。

---

## 11. 文档自审（1.2）

- **选项 A**、**DataLightFlow**、**`remote/`**、**JSONL 清单**、**URL 含 host**、**MinerU 最新** 均有显式条文化，与 §1– §7 **一致**。  
- **§3.2.1** 已消除 `slug_or_hash` 歧义。  
- **首版/第二迭代** 责任边界在 pipeline 上**清楚**。  
- 仍由 **实现计划** 钉死：指纹宽度常量、`ingest` 行是否含运行级元数据、CI 是否 pin `mineru` 小版本。

**下一步（按 brainstorming 工作流）**：由 **writing-plans** 在 **`DataLightFlow`** 仓生成分任务实现计划（`datalight` 新包 + **`remote/`** 迁移动作 + **ingest MVP** 优先），再按 PR 切分实现。