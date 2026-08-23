"""Static overview dashboard for local and CI artifacts."""
from __future__ import annotations

import html
import os
from pathlib import Path


def write_dashboard(reports_root: str | Path = "reports", out: str | Path | None = None) -> Path:
    root = Path(reports_root)
    destination = Path(out) if out is not None else root
    destination.mkdir(parents=True, exist_ok=True)
    rows = []
    for mode in ("assess", "security", "quality", "release"):
        directory = root / mode
        report = directory / "report.html"
        trend = directory / "trend.html"
        links = []
        report_link = os.path.relpath(report, destination) if report.exists() else None
        trend_link = os.path.relpath(trend, destination) if trend.exists() else None
        if report_link: links.append(f"<a href='{html.escape(report_link.replace(os.sep, '/'))}'>最新报告</a>")
        if trend_link: links.append(f"<a href='{html.escape(trend_link.replace(os.sep, '/'))}'>趋势</a>")
        rows.append(f"<tr><td>{mode}</td><td>{' | '.join(links) or '暂无报告'}</td></tr>")
    page = "<!doctype html><meta charset='utf-8'><title>Airt 测试总览</title><style>body{font-family:Arial,sans-serif;margin:2rem}table{border-collapse:collapse}td,th{padding:.6rem;border:1px solid #ccc}</style>" + "<h1>Airt LLM 应用测试总览</h1><p>静态离线 Dashboard，可直接作为 CI artifact 打开。</p><table><tr><th>测试模式</th><th>报告</th></tr>" + "".join(rows) + "</table>"
    path = destination / "dashboard.html"
    path.write_text(page, encoding="utf-8")
    return path


