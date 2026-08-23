"""Compare baseline and candidate evaluation-result-v1 JSONL runs."""
from __future__ import annotations
import argparse
import html
import json
import re
import yaml
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from airt.models import CaseResult
from airt.unified_results import from_airt


def load(path: str) -> dict[str, dict]:
    records = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            if item.get("schema_version") != "evaluation-result-v1" and "status" in item and "case_id" in item:
                item = from_airt(CaseResult.model_validate(item))
            records[str(item["case_id"])] = item
    return records


def tokens(text: str) -> set[str]:
    normalized = text.casefold().strip()
    chunks = set(re.findall(r"[a-z0-9_]+", normalized))
    cjk = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    chunks.update(cjk[i:i+2] for i in range(max(0, len(cjk) - 1)))
    return chunks


def overlap(left: str, right: str) -> float:
    a, b = tokens(left), tokens(right)
    if not a or not b:
        return 1.0 if left.strip() == right.strip() else 0.0
    return len(a & b) / max(1, min(len(a), len(b)))

def tool_names(item: dict) -> set[str]:
    return {str(call.get("name", "")) for call in item.get("tool_calls", []) or []}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--min-answer-overlap", type=float, default=0.4)
    parser.add_argument("--cases", default=None, help="Optional shared YAML for expected-answer-aware comparison.")
    args = parser.parse_args()
    baseline, candidate = load(args.baseline), load(args.candidate)
    expected = {}
    if args.cases:
        for item in yaml.safe_load(Path(args.cases).read_text(encoding="utf-8")) or []:
            expected[str(item.get("case_id"))] = str(item.get("expected_answer", ""))
    ids = sorted(set(baseline) | set(candidate))
    rows, failures = [], []
    for case_id in ids:
        left, right = baseline.get(case_id), candidate.get(case_id)
        if left is None or right is None:
            failures.append(f"missing case: {case_id}")
            continue
        answer_overlap = overlap(str(left.get("answer", "")), str(right.get("answer", "")))
        if expected.get(case_id):
            answer_overlap = min(overlap(expected[case_id], str(left.get("answer", ""))), overlap(expected[case_id], str(right.get("answer", ""))))
        left_tools, right_tools = tool_names(left), tool_names(right)
        status_same = left.get("status") == right.get("status")
        tools_same = left_tools == right_tools
        row = {"case_id": case_id, "category": right.get("category", left.get("category")), "answer_overlap": round(answer_overlap, 6), "status_same": status_same, "tools_same": tools_same, "baseline_tools": sorted(left_tools), "candidate_tools": sorted(right_tools), "baseline_latency_ms": left.get("latency_ms"), "candidate_latency_ms": right.get("latency_ms")}
        rows.append(row)
        if answer_overlap < args.min_answer_overlap:
            failures.append(f"answer overlap below threshold: {case_id} ({answer_overlap:.3f})")
        if not status_same:
            failures.append(f"status mismatch: {case_id}")
        if not tools_same:
            failures.append(f"tool mismatch: {case_id}")
    summary = {"baseline": args.baseline, "candidate": args.candidate, "total_cases": len(rows), "passed_cases": len(rows) - len(failures), "failures": failures, "rows": rows}
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / "comparison.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    html_rows = "".join(f"<tr><td>{html.escape(row['case_id'])}</td><td>{row['answer_overlap']:.3f}</td><td>{row['status_same']}</td><td>{row['tools_same']}</td></tr>" for row in rows)
    (out / "comparison.html").write_text("<!doctype html><meta charset='utf-8'><title>Target equivalence</title>" + f"<h1>Target equivalence</h1><p>Cases: {len(rows)}; failures: {len(failures)}</p><table border='1'><tr><th>Case</th><th>Answer overlap</th><th>Status same</th><th>Tools same</th></tr>{html_rows}</table><pre>{html.escape(chr(10).join(failures))}</pre>", encoding="utf-8")
    if failures:
        print("TARGET EQUIVALENCE: FAIL")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(f"TARGET EQUIVALENCE: PASS ({len(rows)} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())




