from __future__ import annotations

import pytest

from airt.target_registry import TargetRegistryError, load_target_registry


def test_load_registry_expands_distinct_environment_variables(tmp_path, monkeypatch):
    config = tmp_path / "targets.yaml"
    config.write_text(
        """
targets:
  airt_dify_chatflow:
    provider: dify
    app_type: advanced-chat
    base_url: ${AIRT_DIFY_CHATFLOW_BASE_URL}
    api_key: ${AIRT_DIFY_CHATFLOW_API_KEY}
    response_mode: streaming
    capture_tool_calls: true
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("AIRT_DIFY_CHATFLOW_BASE_URL", "http://airt-dify/v1")
    monkeypatch.setenv("AIRT_DIFY_CHATFLOW_API_KEY", "airt-chatflow-secret")

    registry = load_target_registry(config)

    chatflow = registry.resolve("airt_dify_chatflow")
    assert chatflow.app_type == "advanced-chat"
    assert chatflow.capture_tool_calls is True


def test_resolve_unknown_target_lists_available_names(tmp_path, monkeypatch):
    config = tmp_path / "targets.yaml"
    config.write_text(
        "targets:\n  one:\n    provider: dify\n    base_url: http://example\n    api_key: secret\n",
        encoding="utf-8",
    )

    registry = load_target_registry(config)

    with pytest.raises(TargetRegistryError, match="one"):
        registry.resolve("missing")


def test_missing_environment_variable_is_reported_without_echoing_secret_name(tmp_path):
    config = tmp_path / "targets.yaml"
    config.write_text(
        "targets:\n  one:\n    provider: dify\n    base_url: ${MISSING_BASE_URL}\n    api_key: secret\n",
        encoding="utf-8",
    )

    with pytest.raises(TargetRegistryError, match="MISSING_BASE_URL"):
        load_target_registry(config)
