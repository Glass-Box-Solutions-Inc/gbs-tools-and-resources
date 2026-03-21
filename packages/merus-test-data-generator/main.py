"""
CLI entry point for MerusCase WC Test Data Generator.

Usage:
    python main.py generate                    # Generate data + PDFs (legacy 20 cases)
    python main.py generate --count 50         # Dynamic 50 cases via lifecycle engine
    python main.py generate --count 50 --seed 123
    python main.py generate --count 100 --stages balanced
    python main.py create                      # Create cases in MerusCase
    python main.py upload                      # Upload documents
    python main.py run-all                     # Full pipeline
    python main.py status                      # Show progress
    python main.py verify                      # Verify cases in MerusCase
    python main.py serve                       # Start FastAPI server (Phase 3)

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click
import structlog

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from config import AUDIT_DB_PATH, AUDIT_HMAC_KEY, DB_PATH, OUTPUT_DIR, DEFAULT_CASE_COUNT, MIN_CASE_COUNT, MAX_CASE_COUNT
from data.case_profile_generator import CaseConstraints, PRESETS
from orchestration.audit import PipelineAuditLogger
from orchestration.pipeline import Pipeline
from orchestration.progress_tracker import ProgressTracker

_SENSITIVE_KEYS = frozenset({
    "password", "secret", "token", "api_key", "credential",
    "authorization", "ssn", "access_token", "client_secret",
})


def _redact_sensitive_fields(logger, method_name, event_dict):
    """Structlog processor that redacts sensitive field values."""
    for key in event_dict:
        if any(s in key.lower() for s in _SENSITIVE_KEYS):
            event_dict[key] = "***REDACTED***"
    return event_dict


structlog.configure(
    processors=[
        _redact_sensitive_fields,
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),
)

logger = structlog.get_logger()


_audit = PipelineAuditLogger(db_path=AUDIT_DB_PATH, hmac_key=AUDIT_HMAC_KEY)


def _get_pipeline() -> tuple[Pipeline, ProgressTracker]:
    tracker = ProgressTracker()
    pipeline = Pipeline(tracker, audit=_audit)
    return pipeline, tracker


@click.group()
def cli():
    """MerusCase WC Test Data Generator — creates realistic test cases with documents."""
    pass


@cli.command()
@click.option("--count", "-n", type=int, default=None,
              help=f"Number of cases to generate ({MIN_CASE_COUNT}-{MAX_CASE_COUNT}). "
                   f"Omit for legacy 20 hardcoded profiles.")
@click.option("--seed", "-s", type=int, default=None,
              help="Random seed for reproducible generation (default: 42)")
@click.option("--stages", type=str, default=None,
              help="Stage distribution preset: balanced, early_stage, settlement_heavy, complex_litigation. "
                   "Or JSON dict e.g. '{\"intake\": 0.3, \"resolved\": 0.7}'")
@click.option("--constraints", type=str, default=None,
              help="JSON constraints e.g. '{\"min_surgery_cases\": 5, \"attorney_rate\": 0.8}'")
def generate(count: int | None, seed: int | None, stages: str | None, constraints: str | None):
    """Step 1+2: Generate case data and PDF documents.

    Without --count, generates the legacy 20 hardcoded case profiles.
    With --count N, uses the lifecycle engine for dynamic generation.
    """
    pipeline, tracker = _get_pipeline()

    # Parse stage distribution
    stage_dist = None
    if stages:
        if stages in PRESETS:
            stage_dist = PRESETS[stages]
            click.echo(f"Using preset: {stages}")
        else:
            try:
                stage_dist = json.loads(stages)
            except json.JSONDecodeError:
                click.echo(f"ERROR: Invalid --stages value. Use a preset name or valid JSON.", err=True)
                sys.exit(1)

    # Parse constraints
    case_constraints = None
    if constraints:
        try:
            case_constraints = CaseConstraints(**json.loads(constraints))
        except (json.JSONDecodeError, Exception) as e:
            click.echo(f"ERROR: Invalid --constraints JSON: {e}", err=True)
            sys.exit(1)

    # Validate count
    if count is not None:
        if count < MIN_CASE_COUNT or count > MAX_CASE_COUNT:
            click.echo(f"ERROR: --count must be between {MIN_CASE_COUNT} and {MAX_CASE_COUNT}", err=True)
            sys.exit(1)

    try:
        mode = "lifecycle engine" if count is not None else "legacy profiles"
        case_count = count if count is not None else 20
        click.echo(f"Step 1: Generating {case_count} cases via {mode}...")

        cases = pipeline.generate_data(
            count=count,
            seed=seed,
            stage_distribution=stage_dist,
            constraints=case_constraints,
        )
        click.echo(f"  Generated {len(cases)} cases with {sum(len(c.document_specs) for c in cases)} document specs")

        # Show stage breakdown
        stage_counts: dict[str, int] = {}
        for c in cases:
            stage_counts[c.litigation_stage.value] = stage_counts.get(c.litigation_stage.value, 0) + 1
        click.echo(f"  Stages: {dict(sorted(stage_counts.items()))}")

        # Show subtype count
        subtypes_used = set()
        for c in cases:
            for doc in c.document_specs:
                subtypes_used.add(doc.subtype.value)
        click.echo(f"  Distinct subtypes: {len(subtypes_used)}/188")

        click.echo("\nStep 2: Generating PDFs...")
        result = pipeline.generate_pdfs()
        click.echo(f"  Generated: {result['generated']}")
        click.echo(f"  Skipped (already done): {result['skipped']}")
        click.echo(f"  Errors: {result['errors']}")
        click.echo(f"\nPDFs saved to: {OUTPUT_DIR}")
    finally:
        tracker.close()


@cli.command()
@click.option("--dry-run", is_flag=True, help="Preview without creating in MerusCase")
def create(dry_run: bool):
    """Step 3: Create cases in MerusCase via browser automation."""
    pipeline, tracker = _get_pipeline()
    try:
        # Load data first
        click.echo("Loading case data...")
        pipeline.generate_data()

        click.echo("\nStep 3: Creating cases in MerusCase...")
        if dry_run:
            click.echo("  (DRY RUN — no cases will be created)")

        result = asyncio.run(pipeline.create_cases(dry_run=dry_run))
        click.echo(f"  Total: {result['total']}")
        click.echo(f"  Created: {result['created']}")
        click.echo(f"  Failed: {result['failed']}")
    finally:
        tracker.close()


@cli.command()
def upload():
    """Step 4: Upload documents to MerusCase via API."""
    pipeline, tracker = _get_pipeline()
    try:
        click.echo("Step 4: Uploading documents to MerusCase...")
        result = asyncio.run(pipeline.upload_documents())
        click.echo(f"  Cases processed: {result['cases_processed']}")
        click.echo(f"  Documents uploaded: {result['docs_uploaded']}")
        click.echo(f"  Documents failed: {result['docs_failed']}")
    finally:
        tracker.close()


@cli.command("run-all")
@click.option("--dry-run", is_flag=True, help="Preview without creating/uploading")
def run_all(dry_run: bool):
    """Run full pipeline: generate → create → upload."""
    pipeline, tracker = _get_pipeline()
    try:
        if dry_run:
            click.echo("DRY RUN MODE — no MerusCase changes will be made\n")

        result = asyncio.run(pipeline.run_all(dry_run=dry_run))

        click.echo("\n" + "=" * 50)
        click.echo("PIPELINE COMPLETE")
        click.echo("=" * 50)
        click.echo(f"  Cases generated: {result['data']['cases']}")
        click.echo(f"  PDFs: {result['pdfs']['generated']} generated, {result['pdfs']['errors']} errors")
        click.echo(f"  Cases created: {result['cases']['created']}/{result['cases']['total']}")
        click.echo(f"  Docs uploaded: {result['uploads']['docs_uploaded']}, {result['uploads']['docs_failed']} failed")
    finally:
        tracker.close()


@cli.command()
def status():
    """Show current progress."""
    tracker = ProgressTracker()
    try:
        summary = tracker.get_status_summary()
        if not summary["has_run"]:
            click.echo("No runs found. Run 'python main.py generate' to start.")
            return

        click.echo("=" * 50)
        click.echo("PIPELINE STATUS")
        click.echo("=" * 50)
        click.echo(f"  Run ID:      {summary['run_id']}")
        click.echo(f"  Status:      {summary['run_status']}")
        click.echo(f"  Started:     {summary['started_at']}")
        if summary["completed_at"]:
            click.echo(f"  Completed:   {summary['completed_at']}")
        click.echo()
        click.echo("Cases:")
        click.echo(f"  Total:       {summary['total_cases']}")
        click.echo(f"  Data gen:    {summary['cases_data_generated']}")
        click.echo(f"  PDFs gen:    {summary['cases_pdfs_generated']}")
        click.echo(f"  Created:     {summary['cases_created_in_merus']}")
        click.echo(f"  Completed:   {summary['cases_completed']}")
        click.echo(f"  Errors:      {summary['cases_errored']}")
        click.echo()
        click.echo("Documents:")
        click.echo(f"  Total:       {summary['total_docs']}")
        click.echo(f"  PDFs gen:    {summary['docs_pdf_generated']}")
        click.echo(f"  Uploaded:    {summary['docs_uploaded']}")

        # Show per-case breakdown
        click.echo()
        click.echo("-" * 50)
        click.echo(f"{'Case':<10} {'Applicant':<25} {'Stage':<15} {'Status':<12} {'Docs'}")
        click.echo("-" * 50)
        for case_row in tracker.get_all_cases():
            click.echo(
                f"{case_row['internal_id']:<10} "
                f"{case_row['applicant_name'][:24]:<25} "
                f"{case_row['litigation_stage']:<15} "
                f"{case_row['status']:<12} "
                f"{case_row['docs_uploaded']}/{case_row['total_docs']}"
            )
    finally:
        tracker.close()


@cli.command()
@click.option("--visual", is_flag=True, help="Open browser and take screenshots of each case page")
@click.option("--case-id", default=None, help="Verify a specific case (e.g. TC-001)")
def verify(visual: bool, case_id: str | None):
    """Verify cases in MerusCase — API check + optional browser screenshots."""
    tracker = ProgressTracker()
    try:
        cases = tracker.get_all_cases()
        created_cases = [c for c in cases if c["case_created"]]

        if case_id:
            created_cases = [c for c in created_cases if c["internal_id"] == case_id]

        if not created_cases:
            click.echo("No matching cases found in MerusCase.")
            return

        click.echo(f"Verifying {len(created_cases)} cases in MerusCase...\n")

        # API verification
        from config import MERUSCASE_ACCESS_TOKEN

        async def _verify():
            import httpx
            verified = 0
            failed = 0

            if not MERUSCASE_ACCESS_TOKEN:
                click.echo("  WARNING: No API token — skipping API verification")
            else:
                headers = {
                    "Authorization": f"Bearer {MERUSCASE_ACCESS_TOKEN}",
                    "Accept": "application/json",
                }
                async with httpx.AsyncClient(timeout=30) as client:
                    for case_row in created_cases:
                        mc_id = case_row["meruscase_id"]
                        try:
                            resp = await client.get(
                                f"https://api.meruscase.com/caseFiles/view/{mc_id}",
                                headers=headers,
                            )
                            if resp.status_code == 200:
                                data = resp.json().get("CaseFile", {})
                                name = data.get("name", "Unknown")
                                comments = data.get("comments", "")
                                custom = data.get("custom_data", "")
                                has_metadata = bool(comments or custom)
                                status_icon = "OK" if has_metadata else "NO METADATA"
                                click.echo(
                                    f"  {case_row['internal_id']} | MC ID {mc_id} | {name} | {status_icon}"
                                )
                                verified += 1
                            else:
                                click.echo(f"  {case_row['internal_id']} | MC ID {mc_id} | API ERROR {resp.status_code}")
                                failed += 1
                        except Exception as e:
                            click.echo(f"  {case_row['internal_id']} | MC ID {mc_id} | ERROR: {e}")
                            failed += 1

                click.echo(f"\nAPI verification: {verified}/{len(created_cases)} OK, {failed} failed")

            # Visual verification via browser
            if visual:
                click.echo(f"\nStarting browser visual verification...")
                from orchestration.visual_verifier import VisualVerifier

                async with VisualVerifier() as verifier:
                    case_infos = [
                        {
                            "meruscase_id": c["meruscase_id"],
                            "label": f"{c['internal_id']}_{c['applicant_name'].replace(' ', '_')}",
                        }
                        for c in created_cases
                    ]
                    results = await verifier.verify_all_cases(case_infos)

                    click.echo(f"\nScreenshots saved to: {verifier.screenshot_dir}")
                    for r in results:
                        status = "PASS" if r["success"] else f"FAIL: {r['error']}"
                        click.echo(f"  {r['case_label']}: {status} ({len(r['screenshots'])} screenshots)")

        asyncio.run(_verify())
    finally:
        tracker.close()


@cli.command()
@click.option("--verify-chain", "action", flag_value="verify", help="Verify HMAC chain integrity")
@click.option("--stats", "action", flag_value="stats", help="Show event counts by category")
@click.option("--recent", "recent_count", type=int, default=0, help="Show last N audit events")
def audit(action: str | None, recent_count: int):
    """SOC2 audit log management."""
    if action == "verify":
        result = _audit.verify_chain()
        if result["valid"]:
            click.echo(f"HMAC chain VALID ({result['total']} events)")
        else:
            click.echo(f"HMAC chain INVALID — {len(result['errors'])} error(s):")
            for err in result["errors"]:
                click.echo(f"  Event {err['event_id']} at {err.get('timestamp', 'N/A')}")
    elif action == "stats":
        stats = _audit.get_stats()
        click.echo("Audit Event Statistics:")
        for category, count in sorted(stats.items()):
            click.echo(f"  {category}: {count}")
    elif recent_count > 0:
        events = _audit.get_recent(recent_count)
        click.echo(f"Last {len(events)} audit events:")
        click.echo("-" * 80)
        for evt in events:
            click.echo(
                f"  [{evt['timestamp'][:19]}] {evt['event_category']}/{evt['event_type']} "
                f"— {evt['action']} ({evt['status']})"
            )
    else:
        # Default: show stats + verify
        stats = _audit.get_stats()
        result = _audit.verify_chain()
        click.echo("Audit Summary:")
        click.echo(f"  Total events: {stats.get('TOTAL', 0)}")
        for category, count in sorted(stats.items()):
            if category != "TOTAL":
                click.echo(f"  {category}: {count}")
        integrity = "VALID" if result["valid"] else f"INVALID ({len(result['errors'])} errors)"
        click.echo(f"  Chain integrity: {integrity}")


@cli.command()
@click.option("--port", type=int, default=5520, help="Port for FastAPI server (default: 5520)")
@click.option("--host", type=str, default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
def serve(port: int, host: str):
    """Start the FastAPI REST API server (Phase 3)."""
    try:
        import uvicorn
        from service.app import create_app
    except ImportError as e:
        click.echo(f"ERROR: FastAPI dependencies not installed. Run: pip install fastapi uvicorn sse-starlette")
        click.echo(f"  Missing: {e}")
        sys.exit(1)

    click.echo(f"Starting FastAPI server on {host}:{port}...")
    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    cli()
