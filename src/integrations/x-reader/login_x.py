#!/usr/bin/env python3
"""
X-Reader v2 — Interactive Login Setup

Opens a real Chrome browser window so you can manually log into X (Twitter).
The login session is saved to a dedicated x-reader profile and reused automatically.

Usage:
    python3 login_x.py
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ModuleNotFoundError:
    print("Error: playwright not installed. Run: pip install playwright", file=sys.stderr)
    sys.exit(1)

PROFILE_DIR = Path.home() / ".openclaw" / "browser" / "x-reader-profile"

VIEWPORT = {"width": 1440, "height": 900}
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Real Chrome paths to try on macOS (in priority order)
CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Arc.app/Contents/MacOS/Arc",
]


def find_real_browser() -> str | None:
    """Return the path to a real installed browser, or None if not found."""
    for p in CHROME_PATHS:
        if Path(p).exists():
            return p
    return None


def main() -> None:
    print("=== X-Reader v2 — Login Setup ===\n")

    browser_path = find_real_browser()
    if browser_path:
        print(f"  ✓ Found browser: {browser_path}")
    else:
        print("  ℹ  No real Chrome/Brave/Edge found — using Playwright Chromium.")
        print("     Note: X may block login on Playwright Chromium.")
        print("     If login fails, install Google Chrome from https://www.google.com/chrome/\n")

    print(f"  Profile dir: {PROFILE_DIR}\n")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    print("Opening browser — please log into X in the window that appears.")
    print("When fully logged in, close the browser window to save the session.\n")

    launch_kwargs: dict = {
        "headless": False,
        "viewport": VIEWPORT,
        "user_agent": USER_AGENT,
        "args": [
            "--no-first-run",
            "--no-default-browser-check",
        ],
        "ignore_default_args": ["--enable-automation"],
    }
    if browser_path:
        launch_kwargs["executable_path"] = browser_path

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            **launch_kwargs,
        )
        page = context.new_page()
        page.goto("https://x.com/login")

        print("⏳ Browser window is open. Log in to X, then close the window.\n")

        # Wait until the user closes the browser
        try:
            context.wait_for_event("close", timeout=0)  # no timeout — wait forever
        except Exception:
            pass

    print("✅ Session saved!")
    print(f"   Profile: {PROFILE_DIR}\n")
    print("Now run the test to verify it works:")
    print("   bash ~/.openclaw/workspace/skills/x-reader-skill/test_x_reader.sh\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled by user.", file=sys.stderr)
        sys.exit(1)
