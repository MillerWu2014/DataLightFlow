from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from datalight.config import DatalightConfig, TaxonomySettings
from server.schemas import (
    AppConfigResponse,
    AppConfigUpdate,
    LLMConfigBody,
    OutputConfigBody,
    TaxonomyConfigBody,
    TaxonomyPreviewNode,
)


def build_taxonomy_nodes(taxonomy: TaxonomySettings) -> list[TaxonomyPreviewNode]:
    topic = taxonomy.resolved_topic()
    nodes: list[TaxonomyPreviewNode] = [
        TaxonomyPreviewNode(level="01", label=f"root/{topic}", indent=0),
    ]
    level1_order: list[str] = []
    for category in taxonomy.categories:
        if category.level1_name not in level1_order:
            level1_order.append(category.level1_name)
    for level1 in level1_order:
        nodes.append(TaxonomyPreviewNode(level="02", label=level1, indent=1))
        for category in taxonomy.categories:
            if category.level1_name != level1:
                continue
            nodes.append(TaxonomyPreviewNode(level="03", label=category.level2_name, indent=2))
    return nodes


def config_to_response(config_path: Path) -> AppConfigResponse:
    cfg = DatalightConfig.from_file(config_path) if config_path.is_file() else DatalightConfig()
    taxonomy = cfg.taxonomy
    level1_names = {category.level1_name for category in taxonomy.categories}
    return AppConfigResponse(
        llm=LLMConfigBody(
            provider=cfg.llm.provider or "lmstudio",
            baseUrl=cfg.llm.base_url or "http://127.0.0.1:1234/v1",
            model=cfg.llm.model or "",
            timeoutSec=cfg.llm.timeout_sec or 180,
            temperature=cfg.llm.temperature if cfg.llm.temperature is not None else 0.5,
        ),
        output=OutputConfigBody(
            root=str(cfg.output.root or ".output"),
            autoArchive=False,
        ),
        taxonomy=TaxonomyConfigBody(
            complete=taxonomy.is_complete(),
            topic=taxonomy.resolved_topic(),
            level1Count=len(level1_names),
            taskTypeCount=len(taxonomy.task_type),
            nodes=build_taxonomy_nodes(taxonomy),
        ),
    )


def apply_config_update(config_path: Path, update: AppConfigUpdate) -> AppConfigResponse:
    data: dict[str, Any] = {}
    if config_path.is_file():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            data = loaded

    if update.llm is not None:
        llm = data.setdefault("llm", {})
        llm["provider"] = update.llm.provider
        llm["base_url"] = update.llm.base_url
        llm["model"] = update.llm.model
        llm["timeout_sec"] = update.llm.timeout_sec
        llm["temperature"] = update.llm.temperature

    if update.output is not None:
        output = data.setdefault("output", {})
        output["root"] = update.output.root

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return config_to_response(config_path)
