from __future__ import annotations

from pathlib import Path

from datalight.llm import LLMClient, safe_generate
from datalight.log import get_logger
from datalight.pipeline.core import Operator, Record
from datalight.pipeline.models import AgenticQAPipelineResult
from datalight.pipeline.prompts.agentic import (
    DepthAnswerPrompt,
    DepthBackwardTaskPrompt,
    DepthGetIdentifierPrompt,
    DepthQuestionPrompt,
    DepthRecallScorePrompt,
    DepthSupersetCheckPrompt,
    WidthMergePrompt,
    WidthOriginCheckPrompt,
    WidthQuestionVerifyPrompt,
    WidthRecallScorePrompt,
)
from datalight.utils.json_parse import (
    parse_backward_result,
    parse_content_identifier,
    parse_json_dict,
    parse_json_value,
    parse_recall_score,
)
from datalight.utils.jsonl import read_jsonl, write_jsonl

logger = get_logger("pipeline.agentic")


class DepthQAGeneratorOperator(Operator):
    """Generate deeper questions using the original AgenticRAG depth pipeline."""

    def __init__(self, llm_client: LLMClient, n_rounds: int = 2):
        if n_rounds <= 0:
            raise ValueError("n_rounds must be positive")
        self.llm_client = llm_client
        self.n_rounds = n_rounds
        self._get_identifier_prompt = DepthGetIdentifierPrompt()
        self._backward_prompt = DepthBackwardTaskPrompt()
        self._superset_prompt = DepthSupersetCheckPrompt()
        self._question_prompt = DepthQuestionPrompt()
        self._answer_prompt = DepthAnswerPrompt()
        self._recall_prompt = DepthRecallScorePrompt()

    def run(self, rows: list[Record]) -> list[Record]:
        working = [dict(row) for row in rows if str(row.get("question", "")).strip()]
        if not working:
            return []

        working = _ensure_identifiers(self.llm_client, working, self._get_identifier_prompt)
        for round_id in range(1, self.n_rounds + 1):
            logger.info("Depth QA round %s/%s: rows=%s", round_id, self.n_rounds, len(working))
            identifier_key = "identifier" if round_id == 1 else f"new_identifier_{round_id - 1}"
            new_identifier_key = f"new_identifier_{round_id}"
            relation_key = f"relation_{round_id}"
            question_key = f"depth_question_{round_id}"

            working = _depth_backward_step(
                self.llm_client,
                working,
                identifier_key=identifier_key,
                new_identifier_key=new_identifier_key,
                relation_key=relation_key,
                backward_prompt=self._backward_prompt,
            )
            working = _depth_superset_check_step(
                self.llm_client,
                working,
                new_identifier_key=new_identifier_key,
                relation_key=relation_key,
                identifier_key=identifier_key,
                superset_prompt=self._superset_prompt,
            )
            working = _depth_question_step(
                self.llm_client,
                working,
                new_identifier_key=new_identifier_key,
                relation_key=relation_key,
                identifier_key=identifier_key,
                question_key=question_key,
                question_prompt=self._question_prompt,
            )
            working = _depth_verify_step(
                self.llm_client,
                working,
                question_key="question",
                answer_prompt=self._answer_prompt,
                recall_prompt=self._recall_prompt,
            )
            if not working:
                break

        return _build_depth_output_rows(working, n_rounds=self.n_rounds)


