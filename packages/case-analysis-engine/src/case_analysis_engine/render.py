"""Canonical JSON and human-readable Markdown renderers for an analysis report."""

from __future__ import annotations

import json
from collections import Counter

from case_analysis_engine.models import AnalysisReport


def render_json(report: AnalysisReport) -> str:
    """Render stable, newline-terminated JSON suitable for a reproducible pipeline artifact."""
    return json.dumps(report.as_dict(), indent=2, sort_keys=True, ensure_ascii=True, default=str) + "\n"


def render_markdown(report: AnalysisReport) -> str:
    """Render a stable, intentionally caveated report for a human reviewer."""
    counts = Counter(finding.severity for finding in report.findings)
    lines = [
        "# Case analysis report",
        "",
        f"> {report.caveat}",
        "",
        "## Record summary",
        "",
        f"- Normalized facts: {len(report.facts)}",
        f"- Findings: {counts['error']} error(s), {counts['warning']} warning(s), {counts['info']} info note(s)",
        "",
        "## Analysis domains",
        "",
        "| Domain | Facts | Average confidence | Findings |",
        "| --- | ---: | ---: | ---: |",
    ]
    for data in report.domains.values():
        confidence = data["averageConfidence"]
        rendered_confidence = "n/a" if confidence is None else f"{confidence:.3f}"
        lines.append(
            f"| {data['label']} | {data['factCount']} | {rendered_confidence} | {len(data['findingIds'])} |"
        )
    lines.extend(["", "## Integrity findings", ""])
    if report.findings:
        for finding in report.findings:
            refs = ", ".join(finding.fact_ids) or "none"
            lines.append(f"- `{finding.severity}` `{finding.code}`: {finding.message} Facts: {refs}.")
    else:
        lines.append("- No conflicts, duplicates, missing evidence, or chronology questions detected.")
    lines.extend(["", "## Chronology", ""])
    if report.chronology:
        for event in report.chronology:
            lines.append(f"- {event['date']}: `{event['field']}` ({event['factId']})")
    else:
        lines.append("- No parseable, explicitly named date facts were supplied.")
    lines.extend(["", "## Perspectives", ""])
    for angle in report.angles:
        lines.extend([f"### {angle.name.title()}", ""])
        lines.extend(f"- {observation}" for observation in angle.observations)
        lines.extend([f"- Caveat: {angle.caveat}", ""])
    return "\n".join(lines).rstrip() + "\n"
