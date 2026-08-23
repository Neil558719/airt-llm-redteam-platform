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