class WidthQAGeneratorOperator(Operator):
    """Generate breadth questions using the original AgenticRAG width pipeline."""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self._get_identifier_prompt = DepthGetIdentifierPrompt()
        self._merge_prompt = WidthMergePrompt()
        self._origin_prompt = WidthOriginCheckPrompt()
        self._verify_prompt = WidthQuestionVerifyPrompt()
        self._recall_prompt = WidthRecallScorePrompt()

    def run(self, rows: list[Record]) -> list[Record]:
        working = [dict(row) for row in rows if str(row.get("question", "")).strip()]
        if len(working) < 2:
            return []

        working = _ensure_identifiers(self.llm_client, working, self._get_identifier_prompt)
        input_batch = [
            {
                "index": index,
                "question": str(row.get("question", "")),
                "content_identifier": str(row.get("identifier", "")),
                "golden_answer": str(row.get("answer", "")),
            }
            for index, row in enumerate(working)
        ]

        merged_rows = _width_merge_step(self.llm_client, input_batch, merge_prompt=self._merge_prompt)
        if not merged_rows:
            return []

        merged_rows = _width_origin_check_step(self.llm_client, merged_rows, origin_prompt=self._origin_prompt)
        if not merged_rows:
            return []

        merged_rows = _width_verify_step(self.llm_client, merged_rows, verify_prompt=self._verify_prompt)
        if not merged_rows:
            return []

        return _build_width_output_rows(merged_rows, source_rows=working)


def run_depth_qa_pipeline(
    *,
    input_path: Path,
    output_path: Path,
    llm_client: LLMClient,
    n_rounds: int = 2,
) -> AgenticQAPipelineResult:
    rows = read_jsonl(input_path)
    generated = DepthQAGeneratorOperator(llm_client=llm_client, n_rounds=n_rounds).run(rows)
    write_jsonl(output_path, generated)
    return AgenticQAPipelineResult(
        input_path=input_path,
        output_path=output_path,
        qa_type="depth",
        count=len(generated),
    )


def run_width_qa_pipeline(
    *,
    input_path: Path,
    output_path: Path,
    llm_client: LLMClient,
) -> AgenticQAPipelineResult:
    rows = read_jsonl(input_path)
    generated = WidthQAGeneratorOperator(llm_client=llm_client).run(rows)
    write_jsonl(output_path, generated)
    return AgenticQAPipelineResult(
        input_path=input_path,
        output_path=output_path,
        qa_type="width",
        count=len(generated),
    )


def _ensure_identifiers(
    llm_client: LLMClient,
    rows: list[Record],
    prompt: DepthGetIdentifierPrompt,
) -> list[Record]:
    missing = [row for row in rows if not str(row.get("identifier", "")).strip()]
    if not missing:
        return rows

    prompts = [prompt.build_prompt(str(row["question"])) for row in missing]
    responses = safe_generate(llm_client, prompts, system_prompt=prompt.build_system_prompt())
    response_map = {id(row): response for row, response in zip(missing, responses)}

    out: list[Record] = []
    for row in rows:
        item = dict(row)
        if not str(item.get("identifier", "")).strip():
            item["identifier"] = parse_content_identifier(response_map[id(row)])
        out.append(item)
    return out


def _depth_backward_step(
    llm_client: LLMClient,
    rows: list[Record],
    *,
    identifier_key: str,
    new_identifier_key: str,
    relation_key: str,
    backward_prompt: DepthBackwardTaskPrompt,
) -> list[Record]:
    prompts = [backward_prompt.build_prompt(str(row[identifier_key])) for row in rows]
    responses = safe_generate(llm_client, prompts, system_prompt="")
    out: list[Record] = []
    for row, response in zip(rows, responses):
        parsed = parse_backward_result(response)
        if parsed is None:
            logger.warning("Skipped invalid backward result: %s", response)
            continue
        item = dict(row)
        item[new_identifier_key] = parsed["identifier"]
        item[relation_key] = parsed["relation"]
        out.append(item)
    return out


def _depth_superset_check_step(
    llm_client: LLMClient,
    rows: list[Record],
    *,
    new_identifier_key: str,
    relation_key: str,
    identifier_key: str,
    superset_prompt: DepthSupersetCheckPrompt,
) -> list[Record]:
    prompts = [
        superset_prompt.build_prompt(
            str(row[new_identifier_key]),
            str(row[relation_key]),
            str(row[identifier_key]),
        )
        for row in rows
    ]
    responses = safe_generate(llm_client, prompts, system_prompt=superset_prompt.build_system_prompt())
    out: list[Record] = []
    for row, response in zip(rows, responses):
        parsed = parse_json_dict(response)
        if parsed and parsed.get("new_query") == "valid":
            out.append(dict(row))
        else:
            logger.warning("Skipped invalid superset check: %s", response)
    return out


