"""被测应用注册表：让"被测对象"可配置、可用一条命令切换。

- 用 `@register_app("名字")` 注册被测应用的构建器（你的客服 App、Chatbot、RAG 助手…）
- pytest 的 `--app NAME`（或环境变量 `LLM_APP`）选择用哪个被测对象，测试代码不用改
- 不传 --app 时用注册的默认应用
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

AppBuilder = Callable[[], object]


class AppRegistry:
    """名字 → 应用构建器的映射，维护一个默认应用。"""

    def __init__(self) -> None:
        self._builders: Dict[str, AppBuilder] = {}
        self._default: Optional[str] = None

    def register(self, name: str, builder: AppBuilder, *, default: bool = False) -> None:
        self._builders[name] = builder
        if default or self._default is None:
            self._default = name

    @property
    def default(self) -> Optional[str]:
        return self._default

    def names(self):
        return sorted(self._builders)

    def build(self, name: Optional[str] = None) -> object:
        """构建指定应用（默认名），返回它的实例。"""
        key = name or self._default
        if key is None or key not in self._builders:
            available = ", ".join(self.names()) or "(无)"
            raise KeyError(
                f"未注册的被测应用: {key!r}。可用 --app 或 LLM_APP 选择，已注册: {available}"
            )
        return self._builders[key]()


# 进程级单例注册表
apps = AppRegistry()


def register_app(name: str, *, default: bool = False):
    """注册一个被测应用构建器。

    用法：
        @register_app("cs")
        def _build_cs():
            return CustomerServiceApp(...)
    """

    def decorator(builder: AppBuilder) -> AppBuilder:
        apps.register(name, builder, default=default)
        return builder

    return decorator
