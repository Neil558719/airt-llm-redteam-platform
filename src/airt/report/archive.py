"""Immutable timestamped report archives for reproducible run history."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil

from airt.models import CaseResult, RunMetadata, RunSummary
from airt.report.html import render_html
from airt.report.json_report import write_json
from airt.quality_bridge import QualitySummary


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _archive_name() -> str:
    return _utc_now().strftime("%Y%m%dT%H%M%S%fZ")


def _reserve_archive(directory: Path) -> Path:
    """Create and return a unique archive directory without overwriting history."""

    root = directory / "archive"
    root.mkdir(parents=True, exist_ok=True)
    stem = _archive_name()
    for suffix in range(10_000):
        name = stem if suffix == 0 else f"{stem}-{suffix:02d}"
        candidate = root / name
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise RuntimeError(f"could not reserve a unique report archive under {root}")


def archive_reports(
    summary: RunSummary,
    results: list[CaseResult],
    source_jsonl: bytes,
    directory: Path,
    *,
    metadata: RunMetadata | None = None,
    quality: QualitySummary | None = None,
) -> Path:
    """Archive one immutable JSONL/JSON/HTML report bundle.

    The archive is removed if rendering fails, so callers never advertise a
    partial historical report as a completed one.
    """

    archive = _reserve_archive(directory)
    try:
        (archive / "results.jsonl").write_bytes(source_jsonl)
        write_json(summary, results, archive / "report.json", metadata=metadata, quality=quality)
        render_html(summary, results, archive / "report.html", metadata=metadata, quality=quality)
    except Exception:
        shutil.rmtree(archive, ignore_errors=True)
        raise
    return archive
