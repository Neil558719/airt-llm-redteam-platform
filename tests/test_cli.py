from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import airt.cli as cli
from airt.adapter import OpenAICompatTarget
from airt.cli import app, build_target
from airt.config import DifyTargetConfig, TargetConfig
from airt.dify_adapter import DifyTarget
from airt.models import AttackCase, CaseResult, Reply, RunMetadata, Verdict


runner = CliRunner()


def _case(case_id: str = "x-001") -> AttackCase:
    return AttackCase(
        id=case_id,
        name="sample",
        category="jailbreak",
        severity="low",
        turns=["x"],
        detect={},
    )


def test_help_shows_authorization_warning():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "authorized" in result.stdout.lower()


def test_chatflow_without_profile_is_identified_as_agent():
    target = DifyTargetConfig(
        base_url="http://dify/v1", api_key="key", response_mode="streaming", capture_tool_calls=True
    )
    assert ("agent" if getattr(target, "capture_tool_calls", False) else "text") == "agent"


def test_run_mode_resolves_security_and_quality_policies():
    assert cli._resolve_run_mode("security") == ("always", "offline")
    assert cli._resolve_run_mode("quality") == ("case", "live")
    assert cli._resolve_run_mode("release") == ("case", "live")


def test_run_mode_rejects_unknown_value():
    with pytest.raises(ValueError, match="mode"):
        cli._resolve_run_mode("unknown")


def test_run_mode_explicit_security_override_wins():
    assert cli._resolve_run_mode("security", security_judge="off") == ("off", "offline")


def test_quality_judge_context_uses_retrieved_sources():
    reply = Reply(text="回答", sources=["知识库片段一", "知识库片段二"])

    assert cli._quality_judge_context(reply) == "知识库片段一\n知识库片段二"



def test_shortcut_commands_are_registered():
    for command in ("chatflow", "doctor"):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0
    chatflow_help = runner.invoke(app, ["chatflow", "--help"])
    assert "quality" in chatflow_help.stdout
    assert "release" in chatflow_help.stdout
    assert "assess" in chatflow_help.stdout



def test_resolve_output_dir_uses_named_target(tmp_path):
    assert cli._shortcut_output_dir(tmp_path, "chatflow", "security") == tmp_path / "chatflow-security"

