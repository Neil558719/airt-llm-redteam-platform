"""FastGPT 客服机器人适配器：把 FastGPT 应用包成框架认识的"被测对象"。

被测对象 = 你在 FastGPT 上搭的知识库客服（知识库检索 + LLM 生成）；
裁判 = 框架的 llm_client（--llm-*，独立模型），两者分离。

FastGPT 用 OpenAI 兼容接口（POST {base}/api/v1/chat/completions）。

环境变量：
  FASTGPT_BASE_URL   默认 http://localhost:3000（本地 Docker）；官方云 fastgpt.in 用对应地址
  FASTGPT_API_KEY    FastGPT API 密钥（控制台生成）
  FASTGPT_MODEL      默认 fastgpt

说明：
- sources：FastGPT 的 OpenAI 兼容接口**默认不直接返回引用**，这里做多路径宽松解析；
  若拿不到，AppResponse.sources 为空 → 幻觉检测用例自动跳过（其余用例不受影响）。
  后续可按 probe 实测结果补充（如通过 chat 历史接口取引用）。
- 多轮：FastGPT 用 chatId 维持会话，适配器把 conversation_id 映射到 chatId，
  并暴露 last_conversation_id（与 Dify 适配器接口一致，测试用例可无缝复用）。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from llmtest import AppResponse, register_app, track_latency


class FastGPTApp:
    """FastGPT 客服机器人适配器：ask(question) -> AppResponse(answer, sources)。"""

    def __init__(self, base_url: str | None = None, api_key: str = "", model: str = "fastgpt", app_id: str = ""):
        self.base_url = (
            base_url or os.environ.get("FASTGPT_BASE_URL", "http://localhost:3000")
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("FASTGPT_API_KEY", "")
        self.model = model or os.environ.get("FASTGPT_MODEL", "fastgpt")
        # FastGPT 需要指定要调用的 Agent/应用 ID（self-host 必须）
        self.app_id = app_id or os.environ.get("FASTGPT_APP_ID", "")
        self.last_conversation_id = ""

    def ask(
        self,
        question: str,
        user_id: str = "test-user",
        conversation_id: str = "",
    ) -> AppResponse:
        """调 FastGPT OpenAI 兼容接口（非流式），返回回答 + 检索来源。

        conversation_id 对应 FastGPT 的 chatId：传入可维持多轮上下文；
        调用后从 self.last_conversation_id 取新一轮会话 id 继续追问。
        """
        # FastGPT v1 兼容接口：model 固定为空字符串，用 body.appId 指定要调用的 Agent
        payload: dict = {
            "model": "",
            "appId": self.app_id,
            "messages": [{"role": "user", "content": question}],
            "stream": False,
            "user": user_id,
        }
        if conversation_id:
            payload["chatId"] = conversation_id
        with track_latency():  # 真实调用耗时自动进看板「平均延迟」
            data = self._chat(payload)
        self.last_conversation_id = str(
            data.get("chatId") or data.get("id") or ""
        )
        return AppResponse(
            answer=self._extract_answer(data),
            sources=self._extract_sources(data),
        )

    # ------------------------------------------------------------------

    def _chat(self, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}/api/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            # FastGPT 真实生成可能较慢，放宽到 180s
            with urllib.request.urlopen(request, timeout=180) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"FastGPT API 返回 {exc.code}: {body[:500]}") from exc

    @staticmethod
    def _extract_answer(data: dict) -> str:
        """OpenAI 兼容响应里取回答文本（多路径容错）。"""
        try:
            return str(data["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError):
            return str(data.get("answer") or data.get("output") or "")

    @staticmethod
    def _extract_sources(data: dict) -> list[str]:
        """尽力解析 FastGPT 返回的引用片段（不同版本/接口位置有差异）。

        已知的常见位置：
        - choices[0].message.sources / FastGPT
        - data.sources / data.citation / data.references
        - responseData 数组里 type=kbSearch 的 content
        均无则返回空列表（幻觉检测用例会跳过）。
        """
        candidates: list[object] = []
        try:
            msg = data.get("choices", [{}])[0].get("message", {})
            for key in ("sources", "citations", "references", "FastGPT"):
                if isinstance(msg.get(key), list):
                    candidates.extend(msg[key])
        except (IndexError, TypeError, AttributeError):
            pass
        for key in ("sources", "citation", "citations", "references"):
            val = data.get(key)
            if isinstance(val, list):
                candidates.extend(val)
        # responseData（FastGPT 内部引用结构）
        rd = data.get("responseData")
        if isinstance(rd, list):
            for item in rd:
                if isinstance(item, dict) and str(item.get("type", "")) == "kbSearch":
                    c = item.get("content")
                    if c:
                        candidates.append(c)

        contents: list[str] = []
        for c in candidates:
            if isinstance(c, str):
                contents.append(c)
            elif isinstance(c, dict):
                for k in ("content", "text", "quote", "answer"):
                    v = c.get(k)
                    if v:
                        contents.append(str(v))
                        break
        return contents


@register_app("fastgpt")
def _build_fastgpt() -> FastGPTApp:
    return FastGPTApp()
