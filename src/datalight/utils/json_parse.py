from __future__ import annotations

import json
import re
from typing import Any


def clean_json_block(item: str) -> str:
    return item.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()


def extract_json_payload(
    response: str,
    *,
    allow_array: bool = False,
    error_context: str = "response",
) -> str:
    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()

    if text.startswith("{") or (allow_array and text.startswith("[")):
        return text

    indices = [text.find("{")]
    if allow_array:
        indices.append(text.find("["))
    start = min([idx for idx in indices if idx >= 0], default=-1)
    if start < 0:
        raise ValueError(f"No JSON object found in {error_context}")
    return text[start:]


def parse_json_value(response: str) -> Any:
    text = clean_json_block(response)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def parse_json_dict(response: str) -> dict[str, Any]:
    parsed = parse_json_value(response)
    return parsed if isinstance(parsed, dict) else {}


def parse_content_identifier(response: str) -> str:
    parsed = parse_json_dict(response)
    if parsed.get("content_identifier"):
        return str(parsed["content_identifier"]).strip()
    return clean_json_block(response)


def parse_backward_result(response: str) -> dict[str, str] | None:
    parsed = parse_json_dict(response)
    if not parsed:
        return None
    identifier = str(parsed.get("identifier", "")).strip()
    relation = str(parsed.get("relation", "")).strip()
    if not identifier or not relation:
        return None
    return {"identifier": identifier, "relation": relation}


def parse_recall_score(response: str) -> int | None:
    parsed = parse_json_dict(response)
    if not parsed or "answer_score" not in parsed:
        return None
    try:
        return int(parsed["answer_score"])
    except (TypeError, ValueError):
        return None
