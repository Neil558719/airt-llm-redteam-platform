"""Typer command line interface for authorized red-team runs."""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
import yaml
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from airt.adapter import OpenAICompatTarget
from airt.cases import CaseLoadError, load_cases
from airt.case_validation import validate_cases
from airt.config import (
    AppConfig,
    ConfigError,
    DifyTargetConfig,
    TargetConfig,
    load_config,
)
from airt.dify_adapter import DifyTarget
from airt.baseline import compare_assess, compare_results, discover_assess_run, save_baseline, write_comparison
from airt.doctor import CheckResult, check_settings, probe_url
from airt.evaluation_bridge import EvaluationContext
from airt.judge.llm import Judge
from airt.judge.llm import build_judge
from airt.judge.pipeline import evaluate
from airt.metrics import summarize
from airt.models import CaseResult, Reply, ResultStatus, RunMetadata, Severity
from airt.quality_bridge import LiveQualityJudge, QualityEvaluator, QualitySummary
from airt.target_registry import load_target_registry
from airt.shared_cases import SharedCaseError, shared_quality_attack_cases, shared_security_cases


def _select_multimodal_case(cases_path: Path, asset: Path, asset_type: str | None = None) -> dict:
    """Select the closest multimodal case for one local image/audio asset."""
    kind = asset_type or ("audio" if asset.suffix.casefold() in {".wav", ".mp3", ".m4a", ".ogg"} else "image")
    rows = yaml.safe_load(cases_path.read_text(encoding="utf-8"))
    candidates = [row for row in rows if row.get("input", {}).get("type") == kind]
    if not candidates:
        raise ValueError(f"no multimodal {kind} case is available")
    stem = asset.stem.casefold()
    def rank(row: dict) -> tuple[int, str]:
        cid = row["case_id"]
        return (0 if any(token in stem and token in cid for token in ("sensitive", "mixed", "tool", "ocr", "prompt")) else 1, cid)
    selected = dict(sorted(candidates, key=rank)[0])
    selected["input"] = dict(selected["input"])
    selected["input"]["asset"] = _multimodal_asset_url(8765, asset)
    return selected


def _multimodal_asset_url(port: int, asset: Path) -> str:
    return f"http://127.0.0.1:{port}/{asset.name}"


def _result_errors(results: list[CaseResult]) -> list[CaseResult]:
    return [item for item in results if item.status == ResultStatus.ERROR]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def release_gate_failures(
    *,
    risk_score: float,
    quality: QualitySummary,
    min_quality_pass_rate: float | None = None,
    max_average_latency_ms: float | None = None,
) -> list[str]:
    """Return human-readable release-gate violations without raising."""

    failures: list[str] = []
    if min_quality_pass_rate is not None and quality.total:
        pass_rate = quality.passed / quality.total
        if pass_rate < min_quality_pass_rate:
            failures.append(f"quality pass rate {pass_rate:.1%} < required {min_quality_pass_rate:.1%}")
    if max_average_latency_ms is not None and quality.average_latency_ms is not None:
        if quality.average_latency_ms > max_average_latency_ms:
            failures.append(f"average latency {quality.average_latency_ms:.0f} ms > maximum {max_average_latency_ms:.0f} ms")
    return failures


def _quality_judge_context(reply: Reply) -> str:
    """Return the retrieved evidence available to the quality Judge."""

    return "\n".join(source.strip() for source in reply.sources if source.strip())
from airt.report.archive import archive_reports
from airt.report.unified import write_assess_report, write_unified_report
from airt.report.trends import write_trend
from airt.report.dashboard import write_dashboard
from airt.report.console import render_console
from airt.runner import run_cases

_AUTHORIZATION_WARNING = (
    "Only test LLM applications you own or are explicitly authorized to assess."
)

app = typer.Typer(
    name="airt",
    help=(
        "Authorized red-team testing for LLM applications.\n\n"
        f"{_AUTHORIZATION_WARNING}"
    ),
    no_args_is_help=True,
    add_completion=False,
)


@app.command("trend")
def trend_report(
    reports: Annotated[Path, typer.Option("--reports", exists=True, readable=True, help="某个模式的 reports 目录")],
    out: Path | None = typer.Option(None, help="输出目录，默认与 --reports 相同"),
) -> None:
    """离线汇总历史报告趋势。"""
    path = write_trend(reports, out)
    console.print(f"趋势报告：{path}")


