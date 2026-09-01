from pathlib import Path


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

    assert live_jobs.count("HTTP_PROXY: http://127.0.0.1:10808") == 2
    assert live_jobs.count("HTTPS_PROXY: http://127.0.0.1:10808") == 2
    assert "http-proxy:" not in live_jobs
