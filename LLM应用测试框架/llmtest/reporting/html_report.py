"""HTML 质量报告生成器。

自包含单文件 HTML（内联 CSS + 内联 SVG，无 CDN、可离线打开）：
- hero 数字磁贴（通过率 / 准确率 / 幻觉率 / 平均延迟）
- 质量看板：3 张 SVG 条形图（幻觉率 · 响应延迟 · Judge 分）
- 用例明细（可展开失败信息 / 指标 / 幻觉逐条断言）
- 明暗模式（prefers-color-scheme + 手动切换）

配色遵循 dataviz 规范：单序列用 categorical blue / aqua，幻觉率按状态色分档并配标签。
"""

from __future__ import annotations

import glob
import html as html_mod
import json
import os
import shutil
import time
from typing import Callable, List, Optional, Tuple

from .. import __version__
from ..metrics.tracker import Summary, TestRecord
from ..utils import fmt_ms

# ---- 变量名常量（CSS 中定义）----
C_BLUE = "var(--series-1)"
C_AQUA = "var(--series-3)"
C_GOOD = "var(--status-good)"
C_WARN = "var(--status-warn)"
C_CRIT = "var(--status-crit)"

_OUTCOME_ICON = {
    "passed": "✓",
    "failed": "✕",
    "skipped": "–",
    "error": "!",
}
_OUTCOME_LABEL = {
    "passed": "通过",
    "failed": "失败",
    "skipped": "跳过",
    "error": "错误",
}


def _esc(value: object) -> str:
    return html_mod.escape(str(value))


# ----------------------------------------------------------------------
# 对外入口
# ----------------------------------------------------------------------

def write_report(
    summary: Summary,
    records: List[TestRecord],
    path: str,
    history: Optional[List[dict]] = None,
) -> str:
    """渲染并写出报告，返回报告路径。"""
    html = render_report(summary, records, history=history)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def write_report_with_history(
    summary: Summary,
    records: List[TestRecord],
    path: str,
    *,
    keep_history: bool = True,
) -> Tuple[str, Optional[str]]:
    """写最新报告 + 时间戳历史归档 + 更新历史索引。

    - path: 最新报告路径（固定，每次覆盖）
    - 归档: path 同名 + `_YYYYMMDD_HHMMSS.html`（保留每次历史）
    - 索引: 同目录 `index.html`，按时间倒序列出所有归档报告

    返回 (最新报告路径, 归档路径)。
    """
    reports_dir = os.path.dirname(os.path.abspath(path))
    history: List[dict] = []
    if keep_history:
        env_str = (
            f"被测: {summary.env.get('被测对象', '')} · "
            f"裁判: {summary.env.get('裁判', '')}"
        )
        history = _append_history(reports_dir, summary, env_str)
    latest = write_report(summary, records, path, history=history)
    archive: Optional[str] = None
    if keep_history:
        archive = _archive_report(latest)
        write_index(reports_dir, path)
    return latest, archive


def _archive_report(latest_path: str) -> str:
    """把最新报告复制一份时间戳归档，返回归档路径（同秒重跑自动加序号防覆盖）。"""
    base = latest_path[:-5] if latest_path.endswith(".html") else latest_path
    ts = time.strftime("%Y%m%d_%H%M%S")
    archive_path = f"{base}_{ts}.html"
    seq = 1
    while os.path.exists(archive_path):
        archive_path = f"{base}_{ts}_{seq}.html"
        seq += 1
    shutil.copyfile(latest_path, archive_path)
    return archive_path


# ----------------------------------------------------------------------
# 历史运行对比（reports/history.json）
# ----------------------------------------------------------------------

def _history_path(reports_dir: str) -> str:
    return os.path.join(reports_dir, "history.json")


