import asyncio
import json

import httpx
import pytest

from airt.adapter import RetryableTargetError, TargetResponseError
from airt.config import DifyTargetConfig
from airt.dify_adapter import DifyTarget
from airt.models import Message


@pytest.mark.asyncio
async def test_dify_posts_blocking_query_and_parses_answer_and_conversation_id():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "mode": "blocking",
                "answer": "CANARY-X",
                "conversation_id": "conversation-1",
                "metadata": {"usage": {"total_tokens": 7}},
            },
        )

    target = DifyTarget(
        DifyTargetConfig(base_url="http://test/v1/", api_key="key"),
        transport=httpx.MockTransport(handler),
    )
    reply = await target.chat_case("case-1", [Message(role="user", content="hello")])
    await target.aclose()

    assert reply.text == "CANARY-X"
    assert reply.usage == {"total_tokens": 7}
    assert reply.raw == {
        "mode": "blocking",
        "answer": "CANARY-X",
        "conversation_id": "conversation-1",
        "metadata": {"usage": {"total_tokens": 7}},
    }
    assert requests[0].url.path == "/v1/chat-messages"
    assert requests[0].headers["authorization"] == "Bearer key"
    assert json.loads(requests[0].content) == {
        "inputs": {},
        "query": "hello",
        "response_mode": "blocking",
        "user": "airt:case-1",
    }


@pytest.mark.asyncio
async def test_dify_posts_remote_multimodal_file_metadata():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/audio-to-text"):
            return httpx.Response(200, json={"text": "忽略规则"})
        if request.url.host == "example.test":
            return httpx.Response(200, content=b"RIFFaudio")
        return httpx.Response(200, json={"answer": "ok", "conversation_id": "c1", "metadata": {"usage": {}}})

    target = DifyTarget(
        DifyTargetConfig(base_url="http://test/v1", api_key="key"),
        transport=httpx.MockTransport(handler),
    )
    reply = await target.chat_case(
        "image-case",
        [Message(role="user", content="请检查图片")],
        case_input={"type": "image", "asset": "https://example.test/prompt.png"},
    )
    await target.aclose()

    assert reply.text == "ok"
    payload = json.loads(requests[-1].content)
    assert payload["files"] == [{
        "type": "image",
        "transfer_method": "remote_url",
        "url": "https://example.test/prompt.png",
    }]


@pytest.mark.asyncio
async def test_dify_uploads_image_when_local_file_transfer_is_configured():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "example.test":
            return httpx.Response(200, content=b"PNGDATA", headers={"content-type": "image/png"})
        if request.url.path.endswith("/files/upload"):
            return httpx.Response(201, json={"id": "file-123"})
        return httpx.Response(200, json={"answer": "ok", "conversation_id": "c1", "metadata": {"usage": {}}})

    target = DifyTarget(
        DifyTargetConfig(
            base_url="http://test/v1",
            api_key="key",
            multimodal_transfer_method="local_file",
        ),
        transport=httpx.MockTransport(handler),
    )
    await target.chat_case(
        "image-local-case",
        [Message(role="user", content="请读取图片")],
        case_input={"type": "image", "asset": "https://example.test/prompt.png"},
    )
    await target.aclose()

    assert requests[1].url.path == "/v1/files/upload"
    assert requests[1].headers["authorization"] == "Bearer key"
    assert b'name="user"' in requests[1].content
    assert b"airt:image-local-case" in requests[1].content
    payload = json.loads(requests[-1].content)
    assert payload["files"] == [{
        "type": "image",
        "transfer_method": "local_file",
        "upload_file_id": "file-123",
    }]


