"""客服 App 适配器：把真实客服应用包成框架认识的"被测对象"。

被测对象 = 你的 App（可能有自己的模型 + 业务逻辑 + 知识库）。
裁判 = 框架的 llm_client（独立模型，评估质量）。

本适配器把"调用线上客服接口"包成 `ask(question) -> AppResponse`，
框架的断言就能直接复用（语义 / 相似度 / Schema / Judge / 幻觉检测）。

按你的实际情况调整：
- 请求路径 / 请求字段：现在假设 POST {base}/chat，body={"question": ..., "user_id": ...}
- 响应字段：现在假设 data["reply"] 是回答、data["citations"] 是检索依据（sources）

用标准库 urllib 实现，零额外依赖；你的真实项目里换成 requests / httpx 即可。
"""

from __future__ import annotations

import json
import urllib.request

from llmtest import AppResponse, track_latency


class CustomerServiceApp:
    """被测客服 App 的 HTTP 适配器。"""

    def __init__(self, base_url: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def ask(self, question: str, user_id: str | None = None) -> AppResponse:
        """调用客服接口，返回 answer + sources（检索依据）。"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat",
            data=json.dumps(
                {"question": question, "user_id": user_id}
            ).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        # track_latency：把真实调用的耗时自动写进报告看板"平均延迟"
        with track_latency():
            with urllib.request.urlopen(request, timeout=30) as resp:
                body = resp.read()
        data = json.loads(body.decode("utf-8"))
        return AppResponse(
            answer=str(data.get("reply", "")),
            sources=[str(s) for s in data.get("citations", [])],
        )
