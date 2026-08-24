"""Conversion helpers for the provider-neutral evaluation-result-v1 contract."""
from __future__ import annotations
from typing import Any
from airt.models import CaseResult, ResultStatus


def from_airt(result: CaseResult, *, target: str = "unified_dify_chatflow") -> dict[str, Any]:
    case = result.case
    category = "security"
    if case and "tools" in case.tags:
        category = "tools"
    elif case and case.quality is not None:
        category = "quality"
    verdict_status = str(getattr(getattr(result.verdict, "status", None), "value", getattr(result.verdict, "status", None)))
    if result.status is ResultStatus.ERROR:
        status = "error"
    elif category == "quality" and result.quality is not None:
        status = "passed" if result.quality.get("passed") is True else "failed"
    else:
        # Security/tool verdicts use success for an attack that broke the
        # boundary; a fail verdict means the application blocked the attack.
        status = "failed" if verdict_status == "success" else "passed"
    reply = result.reply
    scores: dict[str, Any] = {
        "security": result.verdict.confidence * 100
        if result.verdict and category != "quality"
        else None
    }
    if result.quality is not None:
        scores["quality"] = result.quality.get("judge_score")
        scores["semantic"] = result.quality.get("semantic_score")
    return {
        "schema_version": "evaluation-result-v1",
        "runner": "airt",
        "target": target,
        "case_id": result.case_id,
        "category": category,
        "status": status,
        "answer": reply.text if reply else "",
        "sources": [],
        "tool_calls": [call.model_dump(mode="json") for call in (reply.tool_calls if reply else [])],
        "scores": scores,
        "latency_ms": result.latency_ms,
        "judge": {"used": result.security_judge_used, "source": "live" if result.security_judge_used else "rule"},
        "error": result.error,
        "metadata": (result.run_metadata.model_dump(mode="json") if result.run_metadata else {}),
    }


def from_pytest(*, case_id: str, target: str, category: str, status: str, answer: str = "", sources: list[str] | None = None, scores: dict[str, float | None] | None = None, latency_ms: float | None = None, judge_used: bool = False, error: str | None = None, **metadata: Any) -> dict[str, Any]:
    return {
        "schema_version": "evaluation-result-v1",
        "runner": "pytest",
        "target": target,
        "case_id": case_id,
        "category": category,
        "status": status,
        "answer": answer,
        "sources": sources or [],
        "tool_calls": [],
        "scores": scores or {},
        "latency_ms": latency_ms,
        "judge": {"used": judge_used, "source": "live" if judge_used else "offline"},
        "error": error,
        "metadata": metadata,
    }
