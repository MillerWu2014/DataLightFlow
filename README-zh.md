# DataLightFlow

DataLightFlow 是一个面向 LLM 训练与 RAG 数据准备的轻量化数据流水线工具。它聚焦两件事：

1. 将 PDF、图片、直接 PDF URL 通过本地 MinerU 转换为 Markdown。
2. 基于 Markdown 生成、评估、过滤、扩写、补充 `think` 字段，并导出可用于训练或 RAG 的 QA 数据。

项目目标是保留 DataFlow 中有价值的 Pipeline / Operator 思路，但不依赖原 `dataflow` 运行时，保持模块独立、流程简单、JSONL 可追踪。

## 功能概览

### 文档摄取

- 支持目录批量摄取 PDF 和图片：`.pdf`、`.png`、`.jpg`、`.jpeg`、`.webp`、`.gif`
- 支持直接 PDF URL 摄取
- 使用本地 MinerU CLI，不调用 MinerU 商业 API
- 输出 Markdown 和 `ingest_manifest.jsonl`
- 目录输入会镜像输出目录结构
- URL 输出路径包含 host 和 URL 指纹

暂不支持：

- Word / PPT 文档解析
- HTML 网页正文抽取

### QA 数据生成

- Markdown 分块
- 单跳 QA 生成
- 多跳 QA 生成
- 默认中文 QA，支持英文和自动跟随上下文语言
- 四维 QA 质量评估
- QA 过滤
- QA 扩写
- `think` 字段增强
- Alpaca JSONL 导出
- QAExtractor 风格格式转换
- 轻量去重和多样性过滤
- Depth / Width QA Operator

## 当前架构

```text
src/datalight/
  cli.py
  contracts/
  ingest/
  pipeline/
    core.py
    qa/
      agentic.py
      expansion.py
      filters.py
      formatters.py
      language.py
      llm.py
      multihop.py
      operators.py
      runner.py
      thinking.py
```

核心抽象是极简 `Operator` / `Pipeline`：

```python
Record = dict[str, Any]

class Operator:
    def run(self, rows: list[Record]) -> list[Record]:
        ...
```

所有中间数据都使用 JSONL，便于调试、断点恢复和后续扩展。

## 环境准备

建议使用 Python 3.10+。

安装项目依赖：

```bash
pip install -r requirements.txt
pip install -e .
```

如果只在源码目录中直接运行，也可以使用：

```bash
PYTHONPATH=src python -c "from datalight.service import version; print(version())"
```

### 配置 MinerU

DataLightFlow 通过本地 MinerU CLI 进行 PDF / 图片解析。

如果 `mineru` 不在 `PATH` 中，需要设置：

```bash
export MINERU_EXECUTABLE=/Users/miller/miniconda3/envs/mineru/bin/mineru
```

检查 CLI：

```bash
datalight version
```

或：

```bash
PYTHONPATH=src python -c "from datalight.service import version; print(version())"
```

### 配置 LM Studio

QA 生成、评估、扩写、think 增强都通过 OpenAI-compatible API 调用 LLM。默认适配本地 LM Studio：

```text
Base URL: http://127.0.0.1:1234/v1
Model: gemma-4-31b-it
```

启动 LM Studio 服务后，可以通过 `--lmstudio` 使用本地模型。

### 配置文件

项目支持一个简化 YAML 配置文件，用于统一设置 MinerU 路径、默认输出根目录、LLM 连接参数、QA topic 和各阶段 system prompt。

复制模板：

```bash
cp configs/datalight.example.yaml configs/datalight.yaml
```

使用方式：

```bash
datalight pipeline markdown-qa \
  --config configs/datalight.yaml \
  --markdown ./demo.md
```

配置文件中每个 system prompt 可以显式使用 `{topic}` 占位符：

```yaml
qa:
  topic: OpenClaw 的架构、部署、渠道接入、Skills、安全与成本

llm:
  provider: lmstudio
  base_url: http://127.0.0.1:1234/v1
  model: gemma-4-31b-it

prompts:
  singlehop_system: |
    你只围绕以下 Topic 构建高质量问答对：
    {topic}
```

详细说明见：

```text
docs/配置文件说明.md
```

## 快速开始

### 1. PDF / 图片目录转 Markdown

```bash
datalight ingest directory ./input_pdfs ./outputs/markdown \
  --backend vlm-auto-engine \
  --timeout 3600
```

输出：

```text
outputs/markdown/
  ingest_manifest.jsonl
  <same-relative-path>.md
```

默认成功后会清理 MinerU 中间目录。如需保留：

```bash
--keep-intermediate
```

### 2. PDF URL 转 Markdown

