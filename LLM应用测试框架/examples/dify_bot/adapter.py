"""Dify 客服机器人适配器：把 Dify 应用包成框架认识的"被测对象"。

被测对象 = 你在 Dify 上搭的客服机器人（自带知识库 RAG + 生成模型）。
裁判 = 框架的 llm_client（--llm-* 独立模型），两者分离。

为什么它最贴近企业场景：
- Dify 的对话接口天然返回 answer + 检索到的知识片段（retriever_resources）；
- 把检索片段映射成 AppResponse.sources，幻觉检测就能用"机器人真实看到的知识"
  核对回答，而不是测试方编的资料（生产级做法，见术语手册 4.4「上下文」）。

环境变量：
  DIFY_BASE_URL   Dify API 地址，默认 https://api.dify.ai/v1（云版）；
                  本地 Docker 部署用 http://localhost/v1
  DIFY_API_KEY    Dify 应用密钥（Dify 控制台 → 应用 → 访问 API 页生成，形如 app-xxx）

用法（PowerShell，在项目根目录；bash 把 $env: 换成 export）：
  $env:DIFY_BASE_URL = "https://api.dify.ai/v1"
  $env:DIFY_API_KEY  = "app-xxx"
  pytest examples/dify_bot/ --app dify --llm-mode real --llm-provider openai --llm-model gpt-5.6-sol --llm-api-key $env:DEEPSEEK_API_KEY
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from llmtest import AppResponse, register_app, track_latency


class DifyBotApp:
    """Dify 客服机器人适配器：ask(question) -> AppResponse(answer, sources)。"""

    def __init__(self, base_url: str | None = None, api_key: str = ""):
        self.base_url = (
            base_url or os.environ.get("DIFY_BASE_URL", "https://api.dify.ai/v1")
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("DIFY_API_KEY", "")
        self.last_conversation_id = ""

    def ask(
        self,
        question: str,
        user_id: str = "test-user",
        conversation_id: str = "",
    ) -> AppResponse:
        """调 Dify chat-messages 接口（blocking 模式），返回回答 + 检索来源。

        conversation_id 用于多轮会话：把上一轮返回的会话 id 传进来可维持上下文；
        调用后可从 self.last_conversation_id 取新一轮会话 id 继续追问。
        """
        payload = {
            "inputs": {},
            "query": question,
            "response_mode": "blocking",
            "conversation_id": conversation_id,
            "user": user_id,
        }
        with track_latency():  # 真实调用耗时自动进看板「平均延迟」
            data = self._chat(payload)
        self.last_conversation_id = str(data.get("conversation_id", ""))
        return AppResponse(
            answer=str(data.get("answer", "")),
            sources=self._extract_sources(data),
        )

    # ------------------------------------------------------------------

    def _chat(self, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}/chat-messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            # Dify 真实生成可能较慢（检索 + 模型生成），放宽到 300s，避免慢响应被误判超时
            with urllib.request.urlopen(request, timeout=300) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"Dify API 返回 {exc.code}: {body[:500]}") from exc

    @staticmethod
    def _extract_sources(data: dict) -> list[str]:
        """取 Dify 检索来源片段文本。

        Dify 不同版本返回位置有差异：新版在顶层 retriever_resources，
        旧版在 metadata.retriever_resources；片段字段通常是 content。
        """
        resources = data.get("retriever_resources")
        if resources is None:
            resources = (data.get("metadata") or {}).get("retriever_resources")
        if not resources:
            return []
        contents = []
        for r in resources:
            content = r.get("content") or r.get("segment_content") or r.get("segment")
            if content:
                contents.append(str(content))
        return contents


@register_app("dify")
def _build_dify() -> DifyBotApp:
    return DifyBotApp()
