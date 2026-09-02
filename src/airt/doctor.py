"""Local, side-effect-light preflight checks for Airt runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from airt.config import AppConfig


@dataclass(frozen=True)
class CheckResult:
    """One human-readable diagnostic result."""

    ok: bool
    message: str
    status: str = "ok"


def _credential_result(value: str | None, label: str) -> CheckResult:
    if value:
        return CheckResult(True, f"{label} 已配置")
    return CheckResult(False, f"{label} 未配置", "fail")


def check_settings(
    settings: AppConfig,
    *,
    mode: str,
    cases_path: Path,
    security_judge: str | None = None,
    target_profile: str | None = None,
) -> dict[str, CheckResult]:
    """Check local configuration without creating clients or sending requests."""

    target = settings.resolve_target(target_profile)
    mode_name = mode.casefold()
    requires_judge = mode_name in {"quality", "release"} or (
        mode_name == "security" and (security_judge or "always") != "off"
    )
    cases_ok = cases_path.exists() and (cases_path.is_file() or cases_path.is_dir())
    checks: dict[str, CheckResult] = {
        "config": CheckResult(True, "配置文件已加载"),
        "target_api_key": _credential_result(target.api_key, "目标 API Key"),
        "cases": CheckResult(
            cases_ok,
            "测试用例路径有效" if cases_ok else f"测试用例路径不存在：{cases_path}",
            "ok" if cases_ok else "fail",
        ),
    }
    if requires_judge:
        checks["judge_config"] = CheckResult(
            settings.judge is not None,
            "Judge 配置已加载" if settings.judge is not None else "Judge 配置未加载",
            "ok" if settings.judge is not None else "fail",
        )
        checks["judge_api_key"] = _credential_result(
            settings.judge.api_key if settings.judge else None, "Judge API Key"
        )
    else:
        checks["judge_config"] = CheckResult(True, "当前档位关闭 Judge", "skip")
        checks["judge_api_key"] = CheckResult(True, "当前档位关闭 Judge", "skip")
    return checks


def probe_url(
    url: str,
    *,
    timeout: float = 5.0,
    transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
) -> CheckResult:
    """Probe an endpoint's reachability; HTTP error responses still prove reachability."""

    try:
        with httpx.Client(timeout=timeout, transport=transport, follow_redirects=True) as client:
            response = client.get(url)
    except (httpx.HTTPError, OSError) as error:
        return CheckResult(False, f"无法连接（{error.__class__.__name__}）", "fail")
    return CheckResult(True, f"可访问（HTTP {response.status_code}）", "ok")