def test_list_outputs_case_ids_without_network(tmp_path, monkeypatch):
    def no_target_factory(settings):
        raise AssertionError("list must not build a target")

    monkeypatch.setattr(cli, "build_target", no_target_factory)
    path = tmp_path / "cases.yaml"
    path.write_text(
        "- id: x-001\n  name: sample\n  category: jailbreak\n  severity: low\n"
        "  turns: ['x']\n  detect: {}\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["list", "--cases", str(path)])
    assert result.exit_code == 0
    assert "x-001" in result.stdout
    assert "jailbreak" in result.stdout


def test_report_uses_reports_by_default_without_config_or_network(tmp_path, monkeypatch):
    case = _case()
    result_data = CaseResult(
        case_id=case.id,
        case=case,
        status="completed",
        verdict=Verdict(
            status="fail",
            source="rule",
            confidence=1.0,
            reason="not demonstrated",
        ),
    )
    results = tmp_path / "results.jsonl"
    results.write_text(result_data.model_dump_json() + "\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["report", "--results", str(results)])

    out = tmp_path / "reports" / "quality"
    assert result.exit_code == 0
    assert (out / "report.json").exists()
    assert (out / "report.html").exists()
    archives = list((out / "archive").iterdir())
    assert len(archives) == 1
    assert (archives[0] / "results.jsonl").read_bytes() == results.read_bytes()
    assert (archives[0] / "report.json").exists()
    assert (archives[0] / "report.html").exists()
    assert "ASR" in result.stdout


@pytest.mark.parametrize("mode", ["security", "quality", "release"])
def test_report_default_directory_follows_run_mode(tmp_path, monkeypatch, mode):
    case = _case()
    result_data = CaseResult(
        case_id=case.id,
        case=case,
        status="completed",
        run_metadata=RunMetadata(run_mode=mode),
        verdict=Verdict(status="fail", source="rule", confidence=1.0, reason="not demonstrated"),
    )
    results = tmp_path / "results.jsonl"
    results.write_text(result_data.model_dump_json() + "\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["report", "--results", str(results)])

    out = tmp_path / "reports" / mode
    assert result.exit_code == 0
    assert (out / "report.json").exists()
    assert (out / "report.html").exists()
    assert len(list((out / "archive").iterdir())) == 1


def test_report_regenerates_reports_into_explicit_output_without_config_or_network(tmp_path, monkeypatch):
    case = _case()
    result_data = CaseResult(
        case_id=case.id,
        case=case,
        status="completed",
        verdict=Verdict(
            status="fail",
            source="rule",
            confidence=1.0,
            reason="not demonstrated",
        ),
    )
    results = tmp_path / "results.jsonl"
    results.write_text(result_data.model_dump_json() + "\n", encoding="utf-8")
    out = tmp_path / "reports-export"
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["report", "--results", str(results), "--out", str(out)])

    assert result.exit_code == 0
    assert (out / "report.json").exists()
    assert (out / "report.html").exists()
    archives = list((tmp_path / "reports" / "quality" / "archive").iterdir())
    assert len(archives) == 1
    assert (archives[0] / "results.jsonl").read_bytes() == results.read_bytes()
    assert "ASR" in result.stdout


def test_run_returns_two_for_invalid_config(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("target: {}\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["run", "--config", str(config), "--cases", str(tmp_path), "--out", str(tmp_path / "out")],
    )
    assert result.exit_code == 2


def test_report_rejects_malformed_jsonl(tmp_path):
    results = tmp_path / "results.jsonl"
    results.write_text("not json\n", encoding="utf-8")
    result = runner.invoke(app, ["report", "--results", str(results), "--out", str(tmp_path / "out")])
    assert result.exit_code == 2
    assert "results" in result.stdout.lower()


def test_build_target_selects_openai_compatible_target_without_network():
    target = build_target(
        TargetConfig(
            base_url="http://target/v1",
            api_key="target-key",
            model="target-model",
        )
    )

    assert isinstance(target, OpenAICompatTarget)
    assert target._endpoint == "http://target/v1/chat/completions"


def test_build_target_selects_native_dify_target_without_network():
    target = build_target(
        DifyTargetConfig(
            base_url="http://dify/v1",
            api_key="dify-key",
            system_prompt="matching prompt used for leak detection only",
        )
    )

    assert isinstance(target, DifyTarget)
    assert target._endpoint == "http://dify/v1/chat-messages"


def test_run_returns_two_for_invalid_target_provider(tmp_path):
    config = tmp_path / "config.yaml"
    cases = tmp_path / "cases.yaml"
    config.write_text(
        "target:\n"
        "  provider: unsupported\n"
        "  base_url: http://target/v1\n"
        "  api_key: target-key\n"
        "  model: target-model\n",
        encoding="utf-8",
    )
    cases.write_text(
        "- id: x-001\n  name: sample\n  category: jailbreak\n  severity: low\n"
        "  turns: ['x']\n  detect: {}\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["run", "--config", str(config), "--cases", str(cases), "--out", str(tmp_path / "out")]
    )

    assert result.exit_code == 2
    assert "provider" in result.stdout


def test_run_dify_cases_creates_artifacts_offline_and_isolates_conversations(
    tmp_path, monkeypatch
):
    project_root = Path(__file__).resolve().parents[1]
    case_path = project_root / "cases" / "dify.yaml"
    config = tmp_path / "config.dify.yaml"
    config.write_text(
        "target:\n"
        "  provider: dify\n"
        "  base_url: http://dify.test/v1\n"
        "  api_key: dify-key\n"
        "  system_prompt: |\n"
        "    与 Dify 应用中保持一致，仅用于泄露检测\n"
        "run:\n"
        "  concurrency: 2\n"
        "  qps: null\n"
        "  retries: 0\n",
        encoding="utf-8",
    )
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat-messages"
        payload = json.loads(request.content)
        payloads.append(payload)
        case_id = str(payload["user"]).removeprefix("airt:")
        return httpx.Response(
            200,
            json={
                "mode": "blocking",
                "answer": f"safe response for {case_id}",
                "conversation_id": f"conversation-{case_id}",
                "metadata": {"usage": {"total_tokens": 1}},
            },
        )

    def mock_build_target(config):
        assert isinstance(config, DifyTargetConfig)
        return DifyTarget(config, transport=httpx.MockTransport(handler))

    original_load_case_set = cli._load_case_set

    def load_dify_cases_with_multiturn_checks(path, include_sensitive):
        loaded = original_load_case_set(path, include_sensitive)
        if path == case_path:
            loaded.extend(
                [
                    _case("dify-multiturn-a").model_copy(
                        update={"turns": ["a-first", "a-second"]}
                    ),
                    _case("dify-multiturn-b").model_copy(
                        update={"turns": ["b-first", "b-second"]}
                    ),
                ]
            )
        return loaded

    monkeypatch.setattr(cli, "build_target", mock_build_target)
    monkeypatch.setattr(cli, "_load_case_set", load_dify_cases_with_multiturn_checks)
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "dify-run"

    result = runner.invoke(
        app, ["run", "--config", str(config), "--cases", str(case_path), "--out", str(out)]
    )

    assert result.exit_code == 0, result.stdout
    assert (out / "results.jsonl").exists()
    assert (tmp_path / "reports" / "security" / "report.json").exists()
    assert (tmp_path / "reports" / "security" / "report.html").exists()
    archives = list((tmp_path / "reports" / "security" / "archive").iterdir())
    assert len(archives) == 1
    assert (archives[0] / "results.jsonl").read_bytes() == (out / "results.jsonl").read_bytes()
    assert not (out / "report.json").exists()
    assert not (out / "report.html").exists()
    assert len((out / "results.jsonl").read_text(encoding="utf-8").splitlines()) == 7
    payloads_by_case = {
        case_id: [item for item in payloads if item["user"] == f"airt:{case_id}"]
        for case_id in (
            "dify-kb-001",
            "dify-kb-002",
            "dify-system-001",
            "dify-roleplay-001",
            "dify-goal-001",
            "dify-multiturn-a",
            "dify-multiturn-b",
        )
    }
    for case_id in (
        "dify-kb-001",
        "dify-kb-002",
        "dify-system-001",
        "dify-roleplay-001",
        "dify-goal-001",
    ):
        assert len(payloads_by_case[case_id]) == 1
        assert "conversation_id" not in payloads_by_case[case_id][0]
    assert [item.get("conversation_id") for item in payloads_by_case["dify-multiturn-a"]] == [
        None,
        "conversation-dify-multiturn-a",
    ]
    assert [item.get("conversation_id") for item in payloads_by_case["dify-multiturn-b"]] == [
        None,
        "conversation-dify-multiturn-b",
    ]


def test_chatflow_quality_shortcut_uses_agent_config_without_named_profile(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(cli, "run", lambda **kwargs: calls.append(kwargs))
    cli.chatflow_quality(config=tmp_path / "config.yaml", cases=tmp_path / "cases.yaml", out=tmp_path / "out", runs_dir=tmp_path / "runs")
    assert calls[0]["config"] == tmp_path / "config.yaml"
    assert "target_profile" not in calls[0]
    assert calls[0]["mode"] == "quality"
    assert calls[0]["shared_quality"] is True


def test_chatflow_assess_runs_security_quality_and_assess_report(monkeypatch, tmp_path):
    calls = []
    aggregates = []
    monkeypatch.setattr(cli, "run", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(cli, "write_assess_report", lambda security, quality, out: aggregates.append((security, quality, out)))
    cli.chatflow_assess(config=tmp_path / "config.yaml", cases=tmp_path / "cases.yaml", out=tmp_path / "out", runs_dir=tmp_path / "runs")
    assert [item["mode"] for item in calls] == ["security", "quality"]
    assert calls[0]["security_judge"] == "always" and calls[0]["shared_cases"] is True
    assert calls[1]["shared_quality"] is True
    assert aggregates == [(tmp_path / "out" / "security" / "results.jsonl", tmp_path / "out" / "quality" / "results.jsonl", Path("reports/assess"))]
