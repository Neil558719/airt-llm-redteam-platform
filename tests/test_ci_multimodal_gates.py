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
