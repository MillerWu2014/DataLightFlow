import unittest

from datalight.pipeline.preprocess.semantic_chunking import (
    build_semantic_chunks,
    group_paragraphs,
    split_markdown_sections,
)


class SemanticChunkingTest(unittest.TestCase):
    def test_split_markdown_sections_by_headings(self):
        text = "# Chapter 1\n\nIntro paragraph.\n\n## Section A\n\nDetail A.\n\n## Section B\n\nDetail B."
        sections = split_markdown_sections(text)

        self.assertEqual(len(sections), 3)
        self.assertEqual(sections[0], (1, "Chapter 1", "Intro paragraph."))
        self.assertEqual(sections[1], (2, "Section A", "Detail A."))
        self.assertEqual(sections[2], (2, "Section B", "Detail B."))

    def test_group_paragraphs_respects_max_chars(self):
        paragraphs = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        groups = group_paragraphs(paragraphs, max_chunk_chars=30)

        self.assertEqual(len(groups), 2)
        self.assertIn("Paragraph one.", groups[0])
        self.assertIn("Paragraph three.", groups[1])

    def test_build_semantic_chunks_keeps_section_title_in_chunk(self):
        text = "## 运行规则\n\n第一句说明前提。\n\n第二句说明条件。\n\n第三句说明结论。"
        chunks = build_semantic_chunks(text, max_chunk_chars=500, min_chunk_chars=20)

        self.assertEqual(len(chunks), 1)
        self.assertIn("## 运行规则", chunks[0]["chunk_text"])
        self.assertEqual(chunks[0]["section_title"], "运行规则")
        self.assertEqual(chunks[0]["section_level"], 2)

    def test_fallback_to_paragraphs_when_no_headings(self):
        text = "第一段内容。\n\n第二段内容。\n\n第三段内容。"
        chunks = build_semantic_chunks(text, max_chunk_chars=500, min_chunk_chars=10)

        self.assertEqual(len(chunks), 1)
        self.assertIn("第一段内容。", chunks[0]["chunk_text"])
        self.assertEqual(chunks[0]["section_title"], "")


if __name__ == "__main__":
    unittest.main()