@app.command("dashboard")
def dashboard_report(
    reports: Annotated[Path, typer.Option("--reports", exists=True, readable=True)] = Path("reports"),
    out: Path | None = typer.Option(None, help="输出目录，默认 reports"),
) -> None:
    """生成静态测试总览页，不调用目标应用或 Judge。"""
    path = write_dashboard(reports, out)
    console.print(f"Dashboard：{path}")

@app.command("targets")
def targets(
    registry: Annotated[Path, typer.Option("--registry", exists=True, readable=True)] = Path("targets.example.yaml"),
) -> None:
    """List registered targets without resolving or printing credentials."""
    try:
        raw = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
        entries = raw.get("targets", {}) if isinstance(raw, dict) else {}
    except (OSError, yaml.YAMLError) as error:
        _fail(f"could not read target registry: {error}")
    table = Table(title="Registered targets")
    table.add_column("Name")
    table.add_column("Provider")
    table.add_column("Type")
    table.add_column("Base URL")
    for name, target in sorted(entries.items()):
        table.add_row(name, str(target.get("provider", "")), str(target.get("app_type", "chat")), str(target.get("base_url", "")))
    console.print(table)

cases_app = typer.Typer(help="测试用例资产管理")
app.add_typer(cases_app, name="cases")

baseline_app = typer.Typer(help="离线回归基线管理，不调用目标应用或 Judge")
app.add_typer(baseline_app, name="baseline")


@baseline_app.command("save")
def baseline_save(
    results: Annotated[Path, typer.Option("--results", exists=True, readable=True)],
    out: Path = typer.Option(..., "--out", help="基线 JSONL 输出路径"),
) -> None:
    """保存一份不可混淆的本地结果基线。"""
    try:
        saved = save_baseline(results, out)
    except (OSError, ValueError) as error:
        _fail(str(error))
    console.print(f"基线已保存：{saved}")
    console.print(f"基线元信息：{saved.with_suffix('.json')}")


@baseline_app.command("compare")
def baseline_compare(
    baseline: Annotated[Path, typer.Option("--baseline", exists=True, readable=True)],
    candidate: Annotated[Path, typer.Option("--candidate", exists=True, readable=True)],
    out: Path = typer.Option(..., "--out", help="比较报告输出目录"),
    min_answer_overlap: float = typer.Option(0.4, min=0.0, max=1.0, help="最低回答相似度"),
    max_latency_increase: float | None = typer.Option(None, min=0.0, help="最大延迟增幅，例如 0.5 表示最多增加 50%"),
) -> None:
    """比较本地基线与当前结果并生成 JSON/HTML 报告。"""
    try:
        comparison = compare_results(
            baseline,
            candidate,
            min_answer_overlap=min_answer_overlap,
            max_latency_increase=max_latency_increase,
        )
        json_path, html_path = write_comparison(comparison, out)
    except (OSError, ValueError) as error:
        _fail(str(error))
    if comparison.passed:
        console.print(f"[green]基线比较通过[/green]（{len(comparison.rows)} 条用例）")
    else:
        console.print(f"[red]基线比较失败[/red]（{len(comparison.failures)} 个差异）")
        for failure in comparison.failures:
            console.print(f"- {failure}")
    console.print(f"JSON 报告：{json_path}")
    console.print(f"HTML 报告：{html_path}")
    if not comparison.passed:
        raise typer.Exit(code=1)


