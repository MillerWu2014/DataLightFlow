from __future__ import annotations

import re

from datalight.pipeline.core import Operator, Record


class MultiHopContextBuilderOperator(Operator):
    def __init__(self, min_context_sentences: int = 3):
        if min_context_sentences < 2:
            raise ValueError("min_context_sentences must be at least 2")
        self.min_context_sentences = min_context_sentences

    def run(self, rows: list[Record]) -> list[Record]:
        out: list[Record] = []
        for row in rows:
            sentences = _split_sentences(str(row.get("chunk_text", "")))
            if len(sentences) < self.min_context_sentences:
                continue
            context_sentences = sentences[: self.min_context_sentences]
            item = dict(row)
            item["premise"] = context_sentences[0]
            item["intermediate"] = context_sentences[1]
            item["conclusion"] = context_sentences[2] if len(context_sentences) > 2 else context_sentences[-1]
            item["related_contexts"] = sentences[self.min_context_sentences :]
            item["context"] = " ".join(context_sentences)
            item["supporting_sentence_count"] = len(context_sentences)
            out.append(item)
        return out


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？.!?])\s+", text.strip())
    return [part.strip() for part in parts if len(part.strip()) > 2]
