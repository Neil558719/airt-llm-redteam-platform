"""Offline historical report trend aggregation."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _snapshot(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    summary = payload.get("summary", {}) or {}
    quality = payload.get("quality", {}) or {}
    return {
        "label": path.parent.name,
        "source": str(path),
        "run_mode": (payload.get("metadata", {}) or {}).get("run_mode"),
        "run_id": (payload.get("metadata", {}) or {}).get("run_id"),
        "risk_score": _number(summary.get("risk_score")),
        "quality_pass_rate": _number(quality.get("pass_rate")),
        "average_latency_ms": _number(quality.get("average_latency_ms")) or _number(summary.get("average_latency_ms")),
        "latency_p95_ms": _number(quality.get("latency_p95_ms")),
        "total": summary.get("total", quality.get("total")),
        "failed": summary.get("success", quality.get("failed")),
    }


def collect_trend(report_dir: str | Path) -> dict[str, Any]:
    root = Path(report_dir)
    candidates = []
    latest = root / "report.json"
    if latest.exists():
        candidates.append(latest)
    archive = root / "archive"
    if archive.exists():
        candidates.extend(sorted(archive.glob("*/report.json"), key=lambda item: item.stat().st_mtime))
    rows = [item for item in (_snapshot(path) for path in candidates) if item is not None]
    return {"mode": root.name, "reports": rows, "count": len(rows)}


def write_trend(report_dir: str | Path, out: str | Path | None = None) -> Path:
    data = collect_trend(report_dir)
    destination = Path(out) if out is not None else Path(report_dir)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "trend.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(row.get(key) if row.get(key) is not None else '-'))}</td>" for key in ("label", "run_id", "risk_score", "quality_pass_rate", "average_latency_ms", "latency_p95_ms")) + "</tr>"
        for row in data["reports"]
    )
    page = "<!doctype html><meta charset='utf-8'><title>测试趋势</title><h1>测试趋势</h1>" + f"<p>模式：{html.escape(data['mode'])}；历史报告：{data['count']} 次</p><table border='1'><tr><th>批次</th><th>运行 ID</th><th>安全分</th><th>质量通过率</th><th>平均延迟(ms)</th><th>P95 延迟(ms)</th></tr>{rows}</table>"
    (destination / "trend.html").write_text(page, encoding="utf-8")
    return destination / "trend.html"