@baseline_app.command("compare-assess")
def baseline_compare_assess(
    baseline: Annotated[Path, typer.Option("--baseline", exists=True, readable=True)],
    run_dir: Path | None = typer.Option(None, "--run-dir", help="指定 assess 结果目录；省略时自动选择最近完整结果"),
    out: Path | None = typer.Option(None, "--out", help="比较报告目录；省略时写入 reports/baseline-assess/<时间戳>"),
    min_answer_overlap: float = typer.Option(0.4, min=0.0, max=1.0, help="最低回答相似度"),
    max_latency_increase: float | None = typer.Option(None, min=0.0, help="最大延迟增幅，例如 0.5 表示最多增加 50%"),
) -> None:
    """自动合并最近一次 assess 的安全和质量结果并与基线比较。"""
    try:
        selected_run = run_dir or discover_assess_run(Path("runs"))
        destination = out or (Path("reports") / "baseline-assess" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        comparison = compare_assess(
            baseline,
            selected_run,
            min_answer_overlap=min_answer_overlap,
            max_latency_increase=max_latency_increase,
        )
        json_path, html_path = write_comparison(comparison, destination)
    except (OSError, ValueError) as error:
        _fail(str(error))
    console.print(f"比较对象：{selected_run}")
    if comparison.passed:
        console.print(f"[green]Assess 基线比较通过[/green]（{len(comparison.rows)} 条用例）")
    else:
        console.print(f"[red]Assess 基线比较失败[/red]（{len(comparison.failures)} 个差异）")
        for failure in comparison.failures:
            console.print(f"- {failure}")
    console.print(f"JSON 报告：{json_path}")
    console.print(f"HTML 报告：{html_path}")
    if not comparison.passed:
        raise typer.Exit(code=1)


@cases_app.command("validate")
def validate_case_files(
    path: Annotated[Path, typer.Argument(exists=True, readable=True, help="YAML 文件或用例目录")],
) -> None:
    """离线校验测试用例，不调用目标应用或 Judge。"""
    summary = validate_cases(path)
    if summary.valid:
        console.print(f"[green]通过[/green] 校验 {summary.files} 个文件、{summary.cases} 条用例")
        return
    console.print(f"[red]失败[/red] 校验 {summary.files} 个文件，发现 {len(summary.issues)} 个问题")
    for issue in summary.issues:
        console.print(f"- {issue.source}: {issue.message}")
    raise typer.Exit(code=2)
console = Console()
_RUN_MODES = frozenset({"security", "quality", "release"})


def _resolve_run_mode(mode: str, *, security_judge: str | None = None) -> tuple[str, str]:
    """Resolve a concise run mode into security and quality Judge policies."""
    defaults = {
        "security": ("always", "offline"),
        "quality": ("case", "live"),
        "release": ("case", "live"),
    }
    try:
        security_policy, quality_policy = defaults[mode.casefold()]
    except KeyError as error:
        raise ValueError("mode must be security, quality, or release") from error
    if security_judge is not None:
        security_policy = security_judge.casefold()
        if security_policy not in {"off", "case", "always"}:
            raise ValueError("security-judge must be off, case, or always")
    return security_policy, quality_policy


def _shortcut_output_dir(root: Path, target: str, action: str) -> Path:
    return root / f"{target}-{action}"


def _report_mode(metadata: RunMetadata | None) -> str:
    """Return the safe report subdirectory for a run mode.

    JSONL created before run-mode metadata was introduced is treated as
    ``quality`` so every report still lands in one of the current stable
    directories rather than recreating a flat ``reports/`` layout.
    """

    mode = (metadata.run_mode if metadata is not None else "quality").casefold()
    return mode if mode in _RUN_MODES else "quality"


def _resolve_profile_policy(
    settings: AppConfig,
    mode: str | None,
    *,
    security_judge: str | None,
    quality_judge: str,
) -> tuple[str, str, str, object]:
    selected = mode or ("quality" if quality_judge == "live" else "security")
    security_policy, quality_policy = _resolve_run_mode(selected, security_judge=security_judge)
    if mode is None and quality_judge in {"offline", "live"}:
        quality_policy = quality_judge
    profile = settings.run_profiles.get(selected)
    if profile is not None:
        security_policy = security_judge or profile.security_judge
        quality_policy = profile.quality_judge
    return selected, security_policy, quality_policy, (profile.gates if profile is not None else None)


def _fail(message: str, *, code: int = 2) -> None:
    typer.echo(f"Error: {message}")
    raise typer.Exit(code=code)


def _load_case_set(path: Path, include_sensitive: bool, *, shared: bool = False, shared_quality: bool = False) -> list:
    try:
        if shared_quality:
            return shared_quality_attack_cases(path)
        return shared_security_cases(path) if shared else load_cases(path, include_sensitive=include_sensitive)
    except (CaseLoadError, SharedCaseError) as error:
        _fail(str(error))
    return []


def _wire(value: object) -> str:
    return str(getattr(value, "value", value))


chatflow_app = typer.Typer(help="Airt Dify Chatflow 质量与工具安全测试")
app.add_typer(chatflow_app, name="chatflow")


def _shortcut_out(out: Path | None, runs_dir: Path, target: str, action: str) -> Path:
    return out if out is not None else _shortcut_output_dir(runs_dir, target, action)


@chatflow_app.command("quality")
def chatflow_quality(
    config: Path = typer.Option(Path("config.dify.agent.yaml"), exists=True, readable=True),
    cases: Path = typer.Option(Path("shared_cases/unified_chatflow.yaml"), exists=True, readable=True),
    out: Path | None = typer.Option(None, help="结果目录，默认 runs/chatflow-quality"),
    runs_dir: Path = typer.Option(Path("runs"), help="快捷命令默认运行目录"),
) -> None:
    """Run shared knowledge-base quality cases against the unified Chatflow."""
    run(config=config, cases=cases, out=_shortcut_out(out, runs_dir, "chatflow", "quality"), mode="quality", shared_quality=True)


@chatflow_app.command("release")
def chatflow_release(
    config: Path = typer.Option(Path("config.dify.agent.yaml"), exists=True, readable=True),
    cases: Path = typer.Option(Path("shared_cases/unified_chatflow.yaml"), exists=True, readable=True),
    out: Path | None = typer.Option(None, help="结果目录，默认 runs/chatflow-release"),
    runs_dir: Path = typer.Option(Path("runs"), help="快捷命令默认运行目录"),
) -> None:
    """Run Chatflow quality Judge with release gates."""
    run(config=config, cases=cases, out=_shortcut_out(out, runs_dir, "chatflow", "release"), mode="release", shared_quality=True)


@chatflow_app.command("assess")
def chatflow_assess(
    config: Path = typer.Option(Path("config.dify.agent.yaml"), exists=True, readable=True),
    cases: Path = typer.Option(Path("shared_cases/unified_chatflow.yaml"), exists=True, readable=True),
    out: Path | None = typer.Option(None, help="结果根目录，默认 runs/chatflow-assess"),
    runs_dir: Path = typer.Option(Path("runs"), help="快捷命令默认运行目录"),
) -> None:
    """Run Chatflow security and quality assessment in one command."""
    root = out if out is not None else _shortcut_output_dir(runs_dir, "chatflow", "assess")
    security_results = root / "security" / "results.jsonl"
    quality_results = root / "quality" / "results.jsonl"
    run(config=config, cases=cases, out=root / "security", mode="security", security_judge="always", shared_cases=True)
    run(config=config, cases=cases, out=root / "quality", mode="quality", shared_quality=True)
    write_assess_report(security_results, quality_results, Path("reports/assess"))


@chatflow_app.command("security")
def chatflow_security(
    config: Path = typer.Option(Path("config.dify.agent.yaml"), exists=True, readable=True),
    cases: Path = typer.Option(Path("shared_cases/unified_chatflow.yaml"), exists=True, readable=True),
    out: Path | None = typer.Option(None, help="结果目录，默认 runs/chatflow-security"),
    runs_dir: Path = typer.Option(Path("runs"), help="快捷命令默认运行目录"),
    security_judge: str = typer.Option("always", help="off、case 或 always"),
    asset: Path | None = typer.Option(None, help="单个本地图片或音频文件；自动匹配多模态用例"),
    asset_type: str | None = typer.Option(None, "--asset-type", help="image 或 audio；默认按扩展名推断"),
) -> None:
    if asset is None:
        run(config=config, cases=cases, out=_shortcut_out(out, runs_dir, "chatflow", "security"), mode="security", security_judge=security_judge, shared_cases=True)
        return
    if not asset.is_file():
        _fail(f"asset does not exist: {asset}")
    cases = Path("shared_cases/multimodal_chatflow.yaml")
    selected = _select_multimodal_case(cases, asset, asset_type)
    with tempfile.TemporaryDirectory(prefix="airt-multimodal-") as temp:
        case_file = Path(temp) / "case.yaml"
        port = _free_port()
        selected["input"] = dict(selected["input"])
        selected["input"]["asset"] = _multimodal_asset_url(port, asset)
        case_file.write_text(yaml.safe_dump([selected], allow_unicode=True, sort_keys=False), encoding="utf-8")
        server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "0.0.0.0", "--directory", str(asset.parent)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            run(config=config, cases=case_file, out=_shortcut_out(out, runs_dir, "chatflow", "security"), mode="security", security_judge=security_judge, shared_cases=True)
        finally:
            server.terminate()
            server.wait(timeout=5)


@app.command()
def doctor(
    config: Path = typer.Option(Path("config.dify.yaml"), exists=True, readable=True),
    mode: str = typer.Option("quality", help="security、quality 或 release"),
    cases: Path | None = typer.Option(None, help="测试用例文件或目录；省略时按配置名称推断"),
    target_profile: str | None = typer.Option(None, help="可选目标 profile 名称"),
    security_judge: str | None = typer.Option(None, help="security 模式下的 Judge 策略：off、case 或 always"),
    check_network: bool = typer.Option(False, "--check-network", help="显式探测目标和 Judge 地址；默认不联网"),
) -> None:
    """检查配置、密钥和测试资产；默认不调用被测应用或 Judge。"""
    case_path = cases
    try:
        security, quality = _resolve_run_mode(mode, security_judge=security_judge)
        settings = load_config(config, include_judge=not (security == "off" and quality == "offline"))
        target = settings.resolve_target(target_profile)
        if case_path is None:
            case_path = (
                Path("shared_cases/unified_chatflow.yaml")
                if getattr(target, "capture_tool_calls", False) or "agent" in config.name.casefold()
                else Path("cases/dify.yaml")
            )
        checks = check_settings(
            settings,
            mode=mode,
            security_judge=security_judge,
            cases_path=case_path,
            target_profile=target_profile,
        )
    except (ConfigError, ValueError) as error:
        console.print(f"[red][FAIL][/red] 配置：{error}")
        raise typer.Exit(code=2)
    try:
        case_summary = validate_cases(case_path)
    except (OSError, ValueError) as error:
        case_summary = None
        checks["cases"] = CheckResult(False, f"测试用例校验失败：{error}", "fail")
    if case_summary is not None:
        if case_summary.valid:
            checks["cases"] = CheckResult(
                True, f"测试用例有效（{case_summary.files} 个文件，{case_summary.cases} 条用例）"
            )
        else:
            checks["cases"] = CheckResult(
                False,
                f"测试用例校验失败（{len(case_summary.issues)} 个问题）",
                "fail",
            )
            for issue in case_summary.issues:
                console.print(f"[red]- {issue.source}: {issue.message}[/red]")
    if check_network:
        checks["target_endpoint"] = probe_url(target.base_url)
        if settings.judge is not None and any(
            item.status != "skip" for key, item in checks.items() if key.startswith("judge_")
        ):
            checks["judge_endpoint"] = probe_url(settings.judge.base_url)
    else:
        checks["network"] = CheckResult(True, "网络探测未启用（默认离线）", "skip")
    for label, result in checks.items():
        color = "green" if result.ok and result.status != "fail" else "red"
        marker = "SKIP" if result.status == "skip" else ("OK" if result.ok else "FAIL")
        console.print(f"[{color}][{marker}][/{color}] {result.message}")
    if not all(result.ok for result in checks.values()):
        raise typer.Exit(code=1)


@app.command("list")
def list_cases(
    cases: Annotated[Path, typer.Option("--cases", exists=True, readable=True)],
    include_sensitive: Annotated[
        bool, typer.Option("--include-sensitive", help="Include cases under sensitive/.")
    ] = False,
) -> None:
    """List attack cases without contacting a target or judge."""
    loaded = _load_case_set(cases, include_sensitive)
    table = Table(title="Attack cases")
    for heading in ("ID", "Category", "Severity", "Name"):
        table.add_column(heading)
    for case in loaded:
        table.add_row(case.id, _wire(case.category), _wire(case.severity), case.name)
    console.print(table)


@app.command()
def run(
    config: Annotated[Path, typer.Option("--config", exists=True, readable=True)],
    cases: Annotated[Path, typer.Option("--cases", exists=True, readable=True)],
    out: Annotated[
        Path,
        typer.Option(
            "--out",
            help="Run-state directory for results.jsonl (default: ./reports relative to cwd).",
        ),
    ] = Path("reports"),
    include_sensitive: Annotated[
        bool, typer.Option("--include-sensitive", help="Include cases under sensitive/.")
    ] = False,
    target_profile: Annotated[
        str | None,
        typer.Option(
            "--target-profile",
            help="Optional named target profile from config (for example: text or agent).",
        ),
    ] = None,
    resume: Annotated[
        bool,
        typer.Option(
            "--resume",
            help="Resume from completed records already present in OUT/results.jsonl.",
        ),
    ] = False,
    fail_on_score: Annotated[
        float | None,
        typer.Option(
            "--fail-on-score",
            min=0.0,
            max=100.0,
            help="Exit 1 when the weighted risk score is below this value.",
        ),
    ] = None,
    fail_on_severity: Annotated[
        str | None,
        typer.Option(
            "--fail-on-severity",
            help="Exit 1 when a successful case meets this severity or higher.",
        ),
    ] = None,
    fail_on_quality: Annotated[
        float | None,
        typer.Option("--fail-on-quality", min=0.0, max=1.0, help="Exit 1 when quality pass rate is below this value."),
    ] = None,
    fail_on_latency: Annotated[
        float | None,
        typer.Option("--fail-on-latency", min=0.0, help="Exit 1 when average quality latency exceeds this many milliseconds."),
    ] = None,
    quality_judge: Annotated[
        str,
        typer.Option("--quality-judge", help="Quality evaluator mode: offline (default) or live."),
    ] = "offline",
    mode: Annotated[
        str | None,
        typer.Option("--mode", help="Concise run mode: security, quality, or release."),
    ] = None,
    security_judge: Annotated[
        str | None,
        typer.Option("--security-judge", help="Security Judge policy: off, case, or always."),
    ] = None,
    shared_cases: Annotated[
        bool,
        typer.Option("--shared-cases", help="Read provider-neutral shared cases."),
    ] = False,
    shared_quality: Annotated[
        bool,
        typer.Option("--shared-quality", help="Read shared quality cases from the provider-neutral YAML."),
    ] = False,
) -> None:
    """Execute cases and write JSONL plus JSON, HTML, and console reports."""
    try:
        preliminary_mode = mode or ("quality" if quality_judge == "live" else "security")
        preliminary_security, preliminary_quality = _resolve_run_mode(preliminary_mode, security_judge=security_judge)
        settings = load_config(
            config,
            include_judge=not (preliminary_security == "off" and preliminary_quality == "offline"),
        )
        selected_mode, security_judge_mode, quality_judge_mode, profile_gates = _resolve_profile_policy(
            settings, mode, security_judge=security_judge, quality_judge=quality_judge
        )
        target_config = settings.resolve_target(target_profile)
    except (ConfigError, ValueError) as error:
        _fail(str(error))
    loaded = (_load_case_set(cases, include_sensitive, shared=True) if shared_cases else _load_case_set(cases, include_sensitive, shared_quality=True) if shared_quality else _load_case_set(cases, include_sensitive))
    output_path = out / "results.jsonl"
    report_dir = _report_dir(selected_mode)
    run_started_at = datetime.now(timezone.utc)
    metadata = RunMetadata(
        run_id=f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}",
        started_at=run_started_at.isoformat(),
        target_profile=target_profile or ("agent" if getattr(target_config, "capture_tool_calls", False) else "text"),
        run_mode=selected_mode,
        security_judge_policy=security_judge_mode,
        quality_judge_mode=quality_judge_mode,
    )

    if profile_gates is not None:
        fail_on_score = fail_on_score if fail_on_score is not None else profile_gates.min_score
        fail_on_quality = fail_on_quality if fail_on_quality is not None else profile_gates.min_quality
        fail_on_latency = fail_on_latency if fail_on_latency is not None else profile_gates.max_latency_ms

    if fail_on_severity is not None:
        try:
            threshold = Severity(fail_on_severity.casefold())
        except ValueError:
            _fail(
                "invalid --fail-on-severity; choose critical, high, medium, or low"
            )
        threshold_weight = _severity_weight(threshold)
    else:
        threshold = None
        threshold_weight = 0

    try:
        # The target and judge are created and closed in one event loop. This is
        # important for transports that bind resources to their event loop.
        asyncio.run(
            _execute_run(
                settings,
                target_config,
                loaded,
                output_path,
                resume=resume,
                metadata=metadata,
                quality_judge_mode=quality_judge_mode,
                security_judge_mode=security_judge_mode or "case",
            )
        )
    except (OSError, ValueError, RuntimeError) as error:
        _fail(str(error))

    # A resumed run's JSONL contains the durable records from earlier calls;
    # include them when rendering the complete report.
    try:
        all_results, source_jsonl = _read_results(output_path)
    except ValueError as error:
        _fail(str(error))
    summary = summarize(all_results)
    result_errors = _result_errors(all_results)
    if result_errors:
        for item in result_errors:
            console.print(f"测试执行失败：{item.case_id}（{item.failure_kind or 'unknown'}）")
        raise typer.Exit(code=1)
    quality = QualitySummary.from_dicts([item.quality for item in all_results if item.quality is not None])
    report_metadata = next(
        (result.run_metadata for result in all_results if result.run_metadata is not None),
        metadata,
    )
    report_dir = _report_dir(_report_mode(report_metadata))
    archive = _publish_reports(
        summary,
        all_results,
        source_jsonl,
        latest_dir=report_dir,
        archive_dir=_report_dir(_report_mode(report_metadata)),
        metadata=report_metadata,
        quality=quality if quality.total else None,
    )
    render_console(summary, all_results, console=console, metadata=report_metadata)
    console.print(f"结果 JSONL：{output_path}")
    console.print(f"结构化 JSON 报告：{report_dir / 'report.json'}")
    console.print(f"HTML 报告：{report_dir / 'report.html'}")
    console.print(f"本次报告归档：{archive}")

    violates_score = fail_on_score is not None and summary.risk_score < fail_on_score
    quality_failures = release_gate_failures(
        risk_score=summary.risk_score,
        quality=quality,
        min_quality_pass_rate=fail_on_quality,
        max_average_latency_ms=fail_on_latency,
    )
    violates_severity = threshold is not None and any(
        _wire(item.status) != _wire(ResultStatus.ERROR)
        and item.verdict is not None
        and _wire(item.verdict.status) == "success"
        and item.case is not None
        and _severity_weight(item.case.severity) >= threshold_weight
        for item in all_results
    )
    if quality_failures:
        for failure in quality_failures:
            console.print(f"发布门禁失败：{failure}")
    if violates_score or violates_severity or bool(quality_failures):
        raise typer.Exit(code=1)


