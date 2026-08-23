from pathlib import Path

from airt.report.dashboard import write_dashboard
from airt.report.trends import collect_trend, write_trend


def test_trend_reads_latest_and_archives(tmp_path):
    mode = tmp_path / "quality"
    (mode / "archive" / "a").mkdir(parents=True)
    report = '{"metadata":{"run_id":"r1"},"quality":{"pass_rate":0.8,"average_latency_ms":100}}'
    (mode / "report.json").write_text(report, encoding="utf-8")
    (mode / "archive" / "a" / "report.json").write_text(report, encoding="utf-8")
    data = collect_trend(mode)
    assert data["count"] == 2
    assert data["reports"][0]["quality_pass_rate"] == 0.8


def test_write_trend_and_dashboard_escape_and_create(tmp_path):
    mode = tmp_path / "quality"
    mode.mkdir()
    (mode / "report.json").write_text('{"metadata":{},"quality":{}}', encoding="utf-8")
    trend_path = write_trend(mode)
    dashboard_path = write_dashboard(tmp_path)
    assert trend_path.exists()
    assert dashboard_path.exists()
    assert "quality" in dashboard_path.read_text(encoding="utf-8")

