from __future__ import annotations

from airt.quality_bridge import QualityResult, QualitySummary


def test_quality_result_serializes_judge_observability_fields():
    result = QualityResult(
        latency_ms=100.0,
        judge_score=0.8,
        judge_passed=True,
        judge_reason="准确",
        judge_latency_ms=250.0,
        judge_usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        judge_cost=0.0006,
    )
    data = result.as_dict()
    assert data["judge_latency_ms"] == 250.0
    assert data["judge_usage"]["total_tokens"] == 30
    assert data["judge_cost"] == 0.0006


def test_quality_summary_aggregates_judge_latency_and_cost():
    summary = QualitySummary.from_results([
        QualityResult(judge_latency_ms=100.0, judge_cost=0.001),
        QualityResult(judge_latency_ms=300.0, judge_cost=0.002),
    ])
    data = summary.as_dict()
    assert data["average_judge_latency_ms"] == 200.0
    assert data["total_judge_cost"] == 0.003


def test_quality_summary_calculates_latency_percentiles():
    summary = QualitySummary.from_results([QualityResult(latency_ms=value) for value in [10, 20, 30, 40, 50]])
    assert summary.latency_p50_ms == 30
    assert summary.latency_p95_ms == 48
    assert summary.latency_p99_ms == 49.6