def _depth_question_step(
    llm_client: LLMClient,
    rows: list[Record],
    *,
    new_identifier_key: str,
    relation_key: str,
    identifier_key: str,
    question_key: str,
    question_prompt: DepthQuestionPrompt,
) -> list[Record]:
    prompts = [
        question_prompt.build_prompt(
            str(row[new_identifier_key]),
            str(row[relation_key]),
            str(row[identifier_key]),
        )
        for row in rows
    ]
    responses = safe_generate(llm_client, prompts, system_prompt=question_prompt.build_system_prompt())
    out: list[Record] = []
    for row, response in zip(rows, responses):
        parsed = parse_json_dict(response)
        new_query = str(parsed.get("new_query", "")).strip() if parsed else ""
        if not new_query:
            logger.warning("Skipped invalid depth question: %s", response)
            continue
        item = dict(row)
        item[question_key] = new_query
        out.append(item)
    return out


def _depth_verify_step(
    llm_client: LLMClient,
    rows: list[Record],
    *,
    question_key: str,
    answer_prompt: DepthAnswerPrompt,
    recall_prompt: DepthRecallScorePrompt,
) -> list[Record]:
    prompts = [answer_prompt.build_prompt(str(row[question_key])) for row in rows]
    llm_answers = safe_generate(llm_client, prompts, system_prompt="")
    recall_prompts = [
        recall_prompt.build_prompt(_golden_answer_text(row), llm_answer)
        for row, llm_answer in zip(rows, llm_answers)
    ]
    recall_responses = safe_generate(
        llm_client,
        recall_prompts,
        system_prompt=recall_prompt.build_system_prompt(),
    )
    out: list[Record] = []
    for row, llm_answer, recall_response in zip(rows, llm_answers, recall_responses):
        score = parse_recall_score(recall_response)
        if score is None or score >= 1:
            logger.warning("Skipped depth row after recall verification: score=%s", score)
            continue
        item = dict(row)
        item["llm_answer"] = llm_answer
        item["recall_score"] = score
        out.append(item)
    return out


def _width_merge_step(
    llm_client: LLMClient,
    input_batch: list[dict[str, object]],
    *,
    merge_prompt: WidthMergePrompt,
) -> list[Record]:
    pair_prompts = [
        merge_prompt.build_prompt([input_batch[index], input_batch[index + 1]])
        for index in range(len(input_batch) - 1)
    ]
    responses = safe_generate(llm_client, pair_prompts, system_prompt=merge_prompt.build_system_prompt())
    merged_rows: list[Record] = []
    for merge_index, response in enumerate(responses):
        parsed = parse_json_value(response)
        if isinstance(parsed, list) and parsed:
            result = parsed[0]
        elif isinstance(parsed, dict):
            result = parsed
        else:
            logger.warning("Skipped invalid width merge result: %s", response)
            continue
        if not isinstance(result, dict) or "question" not in result or "index" not in result:
            logger.warning("Skipped invalid width merge payload: %s", result)
            continue

        indices = result["index"] if isinstance(result["index"], list) else [result["index"]]
        group_items = [input_batch[int(index)] for index in indices]
        merged_rows.append(
            {
                "question": str(result["question"]),
                "content_identifier": str(result.get("content_identifier", "")),
                "qa_index": indices,
                "index": merge_index,
                "original_answer": [str(item["golden_answer"]) for item in group_items],
                "original_question": [str(item["question"]) for item in group_items],
            },
        )
    return merged_rows


