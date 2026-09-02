"""Offline baseline snapshots and regression comparisons."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import tempfile
from typing import Any

from airt.models import CaseResult
from airt.unified_results import from_airt


@dataclass(frozen=True)
class Comparison:
    baseline: Path
    candidate: Path
    rows: list[dict[str, Any]]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return not self.failures


def _load(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if item.get("schema_version") != "evaluation-result-v1":
                item = from_airt(CaseResult.model_validate(item))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid results JSONL at {path}:{line_number}") from error
        records[str(item["case_id"])] = item
    return records


def save_baseline(source: Path, destination: Path) -> Path:
    """Copy a results JSONL file and create a small auditable sidecar."""

    if not source.is_file():
        raise ValueError(f"results file does not exist: {source}")
    records = _load(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    metadata = {
        "source": str(source),
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(records),
        "schema": "evaluation-result-v1 or Airt CaseResult JSONL",
    }
    destination.with_suffix(".json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return destination


def discover_assess_run(runs_root: Path = Path("runs")) -> Path:
    """Find the newest complete Chatflow assess run without inspecting report files."""

    candidates = []
    default = runs_root / "chatflow-assess"
    if (default / "security" / "results.jsonl").is_file() and (default / "quality" / "results.jsonl").is_file():
        candidates.append(default)
    for path in runs_root.glob("chatflow-assess-*"):
        if (path / "security" / "results.jsonl").is_file() and (path / "quality" / "results.jsonl").is_file():
            candidates.append(path)
    if not candidates:
        raise ValueError(f"没有找到完整的 assess 结果目录：{runs_root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _merge_assess(run_dir: Path, destination: Path) -> Path:
    security = run_dir / "security" / "results.jsonl"
    quality = run_dir / "quality" / "results.jsonl"
    if not security.is_file() or not quality.is_file():
        raise ValueError(f"assess 目录必须同时包含 security/results.jsonl 和 quality/results.jsonl：{run_dir}")
    destination.write_bytes(security.read_bytes() + quality.read_bytes())
    return destination


def compare_assess(
    baseline: Path,
    run_dir: Path,
    *,
    min_answer_overlap: float = 0.4,
    max_latency_increase: float | None = None,
) -> Comparison:
    """Compare a baseline with an assess directory containing security and quality results."""

    if not run_dir.is_dir():
        raise ValueError(f"assess 结果目录不存在：{run_dir}")
    with tempfile.TemporaryDirectory(prefix="airt-assess-") as temporary:
        merged = _merge_assess(run_dir, Path(temporary) / "results.jsonl")
        comparison = compare_results(
            baseline,
            merged,
            min_answer_overlap=min_answer_overlap,
            max_latency_increase=max_latency_increase,
        )
    return Comparison(run_dir, run_dir, comparison.rows, comparison.failures)


def _tokens(text: str) -> set[str]:
    normalized = text.casefold().strip()
    chunks = set(re.findall(r"[a-z0-9_]+", normalized))
    cjk = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    chunks.update(cjk[i : i + 2] for i in range(max(0, len(cjk) - 1)))
    return chunks


def _overlap(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 1.0 if left.strip() == right.strip() else 0.0
    return len(a & b) / max(1, min(len(a), len(b)))


def _tool_names(item: dict[str, Any]) -> set[str]:
    return {str(call.get("name", "")) for call in item.get("tool_calls", []) or []}


def compare_results(
    baseline: Path,
    candidate: Path,
    *,
    min_answer_overlap: float = 0.4,
    max_latency_increase: float | None = None,
) -> Comparison:
    """Compare two local result files by case ID."""

    left_records, right_records = _load(baseline), _load(candidate)
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for case_id in sorted(set(left_records) | set(right_records)):
        left, right = left_records.get(case_id), right_records.get(case_id)
        if left is None or right is None:
            failures.append(f"用例缺失：{case_id}")
            continue
        answer_overlap = _overlap(str(left.get("answer", "")), str(right.get("answer", "")))
        left_tools, right_tools = _tool_names(left), _tool_names(right)
        left_latency, right_latency = left.get("latency_ms"), right.get("latency_ms")
        latency_delta = None
        latency_ratio = None
        if left_latency is not None and right_latency is not None:
            latency_delta = float(right_latency) - float(left_latency)
            latency_ratio = latency_delta / float(left_latency) if float(left_latency) else None
        row = {
            "case_id": case_id,
            "category": right.get("category", left.get("category")),
            "answer_overlap": round(answer_overlap, 6),
            "baseline_status": left.get("status"),
            "candidate_status": right.get("status"),
            "status_same": left.get("status") == right.get("status"),
            "tools_same": left_tools == right_tools,
            "baseline_tools": sorted(left_tools),
            "candidate_tools": sorted(right_tools),
            "baseline_latency_ms": left_latency,
            "candidate_latency_ms": right_latency,
            "latency_delta_ms": round(latency_delta, 6) if latency_delta is not None else None,
            "latency_increase_ratio": round(latency_ratio, 6) if latency_ratio is not None else None,
        }
        rows.append(row)
        if answer_overlap < min_answer_overlap:
            failures.append(f"回答相似度不足：{case_id}（{answer_overlap:.3f} < {min_answer_overlap:.3f}）")
        if not row["status_same"]:
            failures.append(f"状态变化：{case_id}（{left.get('status')} -> {right.get('status')}）")
        if not row["tools_same"]:
            failures.append(f"工具调用变化：{case_id}")
        if max_latency_increase is not None and latency_ratio is not None and latency_ratio > max_latency_increase:
            failures.append(f"延迟增幅超限：{case_id}（{latency_ratio:.1%} > {max_latency_increase:.1%}）")
    return Comparison(baseline, candidate, rows, failures)


def write_comparison(comparison: Comparison, out: Path) -> tuple[Path, Path]:
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "baseline": str(comparison.baseline),
        "candidate": str(comparison.candidate),
        "passed": comparison.passed,
        "total_cases": len(comparison.rows),
        "failures": comparison.failures,
        "rows": comparison.rows,
    }
    json_path = out / "comparison.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(row.get(key, '-')))}</td>" for key in ("case_id", "answer_overlap", "status_same", "tools_same", "latency_delta_ms")) + "</tr>"
        for row in comparison.rows
    )
    html_path = out / "comparison.html"
    html_path.write_text(
        "<!doctype html><meta charset='utf-8'><title>离线基线比较</title>"
        f"<h1>离线基线比较：{'通过' if comparison.passed else '失败'}</h1>"
        f"<p>用例数：{len(comparison.rows)}；差异数：{len(comparison.failures)}</p>"
        "<table border='1'><tr><th>用例</th><th>回答相似度</th><th>状态一致</th><th>工具一致</th><th>延迟变化(ms)</th></tr>"
        f"{rows}</table><pre>{html.escape(chr(10).join(comparison.failures))}</pre>",
        encoding="utf-8",
    )
    return json_path, html_path
