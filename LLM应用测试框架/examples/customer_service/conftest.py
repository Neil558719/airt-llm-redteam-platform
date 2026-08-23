"""接入真实客服 App 的示例配置。

运行（在本目录）：
    export CS_BASE_URL=https://your-service.example.com
    export CS_API_KEY=sk-xxx
    pytest                        # 用默认注册的 "cs" 应用（被测对象）
    pytest --app cs               # 显式指定被测对象（等价）
    pytest --app cs --llm-model gpt-4o   # 同时切换裁判模型
"""

import os

from llmtest.apps import register_app

from .adapter import CustomerServiceApp


@register_app("cs", default=True)
def _build_cs_app():
    return CustomerServiceApp(
        base_url=os.environ["CS_BASE_URL"],
        api_key=os.environ.get("CS_API_KEY", ""),
    )
