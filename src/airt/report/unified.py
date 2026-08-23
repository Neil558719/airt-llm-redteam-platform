"""Small cross-runner report aggregator for evaluation-result-v1 JSONL."""
from __future__ import annotations
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import re
import shutil
import tempfile
from airt.models import CaseResult
from airt.metrics import summarize
from airt.quality_bridge import QualitySummary
from airt.report.html import render_html
from airt.report.json_report import write_json
from airt.unified_results import from_airt


def load_records(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path_value in paths:
        path = Path(path_value)
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if payload.get("schema_version") == "evaluation-result-v1":
                records.append(payload)
            else:
                records.append(from_airt(CaseResult.model_validate(payload)))
    return records


def write_unified_report(paths: Iterable[str | Path], out: str | Path) -> tuple[Path, Path]:
    destination = Path(out)
    destination.mkdir(parents=True, exist_ok=True)
    source_paths = [Path(path) for path in paths]
    records = load_records(source_paths)
    report = {
        "schema_version": "evaluation-result-v1",
        "total": len(records),
        "passed": sum(item.get("status") == "passed" for item in records),
        "failed": sum(item.get("status") == "failed" for item in records),
        "errors": sum(item.get("status") == "error" for item in records),
        "records": records,
    }
    json_path = destination / "report.json"
    html_path = destination / "report.html"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = "".join(
        f"<tr><td>{html.escape(str(item.get('runner')))}</td><td>{html.escape(str(item.get('target')))}</td><td>{html.escape(str(item.get('case_id')))}</td><td>{html.escape(str(item.get('category')))}</td><td>{html.escape(str(item.get('status')))}</td><td>{html.escape(str(item.get('latency_ms')))}</td></tr>"
        for item in records
    )
    html_path.write_text(
        "<!doctype html><meta charset='utf-8'><title>Unified evaluation report</title>"
        f"<h1>Unified evaluation report</h1><p>Total: {report['total']} | Passed: {report['passed']} | Failed: {report['failed']} | Errors: {report['errors']}</p>"
        "<table border='1' cellspacing='0' cellpadding='6'><tr><th>Runner</th><th>Target</th><th>Case</th><th>Category</th><th>Status</th><th>Latency ms</th></tr>"
        f"{rows}</table>", encoding="utf-8"
    )

    archive_root = destination / "archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive = archive_root / stamp
    suffix = 1
    while archive.exists():
        archive = archive_root / f"{stamp}-{suffix:02d}"
        suffix += 1
    archive.mkdir()
    (archive / "report.json").write_bytes(json_path.read_bytes())
    (archive / "report.html").write_bytes(html_path.read_bytes())
    merged = "".join(path.read_text(encoding="utf-8") for path in source_paths)
    (archive / "results.jsonl").write_text(merged, encoding="utf-8")
    return json_path, html_path



def _load_case_results(path: str | Path) -> list[CaseResult]:
    source = Path(path)
    results: list[CaseResult] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            results.append(CaseResult.model_validate_json(line))
    return results


def _body_from_html(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"<body>(.*)</body>", text, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else text


def write_assess_report(
    security_results_path: str | Path,
    quality_results_path: str | Path,
    out: str | Path,
) -> tuple[Path, Path]:
    """Write a rich combined security + quality report with immutable history."""

    security_results = _load_case_results(security_results_path)
    quality_results = _load_case_results(quality_results_path)
    destination = Path(out)
    destination.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temporary:
        temp_dir = Path(temporary)
        security_html = temp_dir / "security.html"
        quality_html = temp_dir / "quality.html"
        security_json = temp_dir / "security.json"
        quality_json = temp_dir / "quality.json"
        security_summary = summarize(security_results)
        quality_summary = summarize(quality_results)
        security_metadata = next((item.run_metadata for item in security_results if item.run_metadata), None)
        quality_metadata = next((item.run_metadata for item in quality_results if item.run_metadata), None)
        quality_metrics = QualitySummary.from_dicts([item.quality for item in quality_results if item.quality is not None])
        render_html(security_summary, security_results, security_html, metadata=security_metadata)
        render_html(quality_summary, quality_results, quality_html, metadata=quality_metadata, quality=quality_metrics if quality_metrics.total else None)
        # Generate the detailed machine-readable sections using the same serializer as normal reports.
        write_json(security_summary, security_results, security_json, metadata=security_metadata)
        write_json(quality_summary, quality_results, quality_json, metadata=quality_metadata, quality=quality_metrics if quality_metrics.total else None)
        security_payload = json.loads(security_json.read_text(encoding="utf-8"))
        quality_payload = json.loads(quality_json.read_text(encoding="utf-8"))

        html_text = security_html.read_text(encoding="utf-8")
        head = html_text.split("<body>", 1)[0]
        combined_html = (
            head
            + "<body><main><h1>AI 红队 Chatflow 综合评测报告</h1>"
            + "<p class='lede'>本报告包含安全评测与质量评测两部分；每部分保留完整的测试请求、模型回复、工具观测、判定结论和评分依据。</p>"
            + "<section><h2>一、安全评测</h2>" + _body_from_html(security_html) + "</section>"
            + "<section><h2>二、质量评测</h2>" + _body_from_html(quality_html) + "</section>"
            + "</main></body></html>"
        )
        json_report = {
            "report_type": "chatflow-assess",
            "security": security_payload,
            "quality": quality_payload,
        }
        json_path = destination / "report.json"
        html_path = destination / "report.html"
        json_path.write_text(json.dumps(json_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        html_path.write_text(combined_html, encoding="utf-8")

    archive_root = destination / "archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive = archive_root / stamp
    suffix = 1
    while archive.exists():
        archive = archive_root / f"{stamp}-{suffix:02d}"
        suffix += 1
    archive.mkdir()
    shutil.copy2(json_path, archive / "report.json")
    shutil.copy2(html_path, archive / "report.html")
    merged = Path(security_results_path).read_text(encoding="utf-8") + Path(quality_results_path).read_text(encoding="utf-8")
    (archive / "results.jsonl").write_text(merged, encoding="utf-8")
    return json_path, html_path
