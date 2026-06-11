from __future__ import annotations

from typing import Any

from datalight.pipeline.core import Operator, Record
from datalight.pipeline.language import normalize_target_language


class MultiHopContextBuilderOperator(Operator):
    """Build multi-hop contexts using the original DataFlow info-pair extraction flow.

    Pipeline: chunks -> preprocess -> sliding-window info pairs -> context rows
    """

    def __init__(
        self,
        lang: str = "zh",
        min_text_length: int = 100,
        max_text_length: int = 200000,
        min_context_sentences: int = 3,
    ):
        if min_context_sentences < 2:
            raise ValueError("min_context_sentences must be at least 2")
        self.lang = normalize_target_language(lang) if lang in {"zh", "en"} else "zh"
        if self.lang == "auto":
            self.lang = "zh"
        self.min_text_length = min_text_length
        self.max_text_length = max_text_length
        self.min_context_sentences = min_context_sentences

    def run(self, rows: list[Record]) -> list[Record]:
        out: list[Record] = []
        for row in rows:
            processed_text = preprocess_multihop_text(
                str(row.get("chunk_text", "")),
                min_text_length=self.min_text_length,
                max_text_length=self.max_text_length,
            )
            if not processed_text:
                continue

            info_pairs = extract_info_pairs(
                processed_text,
                lang=self.lang,
                min_sentences=self.min_context_sentences,
            )
            if not info_pairs:
                continue

            for pair_index, pair in enumerate(info_pairs):
                context = build_info_pair_context(pair, lang=self.lang)
                item = dict(row)
                item.update(pair)
                item["context"] = context
                item["info_pair_index"] = pair_index
                item["supporting_sentence_count"] = 3
                out.append(item)
        return out


def preprocess_multihop_text(
    text: str,
    *,
    min_text_length: int = 100,
    max_text_length: int = 200000,
) -> str:
    if not isinstance(text, str):
        return ""

    text = text.strip()
    if len(text) < min_text_length or len(text) > max_text_length:
        return ""
    if not check_text_quality(text):
        return ""
    return text


def check_text_quality(text: str) -> bool:
    if text.count("。") < 2 and text.count(".") < 2:
        return False
    if calculate_special_char_ratio(text) > 0.3:
        return False
    return True


def calculate_special_char_ratio(text: str) -> float:
    chinese_ranges = [
        (0x4E00, 0x9FFF),
        (0x3400, 0x4DBF),
        (0x20000, 0x2A6DF),
        (0x2A700, 0x2B73F),
        (0x2B740, 0x2B81F),
        (0x2B820, 0x2CEAF),
    ]
    special_count = 0
    for char in text:
        is_chinese = any(start <= ord(char) <= end for start, end in chinese_ranges)
        if not (char.isalnum() or char.isspace() or is_chinese):
            special_count += 1
    return special_count / len(text) if text else 0.0


def split_sentences(text: str, *, lang: str) -> list[str]:
    if lang == "en":
        parts = [part.strip() for part in text.split(".") if part.strip()]
    else:
        parts = [part.strip() for part in text.split("。") if part.strip()]
    return [part for part in parts if len(part) > 2]


def extract_info_pairs(
    text: str,
    *,
    lang: str,
    min_sentences: int = 3,
) -> list[dict[str, Any]]:
    sentences = split_sentences(text, lang=lang)
    if len(sentences) < min_sentences:
        return []

    info_pairs: list[dict[str, Any]] = []
    for index in range(len(sentences) - 2):
        premise = sentences[index]
        intermediate = sentences[index + 1]
        if len(premise) <= 10 or len(intermediate) <= 10:
            continue
        conclusion = sentences[index + 2] if index + 2 < len(sentences) else ""
        related_contexts = [
            sentence
            for offset, sentence in enumerate(sentences)
            if offset not in {index, index + 1} and len(sentence) > 10
        ][:2]
        info_pairs.append(
            {
                "premise": premise,
                "intermediate": intermediate,
                "conclusion": conclusion,
                "related_contexts": related_contexts,
            },
        )
    return info_pairs


def build_info_pair_context(pair: dict[str, Any], *, lang: str) -> str:
    separator = ". " if lang == "en" else " "
    parts = [str(pair.get("premise", "")).strip(), str(pair.get("intermediate", "")).strip()]
    conclusion = str(pair.get("conclusion", "")).strip()
    if conclusion:
        parts.append(conclusion)
    return separator.join(part for part in parts if part)
