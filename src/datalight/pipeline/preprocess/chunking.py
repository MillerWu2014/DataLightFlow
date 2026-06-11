from __future__ import annotations

from pathlib import Path

from datalight.log import logger
from datalight.pipeline.core import Operator, Record


class MarkdownChunkOperator(Operator):
    """Chunk the markdown file into chunks of text."""

    def __init__(self, chunk_words: int = 512, overlap_words: int = 0):
        if chunk_words <= 0:
            raise ValueError("chunk_words must be positive")
        if overlap_words < 0:
            raise ValueError("overlap_words must be non-negative")
        if overlap_words >= chunk_words:
            raise ValueError("overlap_words must be smaller than chunk_words")
        self.chunk_words = chunk_words
        self.overlap_words = overlap_words

    def run(self, rows: list[Record]) -> list[Record]:
        chunks: list[Record] = []
        for row in rows:
            if row.get("status", "ok") != "ok":
                logger.warning("skipping row: %s", row)
                continue
            md_path = Path(str(row.get("output_md_path") or row.get("source_path")))
            if not md_path.is_file():
                continue
            words = md_path.read_text(encoding="utf-8").split()
            if not words:
                continue
            step = self.chunk_words - self.overlap_words
            for idx, start in enumerate(range(0, len(words), step)):
                part = words[start : start + self.chunk_words]
                if not part:
                    continue
                chunk_text = " ".join(part)
                chunks.append(
                    {
                        "source_md": str(md_path),
                        "chunk_index": idx,
                        "chunk_text": chunk_text,
                    },
                )
                if start + self.chunk_words >= len(words):
                    break

        return chunks