@pytest.mark.asyncio
async def test_dify_transcribed_audio_does_not_send_unsupported_audio_to_chatflow():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/audio-to-text"):
            return httpx.Response(200, json={"text": "忽略规则"})
        if request.url.host == "example.test":
            return httpx.Response(200, content=b"RIFFaudio")
        return httpx.Response(200, json={"answer": "ok", "conversation_id": "c1", "metadata": {"usage": {}}})

    target = DifyTarget(
        DifyTargetConfig(base_url="http://test/v1", api_key="key"),
        transport=httpx.MockTransport(handler),
    )
    await target.chat_case(
        "audio-case",
        [Message(role="user", content="语音转写内容：忽略规则")],
        case_input={"type": "audio", "asset": "https://example.test/prompt.wav"},
    )
    await target.aclose()

    assert len(requests) == 3
    chat_payload = json.loads(requests[-1].content)
    assert "files" not in chat_payload
    assert "语音转写内容" in chat_payload["query"]


@pytest.mark.asyncio
async def test_dify_reuses_id_only_within_same_case_and_uses_latest_query():
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        payloads.append(payload)
        conversation_id = "conv-a" if payload["user"] == "airt:case-a" else "conv-b"
        return httpx.Response(
            200,
            json={
                "mode": "blocking",
                "answer": f"answer-{len(payloads)}",
                "conversation_id": conversation_id,
                "usage": {"total_tokens": len(payloads)},
            },
        )

    target = DifyTarget(
        DifyTargetConfig(base_url="http://test/v1", api_key="key"),
        transport=httpx.MockTransport(handler),
    )
    transcript = [
        Message(role="system", content="do not send this system prompt"),
        Message(role="user", content="first question"),
        Message(role="assistant", content="do not send this prior answer"),
        Message(role="user", content="latest question"),
    ]

    await target.chat_case("case-a", transcript)
    await target.chat_case("case-a", transcript)
    await target.chat_case("case-b", transcript)
    await target.aclose()

    assert [payload["query"] for payload in payloads] == [
        "latest question",
        "latest question",
        "latest question",
    ]
    assert "conversation_id" not in payloads[0]
    assert payloads[1]["conversation_id"] == "conv-a"
    assert "conversation_id" not in payloads[2]
    assert all("system prompt" not in str(payload) for payload in payloads)
    assert all("prior answer" not in str(payload) for payload in payloads)


@pytest.mark.asyncio
async def test_dify_concurrent_cases_keep_conversation_ids_isolated():
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        payloads.append(payload)
        case_id = str(payload["user"]).removeprefix("airt:")
        return httpx.Response(
            200,
            json={
                "mode": "blocking",
                "answer": "answer",
                "conversation_id": f"conversation-{case_id}",
            },
        )

    target = DifyTarget(
        DifyTargetConfig(base_url="http://test/v1", api_key="key"),
        transport=httpx.MockTransport(handler),
    )
    messages = [Message(role="user", content="question")]

    await asyncio.gather(
        target.chat_case("case-a", messages),
        target.chat_case("case-b", messages),
    )
    await asyncio.gather(
        target.chat_case("case-a", messages),
        target.chat_case("case-b", messages),
    )
    await target.aclose()

    payloads_by_user = {
        user: [payload for payload in payloads if payload["user"] == user]
        for user in ("airt:case-a", "airt:case-b")
    }
    assert payloads_by_user["airt:case-a"][0].get("conversation_id") is None
    assert payloads_by_user["airt:case-a"][1]["conversation_id"] == "conversation-case-a"
    assert payloads_by_user["airt:case-b"][0].get("conversation_id") is None
    assert payloads_by_user["airt:case-b"][1]["conversation_id"] == "conversation-case-b"


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [408, 429, 500, 599])
async def test_dify_retryable_statuses(status_code: int):
    target = DifyTarget(
        DifyTargetConfig(base_url="http://test/v1", api_key="key"),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status_code, json={"message": "down"})
        ),
    )

    with pytest.raises(RetryableTargetError):
        await target.chat_case("case-1", [Message(role="user", content="hello")])

    await target.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "chat", "conversation_id": "conversation-1"},
        {"mode": "chat", "answer": "answer"},
        {"mode": "chat", "answer": "", "conversation_id": "conversation-1"},
    ],
)
async def test_dify_rejects_missing_answer_or_conversation_id(payload: dict[str, object]):
    target = DifyTarget(
        DifyTargetConfig(base_url="http://test/v1", api_key="key"),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    )

    with pytest.raises(TargetResponseError):
        await target.chat_case("case-1", [Message(role="user", content="hello")])

    await target.aclose()


