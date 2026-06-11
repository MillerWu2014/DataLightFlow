from __future__ import annotations


class Text2QAAutoPromptTemplate:
    """Port of dataflow.prompts.text2qa.Text2QAAutoPromptGeneratorPrompt."""

    def build_prompt(self, seed_data: str, *, question_num: int = 1) -> str:
        if question_num <= 0:
            raise ValueError("question_num must be positive")
        prompt_count_instruction = (
            f"Generate exactly {question_num} distinct, non-repeating prompts"
            if question_num > 1
            else "Generate as much non-repeat clear and effective prompt as you can"
        )
        return (
            "You will be given a piece of seed data, which may consist of a paragraph, dialogue, "
            "or any other form of text containing potential question-answer information.\n"
            f"Your task is to analyze this seed data carefully and {prompt_count_instruction} that can be used to instruct a language model to extract "
            "a single high-quality question-answer (QA) pair suitable for reinforcement learning (RL) "
            "training from this piece of data.\n\n"
            "The generated prompt should:\n"
            "Clearly describe the type and format of input the model will receive;\n"
            "Explicitly ask for the extraction of a relevant QA pair;\n"
            "Optionally include instructions about the desired style, level of detail, or coverage;\n"
            "Be written in natural, precise English that could be directly used with another LLM;\n"
            "Be strictly the prompt used to extract QA pairs, not the QA pairs themselves.\n\n"
            "Your prompts should contain the following instructions:\n"
            "The question should be clear, focused, and unambiguous, such that it targets specific "
            "factual content from the input;\n"
            "The answer should be a few words that are concise, factual and directly verifiable from "
            "the source rather than a whole sentence, enabling accurate reward computation in the "
            "RL pipeline;\n"
            "Both the question and answer should be simple enough to facilitate evaluation and "
            "automatic feedback.\n\n"
            "Don't include any additional explanations or comments in your output.\n"
            "Don't repeat the seed data in your output.\n"
            "Your output format should be in a list as follow:\n"
            '[\"PROMPT_1\",\"PROMPT_2\",...]\n'
            f"Here is the seed data you need to analyze and generate a prompt for:\n{seed_data}"
        )


class Text2QASeedPromptTemplate:
    """Port of dataflow.prompts.text2qa.Text2QASeedQuestionGeneratorPrompt."""

    def build_suffix(self) -> str:
        return 'Format:\nQ: ...\nA: ..."\nSeed data:\n'

    def build_prompt(self, generated_prompt: str, seed_data: str) -> str:
        return f"{generated_prompt}{self.build_suffix()}{seed_data}"
