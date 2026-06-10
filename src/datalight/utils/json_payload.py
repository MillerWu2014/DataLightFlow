from __future__ import annotations

import re


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
