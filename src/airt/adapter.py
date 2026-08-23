"""OpenAI-compatible asynchronous target adapter."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from airt.config import TargetConfig
from airt.models import Message, Reply


class Target(Protocol):
    """A target that accepts a conversation and returns one normalized reply."""

    async def chat(self, messages: list[Message]) -> Reply:
        """Send a conversation to the target."""


class RetryableTargetError(RuntimeError):
    """An error that the runner may retry safely."""


class TargetResponseError(RuntimeError):
    """A non-retryable target response or malformed successful payload."""


class OpenAICompatTarget:
    """Target backed by an OpenAI-compatible chat-completions API."""

    _PROTECTED_PAYLOAD_KEYS = frozenset({"model", "messages"})

    def __init__(
        self,
        config: TargetConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        protected = self._PROTECTED_PAYLOAD_KEYS.intersection(config.extra_body)
        if protected:
            names = ", ".join(sorted(protected))
            raise ValueError(f"extra_body cannot override protected fields: {names}")
        self._config = config
        self._endpoint = f"{config.base_url.rstrip('/')}/chat/completions"
        self._client = httpx.AsyncClient(timeout=config.timeout, transport=transport)

    async def chat(self, messages: list[Message]) -> Reply:
        """Post messages and normalize the first assistant choice."""
        payload = {
            **self._config.extra_body,
            "model": self._config.model,
            "messages": [message.model_dump() for message in messages],
        }
        try:
            response = await self._client.post(
                self._endpoint,
                headers={"Authorization": f"Bearer {self._config.api_key}"},
                json=payload,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise RetryableTargetError("target transport failed") from error

        if response.status_code in {408, 429} or 500 <= response.status_code <= 599:
            raise RetryableTargetError(f"target returned HTTP {response.status_code}")
        if response.is_error:
            raise TargetResponseError(f"target returned HTTP {response.status_code}")

        try:
            data: dict[str, Any] = response.json()
        except ValueError as error:
            raise TargetResponseError("target returned invalid JSON") from error

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise TargetResponseError("target response is missing choices[0].message.content") from error
        if not isinstance(content, str):
            raise TargetResponseError("target response content must be a string")

        usage = data.get("usage", {})
        if not isinstance(usage, dict):
            raise TargetResponseError("target response usage must be an object")

        return Reply(text=content, usage=usage, raw=data)

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
