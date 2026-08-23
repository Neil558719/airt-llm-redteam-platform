"""客户端工厂。"""

from __future__ import annotations

from typing import Optional

from ..config import Config
from .base import LLMClient
from .mock_client import MockLLMClient


def get_client(config: Optional[Config] = None) -> LLMClient:
    """按配置构造客户端。mock → MockLLMClient；real → 按 provider 分派（自动解析别名）。

    提供商别名见 config.PROVIDER_PRESETS：deepseek / qwen / zhipu / moonshot / ollama / local。
    """
    config = config or Config.from_env()
    if config.mode == "mock":
        return MockLLMClient(config)
    config = config.normalize()
    if config.provider == "anthropic":
        from .anthropic_client import AnthropicClient

        return AnthropicClient(config)
    from .openai_client import OpenAIClient

    return OpenAIClient(config)


__all__ = ["get_client", "LLMClient", "MockLLMClient"]
