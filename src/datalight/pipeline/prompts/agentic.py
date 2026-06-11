from __future__ import annotations

import json
import textwrap


class DepthGetIdentifierPrompt:
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

    def build_prompt(self, question: str) -> str:
        return f"\nNow process this question:{question}\n"


class DepthBackwardTaskPrompt:
    def build_prompt(self, identifier: str) -> str:
        return textwrap.dedent(
            f"""\
            Conduct divergent searches based on the input element to find an appropriate superset related to its attributes, and elaborate on the relationship between the superset and the element (mine for special and uniquely pointing relationships to ensure that the superset + relationship does not mislead to other subsets). Example supersets include:
              1. The superset of a paragraph or sentence can be the text content it belongs to.
              2. The superset of a specific term can be its corresponding discipline or category.
              3. The superset of a specific date can be any date range containing it, such as the week or month it belongs to.
              4. The superset of a short event can be the complete specific event it belongs to.
              5. The superset of a page can be other pages referencing it or its parent page.
              6. Only generate one relationship, and the content of the relationship should preferably not include strongly specific proper nouns.

              Optional expressions for relationships:
              1. Clearly express hierarchical or ownership relationships. If the input is a sub-item of a series of works, the relation should indicate its position; if the input is a part of a superset, the relation should clarify its ownership.
              2. Provide the specific positioning of the input content, such as time range, field of paper publication, or specific role in the superset.
              3. Wording should conform to the research field or industry standards of the input content.
              4. Only provide necessary association information to avoid irrelevant content. Good example: "This study is part of the IRAM NOEMA Large Program research collection". Bad example: "This study is a very important research conducted by many scientists and has produced very meaningful results" (verbose and containing subjective evaluations).

              Note:
              1. Please return the identifier of the superset content, such as attribute name, web page title, paper title, etc., which uniquely locates the superset content.
              2. The content of the superset needs to be obtained through tool invocation, which can be specific web content, PDF text, or image understanding content.
              3. Please clearly describe the relationship between the superset content and the input element, that is, list the qualification conditions from the superset content to ensure that the conditions uniquely point to the input element, and the description of the conditions should be concise.
              4. Use a maximum of 3 search keywords per search; if more than 3 keywords are needed, perform multiple searches separately.
              5. The obtained identifier should preferably be derived from search results and not include the input content.
              6. If the input is a PDF document, give priority to invoking tools to read the document content.

              Return format requirements: Please return the result in JSON format with keys 'identifier': str (identifier) and 'relation': str (relationship).

              Current input:
              {identifier}
            """,
        )


class DepthSupersetCheckPrompt:
    def build_system_prompt(self) -> str:
        return textwrap.dedent(
            """\
            **Task**: Validate if a given "superset" can uniquely identify a "subset" based on the provided "relationship".

              **Rules**:
              1. **Superset-Subset Relationship**:
                - The "superset" must be a true generalization of the "subset" (e.g., "Animal" is a valid superset of "Dog").
                - The "superset" CANNOT be a synonym of the "subset" (e.g., "Car" and "Automobile" are invalid).

              2. **Relationship Validity**:
                - The relationship must **explicitly and uniquely** link the superset to the subset.
                - It CANNOT be a **many-to-one mapping**.

              **Output Format**:
              Return a JSON with the key `new_query`. The value should be:
              - `"valid"` if the superset and relationship can uniquely locate the subset.
              - `"invalid"` otherwise.

              **Example Valid Output**:
              {"new_query": "valid"}
            """,
        )

    def build_prompt(self, new_id: str, relation: str, identifier: str) -> str:
        return (
            f"Given superset: {new_id}\n"
            f"Given relationship: {relation}\n"
            f"Given subset: {identifier}\n"
        )


class DepthQuestionPrompt:
    def build_system_prompt(self) -> str:
        return textwrap.dedent(
            """\
            Please generate a question based on the content of the input identifier, a certain answer, and a certain relationship (this relationship is the relationship between the content of the file corresponding to the identifier and the given answer), such that
              The answer to this question is the input answer.
              The content of this question is determined by the content of the identifier and the content of the given relationship.
              The generated question should not involve the content of the input answer.
              Please return it in JSON format, with the key of the JSON being new_query.
            """,
        )

    def build_prompt(self, new_id: str, relation: str, identifier: str) -> str:
        return (
            f"Certain answer: {identifier}\n"
            f"Identifier: {new_id}\n"
            f"Relationship: {relation}\n"
        )


