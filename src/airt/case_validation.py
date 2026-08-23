"""Offline validation for Airt and provider-neutral shared case files."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from airt.cases import CaseLoadError, load_cases
from airt.shared_cases import SharedCaseError, load_shared_cases


@dataclass(frozen=True)
class CaseValidationIssue:
    source: str
    message: str


@dataclass
class CaseValidationSummary:
    files: int = 0
    cases: int = 0
    issues: list[CaseValidationIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.issues


def _files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted([*path.rglob("*.yaml"), *path.rglob("*.yml")])
    raise ValueError(f"case path does not exist: {path}")


def _looks_shared(source: Path) -> bool:
    try:
        document: Any = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return False
    if not isinstance(document, list) or not document:
        return False
    first = document[0]
    return isinstance(first, dict) and "case_id" in first


def validate_cases(path: str | Path) -> CaseValidationSummary:
    """Validate one YAML file or a directory tree without contacting any service."""
    root = Path(path)
    summary = CaseValidationSummary()
    try:
        sources = _files(root)
    except ValueError as error:
        summary.issues.append(CaseValidationIssue(str(root), str(error)))
        return summary
    summary.files = len(sources)
    seen: dict[str, Path] = {}
    for source in sources:
        try:
            loaded = load_shared_cases(source) if _looks_shared(source) else load_cases(source)
            for item in loaded:
                case_id = str(getattr(item, "case_id", getattr(item, "id", "")))
                if case_id in seen:
                    summary.issues.append(CaseValidationIssue(str(source), f"重复用例 ID {case_id!r}，首次出现于 {seen[case_id]}"))
                else:
                    seen[case_id] = source
            summary.cases += len(loaded)
        except (CaseLoadError, SharedCaseError, OSError, yaml.YAMLError, ValidationError, ValueError) as error:
            summary.issues.append(CaseValidationIssue(str(source), str(error)))
    return summary
