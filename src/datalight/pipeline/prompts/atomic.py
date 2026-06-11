from __future__ import annotations

import json
import textwrap


class AtomicGetIdentifierPrompt:
    def build_system_prompt(self) -> str:
        return textwrap.dedent(
            """\
            You need to extract the content_identifier from question. Here's how:
              1. For each question, identify the main subject/noun phrase that the question is about
              2. This should typically be:
                - Proper nouns (names, titles)
                - Specific technical terms
                - Unique identifiers in the question

              Examples:
              {
                  "question": "What is the third movie in the Avatar series?",
                  "content_identifier": "Avatar series"
              },
              {
                  "question": "龙美术馆2025年展览展览时间范围是什么",
                  "content_identifier": "龙美术馆"
              }

              Return JSON format with key "content_identifier"
            """,
        )

    def build_prompt(self, text: str) -> str:
        return f"\nNow process this question:{text}\n"


class AtomicGetConclusionPrompt:
    def build_system_prompt(self) -> str:
        return textwrap.dedent(
            """\
            # Conclusion Extraction and Relationship Generation Specifications

              ## I. Input/Output Requirements
              **Input**: Any document fragment
              **Output**: JSON array where each element contains `conclusion` and `R` fields

              ## II. Conclusion Extraction Rules
              1. **Atomicity**
                  - Each conclusion must be an indivisible basic fact
                  - ✖ Prohibited combined conclusions

              2. **Verifiability**
                  - Must contain at least one definite identifier:
                    ✓ Numeric value (59.0%)
                    ✓ Time (2025/04/28)
                    ✓ Unique name (Humpback65B)
                  - ✖ Reject vague expressions: "Performance has improved"

              3. **Timeliness Handling**
                  - Explicitly mark time ranges when containing time-sensitive information

              4. **Citation Integrity**
                  - If a conclusion cites other content, the complete referenced content must be embedded

              ## III. Relationship (R) Generation Standards
              - **Structured**: Use semicolons to separate multi-metrics
              - **Operational**: Directly usable for database queries or calculations

              ## IV. Output Specifications
              Return a JSON array, each item:
              {"conclusion": "...", "R": "..."}
            """,
        )

    def build_prompt(self, text: str) -> str:
        return f"\nThe document content to be processed is as follows: {text}\n"


class AtomicQuestionPrompt:
    def build_system_prompt(self) -> str:
        return textwrap.dedent(
            """\
            Your task is to generate a corresponding question (Q) based on the given task identifier (ID), relationship (R), and answer (A).

              Output:
              - Must be in strict JSON format: {"Q": "generated question"}
              - No explanations or extra fields allowed

              Q must satisfy:
              1. Be a complete natural language question
              2. Allow deriving answer A by applying R after accessing context via ID
              3. Exact correspondence with the original conclusion
              4. Self-contained and specific enough for a unique answer
              5. Language consistency with the conclusion

              Only output JSON without additional content.
            """,
        )

    def build_prompt(self, identifier: str, conclusion: str, relation: str) -> str:
        return (
            "Data to be Processed:\n"
            f"ID: {identifier}\n"
            f"R: {relation}\n"
            f"A: {conclusion}\n"
        )


class AtomicCleanQAPrompt:
    def build_system_prompt(self) -> str:
        return textwrap.dedent(
            """\
            Processing Rules:
              1. Extract ONLY the exact information requested in the question
              2. Never omit essential information
              3. Standardize numerical formats where applicable

              Required JSON format:
              {
                  "question": str,
                  "original_answer": str,
                  "refined_answer": str
              }

              Key requirements:
              - Be extremely concise in refined_answer
              - Never add information not present in original_answer
              - Preserve all numerical values exactly
            """,
        )

    def build_prompt(self, payload: dict[str, str]) -> str:
        return f"The data need to be processed is as follows: {json.dumps(payload, ensure_ascii=False)}\n"


class AtomicAnswerPrompt:
    def build_prompt(self, question: str) -> str:
        return (
            "Please solve the following problem and return as many relevant results as possible "
            "that meet the query requirements. Ensure responses are as concise as possible, "
            "focusing only on key information while omitting redundant details. "
            f"The task is:\n{question}"
        )


class AtomicRecallScorePrompt:
    def build_system_prompt(self) -> str:
        return textwrap.dedent(
            """\
            Evaluate the consistency of the core content of the golden answer and the other answer
              # Scoring Criteria
                1) 2 points: completely consistent
                2) 1 point: other answer contains all golden answer information plus extra valid information
                3) 0 point: lacks key information or contradicts

              # the output should be in JSON format
              {
                "answer_analysis":"...",
                "answer_score":0/1/2
              }
            """,
        )

    def build_prompt(self, golden_answer: str, llm_answer: str) -> str:
        return (
            "The inputs are as follows:\n"
            f"Golden Answer: {golden_answer}\n"
            f"Other Answer: {llm_answer}\n"
        )


class AtomicOptionalAnswerPrompt:
    def build_system_prompt(self) -> str:
        return textwrap.dedent(
            """\
            You are an expert in linguistic variation and data augmentation.
            Generate all plausible alternative expressions for the same entity or information.
            Always include the original input as the first item.
            Output a JSON list of strings.
            """,
        )

    def build_prompt(self, answer: str) -> str:
        return (
            f"The original answer is: {answer}\n"
            "Respond with a JSON list of strings. Do not explain."
        )


class AtomicGoldenDocAnswerPrompt:
    def build_prompt(self, golden_doc: str, question: str) -> str:
        return (
            "You are given the following document that contains relevant information to help answer a question.\n"
            "Document:\n"
            f'"""\n{golden_doc}\n"""\n'
            f"Question:\n{question}\n"
            "Please answer the question using ONLY the information in the provided document. "
            "Return the final answer directly, with no explanation."
        )
