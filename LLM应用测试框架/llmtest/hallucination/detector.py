"""幻觉检测：事实一致性评估，计算幻觉率。"""

from __future__ import annotations

from typing import List, Union

from ..metrics.tracker import tracker
from ..registry import get_default_client
from ..specs import HallucinationReport


def _to_context(context: Union[str, List[str]]) -> str:
    """归一化上下文：str 原样，list[str] 按段落拼接。"""
    if isinstance(context, str):
        return context
    return "\n".join(str(c) for c in context)


def detect_hallucination(
    response: str,
    context: Union[str, List[str]],
    *,
    client=None,
) -> HallucinationReport:
    """检测回答相对上下文的幻觉。

    流程：把回答分解为事实断言 → 逐条核对是否被上下文支撑/矛盾 →
    返回报告（含幻觉率）。测量函数，结果自动记入指标采集。
    """
    client = client or get_default_client()
    ctx_text = _to_context(context)
    claims = client.extract_claims(response)
    verdicts = [client.verify_claim(c, ctx_text) for c in claims]
    report = HallucinationReport(response=response, context=ctx_text, claims=verdicts)
    tracker.add_hallucination(report)
    tracker.record_metric("hallucination_rate", report.hallucination_rate)
    return report


def assert_hallucination_rate(
    response: str,
    context: Union[str, List[str]],
    *,
    client=None,
    max_rate: float = 0.5,
) -> HallucinationReport:
    """断言回答相对上下文的幻觉率 ≤ max_rate。失败抛 AssertionError。"""
    report = detect_hallucination(response, context, client=client)
    rate = report.hallucination_rate
    passed = rate <= max_rate

    summary = (
        f"幻觉率 {rate:.1%}（阈值 {max_rate:.1%}）· 断言 {report.total} 条 · "
        f"支持 {len(report.supported)} · 幻觉 {len(report.hallucinated)}"
        f"{'（含矛盾 ' + str(len(report.contradicted)) + '）' if report.contradicted else ''}"
    )
    details = "\n".join(
        f"  [{c.verdict}] {c.claim} —— {c.evidence}" for c in report.claims
    )
    message = f"{summary}\n{details}"

    tracker.add_assertion("assert_hallucination_rate", passed, message, rate, max_rate)
    if not passed:
        raise AssertionError(message)
    return report


__all__ = ["detect_hallucination", "assert_hallucination_rate", "HallucinationReport"]
