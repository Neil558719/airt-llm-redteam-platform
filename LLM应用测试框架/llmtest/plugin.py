"""pytest 插件。

- CLI 选项：--llm-mode / --llm-provider / --llm-model / --llm-base-url / --llm-api-key / --report / --no-report
- 每个用例建立指标记录，结束时写 outcome / duration / 失败信息
- 会话结束聚合指标并生成 HTML 报告
"""

from __future__ import annotations

import os
import traceback

from _pytest.outcomes import Skipped

from .config import Config
from .metrics.tracker import tracker
from .registry import get_default_config, set_default_config


def pytest_addoption(parser):
    group = parser.getgroup("llmtest", "LLM 应用自动化测试框架")
    group.addoption(
        "--llm-mode",
        action="store",
        default=None,
        choices=["mock", "real"],
        help="LLM 运行模式：mock（默认，确定性模拟）/ real（真实模型）。可用环境变量 LLM_TEST_MODE。",
    )
    group.addoption(
        "--llm-provider",
        action="store",
        default=None,
        help=(
            "裁判模型提供商：openai / anthropic，或别名 deepseek / qwen / zhipu / "
            "moonshot / ollama / local。可用 LLM_PROVIDER。"
        ),
    )
    group.addoption(
        "--llm-model", action="store", default=None, help="裁判模型名。可用 LLM_MODEL。"
    )
    group.addoption(
        "--llm-base-url",
        action="store",
        default=None,
        help="裁判模型 OpenAI 兼容接口 base_url。可用 LLM_BASE_URL。",
    )
    group.addoption(
        "--llm-api-key",
        action="store",
        default=None,
        help="裁判模型 API key。可用 LLM_API_KEY（推荐，避免泄漏进命令历史）。",
    )
    group.addoption(
        "--report",
        action="store",
        default=None,
        metavar="PATH",
        help="HTML 报告输出路径（默认 reports/llm_test_report.html）。",
    )
    group.addoption(
        "--no-report", action="store_true", help="不生成 HTML 报告。"
    )
    group.addoption(
        "--no-history",
        action="store_true",
        help="不保留历史报告（默认每次运行会在 reports 下归档一份时间戳副本，并更新 index.html）。",
    )
    group.addoption(
        "--app",
        dest="llm_app",
        action="store",
        default=None,
        metavar="NAME",
        help="被测应用名（register_app 注册，如 --app cs）。不传则用注册的默认应用；可用 LLM_APP。",
    )
    # ---- 被测模型：把裸模型直接当被测对象（不用注册 App）----
    group.addoption(
        "--app-model",
        dest="app_model",
        action="store",
        default=None,
        help="被测模型名（如 deepseek-chat / gpt-4o / claude-sonnet-5）。可用 LLM_APP_MODEL。",
    )
    group.addoption(
        "--app-provider",
        dest="app_provider",
        action="store",
        default=None,
        help="被测模型提供商（同裁判，支持别名）。可用 LLM_APP_PROVIDER。",
    )
    group.addoption(
        "--app-base-url",
        dest="app_base_url",
        action="store",
        default=None,
        help="被测模型 OpenAI 兼容 base_url。可用 LLM_APP_BASE_URL。",
    )
    group.addoption(
        "--app-api-key",
        dest="app_api_key",
        action="store",
        default=None,
        help="被测模型 API key。可用 LLM_APP_API_KEY。",
    )


def pytest_configure(config):
    cfg = Config.from_pytest_options(config.option)
    set_default_config(cfg)
    config.llmtest_config = cfg


def pytest_runtest_setup(item):
    tracker.begin(item.nodeid, _display_name(item.name))


def _display_name(name: str) -> str:
    """pytest 会把参数化用例里的非 ASCII 参数转义成 \\uXXXX，这里还原便于报告阅读。"""
    import re

    return re.sub(
        r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), name
    )


def pytest_runtest_makereport(item, call):
    rec = tracker.by_nodeid(item.nodeid)
    if rec is None:
        return
    if call.excinfo is not None:
        _record_failure(rec, call)
    if call.when == "call":
        rec.duration = call.duration
        if call.excinfo is None:
            rec.outcome = "passed"
    elif call.when == "teardown":
        # setup 阶段即被跳过/报错时，call 不会执行，outcome 已在此前的 setup 分支写入
        if rec.outcome == "pending":
            rec.outcome = "passed"
        tracker.finish(item.nodeid, rec.outcome, rec.duration, rec.failure, rec.traceback)


def _record_failure(rec, call) -> None:
    exc = call.excinfo
    rec.failure = f"{exc.type.__name__}: {exc.value}" if exc.value else exc.type.__name__
    rec.traceback = "".join(
        traceback.format_exception(exc.type, exc.value, exc.tb)
    )
    if exc.type is Skipped:
        rec.outcome = "skipped"
    elif call.when == "setup":
        rec.outcome = "error"
    else:
        rec.outcome = "failed"


def pytest_sessionfinish(session, exitstatus):
    if getattr(session.config.option, "no_report", False):
        return
    cfg = get_default_config()
    report_path = getattr(session.config.option, "report", None) or cfg.report_path
    from .fixtures import describe_app_under_test

    env = {
        "被测对象": describe_app_under_test(session.config.option),
        "裁判": cfg.describe(),
        "裁判模型": cfg.model or "默认",
        "报告路径": report_path,
    }
    summary = tracker.summarize(env)
    from .reporting.html_report import write_report_with_history

    try:
        latest, archive = write_report_with_history(
            summary,
            tracker.records,
            report_path,
            keep_history=not getattr(session.config.option, "no_history", False),
        )
        msg = f"\n[llmtest] 质量报告已生成：{latest}"
        if archive:
            msg += f"\n[llmtest] 历史归档：{archive}（历史索引：{os.path.join(os.path.dirname(latest), 'index.html')}）"
        print(f"{msg}\n")
    except Exception as exc:  # 报告失败不应让测试会话崩溃
        print(f"\n[llmtest] 报告生成失败：{exc}\n")


# 把 fixtures 导入插件命名空间，pytest 会自动注册为可用 fixture
from .fixtures import (  # noqa: E402,F401
    app_under_test,
    llm_client,
    llm_config,
    record_metric,
)
