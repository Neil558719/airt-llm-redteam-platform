"""Native blocking Dify Chat API target adapter."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from airt.adapter import RetryableTargetError, TargetResponseError
from airt.config import DifyTargetConfig
from airt.models import Message, Reply, ToolCall


def _strip_think_blocks(text: str) -> str:
    """Remove model reasoning blocks before exposing an answer to the user."""
    cleaned = re.sub(r"<think\b[^>]*>.*?</think\s*>", "", text, flags=re.IGNORECASE | re.DOTALL)
    return cleaned.strip()


class DifyTarget:
    """Target backed by Dify's native blocking ``/chat-messages`` API."""

    _PROTECTED_PAYLOAD_KEYS = frozenset(
        {"query", "inputs", "response_mode", "user", "conversation_id"}
    )

    def __init__(
        self,
        config: DifyTargetConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        protected = self._PROTECTED_PAYLOAD_KEYS.intersection(config.extra_body)
        if protected:
            names = ", ".join(sorted(protected))
            raise ValueError(f"extra_body cannot override protected fields: {names}")
        self._config = config
        self._endpoint = f"{config.base_url.rstrip('/')}/chat-messages"
        self._client = httpx.AsyncClient(timeout=config.timeout, transport=transport)
        self._conversation_ids: dict[str, str] = {}

    async def chat_case(self, case_id: str, messages: list[Message]) -> Reply:
        """Send the current query, retaining Dify state for this case only."""

        query = self._latest_user_query(messages)
        payload: dict[str, Any] = {
            **self._config.extra_body,
            "inputs": self._config.inputs,
            "query": query,
            "response_mode": self._config.response_mode,
            "user": f"{self._config.user_prefix}:{case_id}",
        }
        conversation_id = self._conversation_ids.get(case_id)
        if conversation_id is not None:
            payload["conversation_id"] = conversation_id

        try:
            if self._config.response_mode == "streaming":
                async with self._client.stream(
                    "POST",
                    self._endpoint,
                    headers={"Authorization": f"Bearer {self._config.api_key}"},
                    json=payload,
                ) as response:
                    self._raise_for_status(response)
                    reply = await self._read_stream(response)
            else:
                response = await self._client.post(
                    self._endpoint,
                    headers={"Authorization": f"Bearer {self._config.api_key}"},
                    json=payload,
                )
                self._raise_for_status(response)
                reply = self._read_blocking(response)
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise RetryableTargetError("target transport failed") from error

        returned_conversation_id = (
            self._conversation_id(reply.raw)
            if self._config.response_mode == "blocking"
            else self._conversation_id(
                (reply.raw or {}).get("message_end")
                or (reply.raw or {}).get("workflow_finished")
            )
        )
        self._conversation_ids[case_id] = returned_conversation_id
        return reply

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code in {408, 429} or 500 <= response.status_code <= 599:
            raise RetryableTargetError(f"target returned HTTP {response.status_code}")
        if response.is_error:
            raise TargetResponseError(f"target returned HTTP {response.status_code}")

    def _read_blocking(self, response: httpx.Response) -> Reply:
        try:
            data: dict[str, Any] = response.json()
        except ValueError as error:
            raise TargetResponseError("target returned invalid JSON") from error
        if not isinstance(data, dict):
            raise TargetResponseError("target response must be an object")
        answer = data.get("answer")
        if not isinstance(answer, str) or not answer:
            raise TargetResponseError("target response answer must be a non-empty string")
        self._conversation_id(data)
        return Reply(text=_strip_think_blocks(answer), usage=self._extract_usage(data), raw=data, sources=self._extract_sources(data))

    async def _read_stream(self, response: httpx.Response) -> Reply:
        answer_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        events: list[dict[str, Any]] = []
        message_end: dict[str, Any] | None = None
        workflow_finished: dict[str, Any] | None = None
        conversation_id: str | None = None
        event_name: str | None = None
        data_lines: list[str] = []

        async for line in response.aiter_lines():
            if line == "":
                event = self._parse_sse_event(event_name, data_lines)
                event_name = None
                data_lines = []
                if event is None:
                    continue
                events.append(event)
                kind = event.get("event")
                if kind in {"message", "agent_message"}:
                    fragment = event.get("answer")
                    if isinstance(fragment, str):
                        answer_parts.append(fragment)
                elif kind == "agent_thought":
                    tool_call = self._tool_call_from_event(event)
                    if tool_call is not None:
                        tool_calls.append(tool_call)
                elif kind == "node_finished":
                    tool_call = self._tool_call_from_workflow_node(event)
                    if tool_call is not None:
                        tool_calls.append(tool_call)
                elif kind == "message_end":
                    message_end = event
                elif kind == "workflow_finished":
                    workflow_finished = event
                    if isinstance(event.get("conversation_id"), str):
                        conversation_id = event["conversation_id"]
                elif kind in {"error", "message_error"}:
                    raise TargetResponseError("target streaming response reported an error")
                continue
            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").lstrip())

        # A final SSE event is permitted to omit the trailing blank separator.
        event = self._parse_sse_event(event_name, data_lines)
        if event is not None:
            events.append(event)
            if event.get("event") == "message_end":
                message_end = event
            elif event.get("event") == "workflow_finished":
                workflow_finished = event
                if isinstance(event.get("conversation_id"), str):
                    conversation_id = event["conversation_id"]
            elif event.get("event") == "agent_thought":
                tool_call = self._tool_call_from_event(event)
                if tool_call is not None:
                    tool_calls.append(tool_call)
            elif event.get("event") == "node_finished":
                tool_call = self._tool_call_from_workflow_node(event)
                if tool_call is not None:
                    tool_calls.append(tool_call)

        if message_end is None and workflow_finished is None:
            raise TargetResponseError("target streaming response is missing message_end or workflow_finished")
        answer = "".join(answer_parts)
        if not answer and isinstance(workflow_finished, dict):
            # Dify Chatflow puts workflow outputs and usage under event.data.
            workflow_data = workflow_finished.get("data")
            if not isinstance(workflow_data, dict):
                workflow_data = workflow_finished
            outputs = workflow_data.get("outputs")
            if isinstance(outputs, dict):
                candidate = outputs.get("answer") or outputs.get("text")
                if isinstance(candidate, str):
                    answer = candidate
        if not answer:
            raise TargetResponseError("target streaming response answer must be a non-empty string")
        terminal = message_end or workflow_finished or {}
        if self._config.response_mode == "streaming" and workflow_finished is not None:
            returned_conversation_id = conversation_id or terminal.get("conversation_id")
        else:
            returned_conversation_id = terminal.get("conversation_id")
        self._conversation_id({"conversation_id": returned_conversation_id})
        usage_data = terminal.get("data") if isinstance(terminal.get("data"), dict) else terminal
        usage = self._extract_usage(usage_data)
        return Reply(
            text=_strip_think_blocks(answer),
            usage=usage,
            raw={"mode": "streaming", "message_end": message_end, "workflow_finished": workflow_finished, "events": events},
            sources=self._extract_sources(message_end or workflow_finished or {}),
            tool_calls=tool_calls if self._config.capture_tool_calls else [],
        )

    @staticmethod
    def _parse_sse_event(event_name: str | None, data_lines: list[str]) -> dict[str, Any] | None:
        if not data_lines:
            return None
        data = "\n".join(data_lines)
        if data == "[DONE]":
            return None
        try:
            event = json.loads(data)
        except json.JSONDecodeError as error:
            raise TargetResponseError("target streaming response contains invalid event JSON") from error
        if not isinstance(event, dict):
            raise TargetResponseError("target streaming event must be an object")
        if event_name and "event" not in event:
            event["event"] = event_name
        return event

    @staticmethod
    def _tool_call_from_workflow_node(event: dict[str, Any]) -> ToolCall | None:
        data = event.get("data")
        if not isinstance(data, dict) or data.get("node_type") not in {"http-request", "tool"}:
            return None
        inputs = data.get("inputs")
        outputs = data.get("outputs")
        title = data.get("title")
        return ToolCall(
            id=data.get("id") if isinstance(data.get("id"), str) else None,
            name=title if isinstance(title, str) and title else "http-request",
            provider="chatflow-http" if data.get("node_type") == "http-request" else "chatflow-tool",
            arguments=inputs,
            result=outputs,
            status=str(data.get("status") or "observed"),
        )

    @staticmethod
    def _tool_call_from_event(event: dict[str, Any]) -> ToolCall | None:
        tool_name = event.get("tool") or event.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name:
            return None
        status = event.get("status")
        return ToolCall(
            id=event.get("id") if isinstance(event.get("id"), str) else None,
            name=tool_name,
            provider=event.get("tool_type") if isinstance(event.get("tool_type"), str) else None,
            arguments=DifyTarget._decode_event_value(event.get("tool_input")),
            result=DifyTarget._decode_event_value(event.get("observation")),
            status=status if isinstance(status, str) and status else "observed",
        )

    @staticmethod
    def _decode_event_value(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    @staticmethod
    def _conversation_id(data: dict[str, Any] | None) -> str:
        if not isinstance(data, dict):
            raise TargetResponseError("target response must be an object")
        returned_conversation_id = data.get("conversation_id")
        if not isinstance(returned_conversation_id, str) or not returned_conversation_id:
            raise TargetResponseError("target response conversation_id must be a non-empty string")
        return returned_conversation_id

    @staticmethod
    def _latest_user_query(messages: list[Message]) -> str:
        for message in reversed(messages):
            if message.role == "user":
                return message.content
        raise TargetResponseError("Dify request has no user message")

    @staticmethod
    def _extract_sources(data: dict[str, Any]) -> list[str]:
        """Extract Dify retriever resource text from blocking or workflow payloads."""
        candidates: list[Any] = [data]
        nested = data.get("data") if isinstance(data, dict) else None
        if isinstance(nested, dict):
            candidates.append(nested)
            metadata = nested.get("metadata")
            if isinstance(metadata, dict):
                candidates.append(metadata)
        metadata = data.get("metadata") if isinstance(data, dict) else None
        if isinstance(metadata, dict):
            candidates.append(metadata)
        sources: list[str] = []
        for candidate in candidates:
            resources = candidate.get("retriever_resources") if isinstance(candidate, dict) else None
            if not isinstance(resources, list):
                continue
            for resource in resources:
                if isinstance(resource, dict) and isinstance(resource.get("content"), str) and resource["content"].strip():
                    content = resource["content"].strip()
                    if content not in sources:
                        sources.append(content)
        return sources

    @staticmethod
    def _extract_usage(data: dict[str, Any]) -> dict[str, Any]:
        usage = data.get("usage")
        if usage is None:
            metadata = data.get("metadata")
            usage = metadata.get("usage", {}) if isinstance(metadata, dict) else {}
        if not isinstance(usage, dict):
            raise TargetResponseError("target response usage must be an object")
        return usage

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""

        await self._client.aclose()
