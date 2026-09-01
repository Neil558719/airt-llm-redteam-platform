"""Configuration loading with environment-only secret interpolation."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator


class ConfigError(ValueError):
    """Raised when a configuration file cannot be expanded or validated."""


class TargetConfig(BaseModel):
    provider: Literal["openai_compatible"] = "openai_compatible"
    base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1)
    system_prompt: str = ""
    timeout: float = Field(default=60, gt=0)
    extra_body: dict[str, Any] = Field(default_factory=dict)


class DifyTargetConfig(BaseModel):
    provider: Literal["dify"] = "dify"
    base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    system_prompt: str = ""
    timeout: float = Field(default=60, gt=0)
    inputs: dict[str, Any] = Field(default_factory=dict)
    user_prefix: str = Field(default="airt", min_length=1)
    extra_body: dict[str, Any] = Field(default_factory=dict)
    response_mode: Literal["blocking", "streaming"] = "blocking"
    capture_tool_calls: bool = False
    multimodal_transfer_method: Literal["remote_url", "local_file"] = "remote_url"

    @model_validator(mode="after")
    def streaming_requires_tool_capture(self) -> "DifyTargetConfig":
        if self.capture_tool_calls and self.response_mode != "streaming":
            raise ValueError("capture_tool_calls requires response_mode=streaming")
        return self


TargetProviderConfig = Annotated[
    TargetConfig | DifyTargetConfig,
    Field(discriminator="provider"),
]


class JudgeConfig(BaseModel):
    provider: Literal["openai_compatible", "anthropic"] = "openai_compatible"
    base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1)
    timeout: float = Field(default=60, gt=0)
    retries: int = Field(default=2, ge=0)
    retry_base_delay: float = Field(default=0.25, ge=0)
    retry_max_delay: float = Field(default=5.0, gt=0)
    extra_body: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def retry_delay_bounds(self) -> "JudgeConfig":
        if self.retry_max_delay < self.retry_base_delay:
            raise ValueError("retry_max_delay must be greater than or equal to retry_base_delay")
        return self


class GateConfig(BaseModel):
    min_score: float | None = Field(default=None, ge=0, le=100)
    min_quality: float | None = Field(default=None, ge=0, le=1)
    max_latency_ms: float | None = Field(default=None, ge=0)


class RunProfile(BaseModel):
    security_judge: Literal["off", "case", "always"] = "case"
    quality_judge: Literal["offline", "live"] = "offline"
    gates: GateConfig = Field(default_factory=GateConfig)


class RunConfig(BaseModel):
    concurrency: int = Field(default=5, gt=0)
    qps: float | None = Field(default=None, ge=0)
    retries: int = Field(default=2, ge=0)
    leak_ngram: int = Field(default=24, gt=0)


class AppConfig(BaseModel):
    target: TargetProviderConfig
    target_profiles: dict[str, TargetProviderConfig] = Field(default_factory=dict)
    judge: JudgeConfig | None = None
    run: RunConfig = Field(default_factory=RunConfig)
    run_profiles: dict[str, RunProfile] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def default_target_provider(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        value = value.copy()
        for key in ("target", "target_profiles"):
            configured = value.get(key)
            if key == "target" and isinstance(configured, dict):
                configured = configured.copy()
                configured.setdefault("provider", "openai_compatible")
                value[key] = configured
            elif key == "target_profiles" and isinstance(configured, dict):
                profiles = {}
                for name, target in configured.items():
                    if isinstance(target, dict):
                        target = target.copy()
                        target.setdefault("provider", "openai_compatible")
                    profiles[name] = target
                value[key] = profiles
        return value

    def resolve_target(self, profile: str | None = None) -> TargetProviderConfig:
        """Resolve an optional profile without changing the legacy target path."""
        if profile is None or (profile == "text" and profile not in self.target_profiles):
            return self.target
        if profile not in self.target_profiles:
            available = ", ".join(["text", *sorted(self.target_profiles)])
            raise ConfigError(f"unknown target profile {profile!r}; available profiles: {available}")
        profile_data = _expand_environment(self.target_profiles[profile].model_dump())
        try:
            if profile_data.get("provider") == "openai_compatible":
                return TargetConfig.model_validate(profile_data)
            if profile_data.get("provider") == "dify":
                return DifyTargetConfig.model_validate(profile_data)
            raise ValueError(f"unsupported target provider {profile_data.get('provider')!r}")
        except (ValidationError, ValueError) as error:
            raise ConfigError(f"invalid target profile {profile!r}: {error}") from error


_ENV_REFERENCE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def _expand_environment(value: Any) -> Any:
    """Expand exact ${NAME} string values recursively, preserving all other text."""

    if isinstance(value, str):
        match = _ENV_REFERENCE.fullmatch(value)
        if match is None:
            return value
        name = match.group(1)
        try:
            return os.environ[name]
        except KeyError as error:
            raise ConfigError(f"environment variable {name} is required") from error
    if isinstance(value, list):
        return [_expand_environment(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_environment(item) for key, item in value.items()}
    return value


def load_config(path: Path, *, include_judge: bool = True) -> AppConfig:
    """Load, recursively expand, and validate a YAML application configuration."""

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"could not read configuration {path}: {error}") from error

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as error:
        raise ConfigError(f"invalid YAML in {path}: {error}") from error

    if not isinstance(data, dict):
        raise ConfigError(f"configuration {path} must contain a YAML mapping")

    # Profile credentials are expanded only when that profile is selected. This
    # keeps text-only runs independent from an Agent API key and makes configs
    # portable across environments with different enabled targets.
    try:
        eager = {key: value for key, value in data.items() if key != "target_profiles" and (include_judge or key != "judge")}
        expanded = _expand_environment(eager)
        expanded["target_profiles"] = data.get("target_profiles", {})
        if not include_judge:
            expanded["judge"] = None
        return AppConfig.model_validate(expanded)
    except ValidationError as error:
        raise ConfigError(f"invalid configuration {path}: {error}") from error
