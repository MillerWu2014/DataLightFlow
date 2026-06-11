import json
import tempfile
import unittest
from pathlib import Path

from datalight.llm import StaticLLMClient
from datalight.pipeline.generation.atomic import AtomicTaskQAGeneratorOperator
from datalight.pipeline.runner import run_markdown_qa_pipeline


class AtomicTaskOperatorTest(unittest.TestCase):
    def test_atomic_pipeline_emits_verified_qa(self):
        chunk = {
            "source_md": "/tmp/doc.md",
            "chunk_index": 0,
            "chunk_text": (
                "航空器活动区行驶速度不得超过25公里每小时。"
                "驾驶员进入活动区前必须完成资质确认。"
                "未获批准车辆禁止进入机坪区域。"
            ),
        }
        responses = [
            '{"content_identifier":"航空器活动区"}',
            '[{"conclusion":"限速25公里每小时","R":"活动区限速"}]',
            '{"Q":"航空器活动区的最高行驶速度是多少？"}',
            '{"question":"航空器活动区的最高行驶速度是多少？","original_answer":"限速25公里每小时","refined_answer":"25公里每小时"}',
            "30公里每小时",
            '{"answer_score":0,"answer_analysis":"missing"}',
            "25公里每小时",
            '{"answer_score":2,"answer_analysis":"match"}',
            '["25公里每小时","25km/h"]',
        ]
        operator = AtomicTaskQAGeneratorOperator(
            StaticLLMClient(responses),
            max_per_task=5,
            max_question=3,
        )
        out = operator.run([chunk])

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["qa_type"], "atomic")
        self.assertEqual(out[0]["answer"], "25公里每小时")
        self.assertEqual(out[0]["question"], "航空器活动区的最高行驶速度是多少？")
        self.assertEqual(out[0]["golden_doc_answer"], "25公里每小时")
        self.assertIn("25公里每小时", out[0]["optional_answer"])


class AtomicRunnerSkipEvalTest(unittest.TestCase):
    def test_atomic_generator_skips_four_dimension_scoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "doc.md"
            md.write_text(
                "航空器活动区行驶速度不得超过25公里每小时。"
                "驾驶员进入活动区前必须完成资质确认。",
                encoding="utf-8",
            )
            output = Path(tmp) / "out"
            responses = [
                '{"content_identifier":"航空器活动区"}',
                '[{"conclusion":"限速25公里每小时","R":"活动区限速"}]',
                '{"Q":"航空器活动区的最高行驶速度是多少？"}',
                '{"question":"航空器活动区的最高行驶速度是多少？","original_answer":"限速25公里每小时","refined_answer":"25公里每小时"}',
                "30公里每小时",
                '{"answer_score":0,"answer_analysis":"missing"}',
                "25公里每小时",
                '{"answer_score":2,"answer_analysis":"match"}',
                '["25公里每小时","25km/h"]',
            ]
            result = run_markdown_qa_pipeline(
                markdown_paths=[md],
                output_dir=output,
                llm_client=StaticLLMClient(responses),
                chunk_words=64,
                generator="atomic",
                atomic_max_per_task=5,
                question_num=3,
            )
            rows = [
                json.loads(line)
                for line in result.export_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(rows), 1)
            scored_rows = [
                json.loads(line)
                for line in result.scored_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(scored_rows), 1)
            self.assertNotIn("question_quality_grade", scored_rows[0])
            self.assertNotIn("chunk_text", scored_rows[0])
            self.assertNotIn("context", scored_rows[0])


if __name__ == "__main__":
    unittest.main()
