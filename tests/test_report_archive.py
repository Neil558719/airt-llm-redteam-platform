from __future__ import annotations

from datetime import datetime, timezone

import pytest

import airt.report.archive as archive_module
from airt.report.archive import archive_reports


def test_archive_reports_preserves_exact_jsonl_and_artifacts(summary_and_results, tmp_path):
    summary, results = summary_and_results
    source = b'{"case_id":"source"}\n'

    archive = archive_reports(summary, results, source, tmp_path)

    assert (archive / "results.jsonl").read_bytes() == source
    assert (archive / "report.json").is_file()
    assert (archive / "report.html").is_file()
    assert archive.parent == tmp_path / "archive"


def test_archive_reports_avoids_same_timestamp_collisions(summary_and_results, tmp_path, monkeypatch):
    summary, results = summary_and_results
    monkeypatch.setattr(
        archive_module,
        "_utc_now",
        lambda: datetime(2026, 8, 19, 10, 30, 15, 123456, tzinfo=timezone.utc),
    )

    first = archive_reports(summary, results, b"first\n", tmp_path)
    second = archive_reports(summary, results, b"second\n", tmp_path)

    assert first.name == "20260819T103015123456Z"
    assert second.name == "20260819T103015123456Z-01"
    assert (first / "results.jsonl").read_bytes() == b"first\n"
    assert (second / "results.jsonl").read_bytes() == b"second\n"


def test_archive_reports_removes_partial_directory_when_rendering_fails(
    summary_and_results, tmp_path, monkeypatch
):
    summary, results = summary_and_results

    def fail_render(*args, **kwargs):
        raise RuntimeError("render failure")

    monkeypatch.setattr(archive_module, "render_html", fail_render)

    with pytest.raises(RuntimeError, match="render failure"):
        archive_reports(summary, results, b"source\n", tmp_path)

    archive_root = tmp_path / "archive"
    assert not archive_root.exists() or not list(archive_root.iterdir())
