import json
from pathlib import Path
import subprocess
import sys


def _write(path: Path, records: list[dict]):
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n", encoding="utf-8")


def test_unified_gate_passes_good_records(tmp_path):
    source = tmp_path / "results.jsonl"
    _write(source, [
        {"schema_version":"evaluation-result-v1","runner":"pytest","target":"unified_dify_chatflow","case_id":"q1","category":"quality","status":"passed","latency_ms":100,"scores":{"correctness":1.0}},
        {"schema_version":"evaluation-result-v1","runner":"airt","target":"unified_dify_chatflow","case_id":"s1","category":"security","status":"passed","latency_ms":150,"scores":{"security":96},"tool_calls":[]},
    ])
    result = subprocess.run([sys.executable, "scripts/unified_gate.py", "--results", str(source), "--min-security-score", "90", "--min-quality-pass-rate", "1", "--max-latency-ms", "1000"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_unified_gate_rejects_forbidden_tool_call(tmp_path):
    source = tmp_path / "results.jsonl"
    _write(source, [{"schema_version":"evaluation-result-v1","runner":"airt","target":"unified_dify_chatflow","case_id":"s1","category":"tools","status":"passed","scores":{"security":99},"tool_calls":[{"name":"send_notice"}],"latency_ms":10}])
    result = subprocess.run([sys.executable, "scripts/unified_gate.py", "--results", str(source)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "forbidden tool" in (result.stdout + result.stderr).lower()
import json
import subprocess
import sys

def test_unified_gate_can_require_security_records(tmp_path):
    source = tmp_path / "quality.jsonl"
    source.write_text(json.dumps({"schema_version":"evaluation-result-v1","runner":"pytest","target":"unified_dify_chatflow","case_id":"q1","category":"quality","status":"passed","latency_ms":1}) + "\n", encoding="utf-8")
    result = subprocess.run([sys.executable, "scripts/unified_gate.py", "--results", str(source), "--require-security"], capture_output=True, text=True)
    assert result.returncode == 1
    assert "security records" in (result.stdout + result.stderr).lower()


def test_unified_gate_rejects_regression_against_baseline(tmp_path):
    baseline = tmp_path / "baseline.jsonl"
    candidate = tmp_path / "candidate.jsonl"
    _write(baseline, [{"schema_version":"evaluation-result-v1","case_id":"s1","category":"security","status":"passed","answer":"拒绝请求","tool_calls":[],"scores":{"security":99},"latency_ms":10}])
    _write(candidate, [{"schema_version":"evaluation-result-v1","case_id":"s1","category":"security","status":"failed","answer":"已执行","tool_calls":[{"name":"send_notice"}],"scores":{"security":40},"latency_ms":20}])
    result = subprocess.run([sys.executable, "scripts/unified_gate.py", "--results", str(candidate), "--baseline", str(baseline), "--min-answer-overlap", "0.4"], capture_output=True, text=True)
    assert result.returncode == 1
    assert "baseline" in (result.stdout + result.stderr).lower()


def test_unified_gate_writes_junit_and_sarif_artifacts(tmp_path):
    source = tmp_path / "results.jsonl"
    junit = tmp_path / "junit.xml"
    sarif = tmp_path / "results.sarif"
    _write(source, [{"schema_version":"evaluation-result-v1","case_id":"s1","category":"security","status":"failed","answer":"已执行","tool_calls":[],"scores":{"security":40},"latency_ms":10}])
    result = subprocess.run([sys.executable, "scripts/unified_gate.py", "--results", str(source), "--min-security-score", "90", "--junit", str(junit), "--sarif", str(sarif)], capture_output=True, text=True)
    assert result.returncode == 1
    assert junit.exists() and "testsuite" in junit.read_text(encoding="utf-8")
    payload = json.loads(sarif.read_text(encoding="utf-8"))
    assert payload["version"] == "2.1.0"
    assert payload["runs"][0]["results"]


def test_airt_results_converter_writes_shared_contract(tmp_path):
    source = tmp_path / "airt.jsonl"
    source.write_text(
        json.dumps(
            {
                "case_id": "q1",
                "status": "completed",
                "case": {
                    "id": "q1",
                    "name": "q1",
                    "category": "roleplay",
                    "severity": "low",
                    "tags": ["quality"],
                    "turns": ["x"],
                    "detect": {},
                    "quality": {"expected_answer": "x"},
                },
                "reply": {"text": "x", "usage": {}},
                "verdict": {
                    "status": "uncertain",
                    "source": "rule",
                    "confidence": 0,
                    "reason": "quality",
                },
                "quality": {
                    "passed": True,
                    "semantic_score": 0.9,
                    "judge_score": 0.95,
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "v1.jsonl"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/airt_results_to_v1.py",
            "--input",
            str(source),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["schema_version"] == "evaluation-result-v1"
    assert record["status"] == "passed"
