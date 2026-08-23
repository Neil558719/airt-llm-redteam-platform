from __future__ import annotations

from airt.quality_bridge import QualitySummary
from airt.cli import release_gate_failures


def test_release_gate_reports_quality_and_latency_failures():
    quality = QualitySummary(total=10, passed=8, failed=2, average_latency_ms=1250.0)
    failures = release_gate_failures(
        risk_score=92.0,
        quality=quality,
        min_quality_pass_rate=0.9,
        max_average_latency_ms=1000.0,
    )
    assert "quality pass rate" in failures[0]
    assert "average latency" in failures[1]


def test_release_gate_skips_quality_threshold_when_no_quality_results_exist():
    failures = release_gate_failures(
        risk_score=100.0,
        quality=QualitySummary(),
        min_quality_pass_rate=0.9,
        max_average_latency_ms=1000.0,
    )
    assert failures == []
