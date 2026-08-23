"""双裁判模型对比：同一批 Dify 回答，用两个裁判模型分别打分，看一致性。

评估两个裁判模型对同一批回答的评分是否稳定一致——这是"裁判本身可不可信"的体检：
- 平均绝对分差：0 = 两裁判完全同分；
- 皮尔逊相关系数：越接近 1，两裁判排序越一致；
- 通过判定一致率：对"过/不过"的结论是否一致。

报告：每次运行生成 reports/judge_compare.html（最新），并：
- 每题可展开查看 Dify 回答 + 两个裁判的打分理由（诊断分差用）；
- 时间戳归档 reports/judge_compare_<时间>.html，历史记录写入
  reports/judge_compare_history.json，最新报告内展示历史对比表。

运行（PowerShell，在项目根目录）：

  场景一 · 两裁判在同一网关、同一分组（共用一个 key）：
    python examples/dify_bot/compare_judges.py --mode real --provider openai --base-url https://newapi.gosuncn.com/v1 --api-key sk-xxx --judge-a gpt-4o --judge-b gpt-4o-mini

  场景二 · 网关按厂商分组、两裁判 key 不同（如 gpt-5.6-sol 与 deepseek-v4-flash）：
    python examples/dify_bot/compare_judges.py --mode real --provider openai --base-url https://newapi.gosuncn.com/v1 --judge-a gpt-5.6-sol --judge-a-key sk-openai分组 --judge-b deepseek-v4-flash --judge-b-key sk-deepseek分组

  场景三 · 跨厂商（如 OpenAI 兼容 vs Anthropic）：
    python examples/dify_bot/compare_judges.py --mode real --judge-a gpt-4o --judge-a-provider openai --judge-a-base-url https://newapi.gosuncn.com/v1 --judge-a-key sk-a --judge-b claude-sonnet-5 --judge-b-provider anthropic --judge-b-key sk-ant

  配置优先级：裁判独立参数(--judge-?-key/provider/base-url) > 公共参数(--mode/--provider/--base-url/--api-key) > 环境变量(LLM_*)。
  未配 real 时自动降级 Mock（不调真实模型），并打印醒目警告。
"""

import argparse
import html as html_mod
import json
import os
import shutil
import sys
import time
from dataclasses import replace
from typing import List, Optional, Tuple

from llmtest import JudgeSpec, llm_judge
from llmtest.clients import get_client
from llmtest.config import Config

from adapter import DifyBotApp
from question_bank import QUESTION_BANK

# (question, score_a, score_b, answer, reasoning_a, reasoning_b)
_ROW = Tuple[str, float, float, str, str, str]


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    """皮尔逊相关系数；样本不足或方差为 0 时返回 None。"""
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return cov / ((vx * vy) ** 0.5)


def _mask(key: Optional[str]) -> str:
    """脱敏显示 key：只留后 4 位。"""
    if not key:
        return "(未设置)"
    return f"…{key[-4:]}"


def _resolve_cfg(args: argparse.Namespace, env_cfg: Config, judge: str, model: str) -> Config:
    """合并"公共配置 + 该裁判独立覆盖"，返回该裁判的 Config。

    优先级：judge-? 独立参数 > 公共参数 > 环境变量。
    """
    common = replace(
        env_cfg,
        mode=args.mode or env_cfg.mode,
        provider=args.provider or env_cfg.provider,
        base_url=args.base_url or env_cfg.base_url,
        api_key=args.api_key or env_cfg.api_key,
    )
    overrides = {
        "provider": getattr(args, f"judge_{judge}_provider"),
        "base_url": getattr(args, f"judge_{judge}_base_url"),
        "api_key": getattr(args, f"judge_{judge}_key"),
    }
    return replace(common, **{k: v for k, v in overrides.items() if v}, model=model)


# ----------------------------------------------------------------------
# 历史记录（reports/judge_compare_history.json）
# ----------------------------------------------------------------------

def _history_path(reports_dir: str) -> str:
    return os.path.join(reports_dir, "judge_compare_history.json")


