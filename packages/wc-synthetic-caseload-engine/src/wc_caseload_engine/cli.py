"""``wc-caseload`` command line interface.

Phase A implements the commands that need no lifecycle machinery:
``seed --template`` and ``taxonomy-check`` are complete, ``validate --spec``
fully validates a caseload, and ``generate`` parses, validates and resolves the
whole caseload (including ``auto:`` derivation) before handing off to the
Phase B renderer.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
import structlog

from wc_caseload_engine import __version__
from wc_caseload_engine.seed_template import CASE_SEED_TEMPLATE, CASELOAD_SPEC_TEMPLATE
from wc_caseload_engine.seeds import (
    CaseloadSpec,
    CaseSeed,
    SeedError,
    load_caseload_spec,
    resolve_caseload,
)
from wc_caseload_engine.substrate import SubstrateUnavailableError, substrate_available
from wc_caseload_engine.taxonomy import (
    EXPECTED_SUBTYPE_COUNT,
    TaxonomySourceError,
    check_taxonomy_drift,
    effective_taxonomy,
)

log = structlog.get_logger(__name__)

PHASE_B_MESSAGE = (
    "Phase B: lifecycle machines, the renderer bridge and manifest writing are "
    "not implemented yet"
)


def _load_spec(spec_path: Path) -> CaseloadSpec:
    """Load and validate a caseload spec, converting seed errors to CLI errors."""
    try:
        return load_caseload_spec(spec_path)
    except SeedError as exc:
        raise click.ClickException(str(exc)) from exc


def _summarize(seed: CaseSeed) -> str:
    """One-line human summary of a resolved seed."""
    lifecycle = seed.lifecycle
    bits = [
        f"{seed.case_id:<24}",
        f"seed={seed.rng_seed:<10}",
        f"stage={lifecycle.target_stage:<16}",
        f"injury={seed.injury.type:<17}",
        f"claim={lifecycle.claim_response:<8}",
        f"resolution={lifecycle.resolution.type:<14}",
        f"liens={lifecycle.liens.count}",
        f"recon={'yes' if lifecycle.reconsideration.enabled else 'no'}",
    ]
    return " ".join(bits)


@click.group(name="wc-caseload", context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="wc-caseload")
def cli() -> None:
    """Seed-driven generator of synthetic CA workers' compensation case files."""


@cli.command()
@click.option(
    "--spec",
    "spec_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Caseload spec YAML (defaults + cases[] + auto:).",
)
@click.option(
    "--out",
    "out_dir",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Output directory; one folder per case is written beneath it.",
)
@click.option(
    "--seed",
    "seed_override",
    type=int,
    default=None,
    help="Override auto.rng_seed for this run (explicit case seeds are untouched).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Parse, validate and resolve the caseload, print the plan, write nothing.",
)
def generate(
    spec_path: Path, out_dir: Path, seed_override: int | None, dry_run: bool
) -> None:
    """Generate synthetic case files from a caseload spec."""
    spec = _load_spec(spec_path)
    if seed_override is not None and spec.auto is not None:
        spec = spec.model_copy(
            update={"auto": spec.auto.model_copy(update={"rng_seed": seed_override})}
        )
    seeds = resolve_caseload(spec)

    click.echo(f"caseload : {spec.caseload_id}")
    click.echo(f"spec     : {spec_path}")
    click.echo(f"cases    : {len(seeds)} ({len(spec.cases)} explicit, "
               f"{len(seeds) - len(spec.cases)} derived)")
    click.echo(f"out      : {out_dir}")
    for seed in seeds:
        click.echo(f"  {_summarize(seed)}")

    if dry_run:
        click.echo("dry-run: spec is valid; no files written")
        return

    raise NotImplementedError(PHASE_B_MESSAGE)


@cli.command("seed")
@click.option("--template", is_flag=True, help="Write an annotated example seed.")
@click.option(
    "--kind",
    type=click.Choice(["case", "caseload"]),
    default="case",
    show_default=True,
    help="Template flavour: one CaseSeed or a whole CaseloadSpec.",
)
@click.option(
    "--out",
    "out_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Destination file; prints to stdout when omitted.",
)
def seed_cmd(template: bool, kind: str, out_path: Path | None) -> None:
    """Write an annotated seed template covering every controllable field."""
    if not template:
        raise click.UsageError("nothing to do — pass --template (other modes are Phase B)")
    content = CASE_SEED_TEMPLATE if kind == "case" else CASELOAD_SPEC_TEMPLATE
    if out_path is None:
        click.echo(content, nl=False)
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    click.echo(f"wrote {kind} template: {out_path}")


@cli.command()
@click.option(
    "--spec",
    "spec_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Validate a caseload spec: schema, cross-field rules and control keys.",
)
@click.option(
    "--out",
    "out_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Validate generated manifests in an output directory (Phase B).",
)
def validate(spec_path: Path | None, out_dir: Path | None) -> None:
    """Validate a spec (schema + taxonomy keys) or a generated output tree."""
    if spec_path is None and out_dir is None:
        raise click.UsageError("pass --spec and/or --out")

    if spec_path is not None:
        spec = _load_spec(spec_path)
        seeds = resolve_caseload(spec)
        click.echo(f"schema   : OK ({len(seeds)} cases resolved from {spec_path})")
        problems = _validate_control_keys(seeds)
        if problems:
            for problem in problems:
                click.echo(f"  {problem}", err=True)
            raise click.ClickException(
                f"{len(problems)} document control key(s) are not valid taxonomy keys"
            )
        click.echo("controls : OK (all document control keys are valid taxonomy keys)")

    if out_dir is not None:
        raise NotImplementedError(PHASE_B_MESSAGE)


def _validate_control_keys(seeds: list[CaseSeed]) -> list[str]:
    """Check include_only/exclude/override keys against the effective taxonomy."""
    if not substrate_available():
        click.echo(
            "controls : SKIPPED (substrate unavailable — cannot resolve taxonomy keys)",
            err=True,
        )
        return []
    taxonomy = effective_taxonomy()
    problems: list[str] = []
    for seed in seeds:
        controls = seed.documents
        keys: list[tuple[str, str]] = []
        keys.extend(("documents.include_only", key) for key in controls.include_only)
        keys.extend(("documents.exclude", key) for key in controls.exclude)
        for override in controls.overrides:
            field = (
                "documents.overrides[].subtype"
                if override.subtype
                else "documents.overrides[].type"
            )
            keys.append((field, override.key))
        for field, key in keys:
            if taxonomy.is_type(key):
                continue
            if not taxonomy.is_renderable(key):
                problems.append(
                    f"{seed.case_id}: {field} = {key!r} is neither a document type nor a "
                    "known subtype"
                )
    return problems


@cli.command("taxonomy-check")
@click.option(
    "--classifier-path",
    "classifier_path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Adjudica-classifier checkout (defaults to WC_CASELOAD_CLASSIFIER / ~/projects).",
)
def taxonomy_check(classifier_path: Path | None) -> None:
    """Diff the engine taxonomy against the classifier source; nonzero on drift."""
    try:
        drift = check_taxonomy_drift(classifier_path)
    except (TaxonomySourceError, SubstrateUnavailableError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(drift.render())
    if drift.engine_count != EXPECTED_SUBTYPE_COUNT:
        click.echo(
            f"warning: engine taxonomy has {drift.engine_count} subtypes, expected "
            f"{EXPECTED_SUBTYPE_COUNT}",
            err=True,
        )
    if not drift.clean:
        sys.exit(1)


def main() -> None:
    """Console-script entry point."""
    cli(prog_name="wc-caseload")


if __name__ == "__main__":  # pragma: no cover
    main()
