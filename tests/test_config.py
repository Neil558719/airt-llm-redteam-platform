import pytest

from airt.config import ConfigError, DifyTargetConfig, TargetConfig, load_config


def test_load_config_expands_environment_variable(tmp_path, monkeypatch):
    monkeypatch.setenv("TARGET_API_KEY", "secret-for-test")
    path = tmp_path / "config.yaml"
    path.write_text(
        "target:\n"
        "  base_url: http://localhost/v1\n"
        "  api_key: ${TARGET_API_KEY}\n"
        "  model: test\n",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.target.api_key == "secret-for-test"
    assert config.judge is None


def test_load_config_expands_exact_variables_recursively(tmp_path, monkeypatch):
    monkeypatch.setenv("TARGET_API_KEY", "target-key")
    monkeypatch.setenv("JUDGE_API_KEY", "judge-key")
    monkeypatch.setenv("CUSTOM_HEADER", "trace-value")
    path = tmp_path / "config.yaml"
    path.write_text(
        "target:\n"
        "  base_url: http://localhost/v1\n"
        "  api_key: ${TARGET_API_KEY}\n"
        "  model: test\n"
        "  extra_body:\n"
        "    metadata:\n"
        "      header: ${CUSTOM_HEADER}\n"
        "judge:\n"
        "  base_url: http://judge/v1\n"
        "  api_key: ${JUDGE_API_KEY}\n"
        "  model: judge-model\n"
        "run:\n"
        "  concurrency: 3\n"
        "  qps: 1.5\n"
        "  retries: 0\n"
        "  leak_ngram: 30\n",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.target.extra_body == {"metadata": {"header": "trace-value"}}
    assert config.judge is not None
    assert config.judge.api_key == "judge-key"
    assert config.judge.provider == "openai_compatible"
    assert config.judge.retries == 2
    assert config.judge.retry_base_delay == 0.25
    assert config.judge.retry_max_delay == 5.0
    assert config.run.concurrency == 3
    assert config.run.qps == 1.5
    assert config.run.leak_ngram == 30


def test_load_config_only_expands_exact_environment_variable_syntax(tmp_path, monkeypatch):
    monkeypatch.setenv("TARGET_API_KEY", "target-key")
    path = tmp_path / "config.yaml"
    path.write_text(
        "target:\n"
        "  base_url: http://localhost/v1\n"
        "  api_key: ${TARGET_API_KEY}-suffix\n"
        "  model: test\n",
        encoding="utf-8",
    )

    assert load_config(path).target.api_key == "${TARGET_API_KEY}-suffix"



def test_load_config_can_skip_judge_for_offline_security_runs(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "target:\n  base_url: http://localhost/v1\n  api_key: target-key\n  model: target-model\n"
        "judge:\n  base_url: ${MISSING_JUDGE_BASE}\n  api_key: ${MISSING_JUDGE_KEY}\n  model: judge-model\n",
        encoding="utf-8",
    )

    config = load_config(path, include_judge=False)

    assert config.judge is None


def test_load_config_reads_run_profiles(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "target:\n  base_url: http://localhost/v1\n  api_key: target-key\n  model: target-model\n"
        "run_profiles:\n  release:\n    security_judge: case\n    quality_judge: live\n    gates:\n      min_score: 90\n      min_quality: 0.9\n      max_latency_ms: 2000\n",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.run_profiles["release"].quality_judge == "live"
    assert config.run_profiles["release"].gates.min_score == 90

def test_load_config_rejects_missing_environment_variable(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "target:\n"
        "  base_url: http://localhost/v1\n"
        "  api_key: ${MISSING_KEY}\n"
        "  model: test\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="MISSING_KEY"):
        load_config(path)


def test_load_config_defaults_target_to_openai_compatible(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "target:\n"
        "  base_url: http://localhost/v1\n"
        "  api_key: target-key\n"
        "  model: target-model\n",
        encoding="utf-8",
    )

    config = load_config(path)

    assert isinstance(config.target, TargetConfig)
    assert config.target.provider == "openai_compatible"


def test_load_config_selects_dify_target_and_expands_its_environment_values(tmp_path, monkeypatch):
    monkeypatch.setenv("DIFY_API_KEY", "dify-key")
    monkeypatch.setenv("DIFY_INPUT", "fixture")
    path = tmp_path / "config.yaml"
    path.write_text(
        "target:\n"
        "  provider: dify\n"
        "  base_url: http://dify/v1\n"
        "  api_key: ${DIFY_API_KEY}\n"
        "  system_prompt: retained only for evaluation\n"
        "  timeout: 30\n"
        "  inputs:\n"
        "    fixture: ${DIFY_INPUT}\n"
        "  user_prefix: test-run\n"
        "  extra_body:\n"
        "    auto_generate_name: false\n",
        encoding="utf-8",
    )

    config = load_config(path)

    assert isinstance(config.target, DifyTargetConfig)
    assert config.target.provider == "dify"
    assert config.target.api_key == "dify-key"
    assert config.target.inputs == {"fixture": "fixture"}
    assert config.target.user_prefix == "test-run"
    assert config.target.extra_body == {"auto_generate_name": False}


@pytest.mark.parametrize("provider", ["unsupported", "anthropic"])
def test_load_config_rejects_unsupported_target_provider(tmp_path, provider):
    path = tmp_path / "config.yaml"
    path.write_text(
        "target:\n"
        f"  provider: {provider}\n"
        "  base_url: http://localhost/v1\n"
        "  api_key: target-key\n"
        "  model: target-model\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="provider"):
        load_config(path)


@pytest.mark.parametrize(
    "config",
    [
        {"base_url": "http://dify/v1", "api_key": "key", "inputs": []},
        {"base_url": "http://dify/v1", "api_key": "key", "user_prefix": ""},
        {"base_url": "http://dify/v1", "api_key": "key", "timeout": 0},
    ],
)
def test_dify_target_config_validates_dify_specific_fields(config):
    with pytest.raises(ValueError):
        DifyTargetConfig(**config)


@pytest.mark.parametrize(
    "field,value",
    [("retries", -1), ("retry_base_delay", -0.1), ("retry_max_delay", 0)],
)
def test_judge_retry_settings_validate_non_negative_bounds(field, value):
    from airt.config import JudgeConfig

    with pytest.raises(ValueError):
        JudgeConfig(
            base_url="http://judge/v1",
            api_key="key",
            model="model",
            **{field: value},
        )


def test_judge_retry_max_delay_cannot_be_less_than_base_delay():
    from airt.config import JudgeConfig

    with pytest.raises(ValueError, match="retry_max_delay"):
        JudgeConfig(
            base_url="http://judge/v1",
            api_key="key",
            model="model",
            retry_base_delay=2,
            retry_max_delay=1,
        )


@pytest.mark.parametrize(
    "content",
    [
        "target: []\n",
        "target:\n  base_url: http://localhost/v1\n  api_key: test\n  model: test\n  timeout: 0\n",
        "target:\n"
        "  base_url: http://localhost/v1\n"
        "  api_key: test\n"
        "  model: test\n"
        "run:\n"
        "  qps: -1\n",
    ],
)
def test_load_config_rejects_invalid_config_models(tmp_path, content):
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(path)
