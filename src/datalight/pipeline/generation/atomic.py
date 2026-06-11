from __future__ import annotations

import json
import re
import string
from collections import Counter
from typing import Any
from tqdm import tqdm

from datalight.llm import LLMClient
from datalight.log import get_logger
from datalight.pipeline.core import Operator, Record, limit_rows_per_chunk
from datalight.pipeline.prompts.atomic import (
    AtomicAnswerPrompt,
    AtomicCleanQAPrompt,
    AtomicGetConclusionPrompt,
    AtomicGetIdentifierPrompt,
    AtomicGoldenDocAnswerPrompt,
    AtomicOptionalAnswerPrompt,
    AtomicQuestionPrompt,
    AtomicRecallScorePrompt,
)
from datalight.utils.json_parse import (
    clean_json_block,
    parse_content_identifier,
    parse_json_dict,
    parse_json_value,
    parse_recall_score,
)

logger = get_logger("pipeline.atomic")


class AtomicTaskQAGeneratorOperator(Operator):
    """Port of AgenticRAGAtomicTaskGenerator for high-quality atomic QA generation."""

    def __init__(
        self,
        llm_client: LLMClient,
        *,
        max_per_task: int = 10,
        max_question: int = 10,
        input_key: str = "chunk_text",
    ):
        if max_per_task <= 0 or max_question <= 0:
            raise ValueError("max_per_task and max_question must be positive")
        self.llm_client = llm_client
        self.max_per_task = max_per_task
        self.max_question = max_question
        self.input_key = input_key
        self._identifier_prompt = AtomicGetIdentifierPrompt()
        self._conclusion_prompt = AtomicGetConclusionPrompt()
        self._question_prompt = AtomicQuestionPrompt()
        self._clean_prompt = AtomicCleanQAPrompt()
        self._answer_prompt = AtomicAnswerPrompt()
        self._recall_prompt = AtomicRecallScorePrompt()
        self._optional_prompt = AtomicOptionalAnswerPrompt()
        self._golden_doc_prompt = AtomicGoldenDocAnswerPrompt()

    def run(self, rows: list[Record]) -> list[Record]:
        source_rows = [dict(row) for row in rows if str(row.get(self.input_key, "")).strip()]
        if not source_rows:
            return []

        logger.info("Atomic QA: get identifier for %s chunks", len(source_rows))
        identifiers = _batch_generate(
            self.llm_client,
            [self._identifier_prompt.build_prompt(str(row[self.input_key])) for row in source_rows],
            system_prompt=self._identifier_prompt.build_system_prompt(),
            desc="Atomic: identifier",
        )

        logger.info("Atomic QA: extract conclusions")
        conclusions = _batch_generate(
            self.llm_client,
            [self._conclusion_prompt.build_prompt(str(row[self.input_key])) for row in source_rows],
            system_prompt=self._conclusion_prompt.build_system_prompt(),
            desc="Atomic: conclusions",
        )

        expanded_rows = _expand_conclusion_rows(
            source_rows,
            identifiers=identifiers,
            conclusions=conclusions,
            input_key=self.input_key,
            max_per_task=self.max_per_task,
        )
        if not expanded_rows:
            logger.warning("Atomic QA: no valid candidate tasks extracted")
            return []

        logger.info("Atomic QA: generate questions from %s candidate tasks", len(expanded_rows))
        question_rows = _generate_atomic_questions(
            self.llm_client,
            expanded_rows,
            question_prompt=self._question_prompt,
        )
        if not question_rows:
            logger.warning("Atomic QA: no valid QA pairs generated")
            return []

        logger.info("Atomic QA: clean %s QA pairs", len(question_rows))
        question_rows = _clean_atomic_qa(self.llm_client, question_rows, clean_prompt=self._clean_prompt)
        question_rows = _verify_llm_recall(
            self.llm_client,
            question_rows,
            answer_prompt=self._answer_prompt,
            recall_prompt=self._recall_prompt,
            input_key=self.input_key,
        )
        if not question_rows:
            logger.warning("Atomic QA: all rows filtered by LLM recall verification")
            return []

        logger.info("Atomic QA: golden doc verification for %s rows", len(question_rows))
        question_rows = _verify_golden_doc(
            self.llm_client,
            question_rows,
            golden_doc_prompt=self._golden_doc_prompt,
            recall_prompt=self._recall_prompt,
            input_key=self.input_key,
        )
        if not question_rows:
            logger.warning("Atomic QA: all rows filtered by golden doc verification")
            return []

        logger.info("Atomic QA: generate optional answers")
        for row in tqdm(question_rows, desc="Atomic: optional answers"):
            row["optional_answer"] = _generate_optional_answers(
                self.llm_client,
                str(row.get("refined_answer", "")),
                optional_prompt=self._optional_prompt,
            )
            row["golden_doc_f1"] = _f1_score(
                str(row.get("golden_doc_answer", "")),
                row.get("optional_answer"),
            )

        limited = limit_rows_per_chunk(question_rows, max_per_chunk=self.max_question)
        return [_build_atomic_output_row(row) for row in limited]


