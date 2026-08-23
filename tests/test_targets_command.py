from typer.testing import CliRunner

from airt.cli import app


def test_targets_command_lists_names_without_keys():
    result = CliRunner().invoke(app, ["targets", "--registry", "targets.example.yaml"])
    assert result.exit_code == 0
    assert "airt_dify_text" in result.stdout
    assert "airt_dify_chatflow" in result.stdout
    assert "dify_quality" not in result.stdout
    assert "fastgpt_quality" not in result.stdout
    assert "QUALITY_DIFY_API_KEY" not in result.stdout