@app.command()
def report(
    results: Annotated[Path, typer.Option("--results", exists=True, readable=True)],
    out: Annotated[
        Path,
        typer.Option("--out", help="Report directory (default: ./reports relative to cwd)."),
    ] = Path("reports"),
) -> None:
    """Regenerate reports from JSONL without loading a config or using a network."""
    try:
        loaded, source_jsonl = _read_results(results)
    except (OSError, ValueError) as error:
        _fail(str(error))
    summary = summarize(loaded)
    quality = QualitySummary.from_dicts([item.quality for item in loaded if item.quality is not None])
    report_metadata = next(
        (result.run_metadata for result in loaded if result.run_metadata is not None),
        None,
    )
    mode = _report_mode(report_metadata)
    latest_dir = _report_dir(mode) if out == Path("reports") else out
    archive = _publish_reports(
        summary,
        loaded,
        source_jsonl,
        latest_dir=latest_dir,
        archive_dir=_report_dir(mode),
        metadata=report_metadata,
        quality=quality if quality.total else None,
    )
    render_console(summary, loaded, console=console)
    console.print(f"结构化 JSON 报告：{latest_dir / 'report.json'}")
    console.print(f"HTML 报告：{latest_dir / 'report.html'}")
    console.print(f"本次报告归档：{archive}")


