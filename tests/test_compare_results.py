import json
import subprocess
import sys
from pathlib import Path


def write(path: Path, rows: list[dict]):
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_compare_results_passes_equivalent_records(tmp_path):
    left = tmp_path / "left.jsonl"
    right = tmp_path / "right.jsonl"
    row = {"schema_version":"evaluation-result-v1","runner":"airt","target":"old","case_id":"q1","category":"quality","status":"passed","answer":"退货期限是 7 天","tool_calls":[],"latency_ms":100}
    write(left, [row])
    write(right, [{**row, "target":"unified", "answer":"普通商品退货期限为 7 天", "latency_ms":120}])
    result = subprocess.run([sys.executable, "scripts/compare_results.py", "--baseline", str(left), "--candidate", str(right), "--out", str(tmp_path / "out"), "--min-answer-overlap", "0.4"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "out" / "comparison.json").exists()


def test_compare_results_rejects_tool_mismatch(tmp_path):
    left = tmp_path / "left.jsonl"
    right = tmp_path / "right.jsonl"
    base = {"schema_version":"evaluation-result-v1","runner":"airt","target":"old","case_id":"t1","category":"tools","status":"passed","answer":"ok","tool_calls":[{"name":"query_order"}],"latency_ms":10}
    write(left, [base])
    write(right, [{**base, "target":"unified", "tool_calls":[]}])
    result = subprocess.run([sys.executable, "scripts/compare_results.py", "--baseline", str(left), "--candidate", str(right), "--out", str(tmp_path / "out")], capture_output=True, text=True)
    assert result.returncode == 1
    assert "tool" in (result.stdout + result.stderr).lower()
import json, subprocess, sys
from pathlib import Path

def test_compare_results_can_use_shared_expected_answers(tmp_path):
    left=tmp_path/'l.jsonl'; right=tmp_path/'r.jsonl'; cases=tmp_path/'cases.yaml'
    row={"schema_version":"evaluation-result-v1","runner":"airt","target":"a","case_id":"q1","category":"quality","status":"passed","answer":"普通商品 7 天内可退货","tool_calls":[],"latency_ms":1}
    left.write_text(json.dumps(row,ensure_ascii=False)+'\n',encoding='utf8'); right.write_text(json.dumps({**row,"target":"b","answer":"退货期限为 7 天"},ensure_ascii=False)+'\n',encoding='utf8'); cases.write_text('- case_id: q1\n  category: quality\n  question: x\n  expected_answer: "退货期限 7 天"\n',encoding='utf8')
    result=subprocess.run([sys.executable,'scripts/compare_results.py','--baseline',str(left),'--candidate',str(right),'--cases',str(cases),'--out',str(tmp_path/'o'),'--min-answer-overlap','0.1'],capture_output=True,text=True)
    assert result.returncode==0, result.stdout+result.stderr