def _width_origin_check_step(
    llm_client: LLMClient,
    rows: list[Record],
    *,
    origin_prompt: WidthOriginCheckPrompt,
) -> list[Record]:
    prompts = [
        origin_prompt.build_prompt(
            {
                "index": row["index"],
                "complex_question": row["question"],
                "original_questions": row["original_question"],
            },
        )
        for row in rows
    ]
    responses = safe_generate(llm_client, prompts, system_prompt=origin_prompt.build_system_prompt())
    out: list[Record] = []
    for row, response in zip(rows, responses):
        parsed = parse_json_value(response)
        if isinstance(parsed, list) and parsed:
            parsed = parsed[0]
        if not isinstance(parsed, dict):
            logger.warning("Skipped invalid width origin check: %s", response)
            continue
        state = parsed.get("state")
        complex_question = parsed.get("complex_question")
        if state != 1:
            continue
        item = dict(row)
        item["state"] = state
        item["generated_width_task"] = str(complex_question or item["question"])
        out.append(item)
    return out


def _width_verify_step(
    llm_client: LLMClient,
    rows: list[Record],
    *,
    verify_prompt: WidthQuestionVerifyPrompt,
) -> list[Record]:
    prompts = [
        verify_prompt.build_prompt(
            {
                "index": row["index"],
                "complex_question": row["generated_width_task"],
            },
        )
        for row in rows
    ]
    responses = safe_generate(llm_client, prompts, system_prompt=verify_prompt.build_system_prompt())
    out: list[Record] = []
    for row, response in zip(rows, responses):
        parsed = parse_json_value(response)
        if isinstance(parsed, list) and parsed:
            parsed = parsed[0]
        if not isinstance(parsed, dict):
            logger.warning("Skipped invalid width verify response: %s", response)
            continue
        llm_answer = parsed.get("llm_answer")
        if llm_answer is None:
            continue
        item = dict(row)
        item["llm_answer"] = str(llm_answer)
        out.append(item)

    recall_prompt = WidthRecallScorePrompt()
    recall_prompts = [
        recall_prompt.build_prompt(_golden_answer_text(row), str(row["llm_answer"]))
        for row in out
    ]
    recall_responses = safe_generate(
        llm_client,
        recall_prompts,
        system_prompt=recall_prompt.build_system_prompt(),
    )

    verified: list[Record] = []
    for row, recall_response in zip(out, recall_responses):
        score = parse_recall_score(recall_response)
        if score is None or score >= 1:
            logger.warning("Skipped width row after recall verification: score=%s", score)
            continue
        item = dict(row)
        item["recall_score"] = score
        verified.append(item)
    return verified


def _build_depth_output_rows(rows: list[Record], *, n_rounds: int) -> list[Record]:
    out: list[Record] = []
    for row in rows:
        for round_id in range(1, n_rounds + 1):
            question_key = f"depth_question_{round_id}"
            if question_key not in row or not str(row[question_key]).strip():
                continue
            item = dict(row)
            item["question"] = str(row[question_key])
            item["answer"] = str(row.get("identifier", ""))
            item["depth_round"] = round_id
            item["qa_type"] = "depth"
            item["hop_type"] = "singlehop"
            item["new_identifier"] = str(row.get(f"new_identifier_{round_id}", ""))
            item["relation"] = str(row.get(f"relation_{round_id}", ""))
            out.append(item)
    return out


def _build_width_output_rows(rows: list[Record], *, source_rows: list[Record]) -> list[Record]:
    out: list[Record] = []
    for row in rows:
        indices = row.get("qa_index", [])
        if not isinstance(indices, list):
            indices = [indices]
        source_refs = [source_rows[int(index)] for index in indices if 0 <= int(index) < len(source_rows)]
        base = dict(source_refs[0]) if source_refs else {}
        item = dict(base)
        item["question"] = str(row.get("generated_width_task", ""))
        item["answer"] = _golden_answer_text(row)
        item["qa_type"] = "width"
        item["hop_type"] = "singlehop"
        item["content_identifier"] = str(row.get("content_identifier", ""))
        item["source_question_indices"] = indices
        item["original_question"] = row.get("original_question", [])
        item["original_answer"] = row.get("original_answer", [])
        item["source_rows"] = source_refs
        out.append(item)
    return out


def _golden_answer_text(row: Record) -> str:
    golden = row.get("refined_answer", row.get("answer", row.get("original_answer", "")))
    if isinstance(golden, list):
        return "；".join(str(item).strip() for item in golden if str(item).strip())
    return str(golden).strip()
