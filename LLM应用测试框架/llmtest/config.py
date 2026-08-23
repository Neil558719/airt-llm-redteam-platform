"""配置：环境变量 + pytest 参数统一收敛为 Config。

优先级：pytest 命令行参数 > 环境变量 > 默认值。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional

DEFAULT_REPORT_PATH = "reports/llm_test_report.html"

# 提供商别名表：把友好的名字解析成 (客户端 provider, 默认 base_url)。
# "openai" 兼容 = 可接 OpenAI / DeepSeek / 通义千问 / 智谱 / Moonshot / Ollama / vLLM 本地部署等。
PROVIDER_PRESETS: Dict[str, Dict[str, Optional[str]]] = {
    "openai": {"provider": "openai", "base_url": None},
    "anthropic": {"provider": "anthropic", "base_url": None},
    "deepseek": {"provider": "openai", "base_url": "https://api.deepseek.com"},
    "qwen": {"provider": "openai", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
    "zhipu": {"provider": "openai", "base_url": "https://open.bigmodel.cn/api/paas/v4"},
    "moonshot": {"provider": "openai", "base_url": "https://api.moonshot.cn/v1"},
    "ollama": {"provider": "openai", "base_url": "http://localhost:11434/v1"},
    "local": {"provider": "openai", "base_url": "http://localhost:8000/v1"},  # vLLM 等本地部署
}


@dataclass
class Config:
    """框架运行配置。"""

    mode: str = "mock"                # mock | real
    provider: str = "openai"          # openai | anthropic（真实模式）
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    embedding_model: Optional[str] = None
    mock_responses: Dict[str, Any] = field(default_factory=dict)
    report_path: str = DEFAULT_REPORT_PATH
    mock_latency_ms: float = 8.0      # Mock 模式模拟的响应延迟（看板演示用；设为 0 关闭）

    # ---- 环境变量名映射 ----
    _ENV = {
        "mode": "LLM_TEST_MODE",
        "provider": "LLM_PROVIDER",
        "api_key": "LLM_API_KEY",
        "base_url": "LLM_BASE_URL",
        "model": "LLM_MODEL",
        "embedding_model": "LLM_EMBEDDING_MODEL",
        "report_path": "LLM_REPORT_PATH",
    }

    @classmethod
    def from_env(cls, **overrides) -> "Config":
        """从环境变量构造，支持字段级覆盖。"""
        kwargs = {}
        for field_name, env_name in cls._ENV.items():
            val = os.environ.get(env_name)
            if val:
                kwargs[field_name] = val
        kwargs.update(overrides)
        return cls(**kwargs)

    @classmethod
    def from_pytest_options(cls, options: Any) -> "Config":
        """从 pytest 配置对象构造（插件传入）。未指定项回退到环境变量。"""
        overrides: Dict[str, Any] = {}
        for attr, field_name in (
            ("llm_mode", "mode"),
            ("llm_provider", "provider"),
            ("llm_api_key", "api_key"),
            ("llm_base_url", "base_url"),
            ("llm_model", "model"),
            ("report", "report_path"),
        ):
            value = getattr(options, attr, None)
            if value is not None:
                overrides[field_name] = value
        cfg = cls.from_env(**overrides)
        if cfg.mode not in ("mock", "real"):
            raise ValueError(f"LLM_TEST_MODE 必须为 mock 或 real，当前: {cfg.mode!r}")
        return cfg

    def describe(self) -> str:
        """一句话描述运行环境，用于报告头部。"""
        if self.mode == "mock":
            return "Mock 模式（确定性模拟，无需 API key）"
        provider_note = {"openai": "OpenAI 兼容", "anthropic": "Anthropic"}.get(
            self.provider, self.provider
        )
        model = self.model or "(默认模型)"
        return f"真实模式 · {provider_note} · {model}"

    # ---- 被测模型（App under test = 裸模型）----

    _APP_MODEL_ENV = {
        "mode": "LLM_APP_MODE",
        "provider": "LLM_APP_PROVIDER",
        "model": "LLM_APP_MODEL",
        "base_url": "LLM_APP_BASE_URL",
        "api_key": "LLM_APP_API_KEY",
    }

    @classmethod
    def from_app_model_options(cls, options: Any) -> Optional["Config"]:
        """从 `--app-*` 参数 / `LLM_APP_*` 环境变量构造"被测模型"配置。

        全部未给时返回 None（表示不使用"模型当被测对象"）。
        """
        overrides: Dict[str, str] = {}
        for field_name, env_name in cls._APP_MODEL_ENV.items():
            attr = f"app_{field_name}"
            value = getattr(options, attr, None) or os.environ.get(env_name)
            if value:
                overrides[field_name] = value
        if not overrides:
            return None
        if "mode" not in overrides:
            overrides["mode"] = "real"  # 指定了被测模型，默认按真实模型
        return cls(**overrides)

    # ---- 提供商别名解析 ----

    def normalize(self) -> "Config":
        """把提供商别名（deepseek/qwen/zhipu/…）解析为具体客户端提供商并补默认 base_url。"""
        if self.mode == "mock":
            return self
        preset = PROVIDER_PRESETS.get(self.provider)
        if preset is None:
            raise ValueError(
                f"未知提供商 {self.provider!r}。可选: {', '.join(sorted(PROVIDER_PRESETS))}"
            )
        return replace(
            self,
            provider=preset["provider"],
            base_url=self.base_url or preset["base_url"],
        )
