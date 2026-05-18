from __future__ import annotations

from datalight.pipeline.core import Operator, Record

DEFAULT_ALPACA_INSTRUCTION = "Please answer the following question based on the provided information."


class QAExtractorOperator(Operator):
    """Flatten generated QA structures into Alpaca-style training records."""

    def __init__(self, instruction: str = DEFAULT_ALPACA_INSTRUCTION):
        self.instruction = instruction

    def run(self, rows: list[Record]) -> list[Record]:
        out: list[Record] = []
        for row in rows:
            pairs = row.get("qa_pairs")
            if pairs is None:
                pairs = [row]
            if not isinstance(pairs, list):
                continue
            for pair in pairs:
                if not isinstance(pair, dict):
                    continue
                question = str(pair.get("question") or pair.get("generated_question") or "").strip()
                answer = str(pair.get("answer") or pair.get("generated_answer") or "").strip()
                if not question or not answer:
                    continue
                out.append(
                    {
                        "instruction": self.instruction,
                        "input": question,
                        "output": answer,
                        "source_md": row.get("source_md", ""),
                        "chunk_index": row.get("chunk_index", -1),
                        "metadata": {
                            "reasoning_steps": pair.get("reasoning_steps", []),
                            "supporting_facts": pair.get("supporting_facts", []),
                            "type": pair.get("type", ""),
                        },
                    },
                )
        return out
