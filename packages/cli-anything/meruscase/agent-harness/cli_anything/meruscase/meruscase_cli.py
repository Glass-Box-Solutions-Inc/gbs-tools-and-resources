"""
cli-anything-meruscase — Agent-native CLI for MerusCase.

Dual-mode: interactive REPL (default) + subcommand (scripting/pipelines).
All commands support --json for machine-readable output.

Usage:
    cli-anything-meruscase                          # REPL mode
    cli-anything-meruscase case list                # subcommand mode
    cli-anything-meruscase --json case list         # JSON output
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import click

from cli_anything.meruscase.core import activities
from cli_anything.meruscase.core import billing
from cli_anything.meruscase.core import cases
from cli_anything.meruscase.core import documents
from cli_anything.meruscase.core import parties
from cli_anything.meruscase.core.cases import CaseNotFoundError
from cli_anything.meruscase.core.session import (
    MerusCaseSession,
    load_token,
    save_token,
)
from cli_anything.meruscase.utils.repl_skin import ReplSkin

# ── Module-level globals ──────────────────────────────────────────────────────

_json_output: bool = False
_session: Optional[MerusCaseSession] = None
_repl_mode: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────


def get_session() -> MerusCaseSession:
    """Return the active MerusCaseSession, loading it from disk if needed.

    Returns:
        MerusCaseSession instance.
    """
    global _session
    if _session is None:
        _session = MerusCaseSession.load()
    return _session


def _print_dict(d: dict, indent: int = 0) -> None:
    """Recursively pretty-print a dict to stdout via click.echo.

    Args:
        d: Dictionary to print.
        indent: Current indentation level (2 spaces per level).
    """
    prefix = "  " * indent
    for k, v in d.items():
        if isinstance(v, dict):
            click.echo(f"{prefix}{k}:")
            _print_dict(v, indent + 1)
        elif isinstance(v, list):
            click.echo(f"{prefix}{k}:")
            _print_list(v, indent + 1)
        else:
            click.echo(f"{prefix}{k}: {v}")


def _print_list(items: list, indent: int = 0) -> None:
    """Recursively pretty-print a list to stdout via click.echo.

    Args:
        items: List to print.
        indent: Current indentation level.
    """
    prefix = "  " * indent
    for i, item in enumerate(items):
        if isinstance(item, dict):
            click.echo(f"{prefix}[{i}]")
            _print_dict(item, indent + 1)
        else:
            click.echo(f"{prefix}- {item}")


def output(data, message: str = "") -> None:
    """Emit command output in either JSON or human-readable form.

    When the global ``_json_output`` flag is set, the data is serialised to
    JSON and written to stdout.  Otherwise a human-readable representation is
    produced using click.echo.

    Args:
        data: The data to emit (dict, list, or scalar).
        message: Optional preamble shown only in human-readable mode.
    """
    if _json_output:
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        if message:
            click.echo(message)
        if isinstance(data, dict):
            _print_dict(data)
        elif isinstance(data, list):
            _print_list(data)
        else:
            click.echo(str(data))


def handle_error(func):
    """Decorator that catches exceptions and formats them consistently.

    In REPL mode exceptions are printed to stderr and execution continues.
    In non-REPL (subcommand) mode the process exits with code 1.

    If ``_json_output`` is active the error is emitted as a JSON object with
    ``error`` and ``type`` keys.
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CaseNotFoundError as exc:
            if _json_output:
                click.echo(
                    json.dumps({"error": str(exc), "type": "CaseNotFoundError"}),
                    err=False,
                )
            else:
                click.echo(f"Case not found: {exc}", err=True)
            if not _repl_mode:
                sys.exit(1)
        except Exception as exc:
            if _json_output:
                click.echo(
                    json.dumps({"error": str(exc), "type": type(exc).__name__}),
                    err=False,
                )
            else:
                click.echo(f"Error: {exc}", err=True)
            if not _repl_mode:
                sys.exit(1)

    # Preserve Click's introspection attributes.
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


# ── REPL ──────────────────────────────────────────────────────────────────────


def _start_repl(use_json: bool) -> None:
    """Start the interactive REPL loop.

    Displays the cli-anything banner, then enters a read-eval-print loop that
    dispatches each line of input through the Click command tree.

    Args:
        use_json: When True, prepend ``--json`` to every dispatched command so
                  all output is machine-readable JSON.
    """
    global _repl_mode
    _repl_mode = True

    skin = ReplSkin("meruscase", version="1.0.0")
    skin.print_banner()

    pt_session = skin.create_prompt_session()

    while True:
        try:
            line = skin.get_input(pt_session).strip()
            if not line:
                continue
            if line.lower() in ("quit", "exit", "q"):
                skin.print_goodbye()
                break
            if line.lower() in ("help", "?"):
                click.echo(cli.get_help(click.Context(cli)))
                continue

            args = line.split()
            if use_json:
                args = ["--json"] + args

            try:
                cli.main(args, standalone_mode=False)
            except click.exceptions.UsageError as exc:
                skin.error(str(exc))
            except SystemExit:
                pass
            except Exception as exc:
                skin.error(str(exc))

        except (EOFError, KeyboardInterrupt):
            skin.print_goodbye()
            break

    _repl_mode = False