def _load_history(reports_dir: str) -> List[dict]:
    try:
        with open(_history_path(reports_dir), encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _append_history(reports_dir: str, summary: Summary, env_str: str) -> List[dict]:
    """把本次运行摘要追加进 history.json，返回最新列表（含本次，最多 20 条）。"""
    history = _load_history(reports_dir)
    history.append(
        {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total": summary.total,
            "passed": summary.passed,
            "failed": summary.failed,
            "skipped": summary.skipped,
            "error": summary.error,
            "pass_rate": summary.pass_rate,
            "accuracy": summary.accuracy,
            "hallucination_rate": summary.hallucination_rate,
            "avg_app_latency_ms": summary.avg_app_latency_ms,
            "env": env_str,
        }
    )
    history = history[-20:]
    try:
        with open(_history_path(reports_dir), "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
    return history


def _render_history(history: List[dict]) -> str:
    """渲染"历史运行对比"小节（最新在上，向下越旧）。无历史时返回空。"""
    if not history:
        return ""
    rows = []
    for e in reversed(history):  # 最新（含本次）在最上
        pass_rate = f"{e['pass_rate']:.0%}" if e.get("pass_rate") is not None else "—"
        accuracy = f"{e['accuracy']:.0%}" if e.get("accuracy") is not None else "—"
        hallu = f"{e['hallucination_rate']:.0%}" if e.get("hallucination_rate") is not None else "—"
        latency = fmt_ms(e.get("avg_app_latency_ms"))
        stats = f"{e['passed']} ✓ / {e['total']}"
        rows.append(
            f"<tr>"
            f"<td class='t'>{_esc(e.get('ts', ''))}</td>"
            f"<td>{_esc(stats)}</td><td>{_esc(pass_rate)}</td>"
            f"<td>{_esc(accuracy)}</td><td>{_esc(hallu)}</td>"
            f"<td>{_esc(latency)}</td>"
            f"<td class='env'>{_esc(e.get('env', ''))}</td>"
            f"</tr>"
        )
    return f"""
<section class="history" aria-label="历史运行对比">
  <h2>历史运行对比</h2>
  <p class="chart-sub">最近 {len(history)} 次运行，最新在上、向下越旧；用于跨版本 / 跨模型回归对比。</p>
  <table class="history-table">
    <thead><tr>
      <th>时间</th><th>通过</th><th>通过率</th><th>准确率</th><th>幻觉率</th><th>平均延迟</th><th>被测 · 裁判</th>
    </tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</section>"""


def _parse_report_meta(report_path: str) -> dict:
    """从已生成的报告 HTML 里提取摘要与环境行，供历史索引展示。"""
    import re

    with open(report_path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(
        r"共 (\d+) 个用例 · 通过 (\d+) · 失败 (\d+) · 跳过 (\d+) · 错误 (\d+)",
        text,
    )
    e = re.search(r'<p class="meta env">(.*?)</p>', text)
    if m:
        total, passed, failed, skipped, error = (int(g) for g in m.groups())
    else:
        total = passed = failed = skipped = error = None
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "error": error,
        "env": e.group(1) if e else "",
    }


def write_index(reports_dir: str, latest_path: str) -> str:
    """在 reports 目录生成/更新 index.html，按时间倒序列出历史报告。"""
    index_path = os.path.join(reports_dir, "index.html")
    base = os.path.basename(latest_path)
    base_name = base[:-5] if base.endswith(".html") else base
    pattern = os.path.join(reports_dir, base_name + "_*.html")

    entries = []
    for p in glob.glob(pattern):
        mtime = os.path.getmtime(p)
        meta = _parse_report_meta(p)
        entries.append(
            {
                "path": p,
                "name": os.path.basename(p),
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)),
                **meta,
            }
        )
    entries.sort(key=lambda e: e["time"], reverse=True)

    rows = []
    for e in entries:
        if e["total"] is not None:
            stats = (
                f"<span class='ok'>✓ {e['passed']}</span>"
                f"<span class='bad'>✕ {e['failed']}</span>"
                f"<span class='skip'>– {e['skipped']}</span>"
                f"<span class='bad'>! {e['error']}</span>"
            )
        else:
            stats = "—"
        rows.append(
            f"<tr><td class='t'><a href='{_esc(e['name'])}'>{_esc(e['time'])}</a></td>"
            f"<td>{stats}</td><td class='env'>{e['env']}</td></tr>"
        )

    latest_link = _esc(os.path.basename(latest_path))
    html = _INDEX_TEMPLATE.format(
        title="llmtest 测试报告历史",
        latest_link=latest_link,
        rows="\n".join(rows) or "<tr><td colspan='3' class='env'>暂无历史报告</td></tr>",
    )
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)
    return index_path


