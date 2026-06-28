from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _camel_config() -> ConfigDict:
    return ConfigDict(populate_by_name=True, serialize_by_alias=True)


class UploadResponse(BaseModel):
    model_config = _camel_config()

    upload_id: str = Field(alias="uploadId")
    path: str
    file_name: str = Field(alias="fileName")
    size: int


class PipelineParamsBody(BaseModel):
    model_config = _camel_config()

    language: Literal["zh", "en", "auto"] = "zh"
    chunk_words: int = Field(default=512, alias="chunkWords")
    overlap_words: int = Field(default=0, alias="overlapWords")
    question_num: int = Field(default=1, alias="questionNum")
    min_score: float = Field(default=3.0, alias="minScore")
    atomic_max_per_task: int = Field(default=10, alias="atomicMaxPerTask")
    expand_qa: bool = Field(default=False, alias="expandQa")
    expand_mode: Literal["detail", "contextual", "reasoning"] = Field(default="detail", alias="expandMode")
    add_think: bool = Field(default=False, alias="addThink")
    add_depth_qa: bool = Field(default=False, alias="addDepthQa")
    depth_rounds: int = Field(default=2, alias="depthRounds")
    add_width_qa: bool = Field(default=False, alias="addWidthQa")


class CreateJobBody(BaseModel):
    model_config = _camel_config()

    upload_id: str = Field(alias="uploadId")
    pipeline: Literal["singlehop", "multihop"]
    generator: Literal["default", "atomic", "taxonomy"] | None = "default"
    params: PipelineParamsBody | None = None
    language: Literal["zh", "en", "auto"] | None = None
    chunk_words: int | None = Field(default=None, alias="chunkWords")
    overlap_words: int | None = Field(default=None, alias="overlapWords")
    question_num: int | None = Field(default=None, alias="questionNum")
    min_score: float | None = Field(default=None, alias="minScore")
    atomic_max_per_task: int | None = Field(default=None, alias="atomicMaxPerTask")
    expand_qa: bool | None = Field(default=None, alias="expandQa")
    expand_mode: Literal["detail", "contextual", "reasoning"] | None = Field(default=None, alias="expandMode")
    add_think: bool | None = Field(default=None, alias="addThink")
    add_depth_qa: bool | None = Field(default=None, alias="addDepthQa")
    depth_rounds: int | None = Field(default=None, alias="depthRounds")
    add_width_qa: bool | None = Field(default=None, alias="addWidthQa")
    model: str | None = None
    timeout_sec: int | None = Field(default=None, alias="timeoutSec")

    def resolved_params(self) -> PipelineParamsBody:
        if self.params is not None:
            return self.params
        base = PipelineParamsBody()
        data = base.model_dump(by_alias=True)
        overrides = {
            "language": self.language,
            "chunkWords": self.chunk_words,
            "overlapWords": self.overlap_words,
            "questionNum": self.question_num,
            "minScore": self.min_score,
            "atomicMaxPerTask": self.atomic_max_per_task,
            "expandQa": self.expand_qa,
            "expandMode": self.expand_mode,
            "addThink": self.add_think,
            "addDepthQa": self.add_depth_qa,
            "depthRounds": self.depth_rounds,
            "addWidthQa": self.add_width_qa,
        }
        for key, value in overrides.items():
            if value is not None:
                data[key] = value
        return PipelineParamsBody.model_validate(data)


class CreateJobResponse(BaseModel):
    model_config = _camel_config()

    job_id: str = Field(alias="jobId")
    session_id: str | None = Field(default=None, alias="sessionId")
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"] = "queued"


class JobSummary(BaseModel):
    model_config = _camel_config()

    job_id: str = Field(alias="jobId")
    session_id: str | None = Field(alias="sessionId")
    source_file_name: str = Field(alias="sourceFileName")
    pipeline: Literal["singlehop", "multihop"]
    generator: Literal["default", "atomic", "taxonomy"] | None = None
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    stage: str | None = None
    qa_count: int | None = Field(default=None, alias="qaCount")
    created_at: str = Field(alias="createdAt")
    finished_at: str | None = Field(default=None, alias="finishedAt")
    error_message: str | None = Field(default=None, alias="errorMessage")
    params: PipelineParamsBody | None = None


class JobProgress(BaseModel):
    current: int | None = None
    total: int | None = None


class JobErrorDetail(BaseModel):
    code: str
    message: str


class JobStatusResponse(BaseModel):
    model_config = _camel_config()

    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    stage: str | None = None
    progress: JobProgress | None = None
    error: JobErrorDetail | str | None = None
    session_id: str | None = Field(default=None, alias="sessionId")
    qa_count: int | None = Field(default=None, alias="qaCount")
    result_paths: dict[str, str] | None = Field(default=None, alias="resultPaths")


class QAWorkspaceItemLocal(BaseModel):
    model_config = _camel_config()

    deleted: bool = False
    dirty: bool = False
    selected: bool = False
    filter_passed: bool | None = Field(default=None, alias="filterPassed")


class QAWorkspaceItem(BaseModel):
    id: str
    record: dict[str, Any]
    local: QAWorkspaceItemLocal


class WorkspaceSessionBody(BaseModel):
    model_config = _camel_config()

    id: str | None = None
    source_file_name: str = Field(alias="sourceFileName")
    pipeline: Literal["singlehop", "multihop"]
    generator: Literal["default", "atomic", "taxonomy"] | None = None
    params: PipelineParamsBody
    job_id: str = Field(alias="jobId")
    items: list[QAWorkspaceItem]
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


class SessionSaveResponse(BaseModel):
    updated_at: str = Field(alias="updatedAt")


class QAPatchBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    record: dict[str, Any] | None = None
    local: dict[str, Any] | None = None


class ExpandQaBody(BaseModel):
    model_config = _camel_config()

    mode: Literal["detail", "contextual", "reasoning"] = "detail"
    model: str | None = None
    timeout_sec: int | None = Field(default=None, alias="timeoutSec")


class EvaluateQaBody(BaseModel):
    model_config = _camel_config()

    model: str | None = None
    timeout_sec: int | None = Field(default=None, alias="timeoutSec")


class QaItemResponse(BaseModel):
    id: str
    record: dict[str, Any]
    local: QAWorkspaceItemLocal
    updated_at: str | None = Field(default=None, alias="updatedAt")


class TaxonomyPreviewNode(BaseModel):
    level: str
    label: str
    indent: int


class LLMConfigBody(BaseModel):
    model_config = _camel_config()

    provider: str
    base_url: str = Field(alias="baseUrl")
    model: str
    timeout_sec: int = Field(alias="timeoutSec")
    temperature: float


class OutputConfigBody(BaseModel):
    model_config = _camel_config()

    root: str
    auto_archive: bool = Field(default=False, alias="autoArchive")


class TaxonomyConfigBody(BaseModel):
    model_config = _camel_config()

    complete: bool
    topic: str
    level1_count: int = Field(alias="level1Count")
    task_type_count: int = Field(alias="taskTypeCount")
    nodes: list[TaxonomyPreviewNode]


class AppConfigResponse(BaseModel):
    model_config = _camel_config()

    llm: LLMConfigBody
    output: OutputConfigBody
    taxonomy: TaxonomyConfigBody


class AppConfigUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    llm: LLMConfigBody | None = None
    output: OutputConfigBody | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_partial(cls, data: Any) -> Any:
        return data