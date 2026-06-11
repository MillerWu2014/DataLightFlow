import unittest

from datalight.llm import StaticLLMClient
from datalight.pipeline.generation.singlehop import (
    Text2QAGeneratorOperator,
    parse_generated_prompt_list,
    parse_qa_response,
)


class Text2QAParsingTest(unittest.TestCase):
    def test_parse_generated_prompt_list(self):
        prompts = parse_generated_prompt_list('["Extract numeric limits", "Extract role duties"]')
        self.assertEqual(len(prompts), 2)

    def test_parse_qa_line_response(self):
        pairs = parse_qa_response("Q: 限速是多少？\nA: 25公里每小时")
        self.assertEqual(pairs, [("限速是多少？", "25公里每小时")])


class Text2QAGeneratorOperatorTest(unittest.TestCase):
    def test_two_stage_pipeline(self):
        chunk = {
            "source_md": "/tmp/doc.md",
            "chunk_index": 0,
            "chunk_text": "航空器活动区行驶速度不得超过25公里每小时。",
        }
        responses = [
            '["Extract the speed limit from the activity area rule."]',
            "Q: 航空器活动区的最高行驶速度是多少？\nA: 25公里每小时",
        ]
        operator = Text2QAGeneratorOperator(StaticLLMClient(responses), question_num=1)
        out = operator.run([chunk])

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["qa_type"], "text2qa_meta")
        self.assertIn("speed limit", out[0]["generated_prompt"])
        self.assertEqual(out[0]["question"], "航空器活动区的最高行驶速度是多少？")
        self.assertEqual(out[0]["answer"], "25公里每小时")

    def test_limits_qa_pairs_per_chunk(self):
        chunks = [
            {
                "source_md": "/tmp/doc.md",
                "chunk_index": 0,
                "chunk_text": "chunk A",
            },
            {
                "source_md": "/tmp/doc.md",
                "chunk_index": 1,
                "chunk_text": "chunk B",
            },
        ]
        responses = [
            '["Prompt A1", "Prompt A2", "Prompt A3"]',
            '["Prompt B1", "Prompt B2"]',
            "Q: Q-A1\nA: A1",
            "Q: Q-A2\nA: A2",
            "Q: Q-B1\nA: B1",
            "Q: Q-B2\nA: B2",
        ]
        operator = Text2QAGeneratorOperator(StaticLLMClient(responses), question_num=2)
        out = operator.run(chunks)

        self.assertEqual(len(out), 4)
        by_chunk: dict[int, int] = {}
        for row in out:
            by_chunk[row["chunk_index"]] = by_chunk.get(row["chunk_index"], 0) + 1
        self.assertEqual(by_chunk, {0: 2, 1: 2})


if __name__ == "__main__":
    unittest.main()
