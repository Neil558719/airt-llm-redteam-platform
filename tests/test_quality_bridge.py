from __future__ import annotations

from airt.evaluation_bridge import EvaluationContext
from airt.quality_bridge import QualityEvaluator, QualityResult


def test_quality_evaluator_reports_semantic_and_rag_metrics_without_network():
    context = EvaluationContext(
        answer="订单 A-1 已发货，预计明天送达。",
        sources=["订单 A-1 状态：已发货；预计明天送达。"],
        latency_ms=42.5,
    )
    result = QualityEvaluator().evaluate(
        context,
        expected_answer="订单 A-1 已发货，预计明天送达。",
        max_hallucination_rate=0.0,
    )
    assert isinstance(result, QualityResult)
    assert result.semantic_passed is True
    assert result.semantic_score == 1.0
    assert result.hallucination_passed is True
    assert result.hallucination_rate == 0.0
    assert result.latency_ms == 42.5


def test_quality_evaluator_validates_json_and_schema_without_llmtest_install():
    context = EvaluationContext(answer='{"status":"shipped","order_id":"A-1"}')
    result = QualityEvaluator().evaluate(
        context,
        json_schema={
            "type": "object",
            "required": ["status", "order_id"],
            "properties": {"status": {"type": "string"}, "order_id": {"type": "string"}},
        },
    )
    assert result.json_valid is True
    assert result.schema_valid is True
    assert result.schema_error is None


def test_quality_evaluator_keeps_failures_as_data_for_report_consumers():
    result = QualityEvaluator().evaluate(
        EvaluationContext(answer="我不知道"),
        expected_answer="订单已发货",
        json_schema={"type": "object"},
    )
    assert result.semantic_passed is False
    assert result.schema_valid is False
    assert result.passed is False
    assert result.errors
