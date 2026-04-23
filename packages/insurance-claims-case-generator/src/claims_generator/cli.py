"""
CLI entry point — claims-gen command.

Phase 1: generate command outputs JSON to stdout or file.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import json
import sys
from datetime import date
from typing import Any

import click

from claims_generator.case_builder import build_case
from claims_generator.scenarios.registry import list_scenarios


class DateEncoder(json.JSONEncoder):
    """JSON encoder that handles date objects and bytes."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return ""  # Never serialize PDF bytes
        return super().default(obj)


@click.group()
@click.version_option(version="0.1.0", prog_name="claims-gen")
def cli() -> None:
    """Insurance Claims Case Generator — synthetic CA Workers' Compensation cases."""


@cli.command()
@click.option(
    "--scenario",
    default="standard_claim",
    show_default=True,
    help="Scenario slug (standard_claim | litigated_qme | denied_claim)",
)
@click.option(
    "--seed",
    default=42,
    show_default=True,
    type=int,
    help="Random seed for reproducibility",
)
@click.option(
    "--output",
    default=None,
    type=click.Path(),
    help="Output file path (default: stdout)",
)
@click.option(
    "--pretty/--compact",
    default=True,
    show_default=True,
    help="Pretty-print JSON output",
)
def generate(scenario: str, seed: int, output: str | None, pretty: bool) -> None:
    """Generate a single claims case and output JSON."""
    try:
        case = build_case(scenario_slug=scenario, seed=seed)
    except KeyError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Produce JSON-safe dict (no pdf_bytes)
    data = case.model_dump_json_safe()

    indent = 2 if pretty else None
    json_str = json.dumps(data, indent=indent, cls=DateEncoder)

    if output:
        with open(output, "w") as f:
            f.write(json_str)
        click.echo(f"Written to {output}", err=True)
    else:
        click.echo(json_str)


@cli.command()
def scenarios() -> None:
    """List all available scenario presets."""
    presets = list_scenarios()
    for p in presets:
        click.echo(f"  {p.slug:20s}  {p.display_name}")
        click.echo(f"    {p.description}")
        click.echo(f"    Docs: {p.expected_doc_min}–{p.expected_doc_max}")
        click.echo()