_INDEX_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ color-scheme: light; --page:#f9f9f7; --surface:#ffffff; --ink:#0b0b0b; --ink2:#52514e; --line:#e1e0d9; --ok:#0ca30c; --bad:#d03b3b; --skip:#b37c00; }}
@media (prefers-color-scheme: dark) {{ :root:where(:not([data-theme="light"])) {{ color-scheme: dark; --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --line:#2c2c2a; --ok:#0ca30c; --bad:#e66767; --skip:#fab219; }} }}
:root[data-theme="dark"] {{ color-scheme: dark; --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --line:#2c2c2a; --ok:#0ca30c; --bad:#e66767; --skip:#fab219; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--page); color:var(--ink); font-family: system-ui,-apple-system,"Segoe UI",sans-serif; }}
.page {{ max-width: 900px; margin:0 auto; padding: 32px 20px; }}
h1 {{ font-size: 20px; margin: 0 0 16px; }}
.latest {{ display:inline-block; margin: 0 0 18px; padding: 8px 16px; border-radius: 999px; background: var(--surface); border:1px solid var(--line); color: var(--ink); text-decoration:none; font-size: 13px; }}
.latest:hover {{ text-decoration: underline; }}
table {{ width:100%; border-collapse: collapse; background: var(--surface); border:1px solid var(--line); border-radius: 12px; overflow:hidden; }}
th, td {{ text-align:left; padding: 10px 14px; border-bottom: 1px solid var(--line); font-size: 13px; }}
th {{ color: var(--ink2); font-weight: 600; }}
tr:last-child td {{ border-bottom: 0; }}
td.t a {{ color: var(--ink); text-decoration:none; font-weight:600; }}
td.t a:hover {{ text-decoration: underline; }}
.ok {{ color: var(--ok); }} .bad {{ color: var(--bad); }} .skip {{ color: var(--skip); }}
.env {{ color: var(--ink2); font-size: 12px; }}
</style>
</head>
<body>
<div class="page">
<h1>{title}</h1>
<a class="latest" href="{latest_link}">打开最新报告</a>
<table>
<thead><tr><th>运行时间</th><th>结果（通过 / 失败 / 跳过 / 错误）</th><th>被测 · 裁判</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
</div>
</body>
</html>"""


def render_report(
    summary: Summary,
    records: List[TestRecord],
    history: Optional[List[dict]] = None,
) -> str:
    tiles = _render_tiles(summary)
    history_html = _render_history(history or [])
    charts = _render_charts(records)
    rows = "\n".join(_render_test_row(r) for r in records)
    empty_rows = (
        '<p class="empty">本次运行没有收集到任何测试用例。</p>' if not records else ""
    )

    summary_line = (
        f"共 {summary.total} 个用例 · 通过 {summary.passed} · 失败 {summary.failed} · "
        f"跳过 {summary.skipped} · 错误 {summary.error}"
    )
    env_line = " · ".join(f"{k}: {v}" for k, v in summary.env.items())

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LLM 应用测试报告</title>
<style>
{_CSS}
</style>
</head>
<body data-palette="#2a78d6,#eb6834,#1baf7a,#eda100,#e87ba4,#008300,#4a3aa7,#e34948">
<div class="page">
  <header class="topbar">
    <div>
      <h1>LLM 应用测试报告</h1>
      <p class="meta">{_esc(summary_line)} · 生成于 {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
      <p class="meta env">{_esc(env_line)}</p>
    </div>
    <button id="theme-toggle" type="button" title="切换明暗模式">🌓 明暗</button>
  </header>

  <section class="tiles" aria-label="总体指标">
    {tiles}
  </section>

  {history_html}

  <section class="dashboard" aria-label="质量看板">
    {charts}
  </section>

  <section class="tests" aria-label="用例明细">
    <h2>用例明细</h2>
    <div class="tlist">
      <div class="trow thead" role="row">
        <span class="c-name">用例</span>
        <span class="c-status">状态</span>
        <span class="c-dur">耗时(s)</span>
        <span class="c-lat">延迟(ms)</span>
        <span class="c-hallu">幻觉率</span>
        <span class="c-judge">Judge 分</span>
        <span class="c-assert">断言</span>
      </div>
      {rows or empty_rows}
    </div>
  </section>

  <footer class="foot">llmtest v{__version__} · 数据来自本次 pytest 会话</footer>
</div>
<script>{_JS}</script>
</body>
</html>"""


# ----------------------------------------------------------------------
# Hero 磁贴
# ----------------------------------------------------------------------

def _render_tiles(s: Summary) -> str:
    pass_rate = f"{s.pass_rate:.1%}" if s.pass_rate is not None else "—"
    accuracy = f"{s.accuracy:.1%}" if s.accuracy is not None else "—"
    hallu = f"{s.hallucination_rate:.1%}" if s.hallucination_rate is not None else "—"
    latency = fmt_ms(s.avg_app_latency_ms)

    tiles = [
        ("通过率", pass_rate, f"{s.passed}/{s.total} 通过"),
        ("准确率", accuracy, "LLM-as-Judge 平均"),
        ("幻觉率", hallu, "越低越好"),
        ("平均延迟", latency, "被测应用响应"),
    ]
    return "\n".join(
        f'<div class="tile"><span class="tile-label">{_esc(label)}</span>'
        f'<span class="tile-value">{_esc(value)}</span>'
        f'<span class="tile-sub">{_esc(sub)}</span></div>'
        for label, value, sub in tiles
    )


# ----------------------------------------------------------------------
# SVG 条形图
# ----------------------------------------------------------------------

def _hbar_svg(
    rows: List[Tuple[str, float, str, str]],
    *,
    scale_max: float,
    fmt: Callable[[float], str],
    width: int = 780,
    label_w: int = 250,
    right: int = 90,
    row_h: int = 30,
    bar_h: int = 14,
) -> str:
    """rows: (label, value, color, sub_label)。

    横向条形图：左侧标签 + 条形 + 值标签。单序列。
    """
    if not rows:
        return ""
    n = len(rows)
    height = 34 + n * row_h
    chart_l = label_w + 18
    chart_r = width - right
    chart_w = chart_r - chart_l
    parts = [
        f'<svg class="hbar" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="条形图" xmlns="http://www.w3.org/2000/svg">'
    ]
    # 基准线（退隐）
    parts.append(
        f'<line class="baseline" x1="{chart_l}" y1="{height - 14}" '
        f'x2="{chart_r}" y2="{height - 14}"/>'
    )
    for i, (label, value, color, _sub) in enumerate(rows):
        y = 26 + i * row_h
        frac = max(0.0, min(value / scale_max, 1.0))
        w = frac * chart_w
        top = y - bar_h // 2
        parts.append(
            f'<text class="bar-label" x="{chart_l - 10}" y="{y + 4}" text-anchor="end">'
            f'{_esc(_truncate(label))}</text>'
        )
        parts.append(
            f'<rect class="bar" x="{chart_l:.1f}" y="{top}" width="{max(w, 1.0):.1f}" '
            f'height="{bar_h}" rx="{min(bar_h / 2, 4)}" fill="{color}"/>'
        )
        parts.append(
            f'<text class="bar-value" x="{chart_l + w + 6:.1f}" y="{y + 4}">{_esc(fmt(value))}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _truncate(label: str, limit: int = 28) -> str:
    return label if len(label) <= limit else label[: limit - 1] + "…"


def _render_charts(records: List[TestRecord]) -> str:
    charts = []

    # 1) 幻觉率（状态色分档）
    hallu_rows: List[Tuple[str, float, str, str]] = []
    for r in records:
        rate = r.hallucination_rate
        if rate is None:
            continue
        if rate <= 0.4:
            color = C_GOOD
        elif rate <= 0.7:
            color = C_WARN
        else:
            color = C_CRIT
        hallu_rows.append((r.name, rate, color, "低 / 中 / 高 对应 ≤40% / ≤70% / >70%"))
    hallu = _hbar_svg(hallu_rows, scale_max=1.0, fmt=lambda v: f"{v:.0%}")
    if hallu:
        legend = (
            '<span class="legend"><span class="dot" style="background:var(--status-good)"></span>'
            '≤40% 低</span>'
            '<span class="legend"><span class="dot" style="background:var(--status-warn)"></span>'
            '40–70% 中</span>'
            '<span class="legend"><span class="dot" style="background:var(--status-crit)"></span>'
            '>70% 高</span>'
        )
    else:
        legend = ""
    charts.append(
        _chart_block(
            "幻觉率（按用例）", "响应中断言相对上下文的幻觉比例，越低越好",
            hallu or '<p class="empty">无幻觉检测数据（本次用例未调用幻觉检测）。</p>', legend,
        )
    )

    # 2) 响应延迟（sequential blue）
    lat_rows = [
        (r.name, r.avg_app_latency, C_BLUE, "ms")
        for r in records
        if r.avg_app_latency is not None
    ]
    lat_max = max((v for _, v, *_ in lat_rows), default=0.0)
    lat = _hbar_svg(
        lat_rows, scale_max=lat_max * 1.1 or 1.0, fmt=lambda v: f"{v:.0f} ms"
    )
    charts.append(
        _chart_block(
            "响应延迟（按用例）", "被测应用单次回答的响应耗时",
            lat or '<p class="empty">无延迟数据。</p>', "",
        )
    )

    # 3) Judge 分（aqua，归一化）
    judge_rows: List[Tuple[str, float, str, str]] = []
    for r in records:
        if r.avg_judge_normalized is None:
            continue
        raw = r.avg_judge_raw or 0.0
        judge_rows.append(
            (r.name, r.avg_judge_normalized, C_AQUA, f"{raw:.1f}")
        )
    judge = _hbar_svg(judge_rows, scale_max=1.0, fmt=lambda v: f"{v:.0%}")
    charts.append(
        _chart_block(
            "LLM-as-Judge 分数（按用例）", "归一化得分（得分/满分），聚合为准确率",
            judge or '<p class="empty">无 Judge 打分数据。</p>', "",
        )
    )

    return "\n".join(charts)


def _chart_block(title: str, subtitle: str, body: str, legend: str) -> str:
    return (
        f'<div class="chart"><div class="chart-head"><h3>{_esc(title)}</h3>'
        f'<p class="chart-sub">{_esc(subtitle)}</p></div>'
        f'<div class="chart-body">{body}</div>'
        f'<div class="legend-row">{legend}</div></div>'
    )


# ----------------------------------------------------------------------
# 用例明细
# ----------------------------------------------------------------------

def _render_test_row(r: TestRecord) -> str:
    status = _OUTCOME_LABEL.get(r.outcome, r.outcome)
    status_cls = r.outcome
    icon = _OUTCOME_ICON.get(r.outcome, "·")
    dur = f"{r.duration:.2f}"
    lat = fmt_ms(r.avg_app_latency)
    hallu = f"{r.hallucination_rate:.0%}" if r.hallucination_rate is not None else "—"
    judge = (
        f"{r.avg_judge_raw:.1f}/{r.judge_results[0].max_score:.0f}"
        if r.judge_results and r.avg_judge_raw is not None
        else "—"
    )
    assert_summary = f"{sum(1 for a in r.assertions if a.passed)}/{len(r.assertions)} 通过"
    if len(r.assertions) == 0:
        assert_summary = "无断言记录"

    detail = _render_detail(r)
    return f"""<details class="trow" open data-outcome="{r.outcome}">
  <summary class="trow-summary" role="row">
    <span class="c-name">{_esc(r.name)}</span>
    <span class="c-status"><span class="status status-{status_cls}">{icon} {_esc(status)}</span></span>
    <span class="c-dur">{_esc(dur)}</span>
    <span class="c-lat">{_esc(lat)}</span>
    <span class="c-hallu">{_esc(hallu)}</span>
    <span class="c-judge">{_esc(judge)}</span>
    <span class="c-assert">{_esc(assert_summary)}</span>
  </summary>
  <div class="detail">
    {detail}
  </div>
</details>"""


def _render_detail(r: TestRecord) -> str:
    blocks = []

    # 用例失败但并非断言未通过时，明确提示，避免"断言都过了却失败"的困惑
    not_assert_failure = bool(r.failure) and not r.failure.startswith("AssertionError")
    if r.outcome in ("failed", "error") and not_assert_failure:
        blocks.append(
            '<div class="d-block hint"><strong>提示：</strong>该用例失败来自'
            '<span class="hint-bad">异常/错误</span>（如 LLM 接口超时、网关 5xx、代码异常），'
            "而非断言不通过——下方「断言记录」只是执行到的那几条，不代表全部通过。</div>"
        )

    if r.failure:
        kind = "断言未通过" if not not_assert_failure else "异常 / 错误"
        blocks.append(
            '<div class="d-block"><h4>失败信息'
            f'<span class="fail-kind">{_esc(kind)}</span></h4>'
            f'<pre class="fail">{_esc(r.failure)}</pre>'
            + (f'<pre class="trace">{_esc(r.traceback)}</pre>' if r.traceback else "")
            + "</div>"
        )

    if r.assertions:
        rows = []
        for a in r.assertions:
            mark = "✓" if a.passed else "✕"
            cls = "a-pass" if a.passed else "a-fail"
            rows.append(
                f'<li class="{cls}"><span class="a-mark">{mark}</span>'
                f'<span class="a-name">{_esc(a.name)}</span>'
                f'<span class="a-score">{_esc(_score_str(a.score, a.threshold))}</span>'
                f'<pre class="a-msg">{_esc(a.message)}</pre></li>'
            )
        blocks.append(
            '<div class="d-block"><h4>断言记录</h4>'
            f'<ul class="a-list">{"".join(rows)}</ul></div>'
        )

    metrics = []
    for m in r.metrics:
        unit = f" {_esc(m.unit)}" if m.unit else ""
        metrics.append(
            f'<li><span class="m-name">{_esc(m.name)}</span>'
            f'<span class="m-value">{_esc(f"{m.value:.4f}")}{unit}</span></li>'
        )
    if r.app_latency_ms:
        metrics.append(
            f'<li><span class="m-name">app 延迟(ms)</span>'
            f'<span class="m-value">{_esc(", ".join(f"{x:.0f}" for x in r.app_latency_ms))}</span></li>'
        )
    if metrics:
        blocks.append(
            '<div class="d-block"><h4>指标</h4><ul class="m-list">'
            + "".join(metrics)
            + "</ul></div>"
        )

    for report in r.hallucination_reports:
        blocks.append(_render_hallucination(report))

    if not blocks:
        return '<div class="d-block muted">无更多细节。</div>'
    return "".join(blocks)


def _render_hallucination(report) -> str:
    if not report.claims:
        return ""
    rows = []
    for c in report.claims:
        cls = "claim-ok" if not c.is_hallucinated else "claim-bad"
        mark = "✓" if not c.is_hallucinated else "✕"
        rows.append(
            f'<li class="claim {cls}"><span class="a-mark">{mark}</span>'
            f'<span class="claim-verdict">{_esc(c.verdict)}</span>'
            f'<span class="claim-text">{_esc(c.claim)}</span>'
            f'<span class="claim-evidence">{_esc(c.evidence)}</span></li>'
        )
    return (
        '<div class="d-block"><h4>幻觉检测</h4>'
        f'<p class="hallu-rate">幻觉率 {report.hallucination_rate:.1%}'
        f' · 支持 {len(report.supported)} · 幻觉 {len(report.hallucinated)}'
        f' · 矛盾 {len(report.contradicted)}</p>'
        f'<ul class="claim-list">{"".join(rows)}</ul></div>'
    )


def _score_str(score, threshold) -> str:
    if score is None:
        return ""
    parts = [f"得分 {score:.3f}"]
    if threshold is not None:
        parts.append(f"阈值 {threshold:.3f}")
    return " · ".join(parts)


# ----------------------------------------------------------------------
# CSS 与 JS
# ----------------------------------------------------------------------

_CSS = """
:root {
  color-scheme: light;
  --page: #f9f9f7;
  --surface-1: #fcfcfb;
  --surface-2: #f3f2ee;
  --ink-1: #0b0b0b;
  --ink-2: #52514e;
  --ink-3: #898781;
  --grid: #e1e0d9;
  --line: #c3c2b7;
  --series-1: #2a78d6;
  --series-3: #1baf7a;
  --status-good: #0ca30c;
  --status-warn: #b37c00;
  --status-crit: #d03b3b;
  --good-bg: rgba(12,163,12,.12);
  --crit-bg: rgba(208,59,59,.12);
  --warn-bg: rgba(179,124,0,.14);
  --border: rgba(11,11,11,.10);
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --page: #0d0d0d;
    --surface-1: #1a1a19;
    --surface-2: #242422;
    --ink-1: #ffffff;
    --ink-2: #c3c2b7;
    --ink-3: #898781;
    --grid: #2c2c2a;
    --line: #383835;
    --series-1: #3987e5;
    --series-3: #199e70;
    --status-good: #0ca30c;
    --status-warn: #fab219;
    --status-crit: #e66767;
    --border: rgba(255,255,255,.10);
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d;
  --surface-1: #1a1a19;
  --surface-2: #242422;
  --ink-1: #ffffff;
  --ink-2: #c3c2b7;
  --ink-3: #898781;
  --grid: #2c2c2a;
  --line: #383835;
  --series-1: #3987e5;
  --series-3: #199e70;
  --status-good: #0ca30c;
  --status-warn: #fab219;
  --status-crit: #e66767;
  --border: rgba(255,255,255,.10);
}

* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--page);
  color: var(--ink-1);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  line-height: 1.5;
}
.page { max-width: 1080px; margin: 0 auto; padding: 28px 20px 48px; }

.topbar { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 24px; }
.topbar h1 { margin: 0 0 6px; font-size: 22px; letter-spacing: .3px; }
.meta { margin: 2px 0; color: var(--ink-2); font-size: 13px; }
#theme-toggle {
  flex: none; border: 1px solid var(--line); background: var(--surface-1);
  color: var(--ink-1); border-radius: 999px; padding: 6px 14px; cursor: pointer; font-size: 13px;
}

.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 28px; }
.tile {
  background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px;
  padding: 16px 18px;
}
.tile-label { display: block; color: var(--ink-2); font-size: 13px; }
.tile-value { display: block; font-size: 34px; font-weight: 600; margin: 4px 0 2px; letter-spacing: .2px; }
.tile-sub { display: block; color: var(--ink-3); font-size: 12px; }

.dashboard { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px; margin-bottom: 32px; }
.chart {
  background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px;
}
.chart-head h3 { margin: 0 0 2px; font-size: 18px; }
.chart-sub { margin: 0 0 10px; color: var(--ink-3); font-size: 13px; }
.hbar { width: 100%; height: auto; display: block; }
.hbar .bar-label { font-size: 15px; fill: var(--ink-2); }
.hbar .bar-value { font-size: 13px; fill: var(--ink-1); font-variant-numeric: tabular-nums; }
.hbar .baseline { stroke: var(--line); stroke-width: 1; }
.legend-row { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 8px; }
.legend { display: inline-flex; align-items: center; gap: 6px; color: var(--ink-2); font-size: 12px; }
.dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
.empty { color: var(--ink-3); font-size: 13px; padding: 8px 0; }

.history { margin-top: 28px; }
.history h2 { font-size: 18px; margin: 0 0 4px; }
.history-table { width:100%; border-collapse: collapse; background: var(--surface); border:1px solid var(--line); border-radius: 12px; overflow:hidden; }
.history-table th, .history-table td { text-align:left; padding: 8px 12px; border-bottom: 1px solid var(--line); font-size: 13px; }
.history-table th { background: var(--surface-2); font-weight: 600; }
.tests h2 { font-size: 17px; margin: 0 0 12px; }
.tlist { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; background: var(--surface-1); }
.trow { border-top: 1px solid var(--border); }
.trow:first-of-type { border-top: 0; }
.trow-summary {
  display: grid;
  grid-template-columns: minmax(220px, 3fr) 96px 72px 84px 72px 84px 1fr;
  gap: 10px; align-items: center; padding: 10px 16px; cursor: pointer; list-style: none;
}
.trow-summary::-webkit-details-marker { display: none; }
.trow-summary:hover { background: var(--surface-2); }
.thead {
  display: grid;
  grid-template-columns: minmax(220px, 3fr) 96px 72px 84px 72px 84px 1fr;
  gap: 10px; padding: 8px 16px; color: var(--ink-3); font-size: 12px; background: var(--surface-2);
}
.c-name { font-weight: 500; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.c-name, .c-dur, .c-lat, .c-hallu, .c-judge, .c-assert { font-variant-numeric: tabular-nums; }

.status { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; border-radius: 999px; padding: 2px 9px; }
.status-passed { background: var(--good-bg); color: var(--status-good); }
.status-failed { background: var(--crit-bg); color: var(--status-crit); }
.status-skipped { background: var(--warn-bg); color: var(--status-warn); }
.status-error { background: var(--warn-bg); color: var(--status-warn); }

.trow[open] .trow-summary { border-bottom: 1px solid var(--border); }
.detail { padding: 12px 16px 16px; }
.d-block { padding: 8px 0 12px; }
.d-block h4 { margin: 0 0 6px; font-size: 13px; color: var(--ink-2); }
.d-block.muted { color: var(--ink-3); font-size: 13px; }
.fail-kind { margin-left: 8px; font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 999px; background: var(--warn-bg); color: var(--status-warn); }
.hint { font-size: 12.5px; color: var(--ink-2); background: var(--warn-bg); border-radius: 8px; padding: 8px 12px; }
.hint-bad { color: var(--status-crit); font-weight: 600; }
pre { white-space: pre-wrap; word-break: break-word; margin: 0; }
.fail { color: var(--status-crit); font-size: 12.5px; background: var(--crit-bg); border-radius: 8px; padding: 10px 12px; }
.trace { color: var(--ink-3); font-size: 11.5px; margin-top: 6px; }

.a-list, .m-list, .claim-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.a-list li { display: grid; grid-template-columns: 20px auto 1fr; gap: 4px 10px; align-items: baseline; padding: 6px 10px; border-radius: 8px; background: var(--surface-2); }
.a-pass .a-mark { color: var(--status-good); }
.a-fail .a-mark { color: var(--status-crit); }
.a-mark { font-weight: 700; }
.a-name { font-weight: 500; font-size: 13px; }
.a-score { color: var(--ink-3); font-size: 12px; grid-column: 3; }
.a-msg { grid-column: 2 / -1; color: var(--ink-2); font-size: 12px; }

.m-list { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); }
.m-list li { display: flex; justify-content: space-between; gap: 8px; background: var(--surface-2); padding: 6px 10px; border-radius: 8px; font-size: 12.5px; }
.m-name { color: var(--ink-2); }
.m-value { font-variant-numeric: tabular-nums; }

.hallu-rate { margin: 0 0 8px; font-size: 13px; color: var(--ink-2); }
.claim-list { display: block; }
.claim { display: grid; grid-template-columns: 20px 120px 1fr; gap: 4px 10px; padding: 7px 10px; border-radius: 8px; background: var(--surface-2); font-size: 12.5px; }
.claim-ok .a-mark { color: var(--status-good); }
.claim-bad .a-mark { color: var(--status-crit); }
.claim-verdict { font-variant-numeric: tabular-nums; font-weight: 600; }
.claim-ok .claim-verdict { color: var(--status-good); }
.claim-bad .claim-verdict { color: var(--status-crit); }
.claim-evidence { grid-column: 3; color: var(--ink-3); font-size: 12px; }

.foot { margin-top: 32px; color: var(--ink-3); font-size: 12px; text-align: center; }
"""

_JS = """
(function () {
  var root = document.documentElement;
  var btn = document.getElementById('theme-toggle');
  if (!btn) return;
  var apply = function (theme) {
    root.setAttribute('data-theme', theme);
    try { localStorage.setItem('llmtest-theme', theme); } catch (e) {}
  };
  var saved = null;
  try { saved = localStorage.getItem('llmtest-theme'); } catch (e) {}
  if (saved === 'light' || saved === 'dark') apply(saved);
  btn.addEventListener('click', function () {
    apply(root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
  });
})();
"""
