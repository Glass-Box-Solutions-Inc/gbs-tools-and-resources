"""Authentication module for Adjudica Staging CLI."""
import os
import json
import subprocess
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "cli-anything-adjudica-staging"
CONFIG_FILE = CONFIG_DIR / "config.json"
AUTH_STATE_FILE = CONFIG_DIR / "auth-state.json"

def setup_config(url: str, email: str = "lawyer@adjudica.ai", password: str = "password123", firm_slug: str = "smith-associates") -> dict:
    """Save configuration options."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config = {
        "url": url,
        "email": email,
        "password": password,
        "firm_slug": firm_slug,
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    return {
        "status": "configured",
        "url": url,
        "email": email,
        "firm_slug": firm_slug,
        "config_path": str(CONFIG_FILE),
    }

def get_config() -> dict:
    """Load config from disk or environment defaults."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "url": os.environ.get("STAGING_URL") or "https://staging.app.adjudica.ai",
        "email": os.environ.get("E2E_TEST_USER_EMAIL") or "lawyer@adjudica.ai",
        "password": os.environ.get("E2E_TEST_USER_PASSWORD") or "password123",
        "firm_slug": os.environ.get("E2E_TEST_FIRM_SLUG") or "smith-associates",
    }

def login(with_extension: bool = False) -> dict:
    """Trigger the Playwright auth/login action to authenticate and save storageState."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = get_config()
    
    # Run the playwright script
    pkg_dir = Path(__file__).parent.parent
    pw_script = pkg_dir / "utils" / "adjudica_playwright.js"
    
    cmd = [
        "bun", "run", str(pw_script),
        "--action", "login",
        "--url", cfg["url"],
        "--email", cfg["email"],
        "--password", cfg["password"],
        "--auth-state", str(AUTH_STATE_FILE),
    ]
    if with_extension:
        cmd.append("--with-extension")
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        try:
            err_data = json.loads(res.stdout)
            raise RuntimeError(err_data.get("error") or "Login failed.")
        except Exception:
            raise RuntimeError(res.stderr or res.stdout or "Login execution failed.")
            
    try:
        data = json.loads(res.stdout)
        return data
    except Exception:
        raise RuntimeError(f"Unexpected output from login script: {res.stdout}")

def status() -> dict:
    """Check authentication status."""
    cfg = get_config()
    is_logged_in = AUTH_STATE_FILE.exists()
    return {
        "logged_in": is_logged_in,
        "email": cfg.get("email"),
        "url": cfg.get("url"),
        "auth_state_path": str(AUTH_STATE_FILE) if is_logged_in else None,
    }