class DepthAnswerPrompt:
    def build_prompt(self, question: str) -> str:
        return textwrap.dedent(
            f"""\
            Please solve the following problem and return as many relevant results as possible that meet the query requirements. Ensure responses are as concise as possible, focusing only on key information while omitting redundant details.
            Please return the result in JSON format with keys 'answer_list': List[str] the list of answers.

            The task is:
            {question}
            """,
        )


class DepthRecallScorePrompt:
    def build_system_prompt(self) -> str:
        return textwrap.dedent(
            """\
            Evaluate the consistency of the core content of the golden answer and the other answer
              # Scoring Criteria
                1) 2 points: the information between the golden answer and the other answer completely consistent, although the expression methods can be different.
                2) 1 point: the other answer contains all the information of the golden answer but has additional valid information.
                3) 0 point: the other answer lacks the necessary key information of the golden answer, or there are contradictions in both the information.

              # the output should be in JSON format as required without any irrelevant content
              {
                "answer_analysis":"give out the reason on how to score the llm_answer",
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


class WidthMergePrompt:
    def build_system_prompt(self) -> str:
        return textwrap.dedent(
            """\
            # Comprehensive Task Guide for Research Questions

              ## Core Objective:
              Intelligently merge 2-3 related research questions into high-quality comprehensive questions while maintaining the integrity and accuracy of the original content.

              ## Input Requirements:
              - Each question includes: index (unique ID), question (question text), golden_answer (standard answer), content_identifier (content identifier)

              ## Grouping Specifications:

              ### Grouping Strategies:
              1. **Content Matching Principle**:
                 - Priority: Merge questions with similar themes

              2. **Quantity Control**:
                 - Each group must contain 2-3 original questions
                 - Ensure all original questions are grouped (no omissions)

              ### Standards for Question Synthesis:
              1. **Content Integrity**:
                 - Retain all elements of the original questions
                 - Do not add new facts or assumptions
                 - Completely preserve time-related elements in their original form

              2. **Question Quality**:
                 - Clear and unambiguous expression
                 - Logically coherent merged questions
                 - Do not imply any solution methods

              3. **Structural Requirements**:
                 - Form complete interrogative sentences (not simply connected with "and")
                 - Correct grammatical structure
                 - Preserve professional terminology in its original form

              ## Output Specifications:
              [
                {
                  "question": "Text of the synthesized question",
                  "index": [1,2,3],
                  "content_identifier": "Original content identifier"
                }
              ]
            """,
        )

    def build_prompt(self, items: list[dict[str, object]]) -> str:
        return (
            "Here are the base questions to process:\n"
            f"{json.dumps(items, indent=2, ensure_ascii=False)}\n"
            "Each dictionary contains: index (unique ID), question (original question), and content_identifier (identifier)."
        )


class WidthOriginCheckPrompt:
    def build_system_prompt(self) -> str:
        return textwrap.dedent(
            """\
            Task Instructions:
              Verify if complex questions can be properly decomposed into their original questions.
              Return state=1 if all conditions are met, state=0 otherwise:

              Conditions for state=1:
              1. The complex question clearly contains all elements from original questions
              2. No information distortion or ambiguity introduced
              3. Logical relationships between original questions are properly maintained

              Example Output:
              [{
                  "index": 1,
                  "complex_question": "original complex question",
                  "state": 1
              }]
            """,
        )

    def build_prompt(self, item: dict[str, object]) -> str:
        return (
            "Here are the base questions to process:\n"
            f"{json.dumps(item, indent=2, ensure_ascii=False)}\n"
            "Each dictionary contains: index (unique ID), complex_question (original complex question), "
            "and original_questions (list of original questions)."
        )


class WidthQuestionVerifyPrompt:
    def build_system_prompt(self) -> str:
        return textwrap.dedent(
            """\
            Answer the provided complex research questions based on your knowledge.
              For each question, provide your answer.

              Output JSON format:
              [{
              "index": 1
              "complex_question": original complex question,
              "llm_answer": your answer
              }]
            """,
        )

    def build_prompt(self, item: dict[str, object]) -> str:
        return (
            "Please answer these research questions:\n"
            f"{json.dumps(item, indent=2, ensure_ascii=False)}"
        )


class WidthRecallScorePrompt:
    def build_system_prompt(self) -> str:
        return DepthRecallScorePrompt().build_system_prompt()

    def build_prompt(self, golden_answer: str, llm_answer: str) -> str:
        return DepthRecallScorePrompt().build_prompt(golden_answer, llm_answer)
