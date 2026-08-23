"""进程级默认配置与客户端单例。

pytest 插件在 `pytest_configure` 时调用 `set_default_config`；测试和断言函数
通过 `get_default_client` 拿到同一个客户端，无需显式传参。
"""

from __future__ import annotations

from typing import Optional

from .clients import get_client
from .config import Config

_default_config: Optional[Config] = None
_default_client = None


def set_default_config(config: Config) -> None:
    """设置默认配置并重建默认客户端（幂等）。"""
    global _default_config, _default_client
    _default_config = config
    _default_client = get_client(config)


def get_default_config() -> Config:
    global _default_config
    if _default_config is None:
        _default_config = Config.from_env()
    return _default_config


def get_default_client():
    """惰性构造并返回默认客户端。"""
    if _default_client is None:
        set_default_config(get_default_config())
    return _default_client