def _batch_generate(
    llm_client: LLMClient,
    prompts: list[str],
    *,
    system_prompt: str = "",
    desc: str | None = None,
) -> list[str]:
    if not prompts:
        return []
    if desc is None:
        return llm_client.generate(prompts, system_prompt=system_prompt)
    return [
        llm_client.generate([prompt], system_prompt=system_prompt)[0]
        for prompt in tqdm(prompts, desc=desc)
    ]


def _expand_conclusion_rows(
    rows: list[Record],
    *,
    identifiers: list[str],
    conclusions: list[str],
    input_key: str,
    max_per_task: int,
) -> list[Record]:
    expanded: list[Record] = []
    for row, identifier_response, conclusion_response in zip(rows, identifiers, conclusions):
        identifier = parse_content_identifier(identifier_response)
        parsed = parse_json_value(conclusion_response)
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list):
            continue
        parsed = parsed[:max_per_task]
        for item in parsed:
            if not isinstance(item, dict):
                continue
            conclusion = str(item.get("conclusion", "")).strip()
            relation = str(item.get("R", "")).strip()
            if not conclusion or not relation:
                continue
            expanded.append(
                {
                    **row,
                    "identifier": identifier,
                    "candidate_tasks_str": json.dumps(
                        {"conclusion": conclusion, "R": relation},
                        ensure_ascii=False,
                    ),
                },
            )
    return expanded


def _generate_atomic_questions(
    llm_client: LLMClient,
    rows: list[Record],
    *,
    question_prompt: AtomicQuestionPrompt,
) -> list[Record]:
    prompts: list[str] = []
    valid_rows: list[Record] = []
    for row in rows:
        try:
            task = json.loads(clean_json_block(str(row["candidate_tasks_str"])))
            identifier = parse_content_identifier(str(row.get("identifier", "")))
        except (json.JSONDecodeError, KeyError):
            continue
        conclusion = str(task.get("conclusion", "")).strip()
        relation = str(task.get("R", "")).strip()
        if not conclusion or not relation:
            continue
        prompts.append(question_prompt.build_prompt(identifier, conclusion, relation))
        valid_rows.append(row)

    responses = _batch_generate(
        llm_client,
        prompts,
        system_prompt=question_prompt.build_system_prompt(),
        desc="Atomic: questions",
    )
    out: list[Record] = []
    for row, response in tqdm(
        zip(valid_rows, responses),
        total=len(valid_rows),
        desc="Atomic: parse questions",
    ):
        parsed = parse_json_dict(response)
        question = str(parsed.get("Q", "")).strip()
        if not question:
            continue
        try:
            task = json.loads(clean_json_block(str(row["candidate_tasks_str"])))
            answer = str(task.get("conclusion", "")).strip()
        except json.JSONDecodeError:
            answer = ""
        item = dict(row)
        item["question"] = question
        item["answer"] = answer
        out.append(item)
    return out


def _clean_atomic_qa(
    llm_client: LLMClient,
    rows: list[Record],
    *,
    clean_prompt: AtomicCleanQAPrompt,
) -> list[Record]:
    prompts = [
        clean_prompt.build_prompt(
            {"question": str(row["question"]), "original_answer": str(row["answer"])},
        )
        for row in rows
    ]
    responses = _batch_generate(
        llm_client,
        prompts,
        system_prompt=clean_prompt.build_system_prompt(),
        desc="Atomic: clean QA",
    )
    out: list[Record] = []
    for row, response in tqdm(
        zip(rows, responses),
        total=len(rows),
        desc="Atomic: parse clean QA",
    ):
        parsed = parse_json_dict(response)
        refined = str(parsed.get("refined_answer", "")).strip()
        if not refined:
            continue
        item = dict(row)
        item["refined_answer"] = refined
        out.append(item)
    return out