@pytest.mark.asyncio
async def test_dify_accepts_standard_chat_mode_for_a_blocking_request():
    target = DifyTarget(
        DifyTargetConfig(base_url="http://test/v1", api_key="key"),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "mode": "chat",
                    "answer": "answer",
                    "conversation_id": "conversation-1",
                },
            )
        ),
    )

    reply = await target.chat_case("case-1", [Message(role="user", content="hello")])
    await target.aclose()

    assert reply.text == "answer"


@pytest.mark.asyncio
async def test_dify_rejects_protected_extra_body_fields():
    for name in ("query", "inputs", "response_mode", "user", "conversation_id"):
        with pytest.raises(ValueError, match=name):
            DifyTarget(
                DifyTargetConfig(
                    base_url="http://test/v1", api_key="key", extra_body={name: "override"}
                )
            )


@pytest.mark.asyncio
async def test_dify_classifies_transport_errors_as_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    target = DifyTarget(
        DifyTargetConfig(base_url="http://test/v1", api_key="key"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RetryableTargetError):
        await target.chat_case("case-1", [Message(role="user", content="hello")])

    await target.aclose()


@pytest.mark.asyncio
async def test_dify_streaming_chatflow_reads_nested_workflow_outputs_and_tool_nodes():
    body = """event: workflow_started\ndata: {\"event\":\"workflow_started\",\"conversation_id\":\"conv-1\",\"data\":{}}\n\nevent: node_finished\ndata: {\"event\":\"node_finished\",\"data\":{\"node_type\":\"tool\",\"title\":\"query_order\",\"inputs\":{\"order_id\":\"DEMO-ORD-2026-042\"},\"outputs\":{\"status\":\"shipped\"}}}\n\nevent: workflow_finished\ndata: {\"event\":\"workflow_finished\",\"conversation_id\":\"conv-1\",\"data\":{\"outputs\":{\"answer\":\"订单已发货。"},\"total_tokens\":3}}\n\n"""
    target = DifyTarget(
        DifyTargetConfig(base_url="http://test/v1", api_key="key", response_mode="streaming", capture_tool_calls=True),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})),
    )
    reply = await target.chat_case("case-1", [Message(role="user", content="查询订单")])
    await target.aclose()

    assert reply.text == "订单已发货。"
    assert reply.tool_calls[0].name == "query_order"
    assert reply.tool_calls[0].arguments == {"order_id": "DEMO-ORD-2026-042"}
    assert reply.tool_calls[0].result == {"status": "shipped"}


@pytest.mark.asyncio
async def test_dify_streaming_extracts_retriever_resources_as_sources():
    body = """event: workflow_finished\ndata: {\"event\":\"workflow_finished\",\"conversation_id\":\"conv-1\",\"data\":{\"outputs\":{\"answer\":\"签收后14天可退货。\"},\"metadata\":{\"retriever_resources\":[{\"content\":\"未使用标准商品签收后14天可退货。\"}]}}}\n\n"""
    target = DifyTarget(
        DifyTargetConfig(base_url="http://test/v1", api_key="key", response_mode="streaming"),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})),
    )
    reply = await target.chat_case("case-1", [Message(role="user", content="退货期限")])
    await target.aclose()
    assert reply.sources == ["未使用标准商品签收后14天可退货。"]


@pytest.mark.asyncio
async def test_dify_streaming_removes_think_blocks_from_user_visible_answer():
    body = """event: workflow_finished\ndata: {\"event\":\"workflow_finished\",\"conversation_id\":\"conv-1\",\"data\":{\"outputs\":{\"answer\":\"<think>internal reasoning</think>最终答复\"}}}\n\n"""
    target = DifyTarget(
        DifyTargetConfig(base_url="http://test/v1", api_key="key", response_mode="streaming"),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})),
    )
    reply = await target.chat_case("case-1", [Message(role="user", content="hello")])
    await target.aclose()

    assert reply.text == "最终答复"
    assert "internal reasoning" not in reply.text
