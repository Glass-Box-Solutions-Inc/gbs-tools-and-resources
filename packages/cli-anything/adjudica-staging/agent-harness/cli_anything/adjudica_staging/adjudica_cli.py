#!/usr/bin/env python3
"""Adjudica Staging CLI — Manage and test Adjudica staging environments.

All commands support --json for machine-readable output.
"""
import sys
import os
import json
import subprocess
import click
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli_anything.adjudica_staging.core import auth as auth_mod
from cli_anything.adjudica_staging.core import document as doc_mod
from cli_anything.adjudica_staging.core import billing as bill_mod

# Global state
_json_output = False
_repl_mode = False

def output(data, message: str = ""):
    """Print output in JSON or human-readable format."""
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

def _print_dict(d: dict, indent: int = 0):
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

def _print_list(items: list, indent: int = 0):
    prefix = "  " * indent
    for i, item in enumerate(items):
        if isinstance(item, dict):
            click.echo(f"{prefix}[{i}]")
            _print_dict(item, indent + 1)
        else:
            click.echo(f"{prefix}- {item}")

def handle_error(func):
    """Decorator for consistent error handling."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if _json_output:
                click.echo(json.dumps({
                    "error": str(e),
                    "type": type(e).__name__,
                }))
            else:
                click.echo(f"Error: {e}", err=True)
            if not _repl_mode:
                sys.exit(1)
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper

@click.group()
@click.option("--json", "json_out", is_flag=True, help="Emit output as JSON")
def main(json_out):
    """Adjudica Staging CLI wrapper for Playwright-driven testing."""
    global _json_output
    _json_output = json_out

# ── Auth Commands ──────────────────────────────────────────────────────────

@main.group()
def auth():
    """Manage credentials and authentication."""
    pass

@auth.command(name="setup")
@click.option("--url", required=True, help="Base URL of staging site")
@click.option("--email", default="lawyer@adjudica.ai", help="Test user email")
@click.option("--password", default="password123", help="Test user password")
@click.option("--firm-slug", default="smith-associates", help="Test firm slug")
@handle_error
def auth_setup(url, email, password, firm_slug):
    """Configure staging credentials."""
    res = auth_mod.setup_config(url, email, password, firm_slug)
    output(res, "Staging environment configured successfully:")

@auth.command(name="login")
@click.option("--with-extension", is_flag=True, help="Load Claude Chrome Extension in headed mode")
@handle_error
def auth_login(with_extension):
    """Login and save storage state."""
    res = auth_mod.login(with_extension=with_extension)
    output(res, "Staging login complete:")

@auth.command(name="status")
@handle_error
def auth_status():
    """Check staging authentication status."""
    res = auth_mod.status()
    output(res, "Staging connection status:")

# ── Document Commands ──────────────────────────────────────────────────────

@main.group()
def document():
    """Document library and upload operations."""
    pass

@document.command(name="upload")
@click.option("--file", required=True, type=click.Path(exists=True), help="Local file path to upload")
@click.option("--matter-id", required=True, help="Target matter database ID")
@click.option("--firm-slug", help="Override default firm slug")
@click.option("--with-extension", is_flag=True, help="Load Claude Chrome Extension in headed mode")
@handle_error
def document_upload(file, matter_id, firm_slug, with_extension):
    """Upload a document to a specific matter on staging."""
    res = doc_mod.upload_document(file, matter_id, firm_slug, with_extension=with_extension)
    output(res, "Upload complete:")

@document.command(name="library")
@click.option("--firm-slug", help="Override default firm slug")
@click.option("--with-extension", is_flag=True, help="Load Claude Chrome Extension in headed mode")
@handle_error
def document_library(firm_slug, with_extension):
    """Verify document library page navigation."""
    res = doc_mod.navigate_to_library(firm_slug, with_extension=with_extension)
    output(res, "Navigation status:")

# ── Billing Commands ───────────────────────────────────────────────────────

@main.group()
def billing():
    """Billing and mailroom operations."""
    pass

@billing.command(name="mailroom")
@click.option("--tab", default="ready-for-review", help="Mailroom tab to select")
@click.option("--firm-slug", help="Override default firm slug")
@click.option("--with-extension", is_flag=True, help="Load Claude Chrome Extension in headed mode")
@handle_error
def billing_mailroom(tab, firm_slug, with_extension):
    """Verify mailroom queue page navigation."""
    res = bill_mod.navigate_to_mailroom(tab, firm_slug, with_extension=with_extension)
    output(res, "Navigation status:")

# ── Test Commands ──────────────────────────────────────────────────────────

@main.group()
def test():
    """Run E2E test suites."""
    pass

@test.command(name="run")
@click.option("--suite", default="staging", help="Test config name (production, real, staging, stress)")
@handle_error
def test_run(suite):
    """Execute Playwright E2E tests against staging."""
    # Find adjudica-ai-app repo path
    app_dir = "/home/sky/sky-pulse/data/repos/adjudica-ai-app"
    if not os.path.exists(app_dir):
        raise RuntimeError(f"adjudica-ai-app repo not found at {app_dir}")
        
    config_file = f"playwright.config.{suite}.ts"
    if not os.path.exists(os.path.join(app_dir, config_file)):
        config_file = "playwright.config.ts"
        
    cmd = ["npx", "playwright", "test", "--config", config_file]
    
    click.echo(f"Running Playwright tests in {app_dir} using config {config_file}...")
    res = subprocess.run(cmd, cwd=app_dir)
    
    res_data = {
        "exit_code": res.returncode,
        "success": res.returncode == 0,
        "config": config_file,
    }
    
    output(res_data, "Test run completed:")

if __name__ == "__main__":
    main()
