from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class MineruSettings:
    executable: str | None = None


@dataclass
class OutputSettings:
    root: Path | None = None

    def ingest_dir(self) -> Path | None:
        return self.root / "ingest" if self.root is not None else None

    def qa_dir(self) -> Path | None:
        return self.root / "qa" if self.root is not None else None

    def multihop_dir(self) -> Path | None:
        return self.root / "multihop" if self.root is not None else None

    def expansion_path(self) -> Path | None:
        return self.root / "expansion" / "qa_expanded.jsonl" if self.root is not None else None

    def think_path(self) -> Path | None:
        return self.root / "think" / "qa_with_think.jsonl" if self.root is not None else None


@dataclass
class QASettings:
    topic: str = ""


@dataclass
class LLMSettings:
    provider: str | None = None
    base_url: str | None = None
    model: str | None = None
    timeout_sec: int | None = None
    temperature: float | None = None

    def is_configured(self) -> bool:
        return self.provider is not None


@dataclass
class PromptConfig:
    topic: str = ""
    singlehop_system: str | None = None
    evaluator_system: str | None = None
    multihop_system: str | None = None
    expansion_system: str | None = None
    thinking_system: str | None = None

    def render(self, stage: str, default: str) -> str:
        template = getattr(self, f"{stage}_system")
        text = template if template is not None else default
        return text.format(topic=self.topic)


@dataclass
class DatalightConfig:
    mineru: MineruSettings = field(default_factory=MineruSettings)
    output: OutputSettings = field(default_factory=OutputSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    qa: QASettings = field(default_factory=QASettings)
    prompts: PromptConfig = field(default_factory=PromptConfig)

    @classmethod
    def from_file(cls, path: Path) -> "DatalightConfig":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("Config file must contain a YAML mapping")
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "DatalightConfig":
        mineru_data = _dict_value(data, "mineru")
        output_data = _dict_value(data, "output")
        llm_data = _dict_value(data, "llm")
        qa_data = _dict_value(data, "qa")
        prompts_data = _dict_value(data, "prompts")

        topic = str(qa_data.get("topic") or "")
        return cls(
            mineru=MineruSettings(
                executable=_optional_str(mineru_data.get("executable")),
            ),
            output=OutputSettings(
                root=_optional_path(output_data.get("root")),
            ),
            llm=LLMSettings(
                provider=_optional_str(llm_data.get("provider")),
                base_url=_optional_str(llm_data.get("base_url")),
                model=_optional_str(llm_data.get("model")),
                timeout_sec=_optional_int(llm_data.get("timeout_sec")),
                temperature=_optional_float(llm_data.get("temperature")),
            ),
            qa=QASettings(topic=topic),
            prompts=PromptConfig(
                topic=topic,
                singlehop_system=_optional_str(prompts_data.get("singlehop_system")),
                evaluator_system=_optional_str(prompts_data.get("evaluator_system")),
                multihop_system=_optional_str(prompts_data.get("multihop_system")),
                expansion_system=_optional_str(prompts_data.get("expansion_system")),
                thinking_system=_optional_str(prompts_data.get("thinking_system")),
            ),
        )

    def prompt_config(self) -> PromptConfig:
        self.prompts.topic = self.qa.topic
        return self.prompts


def _dict_value(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Config field {key!r} must be a mapping")
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_path(value: Any) -> Path | None:
    text = _optional_str(value)
    return Path(text) if text is not None else None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