def _load_history(reports_dir: str) -> List[dict]:
    try:
        with open(_history_path(reports_dir), encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _append_history(reports_dir: str, entry: dict) -> List[dict]:
    history = _load_history(reports_dir)
    history.append(entry)
    history = history[-20:]
    try:
        with open(_history_path(reports_dir), "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
    return history


def _render_history(history: List[dict]) -> str:
    """渲染历史对比表（最新在上）。无历史时返回空。"""
    if not history:
        return ""
    rows = []
    for e in reversed(history):
        corr = f"{e['corr']:.2f}" if e.get("corr") is not None else "—"
        rows.append(
            f"<tr>"
            f"<td>{html_mod.escape(e.get('ts', ''))}</td>"
            f"<td>{e.get('n', 0)}</td>"
            f"<td>{e.get('mean_diff', 0):.1f}</td>"
            f"<td>{corr}</td>"
            f"<td>{e.get('agree_rate', 0):.0%}</td>"
            f"<td>{html_mod.escape(e.get('judge_a', ''))} / {html_mod.escape(e.get('judge_b', ''))}</td>"
            f"</tr>"
        )
    return f"""
<section class="history" aria-label="历史对比">
  <h2>历史对比记录</h2>
  <p class="meta">每次运行的裁判一致性，最新在上、向下越旧；用于观察同一对裁判的稳定性。</p>
  <table class="history-table">
    <thead><tr><th>时间</th><th>样本</th><th>平均分差</th><th>皮尔逊相关</th><th>一致率</th><th>裁判 A / B</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</section>"""


# ----------------------------------------------------------------------
# 报告生成
# ----------------------------------------------------------------------

def _write_report(
    path: str,
    rows: List[_ROW],
    cfg_a: Config,
    cfg_b: Config,
    threshold: float,
    mean_diff: float,
    corr: Optional[float],
    agree_rate: float,
    is_real: bool,
    history: List[dict],
    skipped: Optional[List[str]] = None,
) -> Tuple[str, Optional[str]]:
    """生成最新报告 + 时间戳归档，返回 (最新路径, 归档路径)。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    body_rows = []
    for q, sa, sb, answer, ra_reason, rb_reason in rows:
        agree = (sa >= threshold) == (sb >= threshold)
        body_rows.append(
            f"<tr><td>{html_mod.escape(q)}</td><td>{sa:.1f}</td><td>{sb:.1f}</td>"
            f"<td>{abs(sa - sb):.1f}</td>"
            f"<td>{'一致' if agree else '<span class=bad>分歧</span>'}</td></tr>"
            f"<tr class='detail'><td colspan='5'><details>"
            f"<summary>查看 Dify 回答与两个裁判的打分理由</summary>"
            f"<div class='d-block'><div class='d-title'>Dify 回答</div>"
            f"<div class='d-text'>{html_mod.escape(answer)}</div></div>"
            f"<div class='d-block'><div class='d-title'>裁判 A（{html_mod.escape(cfg_a.model or '')}）打分理由</div>"
            f"<div class='d-text'>{html_mod.escape(ra_reason)}</div></div>"
            f"<div class='d-block'><div class='d-title'>裁判 B（{html_mod.escape(cfg_b.model or '')}）打分理由</div>"
            f"<div class='d-text'>{html_mod.escape(rb_reason)}</div></div>"
            f"</details></td></tr>"
        )
    body_html = "\n".join(body_rows)

    corr_str = f"{corr:.3f}" if corr is not None else "—"
    mode_note = "真实模型打分" if is_real else "Mock 规则打分（未配 real，未调用真实模型）"
    history_html = _render_history(history)

    skipped_html = ""
    if skipped:
        items = "".join(f"<li>{html_mod.escape(s)}</li>" for s in skipped)
        skipped_html = f"""
<section class="skipped" aria-label="跳过题目">
  <h2>跳过的题目（{len(skipped)}）</h2>
  <p class="meta">以下题目因裁判调用失败或空回答而未打分，不计入一致性统计：</p>
  <ul>{items}</ul>
</section>"""

    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>双裁判模型对比</title>
<style>
body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; margin: 0; background: #f6f7f9; color: #1f2328; }}
.page {{ max-width: 900px; margin: 0 auto; padding: 32px 20px; }}
h1 {{ font-size: 22px; margin: 0 0 6px; }}
.meta {{ color: #667085; font-size: 13px; margin: 2px 0; }}
.summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: #fff; border: 1px solid #e4e7ec; border-radius: 12px; padding: 14px 16px; }}
.card .v {{ font-size: 24px; font-weight: 600; margin-top: 4px; }}
.card .l {{ color: #667085; font-size: 13px; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e4e7ec; border-radius: 12px; overflow: hidden; font-size: 13px; }}
th, td {{ text-align: left; padding: 9px 12px; border-bottom: 1px solid #e4e7ec; vertical-align: top; }}
th {{ background: #f2f4f7; font-weight: 600; }}
.bad {{ color: #d92d20; font-weight: 600; }}
.detail {{ background: #fafbfc; }}
.detail details {{ padding: 4px 2px; }}
.detail summary {{ cursor: pointer; color: #175cd3; font-weight: 500; font-size: 13px; }}
.d-block {{ margin-top: 10px; }}
.d-title {{ font-weight: 600; color: #667085; font-size: 12px; margin: 0 0 4px; }}
.d-text {{ color: #1f2328; font-size: 13px; white-space: pre-wrap; word-break: break-word; background: #fff; border: 1px solid #e4e7ec; border-radius: 8px; padding: 8px 10px; }}
.history {{ margin-top: 32px; }}
.history h2 {{ font-size: 18px; margin: 0 0 4px; }}
.history-table {{ margin-top: 8px; }}
.skipped {{ margin-top: 24px; }}
.skipped h2 {{ font-size: 16px; margin: 0 0 4px; }}
.skipped ul {{ margin: 8px 0 0; padding-left: 20px; color: #b54708; font-size: 13px; }}
.foot {{ margin-top: 32px; color: #98a2b3; font-size: 12px; }}
</style></head>
<body><div class="page">
  <h1>双裁判模型对比</h1>
  <p class="meta">生成于 {time.strftime('%Y-%m-%d %H:%M:%S')} · 通过线 = {threshold} · {mode_note}</p>
  <p class="meta">裁判 A = {html_mod.escape(cfg_a.model or '')} [{html_mod.escape(cfg_a.provider)}] key {html_mod.escape(_mask(cfg_a.api_key))}</p>
  <p class="meta">裁判 B = {html_mod.escape(cfg_b.model or '')} [{html_mod.escape(cfg_b.provider)}] key {html_mod.escape(_mask(cfg_b.api_key))}</p>
  <div class="summary">
    <div class="card"><div class="l">有效样本</div><div class="v">{len(rows)}</div></div>
    <div class="card"><div class="l">平均绝对分差（0=同分）</div><div class="v">{mean_diff:.1f}</div></div>
    <div class="card"><div class="l">皮尔逊相关</div><div class="v">{corr_str}</div></div>
    <div class="card"><div class="l">通过判定一致率</div><div class="v">{agree_rate:.0%}</div></div>
  </div>
  <table>
    <thead><tr><th>问题</th><th>裁判 A</th><th>裁判 B</th><th>分差</th><th>判定</th></tr></thead>
    <tbody>{body_html}</tbody>
  </table>
  {skipped_html}
  {history_html}
  <p class="foot">llmtest 双裁判对比 · 每题可展开看 Dify 回答与两裁判理由 · 判定一致率 &lt; 80% 说明打分细则有歧义或裁判不可靠。</p>
</div></body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    # 时间戳归档（同秒重跑自动加序号防覆盖）
    base = path[:-5] if path.endswith(".html") else path
    ts = time.strftime("%Y%m%d_%H%M%S")
    archive_path = f"{base}_{ts}.html"
    seq = 1
    while os.path.exists(archive_path):
        archive_path = f"{base}_{ts}_{seq}.html"
        seq += 1
    shutil.copyfile(path, archive_path)
    return path, archive_path


def main() -> None:
    ap = argparse.ArgumentParser(description="双裁判模型对比")
    ap.add_argument("--judge-a", default="gpt-5.6-sol", help="裁判 A 模型名")
    ap.add_argument("--judge-b", default="deepseek-v4-flash", help="裁判 B 模型名")
    ap.add_argument("--threshold", type=float, default=60.0, help="通过线（默认 60，满分 100）")
    ap.add_argument("--min-questions", type=int, default=3, help="最少有效样本数")
    ap.add_argument("--mode", default=None, help="real | mock（缺省读 LLM_TEST_MODE，再缺省 mock）")
    ap.add_argument("--provider", default=None, help="裁判提供商兜底（缺省读 LLM_PROVIDER）")
    ap.add_argument("--base-url", default=None, help="裁判网关兜底（缺省读 LLM_BASE_URL）")
    ap.add_argument("--api-key", default=None, help="裁判 key 兜底（缺省读 LLM_API_KEY）")
    for judge in ("a", "b"):
        ap.add_argument(f"--judge-{judge}-key", default=None, help=f"裁判 {judge.upper()} 独立 key（优先于 --api-key / LLM_API_KEY）")
        ap.add_argument(f"--judge-{judge}-provider", default=None, help=f"裁判 {judge.upper()} 独立提供商（优先于 --provider / LLM_PROVIDER）")
        ap.add_argument(f"--judge-{judge}-base-url", default=None, help=f"裁判 {judge.upper()} 独立网关（优先于 --base-url / LLM_BASE_URL）")
    ap.add_argument("--report", default="reports/judge_compare.html", help="对比报告输出路径")
    ap.add_argument("--no-report", action="store_true", help="不生成 HTML 报告")
    args = ap.parse_args()

    env_cfg = Config.from_env()
    cfg_a = _resolve_cfg(args, env_cfg, "a", args.judge_a)
    cfg_b = _resolve_cfg(args, env_cfg, "b", args.judge_b)

    client_a = get_client(cfg_a)
    client_b = get_client(cfg_b)
    is_real = not client_a.is_mock and not client_b.is_mock
    if not is_real:
        print("⚠️  当前为 Mock 模式：没有调用真实模型，分数由 Mock 规则算出（仅供参考）。")
        print("    真实调用请传：--mode real，并为每个裁判配好 key（同网关分组不同用 --judge-?-key 分别传；")
        print("    跨厂商再配 --judge-?-provider / --judge-?-base-url）。")

    dify = DifyBotApp()
    spec = JudgeSpec.accuracy()

    print(f"\n裁判 A = {cfg_a.model} [{cfg_a.provider}] key {_mask(cfg_a.api_key)}")
    print(f"裁判 B = {cfg_b.model} [{cfg_b.provider}] key {_mask(cfg_b.api_key)}")
    print(f"通过线 = {args.threshold} · 样本 = question_bank 的 {len(QUESTION_BANK)} 个问题\n")

    rows: List[_ROW] = []
    skipped: List[str] = []
    for question, _expected in QUESTION_BANK:
        resp = dify.ask(question)
        if not resp.answer:
            print(f"[跳过 · 空回答] {question}")
            skipped.append(f"{question}：Dify 返回空回答")
            continue
        try:
            ra = llm_judge(resp.answer, spec, question=question,
                           context="\n".join(resp.sources), client=client_a)
            rb = llm_judge(resp.answer, spec, question=question,
                           context="\n".join(resp.sources), client=client_b)
        except Exception as exc:  # 单个裁判失败（额度不足/超时/模型不存在等）不中断整批
            print(f"[跳过 · 裁判调用失败] {question}：{type(exc).__name__}: {exc}")
            skipped.append(f"{question}：{type(exc).__name__}: {str(exc)[:120]}")
            continue
        rows.append((question, ra.score, rb.score, resp.answer, ra.reasoning, rb.reasoning))
        agree = (ra.score >= args.threshold) == (rb.score >= args.threshold)
        print(
            f"{question}\n"
            f"  A({cfg_a.model}): {ra.score}/{ra.max_score}   "
            f"B({cfg_b.model}): {rb.score}/{rb.max_score}   差 {abs(ra.score - rb.score):.1f}  "
            f"[{'一致' if agree else '分歧'}]"
        )

    if not rows:
        print(f"\n全部题目均未能打分（{len(skipped)} 题跳过）：")
        for s in skipped:
            print(f"  - {s}")
        sys.exit(1)
    if len(rows) < args.min_questions:
        print(f"\n⚠️  有效样本仅 {len(rows)} 题（少于 {args.min_questions}），一致性统计仅供参考。")

    da = [r[1] for r in rows]
    db = [r[2] for r in rows]
    mean_diff = sum(abs(x - y) for x, y in zip(da, db)) / len(da)
    corr = _pearson(da, db)
    agree_rate = sum(
        1 for x, y in zip(da, db) if (x >= args.threshold) == (y >= args.threshold)
    ) / len(da)

    print("\n===== 双裁判一致性汇总 =====")
    print(f"有效样本: {len(rows)}")
    print(f"平均绝对分差: {mean_diff:.2f}   （0 = 完全同分）")
    print(f"皮尔逊相关:   {corr:.3f}        （越接近 1，两裁判排序越一致）")
    print(f"通过判定一致率: {agree_rate:.0%}  （对同一回答判过/不过的吻合度）")
    if agree_rate < 0.8:
        print("提示: 通过判定一致率 < 80%，裁判分歧较大——建议核查打分细则或换更强裁判。")

    if not args.no_report:
        reports_dir = os.path.dirname(os.path.abspath(args.report))
        entry = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "n": len(rows),
            "mean_diff": mean_diff,
            "corr": corr,
            "agree_rate": agree_rate,
            "judge_a": args.judge_a,
            "judge_b": args.judge_b,
        }
        history = _append_history(reports_dir, entry)
        path, archive = _write_report(
            args.report, rows, cfg_a, cfg_b,
            args.threshold, mean_diff, corr, agree_rate, is_real, history, skipped,
        )
        print(f"\n对比报告已生成：{path}")
        print(f"历史归档：{archive}（历史记录：{os.path.join(reports_dir, 'judge_compare_history.json')}）")


if __name__ == "__main__":
    main()