# ── Root CLI group ─────────────────────────────────────────────────────────────


@click.group(
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cli(ctx: click.Context, use_json: bool) -> None:
    """cli-anything-meruscase — MerusCase agent-native CLI.

    Run without a subcommand to enter interactive REPL mode.
    """
    global _json_output
    _json_output = use_json
    ctx.ensure_object(dict)
    ctx.obj["use_json"] = use_json

    if ctx.invoked_subcommand is None:
        _start_repl(use_json)


# ── auth ──────────────────────────────────────────────────────────────────────


@cli.group()
def auth() -> None:
    """Authenticate with MerusCase (login, status, refresh)."""


@auth.command("login")
@handle_error
def auth_login() -> None:
    """Load or prompt for a MerusCase Bearer token."""
    token = load_token()

    if token:
        masked = token[:8] + "..." + token[-8:] if len(token) > 16 else token
        output(
            {"status": "authenticated", "source": "GCP Secret Manager / env / file"},
            f"Token loaded: {masked}",
        )
        return

    click.echo("No token found in GCP Secret Manager or environment.")
    token = click.prompt("Paste your MerusCase Bearer token", hide_input=True)
    save_token(token)

    # Update in-memory session token.
    sess = get_session()
    sess.set_token(token)

    output({"status": "authenticated", "source": "user-provided"})


@auth.command("status")
@handle_error
def auth_status() -> None:
    """Show current authentication status."""
    token = load_token()

    if token:
        masked = token[:8] + "..." + token[-8:] if len(token) > 16 else token
        output(
            {
                "status": "authenticated",
                "token_preview": masked,
                "source": "GCP Secret Manager / env / file",
            }
        )
    else:
        output({"status": "unauthenticated"})


@auth.command("refresh")
@handle_error
def auth_refresh() -> None:
    """Force-reload the Bearer token from GCP Secret Manager."""
    # Bust the in-process cache so load_token() re-queries GCP.
    import cli_anything.meruscase.core.session as _session_mod

    _session_mod._token_cache = None
    _session_mod._gcp_available = None

    token = load_token()
    if not token:
        output({"status": "error", "message": "No token found after refresh"})
        if not _repl_mode:
            sys.exit(1)
        return

    sess = get_session()
    sess.set_token(token)

    output({"status": "refreshed"})


# ── case ──────────────────────────────────────────────────────────────────────


@cli.group()
def case() -> None:
    """Case operations (list, find, get, create)."""


@case.command("list")
@click.option("--status", "case_status", default=None, help="Filter by status (e.g. Active, Closed)")
@click.option("--type", "case_type", default=None, help="Filter by type (e.g. Workers Compensation)")
@click.option("--limit", default=100, show_default=True, help="Maximum results to return")
@handle_error
def case_list(case_status: Optional[str], case_type: Optional[str], limit: int) -> None:
    """List cases, optionally filtered by status and/or type."""
    sess = get_session()
    client = sess.get_client()
    result = asyncio.run(
        cases.list_cases(client, case_status=case_status, case_type=case_type, limit=limit)
    )

    if _json_output:
        output(result)
    else:
        click.echo(f"Found {len(result)} case(s):")
        for c in result:
            cid = c.get("id", "?")
            name = c.get("primary_party_name") or c.get("name") or "Unknown"
            status = c.get("status") or c.get("case_status") or ""
            click.echo(f"  [{cid}] {name} ({status})")


@case.command("find")
@click.argument("search")
@click.option("--limit", default=50, show_default=True, help="Max cases to scan")
@handle_error
def case_find(search: str, limit: int) -> None:
    """Find a case by file number or party name (fuzzy match)."""
    sess = get_session()
    client = sess.get_client()
    result = asyncio.run(cases.find_case(client, search, limit=limit))
    output(result)


@case.command("get")
@click.argument("case_id", type=int)
@handle_error
def case_get(case_id: int) -> None:
    """Fetch full details for a case by its numeric ID."""
    sess = get_session()
    client = sess.get_client()
    result = asyncio.run(cases.get_case(client, case_id))
    output(result)


@case.command("create")
@click.option("--name", required=True, help="Party name in LASTNAME, FIRSTNAME format")
@click.option("--type", "case_type", default="Workers Compensation", show_default=True,
              help="Case type")
@click.option("--date", "date_opened", default=None, help="Date opened MM/DD/YYYY")
@handle_error
def case_create(name: str, case_type: str, date_opened: Optional[str]) -> None:
    """Create a new MerusCase case via browser automation."""
    result = asyncio.run(
        cases.create_case(party_name=name, case_type=case_type, date_opened=date_opened)
    )
    output(result)


# ── billing ───────────────────────────────────────────────────────────────────


@cli.group("billing")
def billing_group() -> None:
    """Billing operations (bill-time, add-cost, summary, codes)."""


@billing_group.command("bill-time")
@click.option("--case", "case_id", type=int, required=True, help="Case ID")
@click.option("--hours", type=float, required=True, help="Time billed in hours")
@click.option("--desc", "description", required=True, help="Description of work")
@click.option("--subject", default=None, help="Short subject line (auto-derived if omitted)")
@click.option("--type-id", "activity_type_id", type=int, default=None,
              help="Activity type ID")
@click.option("--code-id", "billing_code_id", type=int, default=None,
              help="Billing code ID")
@handle_error
def billing_bill_time(
    case_id: int,
    hours: float,
    description: str,
    subject: Optional[str],
    activity_type_id: Optional[int],
    billing_code_id: Optional[int],
) -> None:
    """Bill attorney time to a case."""
    sess = get_session()
    client = sess.get_client()
    result = asyncio.run(
        billing.bill_time(
            client,
            case_id,
            hours,
            description,
            subject=subject,
            activity_type_id=activity_type_id,
            billing_code_id=billing_code_id,
        )
    )
    output(result)


@billing_group.command("add-cost")
@click.option("--case", "case_id", type=int, required=True, help="Case ID")
@click.option("--amount", type=float, required=True, help="Dollar amount")
@click.option("--desc", "description", required=True, help="Description of cost")
@click.option(
    "--type", "ledger_type",
    type=click.Choice(["fee", "cost", "expense"]),
    default="cost",
    show_default=True,
    help="Ledger entry type",
)
@handle_error
def billing_add_cost(
    case_id: int,
    amount: float,
    description: str,
    ledger_type: str,
) -> None:
    """Add a direct cost/fee/expense to a case."""
    sess = get_session()
    client = sess.get_client()
    result = asyncio.run(
        billing.add_cost(client, case_id, amount, description, ledger_type=ledger_type)
    )
    output(result)


@billing_group.command("summary")
@click.option("--case", "case_id", type=int, required=True, help="Case ID")
@click.option("--start", "start_date", default=None, help="Start date YYYY-MM-DD")
@click.option("--end", "end_date", default=None, help="End date YYYY-MM-DD")
@handle_error
def billing_summary(
    case_id: int,
    start_date: Optional[str],
    end_date: Optional[str],
) -> None:
    """Get billing summary with totals for a case."""
    sess = get_session()
    client = sess.get_client()
    result = asyncio.run(
        billing.get_billing_summary(client, case_id, start_date=start_date, end_date=end_date)
    )
    output(result)


@billing_group.command("codes")
@handle_error
def billing_codes() -> None:
    """Fetch available billing codes."""
    sess = get_session()
    client = sess.get_client()
    result = asyncio.run(billing.get_billing_codes(client))
    output(result)


# ── activity ──────────────────────────────────────────────────────────────────


@cli.group()
def activity() -> None:
    """Activity operations (list, add-note, types)."""


@activity.command("list")
@click.option("--case", "case_id", type=int, required=True, help="Case ID")
@click.option("--limit", default=100, show_default=True, help="Maximum results")
@handle_error
def activity_list(case_id: int, limit: int) -> None:
    """List activities and notes for a case."""
    sess = get_session()
    client = sess.get_client()
    result = asyncio.run(activities.get_activities(client, case_id, limit=limit))

    if _json_output:
        output(result)
    else:
        click.echo(f"Found {len(result)} activity/activities for case {case_id}:")
        for act in result:
            aid = act.get("id", "?")
            subject = act.get("subject") or act.get("description") or ""
            click.echo(f"  [{aid}] {subject}")


@activity.command("add-note")
@click.option("--case", "case_id", type=int, required=True, help="Case ID")
@click.option("--subject", required=True, help="Note subject line")
@click.option("--desc", "description", default=None, help="Detailed note body")
@click.option("--type-id", "activity_type_id", type=int, default=None,
              help="Activity type ID")
@handle_error
def activity_add_note(
    case_id: int,
    subject: str,
    description: Optional[str],
    activity_type_id: Optional[int],
) -> None:
    """Add a non-billable note/activity to a case."""
    sess = get_session()
    client = sess.get_client()
    result = asyncio.run(
        activities.add_note(
            client,
            case_id,
            subject,
            description=description,
            activity_type_id=activity_type_id,
        )
    )
    output(result)


@activity.command("types")
@handle_error
def activity_types() -> None:
    """Fetch available activity types."""
    sess = get_session()
    client = sess.get_client()
    result = asyncio.run(activities.get_activity_types(client))
    output(result)


# ── document ──────────────────────────────────────────────────────────────────


@cli.group()
def document() -> None:
    """Document operations (upload, list)."""


@document.command("upload")
@click.option("--case", "case_id", type=int, required=True, help="Case ID")
@click.option(
    "--file", "file_path",
    type=click.Path(exists=True, dir_okay=False, readable=True),
    required=True,
    help="Path to file to upload",
)
@click.option("--desc", "description", default="", help="Document description")
@click.option("--folder-id", type=int, default=None, help="Target folder ID")
@handle_error
def document_upload(
    case_id: int,
    file_path: str,
    description: str,
    folder_id: Optional[int],
) -> None:
    """Upload a document file to a case."""
    sess = get_session()
    client = sess.get_client()
    result = asyncio.run(
        documents.upload_document(
            client,
            case_id,
            file_path,
            description=description,
            folder_id=folder_id,
        )
    )
    output(result)


@document.command("list")
@click.option("--case", "case_id", type=int, required=True, help="Case ID")
@handle_error
def document_list(case_id: int) -> None:
    """List documents associated with a case."""
    sess = get_session()
    client = sess.get_client()
    result = asyncio.run(documents.list_documents(client, case_id))

    if _json_output:
        output(result)
    else:
        click.echo(f"Found {len(result)} document(s) for case {case_id}:")
        for doc in result:
            did = doc.get("id", "?")
            name = doc.get("filename") or doc.get("name") or doc.get("description") or "?"
            click.echo(f"  [{did}] {name}")


# ── party ─────────────────────────────────────────────────────────────────────


@cli.group()
def party() -> None:
    """Party operations (list, add)."""


@party.command("list")
@click.option("--case", "case_id", type=int, required=True, help="Case ID")
@handle_error
def party_list(case_id: int) -> None:
    """List all parties for a case."""
    sess = get_session()
    client = sess.get_client()
    result = asyncio.run(parties.get_parties(client, case_id))

    if _json_output:
        output(result)
    else:
        click.echo(f"Found {len(result)} party/parties for case {case_id}:")
        for p in result:
            pid = p.get("id", "?")
            ptype = p.get("party_type") or p.get("type") or ""
            name = p.get("name") or p.get("company_name") or ""
            click.echo(f"  [{pid}] {ptype}: {name}")


@party.command("add")
@click.option("--case", "case_id", type=int, required=True, help="Case ID")
@click.option("--type", "party_type", required=True, help="Party type (e.g. Employer)")
@click.option("--company", "company_name", default=None, help="Company name")
@click.option("--notes", default=None, help="Optional notes")
@handle_error
def party_add(
    case_id: int,
    party_type: str,
    company_name: Optional[str],
    notes: Optional[str],
) -> None:
    """Add a party to a case."""
    sess = get_session()
    client = sess.get_client()
    result = asyncio.run(
        parties.add_party(
            client,
            case_id,
            party_type,
            company_name=company_name,
            notes=notes,
        )
    )
    output(result)


# ── session ───────────────────────────────────────────────────────────────────


@cli.group()
def session() -> None:
    """Session operations (undo, redo, status)."""


@session.command("undo")
@handle_error
def session_undo() -> None:
    """Undo the most recent state-mutating operation."""
    sess = get_session()
    description = sess.undo()
    if description:
        output({"undone": description})
    else:
        output({"message": "Nothing to undo"})


@session.command("redo")
@handle_error
def session_redo() -> None:
    """Re-apply the most recently undone operation."""
    sess = get_session()
    description = sess.redo()
    if description:
        output({"redone": description})
    else:
        output({"message": "Nothing to redo"})


@session.command("status")
@handle_error
def session_status() -> None:
    """Show current session status."""
    sess = get_session()
    token = load_token()
    status_data = {
        "token_present": token is not None,
        "undo_stack_depth": len(sess._undo_stack),
        "redo_stack_depth": len(sess._redo_stack),
        "modified": sess.is_modified,
    }
    output(status_data)


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point for the cli-anything-meruscase command."""
    cli()


if __name__ == "__main__":
    main()
