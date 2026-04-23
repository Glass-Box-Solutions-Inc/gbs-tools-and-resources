"""
CLI entry point — claims-gen command.

Phase 2: generate outputs JSON + optional ZIP with PDFs; batch command added.
Phase 4: seed command — seeds a generated ClaimCase into a running AdjudiCLAIMS instance.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import asyncio
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
@click.version_option(version="0.2.0", prog_name="claims-gen")
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
    help="Output file path for JSON (default: stdout)",
)
@click.option(
    "--zip-output",
    default=None,
    type=click.Path(),
    help="Output path for ZIP archive with PDFs (optional)",
)
@click.option(
    "--pretty/--compact",
    default=True,
    show_default=True,
    help="Pretty-print JSON output",
)
@click.option(
    "--no-pdfs",
    is_flag=True,
    default=False,
    help="Skip PDF generation (JSON-only mode, Phase 1 behavior)",
)
def generate(
    scenario: str,
    seed: int,
    output: str | None,
    zip_output: str | None,
    pretty: bool,
    no_pdfs: bool,
) -> None:
    """Generate a single claims case and output JSON (+ optional PDF ZIP)."""
    try:
        case = build_case(scenario_slug=scenario, seed=seed, generate_pdfs=not no_pdfs)
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
        click.echo(f"JSON written to {output}", err=True)
    else:
        click.echo(json_str)

    # Optionally export ZIP
    if zip_output and not no_pdfs:
        from claims_generator.exporter import export_case_to_zip

        zip_bytes = export_case_to_zip(case)
        with open(zip_output, "wb") as f:
            f.write(zip_bytes)
        click.echo(f"ZIP written to {zip_output} ({len(zip_bytes):,} bytes)", err=True)


@cli.command()
@click.option(
    "--scenario",
    default="standard_claim",
    show_default=True,
    help="Scenario slug for all cases in the batch",
)
@click.option(
    "--count",
    default=5,
    show_default=True,
    type=int,
    help="Number of cases to generate",
)
@click.option(
    "--seed-start",
    default=0,
    show_default=True,
    type=int,
    help="Starting seed (incremented by 1 for each case)",
)
@click.option(
    "--workers",
    default=4,
    show_default=True,
    type=int,
    help="Number of parallel worker threads",
)
@click.option(
    "--output-dir",
    default=None,
    type=click.Path(),
    help="Directory to write per-case JSON files",
)
@click.option(
    "--zip-output",
    default=None,
    type=click.Path(),
    help="Output path for batch ZIP archive with all PDFs",
)
@click.option(
    "--no-pdfs",
    is_flag=True,
    default=False,
    help="Skip PDF generation (JSON-only mode)",
)
def batch(
    scenario: str,
    count: int,
    seed_start: int,
    workers: int,
    output_dir: str | None,
    zip_output: str | None,
    no_pdfs: bool,
) -> None:
    """Generate a batch of claims cases in parallel."""
    import os

    from claims_generator.batch_builder import build_batch_simple
    from claims_generator.exporter import export_batch_to_zip

    seed_end = seed_start + count - 1
    click.echo(
        f"Generating {count} cases (scenario={scenario}, seeds={seed_start}–{seed_end})",
        err=True,
    )

    cases = build_batch_simple(
        count=count,
        scenario_slug=scenario,
        seed_start=seed_start,
        max_workers=workers,
        generate_pdfs=not no_pdfs,
    )

    click.echo(f"Generated {len(cases)} cases successfully", err=True)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        for case in cases:
            path = os.path.join(output_dir, f"{case.case_id}.json")
            data = case.model_dump_json_safe()
            with open(path, "w") as f:
                json.dump(data, f, indent=2, cls=DateEncoder)
        click.echo(f"JSON files written to {output_dir}/", err=True)

    if zip_output and not no_pdfs:
        zip_bytes = export_batch_to_zip(cases)
        with open(zip_output, "wb") as f:
            f.write(zip_bytes)
        click.echo(f"Batch ZIP written to {zip_output} ({len(zip_bytes):,} bytes)", err=True)

    # Summary to stdout
    summary = [
        {
            "case_id": c.case_id,
            "scenario_slug": c.scenario_slug,
            "seed": c.seed,
            "document_count": len(c.document_events),
        }
        for c in cases
    ]
    click.echo(json.dumps(summary, indent=2))


@cli.command()
@click.option(
    "--scenario",
    default="standard_claim",
    show_default=True,
    help="Scenario slug to generate and seed",
)
@click.option(
    "--seed",
    default=42,
    show_default=True,
    type=int,
    help="Random seed for reproducibility",
)
@click.option(
    "--env",
    default="staging",
    show_default=True,
    type=click.Choice(["staging", "production"], case_sensitive=False),
    help="Target environment",
)
@click.option(
    "--url",
    default=None,
    envvar="ADJUDICLAIMS_URL",
    help="AdjudiCLAIMS base URL (overrides ADJUDICLAIMS_URL env var)",
)
@click.option(
    "--email",
    default=None,
    envvar="ADJUDICLAIMS_EMAIL",
    help="Login email (overrides ADJUDICLAIMS_EMAIL env var)",
)
@click.option(
    "--password",
    default=None,
    envvar="ADJUDICLAIMS_PASSWORD",
    help="Login password (overrides ADJUDICLAIMS_PASSWORD env var)",
)
def seed(
    scenario: str,
    seed: int,
    env: str,
    url: str | None,
    email: str | None,
    password: str | None,
) -> None:
    """Generate a case and seed it into a running AdjudiCLAIMS instance.

    Credentials are resolved from CLI flags → env vars → GCP Secret Manager.
    """
    from claims_generator.integrations.adjudiclaims_client import AdjudiClaimsClient
    from claims_generator.integrations.gcp_secrets import (
        get_adjudiclaims_email,
        get_adjudiclaims_password,
        get_adjudiclaims_url,
    )

    # Resolve credentials
    try:
        resolved_url = url or get_adjudiclaims_url()
        resolved_email = email or get_adjudiclaims_email()
        resolved_password = password or get_adjudiclaims_password()
    except (ValueError, RuntimeError) as exc:
        click.echo(f"Error resolving credentials: {exc}", err=True)
        sys.exit(1)

    # Generate the case (with PDFs so documents can be uploaded)
    click.echo(f"Generating case: scenario={scenario} seed={seed}", err=True)
    try:
        case = build_case(scenario_slug=scenario, seed=seed, generate_pdfs=True)
    except KeyError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    click.echo(
        f"Generated {len(case.document_events)} documents — seeding to {env} ({resolved_url})",
        err=True,
    )

    async def _run() -> None:
        async with AdjudiClaimsClient(base_url=resolved_url) as client:
            await client.login(email=resolved_email, password=resolved_password)
            result = await client.seed_case(case=case, env=env)
        click.echo(
            json.dumps(
                {
                    "claim_id": result.claim_id,
                    "claim_number": result.claim_number,
                    "documents_uploaded": result.documents_uploaded,
                    "document_ids": result.document_ids,
                },
                indent=2,
            )
        )

    asyncio.run(_run())


@cli.command()
def scenarios() -> None:
    """List all available scenario presets."""
    presets = list_scenarios()
    for p in presets:
        click.echo(f"  {p.slug:20s}  {p.display_name}")
        click.echo(f"    {p.description}")
        click.echo(f"    Docs: {p.expected_doc_min}–{p.expected_doc_max}")
        click.echo()