def _report_dir(mode: str = "quality") -> Path:
    """Return the stable latest-report directory grouped by run mode."""

    return Path.cwd() / "reports" / _report_mode(RunMetadata(run_mode=mode))


def _publish_reports(
    summary,
    results: list[CaseResult],
    source_jsonl: bytes,
    *,
    latest_dir: Path,
    archive_dir: Path,
    metadata: RunMetadata | None = None,
    quality: QualitySummary | None = None,
) -> Path:
    """Archive a report before refreshing the replaceable latest-report files."""

    archive = archive_reports(
        summary,
        results,
        source_jsonl,
        archive_dir,
        metadata=metadata,
        quality=quality,
    )
    latest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(archive / "report.json", latest_dir / "report.json")
    shutil.copyfile(archive / "report.html", latest_dir / "report.html")
    return archive


def _read_results(path: Path) -> tuple[list[CaseResult], bytes]:
    try:
        source = path.read_bytes()
    except OSError as error:
        raise ValueError(f"could not read results {path}: {error}") from error
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"could not decode results {path} as UTF-8") from error

    parsed: list[CaseResult] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed.append(CaseResult.model_validate_json(line))
        except (TypeError, ValueError) as error:
            raise ValueError(f"malformed results JSONL at {path}:{line_number}") from error
    return parsed, source


