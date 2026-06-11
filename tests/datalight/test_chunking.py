import tempfile
import unittest
from pathlib import Path

from datalight.pipeline.preprocess.chunking import MarkdownChunkOperator


class ChunkingTest(unittest.TestCase):
    def test_large_document_produces_chunks(self):
        MARKDOWN_PATH = Path(
            "/Users/miller/Workspace/BJBN/project/aviation-llm-finetuning/data/markdown/标准规范/客舱运行管理/客舱运行管理.md",
        )
        text = MARKDOWN_PATH.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp_dir:
            md_path = Path(tmp_dir) / "sample.md"
            md_path.write_text(text, encoding="utf-8")
            chunks = MarkdownChunkOperator(chunk_words=512, overlap_words=64).run(
                [{"output_md_path": str(md_path)}],
            )
            print(chunks)

        self.assertEqual(len(chunks), 1)
        self.assertIn("为适应客舱安全形势发展的需要", chunks[0]["chunk_text"])


if __name__ == "__main__":
    unittest.main()
