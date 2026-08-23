import json

import httpx
import pytest

from airt.adapter import OpenAICompatTarget, RetryableTargetError, TargetResponseError
from airt.config import TargetConfig
from airt.models import Message


@pytest.mark.asyncio
async def test_adapter_posts_messages_and_extracts_reply():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "CANARY-X"}}],
                "usage": {"total_tokens": 7},
            },
        )

    target = OpenAICompatTarget(
        TargetConfig(
            base_url="http://test/v1/",
            api_key="key",
            model="model",
            extra_body={"temperature": 0},
        ),
        transport=httpx.MockTransport(handler),
    )

    reply = await target.chat([Message(role="user", content="hello")])
    await target.aclose()

    assert reply.text == "CANARY-X"
    assert reply.usage == {"total_tokens": 7}
    assert reply.raw is not None
    assert requests[0].url.path == "/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer key"
    assert json.loads(requests[0].content) == {
        "model": "model",
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0,
    }


def test_adapter_rejects_extra_body_overriding_core_fields():
    with pytest.raises(ValueError, match="messages, model"):
        OpenAICompatTarget(
            TargetConfig(
                base_url="http://test/v1",
                api_key="key",
                model="model",
                extra_body={"model": "other", "messages": []},
            )
        )


@pytest.mark.asyncio
async def test_adapter_rejects_malformed_success_response():
    target = OpenAICompatTarget(
        TargetConfig(base_url="http://test/v1", api_key="key", model="model"),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": []})),
    )

    with pytest.raises(TargetResponseError):
        await target.chat([Message(role="user", content="hello")])

    await target.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [408, 429, 500, 599])
async def test_adapter_classifies_retryable_http_statuses(status_code: int):
    target = OpenAICompatTarget(
        TargetConfig(base_url="http://test/v1", api_key="key", model="model"),
        transport=httpx.MockTransport(lambda request: httpx.Response(status_code, json={"error": "down"})),
    )

    with pytest.raises(RetryableTargetError):
        await target.chat([Message(role="user", content="hello")])

    await target.aclose()


@pytest.mark.asyncio
async def test_adapter_classifies_nonretryable_http_status_as_response_error():
    target = OpenAICompatTarget(
        TargetConfig(base_url="http://test/v1", api_key="key", model="model"),
        transport=httpx.MockTransport(lambda request: httpx.Response(400, json={"error": "bad request"})),
    )

    with pytest.raises(TargetResponseError):
        await target.chat([Message(role="user", content="hello")])

    await target.aclose()


@pytest.mark.asyncio
async def test_adapter_rejects_null_content():
    target = OpenAICompatTarget(
        TargetConfig(base_url="http://test/v1", api_key="key", model="model"),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant", "content": None}}]},
            )
        ),
    )

    with pytest.raises(TargetResponseError):
        await target.chat([Message(role="user", content="hello")])

    await target.aclose()


@pytest.mark.asyncio
async def test_adapter_classifies_transport_errors_as_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    target = OpenAICompatTarget(
        TargetConfig(base_url="http://test/v1", api_key="key", model="model"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RetryableTargetError):
        await target.chat([Message(role="user", content="hello")])

    await target.aclose()


@pytest.mark.asyncio
async def test_adapter_aclose_closes_http_client():
    target = OpenAICompatTarget(
        TargetConfig(base_url="http://test/v1", api_key="key", model="model"),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
    )

    await target.aclose()

    assert target._client.is_closed