def _verify_llm_recall(
    llm_client: LLMClient,
    rows: list[Record],
    *,
    answer_prompt: AtomicAnswerPrompt,
    recall_prompt: AtomicRecallScorePrompt,
    input_key: str,
) -> list[Record]:
    llm_answers = _batch_generate(
        llm_client,
        [answer_prompt.build_prompt(str(row["question"])) for row in rows],
        desc="Atomic: LLM answers",
    )
    recall_responses = _batch_generate(
        llm_client,
        [
            recall_prompt.build_prompt(str(row["refined_answer"]), llm_answer)
            for row, llm_answer in zip(rows, llm_answers)
        ],
        system_prompt=recall_prompt.build_system_prompt(),
        desc="Atomic: LLM recall",
    )
    out: list[Record] = []
    for row, llm_answer, recall_response in tqdm(
        zip(rows, llm_answers, recall_responses),
        total=len(rows),
        desc="Atomic: filter LLM recall",
    ):
        score = parse_recall_score(recall_response)
        if score is None or score >= 1:
            continue
        item = dict(row)
        item["llm_answer"] = llm_answer
        item["llm_recall_score"] = score
        out.append(item)
    return out


def _verify_golden_doc(
    llm_client: LLMClient,
    rows: list[Record],
    *,
    golden_doc_prompt: AtomicGoldenDocAnswerPrompt,
    recall_prompt: AtomicRecallScorePrompt,
    input_key: str,
) -> list[Record]:
    golden_answers = _batch_generate(
        llm_client,
        [
            golden_doc_prompt.build_prompt(str(row[input_key]), str(row["question"]))
            for row in rows
        ],
        desc="Atomic: golden doc",
    )
    recall_responses = _batch_generate(
        llm_client,
        [
            recall_prompt.build_prompt(str(row["refined_answer"]), golden_answer)
            for row, golden_answer in zip(rows, golden_answers)
        ],
        system_prompt=recall_prompt.build_system_prompt(),
        desc="Atomic: golden recall",
    )
    out: list[Record] = []
    for row, golden_answer, recall_response in tqdm(
        zip(rows, golden_answers, recall_responses),
        total=len(rows),
        desc="Atomic: filter golden doc",
    ):
        score = parse_recall_score(recall_response)
        if score is None or score < 1:
            continue
        item = dict(row)
        item["golden_doc_answer"] = golden_answer
        item["golden_doc_recall_score"] = score
        out.append(item)
    return out


def _generate_optional_answers(
    llm_client: LLMClient,
    refined_answer: str,
    *,
    optional_prompt: AtomicOptionalAnswerPrompt,
) -> list[str]:
    if not refined_answer:
        return []
    response = _batch_generate(
        llm_client,
        [optional_prompt.build_prompt(refined_answer)],
        system_prompt=optional_prompt.build_system_prompt(),
    )[0]
    parsed = parse_json_value(response)
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [refined_answer]


def _build_atomic_output_row(row: Record) -> Record:
    item = dict(row)
    raw_answer = str(row.get("answer", ""))
    item["original_answer"] = raw_answer
    item["answer"] = str(row.get("refined_answer", raw_answer))
    item["context"] = str(row.get("chunk_text", ""))
    item["qa_type"] = "atomic"
    item["hop_type"] = "singlehop"
    item["reasoning_steps"] = []
    item["supporting_facts"] = []
    return item


def _normalize_answer(text: str) -> str:
    def remove_articles(value: str) -> str:
        return re.sub(r"\b(a|an|the)\b", " ", value)

    def white_space_fix(value: str) -> str:
        return " ".join(value.split())

    def remove_punc(value: str) -> str:
        exclude = set(string.punctuation)
        return "".join(char for char in value if char not in exclude)

    return white_space_fix(remove_articles(remove_punc(text.lower())))


def _f1_score(prediction: str, ground_truths: Any) -> float:
    if ground_truths is None or not prediction:
        return 0.0
    if isinstance(ground_truths, str):
        ground_truths = [ground_truths]
    if not isinstance(ground_truths, list):
        return 0.0

    best_f1 = 0.0
    normalized_prediction = _normalize_answer(prediction)
    for ground_truth in ground_truths:
        if ground_truth is None:
            continue
        normalized_truth = _normalize_answer(str(ground_truth))
        prediction_tokens = normalized_prediction.split()
        truth_tokens = normalized_truth.split()
        common = Counter(prediction_tokens) & Counter(truth_tokens)
        num_same = sum(common.values())
        if num_same == 0:
            continue
        precision = num_same / len(prediction_tokens) if prediction_tokens else 0.0
        recall = num_same / len(truth_tokens) if truth_tokens else 0.0
        if precision + recall == 0:
            continue
        best_f1 = max(best_f1, (2 * precision * recall) / (precision + recall))
    return best_f1
