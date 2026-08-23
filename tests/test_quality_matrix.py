from __future__ import annotations

import pytest

from airt.evaluation_bridge import EvaluationContext
from airt.quality_bridge import QualityEvaluator


@pytest.mark.parametrize("target_name", ["airt_dify_text", "airt_dify_chatflow"])
def test_quality_suite_can_consume_each_target_family_offline(target_name):
    context = EvaluationContext(
        answer=f"{target_name}：订单 A-1 已发货。",
        sources=[f"{target_name}：订单 A-1 已发货。"],
        latency_ms=25.0,
    )
    result = QualityEvaluator().evaluate(context, expected_answer="订单 A-1 已发货。", max_hallucination_rate=0.0)
    assert result.passed is True
    assert result.latency_ms == 25.0
