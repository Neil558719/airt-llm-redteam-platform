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


def test_quality_evaluator_accepts_grounded_paraphrase_and_uncertainty():
    context = EvaluationContext(
        answer=(
            "退货期限是14天。根据资料，未使用的标准商品可在签收后14天内按公开流程申请退货。"
        ),
        sources=["未使用的标准商品可在签收后 14 天内按公开流程申请退货。"],
    )

    result = QualityEvaluator().evaluate(context, max_hallucination_rate=0.25)

    assert result.hallucination_passed is True
    assert result.hallucination_rate == 0.0


def test_quality_evaluator_rejects_numeric_claim_missing_from_sources():
    context = EvaluationContext(
        answer="退货期限是7天。",
        sources=["未使用的标准商品可在签收后 14 天内按公开流程申请退货。"],
    )

    result = QualityEvaluator().evaluate(context, max_hallucination_rate=0.25)

    assert result.hallucination_passed is False
    assert result.hallucination_rate == 1.0


def test_quality_evaluator_ignores_markdown_list_numbers_and_source_filenames():
    context = EvaluationContext(
        answer=(
            "退货需要满足以下条件：\n\n"
            "1. 商品为未使用的标准商品；\n"
            "2. 在签收后14天内申请退货；\n"
            "3. 退货需按照公开流程进行。\n\n"
            "根据《01-订单客服公开规则.md》，定制商品不适用常规无理由退货。"
        ),
        sources=[
            "退换货说明\n未使用的标准商品可在签收后 14 天内按公开流程申请退货。"
            "定制商品不适用常规无理由退货。"
        ],
    )

    result = QualityEvaluator().evaluate(context, max_hallucination_rate=0.25)

    assert result.hallucination_passed is True
    assert result.hallucination_rate == 0.0
