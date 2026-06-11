import unittest

from datalight.llm import StaticLLMClient
from datalight.pipeline.generation.agentic import DepthQAGeneratorOperator, WidthQAGeneratorOperator
from datalight.utils.json_parse import (
    parse_backward_result,
    parse_content_identifier,
    parse_recall_score,
)
from datalight.pipeline.prompts.agentic import DepthGetIdentifierPrompt, WidthMergePrompt


class AgenticPromptTest(unittest.TestCase):
    def test_depth_identifier_prompt_contains_json_key(self):
        prompt = DepthGetIdentifierPrompt()
        self.assertIn("content_identifier", prompt.build_system_prompt())

    def test_width_merge_prompt_contains_output_schema(self):
        prompt = WidthMergePrompt()
        self.assertIn("content_identifier", prompt.build_system_prompt())


class AgenticParsingTest(unittest.TestCase):
    def test_parse_content_identifier_from_json(self):
        value = parse_content_identifier('{"content_identifier":"航空器活动区"}')
        self.assertEqual(value, "航空器活动区")

    def test_parse_backward_result(self):
        parsed = parse_backward_result('{"identifier":"运行手册","relation":"第三章"}')
        self.assertEqual(parsed["identifier"], "运行手册")

    def test_parse_recall_score(self):
        self.assertEqual(parse_recall_score('{"answer_score":0,"answer_analysis":"x"}'), 0)


class DepthOperatorTest(unittest.TestCase):
    def test_depth_pipeline_emits_verified_question(self):
        rows = [
            {
                "question": "航空器活动区的限速是多少？",
                "answer": "25公里每小时",
                "context": "示例上下文",
            },
        ]
        responses = [
            '{"content_identifier":"航空器活动区"}',
            '{"identifier":"机场运行手册","relation":"第三章限速规定"}',
            '{"new_query":"valid"}',
            '{"new_query":"依据机场运行手册第三章，航空器活动区的限速是多少？"}',
            '{"answer_list":["25公里每小时"]}',
            '{"answer_score":0,"answer_analysis":"missing key info"}',
        ]
        operator = DepthQAGeneratorOperator(StaticLLMClient(responses), n_rounds=1)
        out = operator.run(rows)

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["qa_type"], "depth")
        self.assertIn("机场运行手册", out[0]["question"])
        self.assertEqual(out[0]["answer"], "航空器活动区")


class WidthOperatorTest(unittest.TestCase):
    def test_width_pipeline_emits_verified_question(self):
        rows = [
            {
                "question": "Q1",
                "answer": "A1",
                "identifier": "主题A",
            },
            {
                "question": "Q2",
                "answer": "A2",
                "identifier": "主题A",
            },
        ]
        responses = [
            '[{"question":"合并后的问题？","index":[0,1],"content_identifier":"主题A"}]',
            '[{"index":0,"complex_question":"合并后的问题？","state":1}]',
            '[{"index":0,"complex_question":"合并后的问题？","llm_answer":"合并答案"}]',
            '{"answer_score":0,"answer_analysis":"not enough"}',
        ]
        operator = WidthQAGeneratorOperator(StaticLLMClient(responses))
        out = operator.run(rows)

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["qa_type"], "width")
        self.assertEqual(out[0]["question"], "合并后的问题？")
        self.assertEqual(out[0]["source_question_indices"], [0, 1])


if __name__ == "__main__":
    unittest.main()