```bash
datalight ingest url ./outputs/url_ingest \
  --url "https://example.com/paper.pdf"
```

输出路径形如：

```text
outputs/url_ingest/
  urls/<host>/<url_fingerprint>/source.md
  ingest_manifest.jsonl
```

### 3. Markdown 生成中文单跳 QA

```bash
datalight pipeline markdown-qa \
  --markdown ./outputs/markdown/demo.md \
  --output-dir ./outputs/qa_single \
  --lmstudio \
  --language zh \
  --chunk-words 512 \
  --question-num 1 \
  --min-score 3
```

主要产物：

```text
outputs/qa_single/
  chunks.jsonl
  qa_generated.jsonl
  qa_scored.jsonl
  qa_export.jsonl
```

`qa_export.jsonl` 为 Alpaca 风格：

```json
{
  "instruction": "Please answer the following question based on the provided information.",
  "input": "OpenClaw 与 ChatGPT 在数据控制方面有什么区别？",
  "output": "OpenClaw 数据完全本地，用户拥有所有数据；ChatGPT 的数据由 OpenAI 托管。",
  "source_md": "demo.md",
  "chunk_index": 0
}
```

### 4. Markdown 生成多跳 QA

```bash
datalight pipeline markdown-multihop-qa \
  --markdown ./outputs/markdown/demo.md \
  --output-dir ./outputs/qa_multihop \
  --lmstudio \
  --language zh \
  --chunk-words 800 \
  --min-context-sentences 3
```

主要产物：

```text
outputs/qa_multihop/
  chunks.jsonl
  multihop_contexts.jsonl
  qa_multihop_generated.jsonl
  qa_multihop_export.jsonl
```

多跳 context 会包含：

- `premise`
- `intermediate`
- `conclusion`
- `related_contexts`
- `multihop_context`

## 可选增强流程

### QA 扩写

扩写用于让已有 QA 更自然、更完整、更适合训练或 RAG。

独立运行：

```bash
datalight pipeline expand-qa \
  --input ./outputs/qa_single/qa_scored.jsonl \
  --output ./outputs/qa_single/qa_expanded.jsonl \
  --lmstudio \
  --mode detail \
  --language zh
```

支持模式：

- `detail`：扩写答案，补充背景、边界和解释
- `contextual`：改写问题，使其更自然、更贴近真实用户提问
- `reasoning`：补充简短推理说明，同时保持可验证

也可以接入单跳 QA 主流程：

```bash
datalight pipeline markdown-qa \
  --markdown ./outputs/markdown/demo.md \
  --output-dir ./outputs/qa_single \
  --lmstudio \
  --expand-qa \
  --expand-mode detail
```

扩写产物：

```text
qa_expanded.jsonl
```

新增字段：

- `expanded_question`
- `expanded_answer`
- `expansion_type`
- `expansion_notes`
- `expansion_status`

### Think 字段增强

`think` 增强会让 LLM 为已有 QA 生成一个推理说明字段，并根据该推理重构答案。

独立运行：

```bash
datalight pipeline add-think \
  --input ./outputs/qa_single/qa_expanded.jsonl \
  --output ./outputs/qa_single/qa_with_think.jsonl \
  --lmstudio \
  --language zh
```

也可以接入单跳 QA 主流程：

```bash
datalight pipeline markdown-qa \
  --markdown ./outputs/markdown/demo.md \
  --output-dir ./outputs/qa_single \
  --lmstudio \
  --expand-qa \
  --add-think
```

新增字段：

- `think`
- `think_status`
- `original_generated_answer` 或 `original_expanded_answer`

如果 LLM 不输出 `think`，则 `think` 字段为空字符串。

## 完整单跳 QA 示例

从 Markdown 直接生成、评分、过滤、扩写、补充 think，并导出：

```bash
datalight pipeline markdown-qa \
  --markdown ./outputs/markdown/demo.md \
  --output-dir ./outputs/qa_full \
  --lmstudio \
  --llm-model gemma-4-31b-it \
  --language zh \
  --chunk-words 512 \
  --question-num 1 \
  --min-score 3 \
  --expand-qa \
  --expand-mode detail \
  --add-think
```

输出：

```text
outputs/qa_full/
  chunks.jsonl
  qa_generated.jsonl
  qa_scored.jsonl
  qa_expanded.jsonl
  qa_with_think.jsonl
  qa_export.jsonl
```

最终导出会优先使用扩写后的问题和答案，并保留 `think`：

