import json
from pathlib import Path
from airt.report.unified import write_unified_report


def test_unified_report_accepts_v1_records(tmp_path):
    source = tmp_path / "results.jsonl"
    source.write_text(json.dumps({"schema_version":"evaluation-result-v1","runner":"pytest","target":"unified_dify_chatflow","case_id":"q1","category":"quality","status":"passed","latency_ms":12}) + "\n", encoding="utf-8")
    json_path, html_path = write_unified_report([source], tmp_path / "report")
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["total"] == 1
    assert html_path.exists()


def test_unified_report_creates_immutable_archive(tmp_path):
    source = tmp_path / "results.jsonl"
    source.write_text(
        '{"schema_version":"evaluation-result-v1","runner":"airt","target":"chatflow","case_id":"s1","category":"security","status":"passed"}\n',
        encoding="utf-8",
    )
    out = tmp_path / "reports" / "assess"
    write_unified_report([source], out)
    archives = list((out / "archive").iterdir())
    assert len(archives) == 1
    assert (archives[0] / "report.json").exists()
    assert (archives[0] / "report.html").exists()
    assert (archives[0] / "results.jsonl").read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
