"""Rich terminal rendering for a completed red-team run."""

from __future__ import annotations

from collections.abc import Sequence

from rich.console import Console
from rich.table import Table
from rich.text import Text

from airt.models import CaseResult, RunMetadata, RunSummary
from airt.report.presentation import (
    case_displays,
    category_label,
    metadata_display,
    severity_label,
)

_LEGACY_METADATA = RunMetadata(
    test_type="Not recorded in original results (legacy JSONL)",
    test_method="Not recorded in original results (legacy JSONL)",
)
_SEVERITY_WEIGHTS = {"critical": 8, "high": 4, "medium": 2, "low": 1}


def _metadata(results: Sequence[CaseResult], metadata: RunMetadata | None) -> RunMetadata:
    if metadata is not None:
        return metadata
    for result in results:
        if result.run_metadata is not None:
            return result.run_metadata
    return _LEGACY_METADATA


def _wire(value: object) -> str:
    return str(getattr(value, "value", value))


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _safe(value: object, console: Console | None = None) -> Text:
    """Build Rich text without markup or unsupported terminal code points."""

    text = str(value)
    encoding = getattr(getattr(console, "file", None), "encoding", None)
    if encoding:
        text = text.encode(encoding, errors="replace").decode(encoding)
    return Text(text)


def _ordered(results: Sequence[CaseResult]) -> list[CaseResult]:
    return sorted(
        results,
        key=lambda result: (
            -_SEVERITY_WEIGHTS.get(_wire(result.case.severity) if result.case else "", 0),
            result.case_id,
        ),
    )


def render_console(
    summary: RunSummary,
    results: Sequence[CaseResult],
    *,
    console: Console | None = None,
    metadata: RunMetadata | None = None,
) -> None:
    """Render a complete Chinese report with readable evidence for every case."""

    output = console or Console()
    denominator = summary.success + summary.fail
    description = metadata_display(_metadata(results, metadata), results)
    output.print("[bold]AI 红队测试报告[/bold]")
    output.print(f"测试类型：{description['test_type']}")
    output.print(f"测试方式：{description['test_method']}")
    output.print(f"测试对象模式：{description['target_profile']}")
    output.print(f"运行模式：{description['run_mode']}；安全 Judge：{description['security_judge_policy']}（实际调用：{description['security_judge_used']}）；质量 Judge：{description['quality_judge_mode']}（实际调用：{description['quality_judge_used']}）")
    output.print(
        f"攻击成功率（ASR）：{_pct(summary.asr)}（{summary.success}/{denominator}）  "
        f"结论不确定：{summary.uncertain}  执行异常：{summary.error}"
    )
    output.print(f"风险分：{summary.risk_score:.1f}/100")

    table = Table(title="按攻击类别汇总")
    for heading in (
        "攻击类别",
        "攻击成功率",
        "攻击成功",
        "攻击未成功",
        "结论不确定",
        "执行异常",
        "总计",
    ):
        table.add_column(heading)
    groups = sorted(summary.by_category.items(), key=lambda item: (item[1].asr, item[0]))
    if not groups:
        table.add_row("（无）", "0.0%", "0", "0", "0", "0", "0")
    else:
        for name, group in groups:
            table.add_row(
                _safe(category_label(name), output),
                _pct(group.asr),
                str(group.success),
                str(group.fail),
                str(group.uncertain),
                str(group.error),
                str(group.total),
            )
    output.print(table)
    output.print("[bold]用例详情[/bold]")

    displays = {item["case_id"]: item for item in case_displays(_ordered(results))}
    for result in _ordered(results):
        item = displays[result.case_id]
        output.print(
            f"[bold]{item['case_id']}[/bold]｜{item['severity']}｜{item['category']}｜"
            f"{item['outcome_label']}｜耗时：{item['latency']}"
        )
        output.print("测试请求：")
        if item["requests"]:
            for request in item["requests"]:
                output.print(f"第 {request['round']} 轮：")
                output.print(_safe(request["content"], output))
        else:
            output.print("未记录测试请求。")
        for context in item["context_messages"]:
            output.print(f"{context['label']}：")
            output.print(_safe(context["content"], output))
        output.print("模型回复：")
        output.print(_safe(item["reply"], output))
        if item["tool_calls"]:
            output.print("工具调用观测：")
            for call in item["tool_calls"]:
                output.print(f"工具：{_safe(call['name'], output)}｜状态：{_safe(call['status'], output)}｜提供方：{_safe(call['provider'], output)}")
                output.print(f"参数：{_safe(call['arguments'], output)}")
                output.print(f"结果：{_safe(call['result'], output)}")
        output.print("判定结论：")
        if item["error"]:
            output.print(f"结论：{item['outcome_label']}")
            output.print(f"异常信息：{_safe(item['error'], output)}")
        elif item["verdict"]:
            verdict = item["verdict"]
            output.print(f"结论：{verdict['outcome']}")
            output.print(f"判定方式：{verdict['source']}")
            output.print(f"置信度：{verdict['confidence']}")
            output.print(f"判定说明：{_safe(verdict['reason'], output)}")
        else:
            output.print("未记录判定结论。")