```json
{
  "instruction": "Please answer the following question based on the provided information.",
  "input": "OpenClaw 与 ChatGPT 在交互模式、运行环境和数据控制方面有哪些核心区别？",
  "output": "OpenClaw 与 ChatGPT 在这三个维度的核心区别如下：...",
  "source_md": "demo.md",
  "chunk_index": 0,
  "think": "先定位对比维度，再分别抽取交互模式、运行环境和数据控制信息。"
}
```

## 语言参数

所有 LLM 相关 QA 命令支持：

```bash
--language zh
--language en
--language auto
```

默认：

```text
zh
```

含义：

- `zh`：问题、答案、评分反馈、推理步骤使用中文
- `en`：强制英文
- `auto`：跟随上下文主语言

## 确定性测试模式

为了不依赖真实 LLM，所有 LLM 相关 CLI 都支持 `--responses-file`：

```bash
datalight pipeline markdown-qa \
  --markdown ./demo.md \
  --output-dir ./outputs/test \
  --responses-file ./responses.txt
```

`responses.txt` 使用单独一行 `---` 分隔多次 LLM 返回：

```text
Q: 什么是 OpenClaw？
A: 一个开源自托管 AI Agent 系统。
---
**Grading**: 5
**Feedback**: 问题清晰
---
**Grading**: 5
**Feedback**: 答案匹配
```

## 输出文件说明

### 摄取输出

```text
ingest_manifest.jsonl
```

记录每个输入文件或 URL 的解析状态：

```json
{
  "source_path": "...",
  "output_md_path": "...",
  "status": "ok",
  "parser": "mineru_local",
  "sha256": "...",
  "mineru_version": "...",
  "mineru_backend": "vlm-auto-engine",
  "source_kind": "file",
  "duration_ms": 1234
}
```

### 单跳 QA 输出

```text
chunks.jsonl
qa_generated.jsonl
qa_scored.jsonl
qa_expanded.jsonl       # 可选
qa_with_think.jsonl     # 可选
qa_export.jsonl
```

### 多跳 QA 输出

```text
chunks.jsonl
multihop_contexts.jsonl
qa_multihop_generated.jsonl
qa_multihop_export.jsonl
```

## QA 质量评估维度

`qa_scored.jsonl` 包含四组评分和反馈：

- `question_quality_grade` / `question_quality_feedback`
- `answer_alignment_grade` / `answer_alignment_feedback`
- `answer_verifiability_grade` / `answer_verifiability_feedback`
- `downstream_value_grade` / `downstream_value_feedback`

`--min-score` 会用于过滤低质量 QA。

## 编程接口示例

```python
from pathlib import Path

from datalight.llm import OpenAICompatibleLLMClient
from datalight.pipeline.qa.runner import run_markdown_qa_pipeline

llm = OpenAICompatibleLLMClient(
    base_url="http://127.0.0.1:1234/v1",
    model="gemma-4-31b-it",
)

result = run_markdown_qa_pipeline(
    markdown_paths=[Path("demo.md")],
    output_dir=Path("outputs/qa"),
    llm_client=llm,
    target_language="zh",
    expand_qa=True,
    add_think=True,
)

print(result.export_path)
```

## 测试

运行 focused QA 回归：

```bash
PYTHONPATH=src python -m pytest -c /dev/null \
  tests/datalight/test_markdown_qa_pipeline.py \
  tests/datalight/test_multihop_qa_pipeline.py \
  tests/datalight/test_qa_integrations.py \
  tests/datalight/test_qa_language.py \
  tests/datalight/test_qa_expansion.py \
  tests/datalight/test_qa_thinking.py -q
```

运行非 CLI 的 datalight 测试：

```bash
PYTHONPATH=src python -m pytest -c /dev/null tests/datalight --ignore=tests/datalight/test_cli.py -q
```

如果当前 Python 环境缺少 `typer`，CLI smoke 可使用包含 Typer 的 conda 环境运行。

## 设计文档

更完整的技术实现细节见：

```text
docs/技术实现方案.md
```

## 当前限制

- 暂不支持 Word / PPT 文档解析
- 暂不支持 HTML URL 正文抽取
- 多跳 QA 暂未接入扩写和 think 的一体化 CLI 参数
- Depth / Width QA 暂未暴露为 CLI 命令
- 去重目前是轻量文本相似度，未接入 embedding
- LLM 质量依赖本地模型能力和 prompt 遵循程度

## 路线图

- 批量 Markdown 目录级 QA 生成
- 多跳 QA 接入扩写和 think 增强
- Depth / Width QA 独立 CLI
- ShareGPT / ChatML 导出格式
- Embedding-based 去重与多样性采样
- LLM 调用缓存和断点续跑
- Markdown 清洗、表格结构化与更强的 chunk 策略
