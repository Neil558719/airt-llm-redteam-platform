"""Unified evaluation-result-v1 records emitted by the pytest runner."""
from __future__ import annotations
from typing import Any


def quality_result(*, case_id: str, target: str, answer: str, expected: str, latency_ms: float | None, passed: bool, judge_used: bool = False, hallucination_rate: float | None = None, error: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": "evaluation-result-v1",
        "runner": "pytest",
        "target": target,
        "case_id": case_id,
        "category": "quality",
        "status": "passed" if passed else "failed",
        "answer": answer,
        "sources": [],
        "tool_calls": [],
        "scores": {
            "correctness": 1.0 if passed else 0.0,
            "hallucination_rate": hallucination_rate,
        },
        "latency_ms": latency_ms,
        "judge": {"used": judge_used, "source": "live" if judge_used else "offline"},
        "error": error,
        "metadata": {"expected_answer": expected},
    }
