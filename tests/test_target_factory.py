from __future__ import annotations

from airt.target_registry import RegisteredTarget, build_registered_target
from airt.dify_adapter import DifyTarget


def test_target_factory_builds_dify_chatflow_config_without_network():
    target = build_registered_target(RegisteredTarget(
        provider="dify", app_type="advanced-chat", base_url="http://dify/v1", api_key="secret",
        response_mode="streaming", capture_tool_calls=True,
    ))
    assert isinstance(target, DifyTarget)
    assert target._config.response_mode == "streaming"
    assert target._config.capture_tool_calls is True


def test_target_registry_hides_key_from_description():
    item = RegisteredTarget(provider="fastgpt", base_url="http://fastgpt", api_key="secret", app_id="app")
    assert "secret" not in item.description()
    assert "fastgpt" in item.description()
