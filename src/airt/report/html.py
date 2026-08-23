"""Self-contained HTML report rendering."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from airt.models import CaseResult, RunMetadata, RunSummary
from airt.quality_bridge import QualitySummary
from airt.report.presentation import (
    case_displays,
    category_label,
    metadata_display,
    severity_label,
)

_LEGACY_METADATA = RunMetadata(
    test_type="Not recorded in original results (legacy JSONL)",
    test_method="Not recorded in original results (legacy JSONL)",
)
_TEMPLATE_DIR = Path(__file__).with_name("templates")
_SEVERITY_WEIGHTS = {"critical": 8, "high": 4, "medium": 2, "low": 1}


def _metadata(results: Sequence[CaseResult], metadata: RunMetadata | None) -> RunMetadata:
    if metadata is not None:
        return metadata
    for result in results:
        if result.run_metadata is not None:
            return result.run_metadata
    return _LEGACY_METADATA


def _wire(value: object) -> str:
    return str(getattr(value, "value", value))


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_html(
    summary: RunSummary,
    results: Sequence[CaseResult],
    destination: Path,
    metadata: RunMetadata | None = None,
    quality: QualitySummary | None = None,
) -> None:
    """Render one UTF-8 HTML file with inline assets and escaped data."""

    environment = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(enabled_extensions=("j2", "html", "xml")),
        undefined=StrictUndefined,
    )
    category_rows = []
    for name, group in sorted(summary.by_category.items(), key=lambda item: (item[1].asr, item[0])):
        category_rows.append(
            {
                "name": category_label(name),
                "percent": _pct(group.asr),
                "width": f"{group.asr * 100:.2f}",
                "success": str(group.success),
                "fail": str(group.fail),
                "uncertain": str(group.uncertain),
                "error": str(group.error),
                "total": str(group.total),
            }
        )

    html = environment.get_template("report.html.j2").render(
        summary=summary,
        metadata=metadata_display(_metadata(results, metadata), results),
        asr_percent=_pct(summary.asr),
        asr_denominator=summary.success + summary.fail,
        risk_score=f"{summary.risk_score:.1f}/100",
        category_rows=category_rows,
        case_rows=case_displays(results),
        severities=[
            {"value": value, "label": severity_label(value)}
            for value in sorted(
                {
                    _wire(result.case.severity)
                    for result in results
                    if result.case is not None
                },
                key=lambda value: (-_SEVERITY_WEIGHTS.get(value, 0), value),
            )
        ],
        quality=quality.as_dict() if quality is not None else None,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")
