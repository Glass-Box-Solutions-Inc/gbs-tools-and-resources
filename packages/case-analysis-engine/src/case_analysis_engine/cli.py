"""Click CLI for normalization, integrity validation, analysis, and perspective views."""

from __future__ import annotations

from pathlib import Path

import click
import yaml

from case_analysis_engine import __version__
from case_analysis_engine.analysis import analyze_paths
from case_analysis_engine.input import normalize_paths
from case_analysis_engine.render import render_json, render_markdown
from case_analysis_engine.validation import validate_facts


def _paths(values: tuple[Path, ...]) -> list[Path]:
    if not values:
        raise click.UsageError("provide at least one extraction, manifest, or case_facts input")
    return list(values)


def _write_or_echo(content: str, out: Path | None) -> None:
    if out is None:
        click.echo(content, nl=False)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    click.echo(f"wrote: {out}")


@click.group(name="case-analysis", context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="case-analysis")
def cli() -> None:
    """Analyze supplied case facts without asserting unsourced legal conclusions."""


@cli.command()
@click.argument("inputs", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--format", "output_format", type=click.Choice(["json", "yaml"]), default="json", show_default=True)
def normalize(inputs: tuple[Path, ...], out: Path | None, output_format: str) -> None:
    """Normalize JSON/YAML claims into evidence-bearing facts."""
    facts = normalize_paths(_paths(inputs))
    payload = {"facts": [fact.as_dict() for fact in facts]}
    content = (
        yaml.safe_dump(payload, sort_keys=True, allow_unicode=False)
        if output_format == "yaml"
        else __import__("json").dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    )
    _write_or_echo(content, out)


@cli.command()
@click.argument("inputs", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), default=None)
def validate(inputs: tuple[Path, ...], out: Path | None) -> None:
    """Report conflicts, duplicates, missing provenance, and chronology questions."""
    findings = validate_facts(normalize_paths(_paths(inputs)))
    content = __import__("json").dumps(
        {"findings": [finding.as_dict() for finding in findings]}, indent=2, sort_keys=True
    ) + "\n"
    _write_or_echo(content, out)
    if any(finding.severity == "error" for finding in findings):
        raise click.exceptions.Exit(1)


@cli.command()
@click.argument("inputs", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--json-out", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--markdown-out", type=click.Path(dir_okay=False, path_type=Path), default=None)
def analyze(inputs: tuple[Path, ...], json_out: Path | None, markdown_out: Path | None) -> None:
    """Produce deterministic JSON and/or Markdown evidence reports."""
    report = analyze_paths(_paths(inputs))
    if json_out is None and markdown_out is None:
        click.echo(render_markdown(report), nl=False)
        return
    if json_out is not None:
        _write_or_echo(render_json(report), json_out)
    if markdown_out is not None:
        _write_or_echo(render_markdown(report), markdown_out)


@cli.command()
@click.argument("inputs", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--angle", type=click.Choice(["applicant", "defense", "neutral"]), default=None)
def angles(inputs: tuple[Path, ...], angle: str | None) -> None:
    """Show supplied-evidence observations from applicant, defense, and neutral viewpoints."""
    report = analyze_paths(_paths(inputs))
    selected = [item for item in report.angles if angle is None or item.name == angle]
    for item in selected:
        click.echo(f"{item.name}:")
        for observation in item.observations:
            click.echo(f"  - {observation}")
        click.echo(f"  - Caveat: {item.caveat}")
