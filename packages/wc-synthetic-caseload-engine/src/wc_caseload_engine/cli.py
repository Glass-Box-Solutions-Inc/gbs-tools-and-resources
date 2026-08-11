"""``wc-caseload`` command line interface.

Four commands:

* ``generate --spec S --out D`` — the whole pipeline: resolve the caseload
  (including ``auto:`` derivation), plan every case, render every document and
  write the manifests.
* ``seed --template`` — an annotated seed covering every controllable field.
* ``validate --spec S`` / ``--out D`` — schema and control keys before
  generation; taxonomy validity and checksums after it.
* ``taxonomy-check`` — drift against the classifier source; nonzero on drift.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import sys

# Before any other import, and deliberately not at the bottom of the import
# block: importing this package pulls in the substrate, and a fresh interpreter
# writes ``__pycache__`` directories into whatever it imports. Those writes land
# in the package and substrate *source* trees — outside ``--out``, and outside
# the guarantee this tool makes about where it writes. Setting the flag after
# the imports would be setting it one directory tree too late.
sys.dont_write_bytecode = True

from pathlib import Path

import click
import structlog

from wc_caseload_engine import __version__
from wc_caseload_engine.determinism import ensure_stable_hashing
from wc_caseload_engine.manifests import (
    CASELOAD_MANIFEST_NAME,
    generate_caseload,
    validate_output_tree,
)
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
from wc_caseload_engine.truth_manifest import TRUTH_DIR

log = structlog.get_logger(__name__)


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
        f"pov={seed.perspective:<9}",
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
@click.option(
    "--truth-manifest/--no-truth-manifest",
    "truth_manifest",
    default=True,
    show_default=True,
    help="Write scorer-only ground truth beneath the output truth directory.",
)
def generate(
    spec_path: Path,
    out_dir: Path,
    seed_override: int | None,
    dry_run: bool,
    truth_manifest: bool,
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
    click.echo(
        f"cases    : {len(seeds)} ({len(spec.cases)} explicit, "
        f"{len(seeds) - len(spec.cases)} derived)"
    )
    click.echo(f"out      : {out_dir}")
    for seed in seeds:
        click.echo(f"  {_summarize(seed)}")

    if dry_run:
        click.echo("dry-run: spec is valid; no files written")
        return

    try:
        results = generate_caseload(
            spec.caseload_id,
            seeds,
            out_dir,
            truth=truth_manifest,
        )
    except SubstrateUnavailableError as exc:
        raise click.ClickException(str(exc)) from exc

    total_documents = sum(result.document_count for result in results)
    formats: dict[str, int] = {}
    warnings = 0
    for result in results:
        warnings += len(result.plan.warnings)
        for render in result.renders:
            formats[render.doc_format] = formats.get(render.doc_format, 0) + 1

    click.echo("")
    click.echo(f"generated: {len(results)} cases, {total_documents} documents")
    for name, count in sorted(formats.items()):
        click.echo(f"  {name:<12} {count}")
    for result in results:
        click.echo(
            f"  {result.case_id:<24} {result.document_count:>4} docs  "
            f"liens={len(result.plan.lien_tracks)} "
            f"recon={result.plan.recon.outcome or '-'}"
        )
    if warnings:
        click.echo(f"warnings : {warnings} (see per-case manifest 'warnings')", err=True)
    click.echo(f"manifest : {out_dir / CASELOAD_MANIFEST_NAME}")
    if truth_manifest:
        click.echo(f"truth    : {out_dir / TRUTH_DIR}")


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
@click.option(
    "--allow-fallback",
    is_flag=True,
    help="Permit documents rendered by a fallback template (still reported).",
)
def validate(spec_path: Path | None, out_dir: Path | None, allow_fallback: bool) -> None:
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
        assertion_problems = _validate_assertion_coherence(seeds)
        if assertion_problems:
            for problem in assertion_problems:
                click.echo(f"  {problem}", err=True)
            raise click.ClickException(
                f"{len(assertion_problems)} medical-assertion incoherence problem(s); "
                "divergence from world truth is legal — these are internal contradictions"
            )

    if out_dir is not None:
        try:
            report = validate_output_tree(out_dir, allow_fallback=allow_fallback)
        except SubstrateUnavailableError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(report.render())
        if not report.ok:
            sys.exit(1)


def _validate_assertion_coherence(seeds: list[CaseSeed]) -> list[str]:
    """Run the §C referential validator for every assertion-bearing seed.

    The polarity rule applies here exactly as at generation time: assertion
    divergence from world truth is case content and passes; only internal
    incoherence — dangling references, contradictory lifecycles, impossible
    percentages — is reported. Skips cleanly without the substrate, which the
    world-truth derivation needs for the applicant's date of birth.
    """
    bearing = [seed for seed in seeds if seed.scenario.medical_assertions is not None]
    if not bearing:
        return []
    if not substrate_available():
        click.echo(
            "asserts  : SKIPPED (substrate unavailable — cannot derive the "
            "world-truth ledger)",
            err=True,
        )
        return []
    from wc_caseload_engine.medical_assertions import (
        MedicalAssertionError,
        assertion_context,
        derive_medical_assertions,
        project_medical_history,
        validate_medical_assertions,
    )
    from wc_caseload_engine.medical_history import derive_medical_history

    problems: list[str] = []
    for seed in bearing:
        try:
            history = derive_medical_history(seed)
            ledger = derive_medical_assertions(seed, history)
        except MedicalAssertionError as exc:
            problems.extend(f"{seed.case_id}: {line}" for line in str(exc).splitlines())
            continue
        context = assertion_context(seed)
        projection = project_medical_history(history, context.current_body_parts)
        problems.extend(
            f"{seed.case_id}: {problem}"
            for problem in validate_medical_assertions(context, projection, ledger)
        )
    if not problems:
        click.echo(
            f"asserts  : OK ({len(bearing)} assertion-bearing case(s) internally coherent)"
        )
    return problems


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
    """Console-script entry point.

    Pins ``PYTHONHASHSEED`` before anything else runs. The substrate's content
    pools order strings through ``set``, so without a fixed hash seed the same
    seed renders different documents in different processes. See
    :mod:`wc_caseload_engine.determinism`.
    """
    ensure_stable_hashing()
    cli(prog_name="wc-caseload")


if __name__ == "__main__":  # pragma: no cover
    main()
