from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NotRequired, TypedDict


@dataclass
class MarkdownQAPipelineResult:
    """单跳 QA 主流水线产物路径集合"""

    # Markdown 切块结果（每行一个 chunk record）
    chunks_path: Path
    # 单跳 QA 生成结果（每行一个 QA record）
    generated_path: Path
    # QA 评估打分结果（在 generated 基础上追加评分字段）
    scored_path: Path
    # 最终训练导出文件（Alpaca 风格 JSONL）
    export_path: Path
    # 可选：扩写后的 QA 文件（开启 expand_qa 时生成）
    expanded_path: Path | None = None
    # 可选：附带 think 的 QA 文件（开启 add_think 时生成）
    think_path: Path | None = None


@dataclass
class MarkdownMultiHopQAPipelineResult:
    """多跳 QA 主流水线产物路径集合"""

    # Markdown 切块结果（每行一个 chunk record）
    chunks_path: Path
    # 多跳上下文构建结果（每行一个 context record）
    contexts_path: Path
    # 多跳 QA 生成结果（每行一个 QA record）
    generated_path: Path
    # 最终训练导出文件（Alpaca 风格 JSONL）
    export_path: Path


@dataclass
class QAExpansionPipelineResult:
    """扩写流水线输入/输出路径"""

    # 扩写前 QA JSONL 路径
    input_path: Path
    # 扩写后 QA JSONL 路径
    output_path: Path


@dataclass
class QAThinkingPipelineResult:
    """think 流水线输入/输出路径"""

    # 加 think 前 QA JSONL 路径
    input_path: Path
    # 加 think 后 QA JSONL 路径
    output_path: Path


# QA 跳数类型：单跳 / 多跳
HopType = Literal["singlehop", "multihop"]


class QAChunkRecord(TypedDict):
    """切块阶段 record 结构"""

    # 来源 markdown 文件绝对/相对路径
    source_md: str
    # chunk 在源文档中的顺序索引（从 0 开始）
    chunk_index: int
    # 当前 chunk 的原始文本
    chunk_text: str


class QAMultiHopContextRecord(QAChunkRecord):
    """多跳上下文构建阶段 record 结构"""

    # 推理链第 1 句（前提）
    premise: str
    # 推理链第 2 句（中间结论）
    intermediate: str
    # 推理链第 3 句（结论）
    conclusion: str
    # 其余可用上下文句子
    related_contexts: list[str]
    # 多跳生成阶段使用的统一上下文字段
    context: str
    # 实际用于构建 context 的句子数量
    supporting_sentence_count: int


class QABaseRecord(QAChunkRecord):
    """统一后的 QA 基础结构（单跳/多跳共用）"""

    # 生成的问题文本（统一主字段）
    question: str
    # 生成的答案文本（统一主字段）
    answer: str
    # 生成该 QA 的核心上下文（统一主字段）
    context: str
    # 跳数类型：singlehop 或 multihop
    hop_type: HopType
    # 推理步骤（单跳通常为空列表）
    reasoning_steps: list[dict[str, str] | str]
    # 支撑事实列表（单跳通常为空列表）
    supporting_facts: list[str]
    # QA 类型标签（如 singlehop/privacy/...）
    qa_type: str
    # taxonomy 一级分类（taxonomy 流程产出）
    level1_name: NotRequired[str]
    # taxonomy 二级分类（taxonomy 流程产出）
    level2_name: NotRequired[str]
    # taxonomy 任务类型（taxonomy 流程产出）
    task_type: NotRequired[str]
    # taxonomy 推理风格（taxonomy 流程产出）
    reasoning_style: NotRequired[str]


class QAScoredRecord(QABaseRecord):
    """在基础 QA 结构上增加评估评分字段"""

    # 问题质量分数
    question_quality_grade: float | int
    # 问题质量反馈
    question_quality_feedback: str
    # 答案对齐分数（是否直接回答问题）
    answer_alignment_grade: float | int
    # 答案对齐反馈
    answer_alignment_feedback: str
    # 答案可验证性分数
    answer_verifiability_grade: float | int
    # 答案可验证性反馈
    answer_verifiability_feedback: str
    # 下游训练/RAG 价值分数
    downstream_value_grade: float | int
    # 下游价值反馈
    downstream_value_feedback: str


class QAExpandedRecord(QAScoredRecord):
    """在评分结构上增加扩写阶段字段"""

    # 扩写问题（可选；扩写失败时缺失）
    expanded_question: NotRequired[str]
    # 扩写答案（可选；扩写失败时缺失）
    expanded_answer: NotRequired[str]
    # 扩写模式/类型（detail/contextual/reasoning）
    expansion_type: NotRequired[str]
    # 扩写备注
    expansion_notes: NotRequired[str]
    # 扩写状态：ok 或 failed
    expansion_status: str
    # 扩写失败错误信息（失败时出现）
    expansion_error: NotRequired[str]


class QAThinkingRecord(QAExpandedRecord):
    """在扩写结构上增加 think 阶段字段"""

    # 生成的 think 文本（失败时通常为空字符串）
    think: str
    # think 状态：ok 或 failed
    think_status: str
    # think 失败错误信息（失败时出现）
    think_error: NotRequired[str]
    # 原始答案备份（非 expanded 分支）
    original_answer: NotRequired[str]
    # 原始扩写答案备份（expanded 分支）
    original_expanded_answer: NotRequired[str]
