from __future__ import annotations

import httpx

from airt.config import AppConfig, DifyTargetConfig, JudgeConfig
from airt.doctor import check_settings, probe_url


def _settings(*, judge: bool = True) -> AppConfig:
    return AppConfig(
        target=DifyTargetConfig(base_url="http://dify.test/v1", api_key="dify-key"),
        judge=(
            JudgeConfig(base_url="http://judge.test/v1", api_key="judge-key", model="judge")
            if judge
            else None
        ),
    )


def test_check_settings_reports_target_and_judge_without_exposing_keys(tmp_path):
    checks = check_settings(_settings(), mode="quality", cases_path=tmp_path / "cases.yaml")

    assert checks["target_api_key"].ok is True
    assert checks["judge_api_key"].ok is True
    assert checks["cases"].ok is False
    assert "dify-key" not in checks["target_api_key"].message
    assert "judge-key" not in checks["judge_api_key"].message


def test_check_settings_skips_judge_for_offline_security_mode(tmp_path):
    checks = check_settings(
        _settings(judge=False),
        mode="security",
        security_judge="off",
        cases_path=tmp_path / "cases.yaml",
    )

    assert checks["judge_config"].ok is True
    assert checks["judge_config"].status == "skip"


def test_probe_url_treats_http_error_as_reachable():
    transport = httpx.MockTransport(lambda request: httpx.Response(404))

    result = probe_url("http://dify.test/v1", transport=transport)

    assert result.ok is True
    assert result.status == "ok"
    assert "HTTP 404" in result.message


def test_probe_url_reports_connection_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    result = probe_url("http://dify.test/v1", transport=httpx.MockTransport(handler))

    assert result.ok is False
    assert result.status == "fail"
    assert "无法连接" in result.message
