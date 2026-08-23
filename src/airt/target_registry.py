"""Independent target registry for quality and security test matrices."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator


class TargetRegistryError(ValueError):
    """Raised when a target registry cannot be safely loaded or resolved."""


class RegisteredTarget(BaseModel):
    provider: Literal["dify", "fastgpt", "openai_compatible"]
    app_type: Literal["chat", "advanced-chat"] = "chat"
    base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    model: str | None = None
    app_id: str | None = None
    timeout: float = Field(default=60, gt=0)
    response_mode: Literal["blocking", "streaming"] = "blocking"
    capture_tool_calls: bool = False
    inputs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("base_url")
    @classmethod
    def base_url_is_http(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return value.rstrip("/")

    def description(self) -> str:
        return f"{self.provider}/{self.app_type} @ {self.base_url}"


def build_registered_target(config: RegisteredTarget) -> object:
    """Build the existing Airt adapter from a registry entry."""
    if config.provider == "dify":
        from airt.config import DifyTargetConfig
        from airt.dify_adapter import DifyTarget
        return DifyTarget(DifyTargetConfig(base_url=config.base_url, api_key=config.api_key, inputs=config.inputs, timeout=config.timeout, response_mode=config.response_mode, capture_tool_calls=config.capture_tool_calls))
    if config.provider == "openai_compatible":
        from airt.adapter import OpenAICompatTarget
        from airt.config import TargetConfig
        return OpenAICompatTarget(TargetConfig(base_url=config.base_url, api_key=config.api_key, model=config.model or "default", timeout=config.timeout))
    raise TargetRegistryError("FastGPT adapter factory is intentionally isolated; use its llmtest adapter")


class TargetRegistry(BaseModel):
    targets: dict[str, RegisteredTarget] = Field(min_length=1)

    def resolve(self, name: str) -> RegisteredTarget:
        try:
            return self.targets[name]
        except KeyError as error:
            available = ", ".join(sorted(self.targets))
            raise TargetRegistryError(
                f"unknown target {name!r}; available targets: {available}"
            ) from error


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        current = os.environ.get(name)
        if current is not None and current != "":
            return current
        if default is not None:
            return default
        raise TargetRegistryError(f"missing environment variable: {name}")

    return _ENV_PATTERN.sub(replace, value)


def load_target_registry(path: str | Path) -> TargetRegistry:
    """Load YAML and interpolate environment variables before validation."""

    source = Path(path)
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    except OSError as error:
        raise TargetRegistryError(f"cannot read target registry: {source}") from error
    except yaml.YAMLError as error:
        raise TargetRegistryError(f"invalid target registry YAML: {source}") from error
    if not isinstance(data, dict):
        raise TargetRegistryError("target registry root must be a mapping")
    try:
        return TargetRegistry.model_validate(_expand_env(data))
    except TargetRegistryError:
        raise
    except ValueError as error:
        raise TargetRegistryError(f"invalid target registry: {error}") from error
