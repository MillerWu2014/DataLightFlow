export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type PipelineType = "singlehop" | "multihop";
export type GeneratorType = "default" | "atomic" | "taxonomy";
export type Language = "zh" | "en" | "auto";
export type ExpandMode = "detail" | "contextual" | "reasoning";

export interface PipelineParamsSnapshot {
  language: Language;
  chunkWords: number;
  overlapWords: number;
  questionNum: number;
  minScore: number;
  atomicMaxPerTask?: number;
  expandQa: boolean;
  expandMode: ExpandMode;
  addThink: boolean;
  /** Agentic 深挖：在 qa_generated 之后调用 pipeline_depth_qa */
  addDepthQa: boolean;
  depthRounds: number;
  /** Agentic 扩宽：在 qa_generated 之后调用 pipeline_width_qa（输入需 ≥2 条 QA） */
  addWidthQa: boolean;
}

export interface QARecord {
  source_md?: string;
  chunk_index?: number;
  question?: string;
  answer?: string;
  chunk_text?: string;
  context?: string;
  hop_type?: string;
  qa_type?: string;
  level1_name?: string;
  level2_name?: string;
  task_type?: string;
  reasoning_style?: string;
  reasoning_steps?: string[];
  supporting_facts?: string[];
  think?: string;
  think_status?: string;
  think_error?: string;
  expanded_question?: string;
  expanded_answer?: string;
  expansion_status?: string;
  expansion_notes?: string;
  expansion_error?: string;
  question_quality_grade?: number;
  question_quality_feedback?: string;
  answer_alignment_grade?: number;
  answer_alignment_feedback?: string;
  answer_verifiability_grade?: number;
  answer_verifiability_feedback?: string;
  downstream_value_grade?: number;
  downstream_value_feedback?: string;
  user_modified?: boolean;
  [key: string]: unknown;
}

export interface QAWorkspaceItem {
  id: string;
  record: QARecord;
  local: {
    deleted: boolean;
    dirty: boolean;
    selected: boolean;
    filterPassed?: boolean;
  };
}

export interface WorkspaceSession {
  id: string;
  sourceFileName: string;
  pipeline: PipelineType;
  generator?: GeneratorType;
  params: PipelineParamsSnapshot;
  jobId: string;
  items: QAWorkspaceItem[];
  createdAt: string;
  updatedAt: string;
}

export interface TaskHistoryEntry {
  jobId: string;
  sessionId: string | null;
  sourceFileName: string;
  pipeline: PipelineType;
  generator?: GeneratorType;
  status: JobStatus;
  stage?: string;
  qaCount?: number;
  createdAt: string;
  finishedAt?: string;
  errorMessage?: string;
  params?: PipelineParamsSnapshot;
  uploadContent?: string;
}

export interface AppSettings {
  llm: {
    provider: string;
    baseUrl: string;
    model: string;
    timeoutSec: number;
    temperature: number;
  };
  output: {
    root: string;
    autoArchive: boolean;
  };
  taxonomy: {
    complete: boolean;
    topic: string;
    level1Count: number;
    taskTypeCount: number;
    nodes: TaxonomyPreviewNode[];
  };
}

export interface TaxonomyPreviewNode {
  level: string;
  label: string;
  indent: number;
}

export type ListFilter = "all" | "passed" | "failed" | "edited";
export type ExportScope = "passed" | "all" | "selected";

export const SCORE_DIMENSIONS = [
  { key: "question_quality", label: "问题质量", gradeKey: "question_quality_grade", feedbackKey: "question_quality_feedback" },
  { key: "answer_alignment", label: "答案对齐", gradeKey: "answer_alignment_grade", feedbackKey: "answer_alignment_feedback" },
  { key: "answer_verifiability", label: "答案可验证性", gradeKey: "answer_verifiability_grade", feedbackKey: "answer_verifiability_feedback" },
  { key: "downstream_value", label: "下游价值", gradeKey: "downstream_value_grade", feedbackKey: "downstream_value_feedback" },
] as const;
