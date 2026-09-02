from pathlib import Path

import yaml


WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "airt-quality-security.yml"


def test_live_security_gate_runs_image_and_audio_smoke_cases():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "chatflow security --config config.dify.agent.yaml --out runs/ci-chatflow" in workflow
    assert "--asset fixtures\\multimodal\\prompt_injection.png" in workflow
    assert "--asset-type image" in workflow
    assert "--asset fixtures\\multimodal\\prompt_injection.wav" in workflow
    assert "--asset-type audio" in workflow
    assert "runs/ci-chatflow-multimodal-image/results.jsonl" in workflow
    assert "runs/ci-chatflow-multimodal-audio/results.jsonl" in workflow


def test_self_hosted_live_gates_configure_runner_proxy_for_checkout():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    live_jobs = workflow.split("  live-chatflow-security:", 1)[1]

    assert live_jobs.count("HTTP_PROXY: http://127.0.0.1:10808") == 4
    assert live_jobs.count("HTTPS_PROXY: http://127.0.0.1:10808") == 4
    assert "http-proxy:" not in live_jobs


def _jobs():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]


def test_text_image_and_audio_security_are_independent_jobs():
    jobs = _jobs()

    assert {
        "live-chatflow-security",
        "live-chatflow-image-smoke",
        "live-chatflow-audio-smoke",
    } <= jobs.keys()
    assert jobs["live-chatflow-image-smoke"]["needs"] == "offline"
    assert jobs["live-chatflow-audio-smoke"]["needs"] == "offline"


def test_each_security_job_retries_only_failed_cases_once():
    jobs = _jobs()

    for name in ("live-chatflow-security", "live-chatflow-image-smoke", "live-chatflow-audio-smoke"):
        commands = "\n".join(str(step.get("run", "")) for step in jobs[name]["steps"])
        assert "--resume" in commands
        assert "$LASTEXITCODE" in commands


def test_unified_gate_always_runs_after_all_live_jobs():
    gate = _jobs()["unified-gate"]

    assert set(gate["needs"]) == {
        "offline",
        "shared-quality",
        "live-chatflow-security",
        "live-chatflow-image-smoke",
        "live-chatflow-audio-smoke",
        "live-chatflow-quality",
    }
    assert "always()" in gate["if"]


def test_feature_branches_run_once_via_pull_request_event():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "push:\n    branches: [main]" in workflow
