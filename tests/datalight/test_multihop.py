import unittest

from datalight.pipeline.generation.multihop import (
    calculate_multihop_complexity,
    extract_multihop_qa_pairs,
)
from datalight.pipeline.preprocess.multihop_context import (
    build_info_pair_context,
    extract_info_pairs,
    preprocess_multihop_text,
)
from datalight.pipeline.prompts.multihop import MultihopPromptTemplate


class MultihopPromptTemplateTest(unittest.TestCase):
    def test_zh_prompt_contains_core_sections(self):
        template = MultihopPromptTemplate(lang="zh")
        system_prompt = template.build_system_prompt()
        user_prompt = template.build_prompt("示例上下文")

        self.assertIn("核心要求", system_prompt)
        self.assertIn("输出规范", system_prompt)
        self.assertIn("违规处理", system_prompt)
        self.assertIn("示例上下文", user_prompt)
        self.assertIn("reasoning_steps", user_prompt)

    def test_en_prompt_contains_core_sections(self):
        template = MultihopPromptTemplate(lang="en")
        system_prompt = template.build_system_prompt()

        self.assertIn("Core Requirements", system_prompt)
        self.assertIn("Rejection Criteria", system_prompt)


class MultihopContextTest(unittest.TestCase):
    def test_extract_info_pairs_uses_sliding_window(self):
        text = "第一句足够长的前提内容在这里。第二句足够长的中间推断内容在这里。第三句足够长的结论内容在这里。第四句额外上下文也足够长。"
        pairs = extract_info_pairs(text, lang="zh")

        self.assertGreaterEqual(len(pairs), 2)
        self.assertEqual(pairs[0]["premise"], "第一句足够长的前提内容在这里")
        self.assertEqual(pairs[0]["intermediate"], "第二句足够长的中间推断内容在这里")

    def test_preprocess_rejects_short_text(self):
        self.assertEqual(preprocess_multihop_text("太短", min_text_length=100), "")

    def test_build_info_pair_context_joins_three_sentences(self):
        context = build_info_pair_context(
            {
                "premise": "前提句",
                "intermediate": "中间句",
                "conclusion": "结论句",
            },
            lang="zh",
        )
        self.assertEqual(context, "前提句 中间句 结论句")


class MultihopExtractionTest(unittest.TestCase):
    def test_extract_valid_json_object(self):
        response = """
        {
          "question": "为什么量子纠缠现象对量子计算很重要？",
          "reasoning_steps": [
            {"step": "贝尔实验证实了量子纠缠的真实性"},
            {"step": "该现象是量子计算的基础"}
          ],
          "answer": "因为量子纠缠被证实真实且是量子计算的基础",
          "supporting_facts": [
            "后来贝尔实验证实了其真实性",
            "该现象是量子计算的基础"
          ],
          "type": "量子物理"
        }
        """
        qa_pairs = extract_multihop_qa_pairs(response, strict=True)

        self.assertEqual(len(qa_pairs), 1)
        self.assertEqual(qa_pairs[0]["type"], "量子物理")
        self.assertEqual(len(qa_pairs[0]["reasoning_steps"]), 2)

    def test_reject_incomplete_multihop_payload(self):
        response = '{"question":"Q","answer":"A","reasoning_steps":[{"step":"1"}],"supporting_facts":["f1"],"type":"x"}'
        qa_pairs = extract_multihop_qa_pairs(response, strict=True)
        self.assertEqual(qa_pairs, [])

    def test_extract_json_from_noisy_response(self):
        response = (
            "说明文字\n"
            '{"question":"Q1","reasoning_steps":[{"step":"s1"},{"step":"s2"}],'
            '"answer":"A1","supporting_facts":["f1","f2"],"type":"domain"}\n'
            "尾部说明"
        )
        qa_pairs = extract_multihop_qa_pairs(response, strict=True)
        self.assertEqual(len(qa_pairs), 1)
        self.assertEqual(qa_pairs[0]["question"], "Q1")

    def test_calculate_complexity(self):
        score = calculate_multihop_complexity(
            [
                {
                    "question": "one two three",
                    "answer": "one two three four five",
                    "reasoning_steps": [{"step": "1"}, {"step": "2"}],
                    "supporting_facts": ["f1", "f2"],
                },
            ],
        )
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 1.0)


if __name__ == "__main__":
    unittest.main()
