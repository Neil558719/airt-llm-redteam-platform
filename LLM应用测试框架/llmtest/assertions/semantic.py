"""语义断言：判断模型回答与期望含义是否语义等价。"""

from __future__ import annotations

from typing import Optional

from ..metrics.tracker import tracker
from ..registry import get_default_client
from ..specs import SemanticResult


def semantic_match(
    actual: str,
    expected: str,
    *,
    client=None,
    context: Optional[str] = None,
) -> SemanticResult:
    """测量实际回答与期望含义的语义等价性（0~1），并记录指标。"""
    client = client or get_default_client()
    result = client.semantic_equivalent(actual, expected, context)
    tracker.record_metric("semantic_score", result.score)
    return result


def assert_semantic_match(
    actual: str,
    expected: str,
    *,
    client=None,
    threshold: float = 0.7,
    context: Optional[str] = None,
) -> SemanticResult:
    """断言实际回答与期望含义语义等价（分数 ≥ threshold）。失败抛 AssertionError。"""
    result = semantic_match(actual, expected, client=client, context=context)
    passed = result.score >= threshold
    message = (
        f"语义断言失败: 分数 {result.score:.3f} < 阈值 {threshold:.3f}\n"
        f"实际回答: {actual[:200]}\n期望含义: {expected[:200]}\n理由: {result.reasoning}"
    )
    tracker.add_assertion("assert_semantic_match", passed, message, result.score, threshold)
    if not passed:
        raise AssertionError(message)
    return result
