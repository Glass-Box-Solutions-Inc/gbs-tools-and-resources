"""Billing operations on Adjudica Staging."""
import json
import subprocess
from pathlib import Path
from cli_anything.adjudica_staging.core.auth import get_config, AUTH_STATE_FILE

def navigate_to_mailroom(tab: str = "ready-for-review", firm_slug: str = None, with_extension: bool = False) -> dict:
    """Navigate to the mailroom page."""
    cfg = get_config()
    slug = firm_slug or cfg.get("firm-slug") or cfg.get("firm_slug") or "smith-associates"
    
    pkg_dir = Path(__file__).parent.parent
    pw_script = pkg_dir / "utils" / "adjudica_playwright.js"
    
    cmd = [
        "bun", "run", str(pw_script),
        "--action", "navigate",
        "--url", cfg["url"],
        "--auth-state", str(AUTH_STATE_FILE),
        "--target-path", f"/firm/{slug}/mail-room?tab={tab}",
    ]
    if with_extension:
        cmd.append("--with-extension")
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        try:
            err_data = json.loads(res.stdout)
            raise RuntimeError(err_data.get("error") or "Navigation to mailroom failed.")
        except Exception:
            raise RuntimeError(res.stderr or res.stdout or "Navigation execution failed.")
            
    try:
        data = json.loads(res.stdout)
        return data
    except Exception:
        raise RuntimeError(f"Unexpected output from navigation script: {res.stdout}")
