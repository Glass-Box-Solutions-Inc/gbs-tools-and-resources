#!/usr/bin/env python3
"""
Spectacles Auth Capture CLI

Standalone tool to capture authenticated browser state for any service.
Opens a live Browserless session, waits for manual login, then saves
cookies + localStorage locally and to GCP Secret Manager.

Usage:
    python projects/spectacles/tools/capture_auth.py                          # interactive preset menu
    python projects/spectacles/tools/capture_auth.py --service google         # preset
    python projects/spectacles/tools/capture_auth.py --service myapp \\
        --login-url https://myapp.com/login --verify-url https://myapp.com/dashboard

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import argparse
import asyncio
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

# Ensure the spectacles package root is importable
_SPECTACLES_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SPECTACLES_ROOT))

from security.auth_capture import AuthCaptureSession, resolve_auth_params, AUTH_PRESETS

# Defaults
BROWSERLESS_TOKEN = "2TcWyCwbfKt7UWCbec6a2ee3b613b579fb0edb5f7a52b0ace"
BROWSERLESS_WSS = "wss://production-sfo.browserless.io"
AUTH_DIR = Path("/home/vncuser/Desktop/Claude_Code/.auth")
GCP_PROJECT = "glassbox-spectacles"


def open_browser(url: str):
    """Open a URL in the system browser."""
    try:
        subprocess.Popen(
            ["google-chrome", "--no-first-run", "--disable-session-crashed-bubble", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        try:
            webbrowser.open(url)
        except Exception:
            pass  # URL is printed anyway


async def run_capture(args: argparse.Namespace):
    """Main capture flow."""
    # Resolve service params
    service, login_url, verify_url = resolve_auth_params(
        service=args.service,
        login_url=args.login_url,
        verify_url=args.verify_url,
        interactive=not args.service and not args.login_url,
    )

    credential_key = args.credential_key or f"{service}-auth"
    local_dir = str(AUTH_DIR) if not args.no_local else None
    gcp_project = None if args.no_gcp else GCP_PROJECT

    print(f"\n{'='*55}")
    print("  SPECTACLES AUTH CAPTURE")
    print(f"{'='*55}")
    print(f"  Service:        {service}")
    print(f"  Login URL:      {login_url}")
    print(f"  Verify URL:     {verify_url or '(none)'}")
    print(f"  Credential key: {credential_key}")
    if local_dir:
        print(f"  Local path:     {AUTH_DIR / f'{credential_key}.json'}")
    if gcp_project:
        print(f"  GCP project:    {gcp_project}")
    print()

    async with AuthCaptureSession(
        service=service,
        login_url=login_url,
        verify_url=verify_url,
        credential_key=credential_key,
        browserless_token=BROWSERLESS_TOKEN,
        browserless_wss=BROWSERLESS_WSS,
        timeout_ms=args.timeout * 1000,
    ) as session:
        # Start session and get live URL
        live_url = await session.start()

        print(f"{'='*55}")
        print("  LIVE BROWSER SESSION READY")
        print(f"{'='*55}")
        print(f"\n  Opening in browser:\n")
        print(f"    {live_url}\n")
        open_browser(live_url)

        print("-" * 55)
        print(f"  Complete login for '{service}' in the live browser:")
        print("    1. Enter your credentials")
        print("    2. Complete any 2FA / MFA prompts")
        print("    3. Wait until you are fully logged in")
        print("-" * 55)

        if args.wait:
            print(f"  (Auto-wait mode: waiting {args.wait}s for login...)")
            await asyncio.sleep(args.wait)
        else:
            input("\n  Press Enter here AFTER you've signed in...")

        # Capture
        print("\n  Capturing storage state...")
        state = await session.capture()
        cookie_count = len(state.get("cookies", []))
        origin_count = len(state.get("origins", []))
        print(f"  Captured: {cookie_count} cookies, {origin_count} origins")

        if cookie_count == 0:
            print("\n  WARNING: No cookies captured - login may not have completed")
            print("  Aborting save.")
            return

        # Save
        print("\n  Saving...")
        results = await session.save(local_dir=local_dir, gcp_project=gcp_project)

        if results.get("local_path"):
            print(f"  Saved locally: {results['local_path']}")
        if results.get("gcp_saved"):
            print(f"  Saved to GCP:  {results['secret_name']}")
        elif gcp_project:
            print("  WARNING: Failed to save to GCP Secret Manager")

        # Verify
        if verify_url:
            print(f"\n  Verifying auth at {verify_url} ...")
            verified = await session.verify()
            if verified:
                print("  Verification PASSED")
            else:
                print("  Verification FAILED - redirected back to login")
        else:
            print("\n  (No verify URL - skipping verification)")

    print(f"\n{'='*55}")
    print(f"  Auth state for '{service}' captured successfully!")
    print(f"{'='*55}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Capture authenticated browser state for any service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  %(prog)s                                           # Interactive preset menu
  %(prog)s --service google                          # Google preset
  %(prog)s --service github                          # GitHub preset
  %(prog)s --service myapp --login-url https://myapp.com/login
  %(prog)s --service myapp --login-url https://myapp.com/login \\
           --verify-url https://myapp.com/dashboard

Available presets: {', '.join(AUTH_PRESETS.keys())}
        """,
    )
    parser.add_argument(
        "--service",
        type=str,
        help="Service preset name or custom name",
    )
    parser.add_argument(
        "--login-url",
        type=str,
        help="Login page URL (overrides preset)",
    )
    parser.add_argument(
        "--verify-url",
        type=str,
        help="URL to verify auth after capture",
    )
    parser.add_argument(
        "--credential-key",
        type=str,
        help="Secret Manager key (default: {service}-auth)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Live session timeout in seconds (default: 600)",
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=None,
        help="Auto-wait N seconds instead of interactive prompt",
    )
    parser.add_argument(
        "--no-local",
        action="store_true",
        help="Skip saving locally",
    )
    parser.add_argument(
        "--no-gcp",
        action="store_true",
        help="Skip saving to GCP Secret Manager",
    )

    args = parser.parse_args()
    asyncio.run(run_capture(args))


if __name__ == "__main__":
    main()
