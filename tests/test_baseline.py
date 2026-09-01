from __future__ import annotations

import json

from airt.baseline import compare_assess, compare_results, discover_assess_run, save_baseline


def _write(path, rows):
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _row(**overrides):
    row = {
        "schema_version": "evaluation-result-v1",
        "runner": "airt",
        "target": "chatflow",
        "case_id": "q1",
        "category": "quality",
        "status": "passed",
        "answer": "普通商品 14 天内可退货",
        "tool_calls": [],
        "latency_ms": 100,
    }
    row.update(overrides)
    return row


def test_save_baseline_copies_results_and_adds_metadata(tmp_path):
    source = tmp_path / "results.jsonl"
    destination = tmp_path / "baselines" / "quality.jsonl"
    _write(source, [_row()])

    saved = save_baseline(source, destination)

    assert saved == destination
    lines = destination.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["case_id"] == "q1"
    assert destination.with_suffix(".json").exists()


def test_compare_results_accepts_equivalent_candidate(tmp_path):
    baseline = tmp_path / "baseline.jsonl"
    candidate = tmp_path / "candidate.jsonl"
    _write(baseline, [_row()])
    _write(candidate, [_row(answer="标准商品可在签收后 14 天内退货", latency_ms=120)])

    comparison = compare_results(baseline, candidate, min_answer_overlap=0.4, max_latency_increase=1.0)

    assert comparison.passed is True
    assert comparison.failures == []
    assert comparison.rows[0]["latency_delta_ms"] == 20


def test_compare_results_rejects_status_and_tool_regression(tmp_path):
    baseline = tmp_path / "baseline.jsonl"
    candidate = tmp_path / "candidate.jsonl"
    _write(baseline, [_row(category="tools", tool_calls=[{"name": "query_order"}])])
    _write(candidate, [_row(category="tools", status="failed", tool_calls=[{"name": "send_notice"}])])

    comparison = compare_results(baseline, candidate)

    assert comparison.passed is False
    assert any("状态变化" in failure for failure in comparison.failures)
    assert any("工具调用变化" in failure for failure in comparison.failures)


def test_discover_assess_run_prefers_default_complete_run(tmp_path):
    default = tmp_path / "chatflow-assess"
    (default / "security").mkdir(parents=True)
    (default / "quality").mkdir()
    (default / "security" / "results.jsonl").write_text("{}\n", encoding="utf-8")
    (default / "quality" / "results.jsonl").write_text("{}\n", encoding="utf-8")

    found = discover_assess_run(tmp_path)

    assert found == default


def test_compare_assess_merges_security_and_quality_automatically(tmp_path):
    run = tmp_path / "chatflow-assess"
    (run / "security").mkdir(parents=True)
    (run / "quality").mkdir()
    _write(run / "security" / "results.jsonl", [_row(case_id="s1", category="security")])
    _write(run / "quality" / "results.jsonl", [_row(case_id="q1", category="quality")])
    baseline = tmp_path / "baseline.jsonl"
    _write(baseline, [_row(case_id="s1", category="security"), _row(case_id="q1", category="quality")])

    comparison = compare_assess(baseline, run)

    assert comparison.passed is True
    assert {row["case_id"] for row in comparison.rows} == {"s1", "q1"}
