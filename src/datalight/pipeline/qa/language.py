from __future__ import annotations

SUPPORTED_LANGUAGES = {"zh", "en", "auto"}


def normalize_target_language(target_language: str) -> str:
    value = target_language.strip().lower()
    if value not in SUPPORTED_LANGUAGES:
        raise ValueError("target_language must be one of: zh, en, auto")
    return value


def language_instruction(target_language: str) -> str:
    language = normalize_target_language(target_language)
    if language == "zh":
        return "Language requirement: 问题、答案、评分反馈和推理步骤必须使用中文。"
    if language == "en":
        return "Language requirement: Questions, answers, feedback, and reasoning steps must be in English."
    return "Language requirement: Use the primary language of the context for questions, answers, feedback, and reasoning steps."
