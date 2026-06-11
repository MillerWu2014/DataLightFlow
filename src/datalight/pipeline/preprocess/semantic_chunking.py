from __future__ import annotations

import re
from pathlib import Path

from datalight.pipeline.core import Operator, Record
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


class MarkdownSemanticChunkOperator(Operator):
    """Chunk markdown by headings and paragraphs for multi-hop QA.

    Unlike fixed word-count chunking, this keeps section and paragraph boundaries
    so consecutive sentences are more likely to describe the same topic.
    """

    def __init__(
        self,
        max_chunk_chars: int = 2048,
        min_chunk_chars: int = 256,
    ):
        if max_chunk_chars <= 0:
            raise ValueError("max_chunk_chars must be positive")
        if min_chunk_chars < 0:
            raise ValueError("min_chunk_chars must be non-negative")
        if min_chunk_chars >= max_chunk_chars:
            raise ValueError("min_chunk_chars must be smaller than max_chunk_chars")
        self.max_chunk_chars = max_chunk_chars
        self.min_chunk_chars = min_chunk_chars

    def run(self, rows: list[Record]) -> list[Record]:
        chunks: list[Record] = []
        for row in rows:
            if row.get("status", "ok") != "ok":
                continue
            md_path = Path(str(row.get("output_md_path") or row.get("source_path")))
            if not md_path.is_file():
                continue
            text = md_path.read_text(encoding="utf-8")
            if not text.strip():
                continue
            for chunk_index, chunk in enumerate(
                build_semantic_chunks(
                    text,
                    max_chunk_chars=self.max_chunk_chars,
                    min_chunk_chars=self.min_chunk_chars,
                ),
            ):
                chunks.append(
                    {
                        "source_md": str(md_path),
                        "chunk_index": chunk_index,
                        "chunk_text": chunk["chunk_text"],
                        "section_title": chunk["section_title"],
                        "section_level": chunk["section_level"],
                        "chunking_strategy": "semantic",
                    },
                )
        return chunks


def build_semantic_chunks(
    text: str,
    *,
    max_chunk_chars: int,
    min_chunk_chars: int,
) -> list[dict[str, str | int]]:
    sections = split_markdown_sections(text)
    chunks: list[dict[str, str | int]] = []
    for level, title, body in sections:
        if not body.strip():
            continue
        section_prefix = _section_prefix(level, title)
        for part in group_paragraphs(body, max_chunk_chars=max_chunk_chars):
            chunk_text = f"{section_prefix}{part}".strip() if section_prefix else part.strip()
            if len(chunk_text) < min_chunk_chars:
                continue
            chunks.append(
                {
                    "chunk_text": chunk_text,
                    "section_title": title,
                    "section_level": level,
                },
            )
    return chunks


def split_markdown_sections(text: str) -> list[tuple[int, str, str]]:
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return [(0, "", text)]

    sections: list[tuple[int, str, str]] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.append((0, "", preamble))

    for index, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2).strip()
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        sections.append((level, title, body))
    return sections


def group_paragraphs(text: str, *, max_chunk_chars: int) -> list[str]:
    paragraphs = split_paragraphs(text)
    if not paragraphs:
        return []

    if len(text) <= max_chunk_chars:
        return [text.strip()]

    groups: list[str] = []
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        paragraph_len = len(paragraph)
        if paragraph_len > max_chunk_chars:
            if current:
                groups.append("\n\n".join(current))
                current = []
                current_len = 0
            groups.extend(_split_oversized_paragraph(paragraph, max_chunk_chars=max_chunk_chars))
            continue

        extra = 2 if current else 0
        if current and current_len + extra + paragraph_len > max_chunk_chars:
            groups.append("\n\n".join(current))
            current = [paragraph]
            current_len = paragraph_len
        else:
            current.append(paragraph)
            current_len += extra + paragraph_len

    if current:
        groups.append("\n\n".join(current))
    return groups


def split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _split_oversized_paragraph(paragraph: str, *, max_chunk_chars: int) -> list[str]:
    sentences = re.split(r"(?<=[。！？.!?])\s*", paragraph.strip())
    sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
    if not sentences:
        return [paragraph.strip()]

    groups: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        extra = 1 if current else 0
        if current and current_len + extra + len(sentence) > max_chunk_chars:
            groups.append("".join(current))
            current = [sentence]
            current_len = len(sentence)
        else:
            current.append(sentence)
            current_len += extra + len(sentence)
    if current:
        groups.append("".join(current))
    return groups


def _section_prefix(level: int, title: str) -> str:
    if not title:
        return ""
    hashes = "#" * level if level > 0 else "##"
    return f"{hashes} {title}\n\n"

