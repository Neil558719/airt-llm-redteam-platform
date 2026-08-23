"""pytest fixtures：llm_client / llm_config / app_under_test / record_metric。

插件加载后自动可用；用户项目无需额外 import。
"""

from __future__ import annotations

import os

import pytest

from .apps import apps
from .metrics.tracker import tracker
from .registry import get_default_client, get_default_config


@pytest.fixture(scope="session")
def llm_config():
    """当前运行配置（Config，即裁判/评测客户端的配置）。"""
    return get_default_config()


@pytest.fixture(scope="session")
def llm_client():
    """框架内置评测客户端（裁判）：语义 / 相似度 / Judge / 幻觉判定用。"""
    return get_default_client()


def describe_app_under_test(options) -> str:
    """描述当前被测对象（用于报告头部，便于一眼看出是否误用了 Mock）。"""
    from .apps import apps
    from .config import Config

    name = getattr(options, "llm_app", None) or os.environ.get("LLM_APP")
    if name:
        return f"App[{name}]（注册应用）"
    cfg = Config.from_app_model_options(options)
    if cfg is not None:
        model = cfg.model or "(默认模型)"
        return f"模型[{cfg.provider}/{model}]"
    if apps.default:
        return f"App[{apps.default}]（注册默认）"
    return "Mock（兜底）——未指定被测对象/模型"


@pytest.fixture(scope="session")
def app_under_test(request):
    """被测对象（App under test），支持三种来源，优先级从高到低：

    1. 注册的真实应用：`pytest --app NAME`（或环境变量 `LLM_APP`）——接你自己的 App；
    2. 被测模型：`pytest --app-model <模型> --app-provider <提供商> ...`（或 `LLM_APP_*` 环境变量）
       ——把裸模型直接当被测对象，不用改代码；
    3. 注册的默认应用 / 空 Mock 兜底。
    """
    from .apps import apps
    from .clients import get_client
    from .config import Config

    # 1) 注册的真实应用
    name = getattr(request.config.option, "llm_app", None) or os.environ.get("LLM_APP")
    if name:
        return apps.build(name)
    # 2) 被测模型当被测对象
    app_model_cfg = Config.from_app_model_options(request.config.option)
    if app_model_cfg is not None:
        return get_client(app_model_cfg)
    # 3) 注册的默认应用
    if apps.default:
        return apps.build()
    # 4) 空 Mock 兜底（仅保证跑通）
    from .clients.mock_client import MockLLMClient

    return MockLLMClient(Config(mode="mock"))


@pytest.fixture
def record_metric():
    """把自定义指标写入当前用例记录，供报告看板展示。

    用法：record_metric("bleu", 0.42)
    """

    def _record(name: str, value: float, unit: str = "", meta: str = "") -> None:
        tracker.record_metric(name, value, unit, meta)

    return _record
