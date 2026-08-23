import json

import httpx
import pytest

from airt.config import ConfigError, DifyTargetConfig, load_config
from airt.dify_adapter import DifyTarget
from airt.judge.rules import rule_evaluate
from airt.models import AttackCase, CaseResult, Message, Reply, RunMetadata, ToolCall, Verdict
from airt.report.html import render_html


def _case(*, detect: dict) -> AttackCase:
    return AttackCase(
        id="agent-case",
        name="agent case",
        category="prompt_injection",
        severity="high",
        turns=["test"],
        detect=detect,
    )


def test_text_profile_does_not_require_an_unselected_agent_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DIFY_TEXT_API_KEY", "text-key")
    path = tmp_path / "config.yaml"
    path.write_text(
        "target:\n"
        "  provider: dify\n"
        "  base_url: http://dify/v1\n"
        "  api_key: ${DIFY_TEXT_API_KEY}\n"
        "target_profiles:\n"
        "  agent:\n"
        "    provider: dify\n"
        "    base_url: http://dify/v1\n"
        "    api_key: ${DIFY_AGENT_API_KEY}\n"
        "    response_mode: streaming\n"
        "    capture_tool_calls: true\n",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.resolve_target("text").api_key == "text-key"
    # 未选择 agent profile 时，不应因为其未配置的 Key 阻塞纯文本配置加载。


def test_agent_profile_expands_its_key_only_when_selected(tmp_path, monkeypatch):
    monkeypatch.setenv("DIFY_TEXT_API_KEY", "text-key")
    monkeypatch.setenv("DIFY_AGENT_API_KEY", "agent-key")
    path = tmp_path / "config.yaml"
    path.write_text(
        "target:\n"
        "  provider: dify\n"
        "  base_url: http://dify/v1\n"
        "  api_key: ${DIFY_TEXT_API_KEY}\n"
        "target_profiles:\n"
        "  agent:\n"
        "    provider: dify\n"
        "    base_url: http://dify/v1\n"
        "    api_key: ${DIFY_AGENT_API_KEY}\n"
        "    response_mode: streaming\n"
        "    capture_tool_calls: true\n",
        encoding="utf-8",
    )

    target = load_config(path).resolve_target("agent")

    assert isinstance(target, DifyTargetConfig)
    assert target.api_key == "agent-key"
    assert target.response_mode == "streaming"
    assert target.capture_tool_calls is True


def test_agent_rule_detects_forbidden_and_expected_tools():
    forbidden = rule_evaluate(
        _case(detect={"tool_call_none": ["send_notice"]}),
        Reply(text="done", tool_calls=[ToolCall(name="send_notice")]),
        "",
    )
    expected = rule_evaluate(
        _case(detect={"tool_call_expected": ["query_order"]}),
        Reply(text="done", tool_calls=[ToolCall(name="query_order")]),
        "",
    )
    missing = rule_evaluate(
        _case(detect={"tool_call_required": ["query_order"]}),
        Reply(text="done"),
        "",
    )

    assert forbidden is not None and forbidden.status == "success"
    assert expected is not None and expected.status == "fail"
    assert missing is not None and missing.status == "success"


def test_forbidden_tool_precedes_expected_tool_rule():
    verdict = rule_evaluate(
        _case(detect={"tool_call_expected": ["query_order"], "tool_call_none": ["send_notice"]}),
        Reply(text="done", tool_calls=[ToolCall(name="query_order"), ToolCall(name="send_notice")]),
        "",
    )

    assert verdict is not None
    assert verdict.status == "success"
    assert "forbidden" in verdict.reason


def test_agent_report_displays_redacted_tool_observation(tmp_path):
    case = _case(detect={})
    result = CaseResult(
        case_id=case.id,
        case=case,
        status="completed",
        run_metadata=RunMetadata(target_profile="agent"),
        reply=Reply(
            text="已完成",
            tool_calls=[
                ToolCall(
                    name="query_order",
                    arguments={"order_id": "DEMO-ORD-2026-042", "api_key": "must-not-leak"},
                    result={"status": "mocked"},
                )
            ],
        ),
        verdict=Verdict(status="fail", source="rule", confidence=1.0, reason="safe"),
    )
    from airt.metrics import summarize

    path = tmp_path / "report.html"
    render_html(summarize([result]), [result], path)
    html = path.read_text(encoding="utf-8")

    assert "Agent / 工具调用" in html
    assert "工具调用观测" in html
    assert "query_order" in html
    assert "DEMO-ORD-2026-042" in html
    assert "must-not-leak" not in html
    assert "[已脱敏]" in html


def test_workflow_http_node_is_observed_as_tool_call():
    call = DifyTarget._tool_call_from_workflow_node(
        {
            "data": {
                "id": "node-run-1",
                "node_type": "http-request",
                "title": "query_order",
                "inputs": {"url": "http://host.docker.internal:18080/query_order"},
                "outputs": {"body": "{\"ok\":true}"},
                "status": "succeeded",
            }
        }
    )

    assert call is not None
    assert call.name == "query_order"
    assert call.provider == "chatflow-http"
    assert call.status == "succeeded"


def test_chatflow_workflow_finished_is_a_valid_terminal_event():
    payloads: list[dict[str, object]] = []
    sse = "\n".join(
        [
            'event: workflow_started',
            'data: {"event":"workflow_started","workflow_run_id":"run-1"}',
            "",
            'event: node_finished',
            'data: {"event":"node_finished","data":{"node_type":"http-request","title":"query_order","status":"succeeded","outputs":{"body":"{\\"ok\\":true}"}}}',
            "",
            'event: message',
            'data: {"event":"message","answer":"查询完成"}',
            "",
            'event: workflow_finished',
            'data: {"event":"workflow_finished","conversation_id":"conversation-2","outputs":{"answer":"查询完成"},"metadata":{"usage":{"total_tokens":11}}}',
            "",
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse)

    async def run():
        target = DifyTarget(
            DifyTargetConfig(
                base_url="http://test/v1", api_key="key", response_mode="streaming", capture_tool_calls=True
            ),
            transport=httpx.MockTransport(handler),
        )
        try:
            return await target.chat_case("flow-case", [Message(role="user", content="查询")])
        finally:
            await target.aclose()

    import asyncio

    reply = asyncio.run(run())
    assert reply.text == "查询完成"
    assert reply.usage == {"total_tokens": 11}
    assert [call.name for call in reply.tool_calls] == ["query_order"]


@pytest.mark.asyncio
async def test_dify_agent_stream_collects_tool_observations_and_final_answer():
    observed_payloads: list[dict[str, object]] = []
    sse = "\n".join(
        [
            'event: agent_thought',
            'data: {"event":"agent_thought","id":"thought-1","tool":"query_order","tool_input":"{\\"order_id\\": \\"DEMO-ORD-2026-042\\"}","observation":"{\\"status\\": \\"mocked\\"}"}',
            "",
            'event: agent_message',
            'data: {"event":"agent_message","answer":"订单状态已查询。"}',
            "",
            'event: message_end',
            'data: {"event":"message_end","conversation_id":"conversation-1","metadata":{"usage":{"total_tokens":9}}}',
            "",
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        observed_payloads.append(json.loads(request.content))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse)

    target = DifyTarget(
        DifyTargetConfig(
            base_url="http://test/v1",
            api_key="key",
            response_mode="streaming",
            capture_tool_calls=True,
        ),
        transport=httpx.MockTransport(handler),
    )
    try:
        reply = await target.chat_case("agent-case", [Message(role="user", content="查询订单")])
    finally:
        await target.aclose()

    assert observed_payloads[0]["response_mode"] == "streaming"
    assert reply.text == "订单状态已查询。"
    assert reply.usage == {"total_tokens": 9}
    assert len(reply.tool_calls) == 1
    assert reply.tool_calls[0].name == "query_order"
    assert reply.tool_calls[0].arguments == {"order_id": "DEMO-ORD-2026-042"}
    assert reply.tool_calls[0].result == {"status": "mocked"}
