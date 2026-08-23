"""Load and validate harmless red-team cases from YAML files."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from airt.models import AttackCase


class CaseLoadError(ValueError):
    """Raised when a case library cannot be parsed or validated."""


def load_cases(path: Path, include_sensitive: bool = False) -> list[AttackCase]:
    """Load validated cases from one YAML file or a directory tree.

    Files under a directory named ``sensitive`` are excluded unless explicitly
    requested. Case IDs must be unique across every file loaded.
    """
    source_path = Path(path)
    sources = _case_files(source_path, include_sensitive=include_sensitive)
    cases: list[AttackCase] = []
    case_sources: dict[str, Path] = {}

    for source in sources:
        for item in _load_document(source):
            try:
                case = AttackCase.model_validate(item)
            except ValidationError as error:
                raise CaseLoadError(f"{source}: invalid case: {error}") from error

            if case.detect.canary and not any(
                case.detect.canary in turn for turn in case.turns
            ):
                raise CaseLoadError(
                    f"{source}: case {case.id!r} canary must appear in a turn"
                )

            previous_source = case_sources.get(case.id)
            if previous_source is not None:
                raise CaseLoadError(
                    f"duplicate case ID {case.id!r} in {previous_source} and {source}"
                )

            case_sources[case.id] = source
            cases.append(case)

    return cases


def _case_files(path: Path, *, include_sensitive: bool) -> list[Path]:
    if path.is_file():
        candidates = [path]
    elif path.is_dir():
        candidates = [
            candidate
            for pattern in ("*.yaml", "*.yml")
            for candidate in path.rglob(pattern)
        ]
    else:
        raise CaseLoadError(f"case path does not exist: {path}")

    return sorted(
        (
            candidate
            for candidate in candidates
            if include_sensitive or "sensitive" not in candidate.parts
        ),
        key=lambda candidate: candidate.as_posix(),
    )


def _load_document(source: Path) -> list[object]:
    try:
        document = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise CaseLoadError(f"{source}: unable to parse YAML: {error}") from error

    if not isinstance(document, list):
        raise CaseLoadError(f"{source}: YAML document must contain a list of cases")

    return document
