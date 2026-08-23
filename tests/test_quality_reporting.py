from __future__ import annotations

import json

from airt.evaluation_bridge import EvaluationContext
from airt.metrics import summarize
from airt.models import AttackCase, CaseResult, Verdict
from airt.quality_bridge import QualityEvaluator, QualitySummary
from airt.report.html import render_html
from airt.report.json_report import write_json


def _security_result() -> CaseResult:
    case = AttackCase(id="quality-case", name="质量用例", category="roleplay", severity="low", turns=["x"])
    return CaseResult(case_id=case.id, case=case, status="completed", verdict=Verdict(status="fail", source="rule", confidence=1.0, reason="safe"))


def test_quality_summary_aggregates_dimensions():
    evaluator = QualityEvaluator()
    items = [
        evaluator.evaluate(EvaluationContext(answer="已发货", sources=["已发货"]), expected_answer="已发货", max_hallucination_rate=0.0),
        evaluator.evaluate(EvaluationContext(answer="不知道"), expected_answer="已发货", max_hallucination_rate=0.0),
    ]
    summary = QualitySummary.from_results(items)
    assert summary.total == 2
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.as_dict()["pass_rate"] == 0.5


def test_json_and_html_reports_include_quality_section(tmp_path):
    security = _security_result()
    quality = QualitySummary.from_results([QualityEvaluator().evaluate(EvaluationContext(answer="已发货"), expected_answer="已发货")])
    json_path = tmp_path / "report.json"
    html_path = tmp_path / "report.html"
    write_json(summarize([security]), [security], json_path, quality=quality)
    render_html(summarize([security]), [security], html_path, quality=quality)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["quality"]["passed"] == 1
    html = html_path.read_text(encoding="utf-8")
    assert "质量评测" in html
    assert "语义匹配平均分" in html