def _severity_weight(value: object) -> int:
    return {"critical": 8, "high": 4, "medium": 2, "low": 1}[_wire(value)]


def build_target(config: TargetConfig | DifyTargetConfig) -> OpenAICompatTarget | DifyTarget:
    """Construct the configured target without changing the CLI execution path."""

    if config.provider == "openai_compatible":
        return OpenAICompatTarget(config)
    if config.provider == "dify":
        return DifyTarget(config)
    raise ValueError(f"unsupported target provider: {config.provider}")


async def _execute_run(
    settings: AppConfig,
    target_config: TargetConfig | DifyTargetConfig,
    cases,
    output_path: Path,
    *,
    resume: bool,
    metadata: RunMetadata,
    quality_judge_mode: str = "offline",
    security_judge_mode: str = "case",
) -> None:
    """Build independent clients, execute cases, and always close both clients."""
    target = build_target(target_config)
    judge: Judge | None = None
    quality_judge: LiveQualityJudge | None = None
    try:
        if security_judge_mode not in {"off", "case", "always"}:
            raise ValueError("security-judge must be off, case, or always")
        if security_judge_mode != "off" and settings.judge is not None:
            judge = build_judge(settings.judge)
        if quality_judge_mode not in {"offline", "live"}:
            raise ValueError("--quality-judge must be offline or live")
        if quality_judge_mode == "live":
            if settings.judge is None:
                raise ValueError("--quality-judge live requires a judge configuration")
            quality_judge = LiveQualityJudge(
                base_url=settings.judge.base_url,
                api_key=settings.judge.api_key,
                model=settings.judge.model,
                timeout=settings.judge.timeout,
            )

        async def evaluator(case, reply, *, system_prompt: str = ""):
            return await evaluate(
                case,
                reply,
                system_prompt=system_prompt,
                judge=judge,
                leak_ngram=settings.run.leak_ngram,
                judge_mode_override="always" if security_judge_mode == "always" else None,
            )

        async def live_quality(case, reply, latency_ms):
            offline = QualityEvaluator().evaluate(
                EvaluationContext.from_reply(reply, latency_ms=latency_ms),
                expected_answer=case.quality.expected_answer if case.quality else None,
                semantic_threshold=case.quality.semantic_threshold if case.quality else 0.7,
                max_hallucination_rate=case.quality.max_hallucination_rate if case.quality else None,
                json_schema=case.quality.json_schema if case.quality else None,
            )
            judged = await quality_judge.evaluate(
                case.turns[-1], reply.text,
                case.quality.expected_answer if case.quality and case.quality.expected_answer else "回答是否准确、相关、完整",
                context=_quality_judge_context(reply),
            )
            offline.judge_score = judged.score
            offline.judge_passed = judged.passed
            offline.judge_reason = judged.reason
            offline.judge_latency_ms = judged.latency_ms
            offline.judge_usage = judged.usage
            offline.judge_cost = judged.cost
            if not judged.passed:
                offline.errors.append(f"judge score {judged.score:.3f} < {judged.threshold:.3f}")
            return offline.as_dict()

        await run_cases(
            cases,
            target,
            evaluator,
            output_path,
            concurrency=settings.run.concurrency,
            qps=settings.run.qps,
            retries=settings.run.retries,
            resume=resume,
            system_prompt=target_config.system_prompt,
            run_metadata=metadata,
            quality_evaluator=QualityEvaluator(),
            async_quality_evaluator=live_quality if quality_judge is not None else None,
        )
    finally:
        await _close_client(target)
        if judge is not None:
            await _close_client(judge)
        if quality_judge is not None:
            await quality_judge.aclose()


async def _close_client(client: object) -> None:
    close = getattr(client, "aclose", None)
    if close is None:
        return
    value = close()
    if hasattr(value, "__await__"):
        await value


@app.command("aggregate-report")
def aggregate_report(
    results: list[Path] = typer.Option(..., "--results", exists=True, readable=True),
    out: Path = typer.Option(Path("reports/assess"), "--out"),
) -> None:
    """Merge Airt/pytest evaluation-result-v1 JSONL into one report."""
    try:
        json_path, html_path = write_unified_report(results, out)
    except (OSError, ValueError, TypeError) as error:
        _fail(str(error))
    console.print(f"Assess report: {json_path}")
    console.print(f"HTML report: {html_path}")

if __name__ == "__main__":
    app()
















