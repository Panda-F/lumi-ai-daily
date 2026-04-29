#!/usr/bin/env python3
"""
Diagnostic script — shows what the browser sees when visiting X.
Saves a screenshot and page HTML to /tmp/ for inspection.
Run this to diagnose why tweet text is not found.
"""

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Reuse cookie extraction from x-reader.py (hyphen means we can't import normally)
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent
_spec = importlib.util.spec_from_file_location("x_reader", _HERE / "x-reader.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
get_x_cookies = _mod.get_x_cookies
find_real_browser = _mod.find_real_browser

DEFAULT_TEST_URL = "https://x.com/simonw/status/1984390532790153484"
SCREENSHOT_PATH = "/tmp/x-debug-screenshot.png"
HTML_PATH = "/tmp/x-debug-page.html"
COOKIES_PATH = "/tmp/x-debug-cookies.json"

VIEWPORT = {"width": 1440, "height": 900}
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose what X renders for a specific status URL.")
    parser.add_argument(
        "url",
        nargs="?",
        default=DEFAULT_TEST_URL,
        help="Status URL to inspect. Defaults to a currently known-good public tweet.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    test_url = args.url
    print("=== X-Reader Diagnostic ===\n")

    # 1. Show cookies
    print("[1] Extracting cookies from Chrome…")
    cookies = get_x_cookies()
    print(f"    Total cookies: {len(cookies)}")

    critical = ["auth_token", "ct0", "twid"]
    for name in critical:
        found = next((c for c in cookies if c["name"] == name), None)
        if found:
            val_preview = found["value"][:20] + "…" if len(found["value"]) > 20 else found["value"]
            print(f"    ✓ {name}: {val_preview}")
        else:
            print(f"    ✗ {name}: MISSING — this is required for X auth!")

    Path(COOKIES_PATH).write_text(
        json.dumps([{"name": c["name"], "value_len": len(c["value"])} for c in cookies], indent=2),
        encoding="utf-8"
    )
    print(f"    Cookie names saved to {COOKIES_PATH}")

    # 2. Launch browser (NON-HEADLESS so you can see it)
    print("\n[2] Launching browser (visible window)…")
    from playwright.sync_api import sync_playwright

    real_browser = find_real_browser()
    launch_kwargs = {
        "headless": False,  # <-- show the browser so we can see what's happening
        "args": ["--no-first-run", "--no-default-browser-check"],
        "ignore_default_args": ["--enable-automation"],
        "slow_mo": 500,
    }
    if real_browser:
        print(f"    Using: {real_browser}")
        launch_kwargs["executable_path"] = real_browser
    else:
        print("    Using Playwright Chromium")
        launch_kwargs["args"].append("--disable-gpu")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_kwargs)
        context = browser.new_context(viewport=VIEWPORT, user_agent=USER_AGENT)

        if cookies:
            context.add_cookies(cookies)
            print(f"    Injected {len(cookies)} cookies")
        else:
            print("    ⚠️  No cookies to inject!")

        page = context.new_page()

        print(f"\n[3] Navigating to: {test_url}")
        try:
            page.goto(test_url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            print(f"    Navigation error: {e}")

        print(f"    Current URL: {page.url}")
        print(f"    Page title:  {page.title()}")

        # Check if login wall
        try:
            page.wait_for_selector('[data-testid="tweetText"]', timeout=12_000)
            print("    ✓ Found tweet text element!")
        except Exception:
            print("    ✗ Tweet text element NOT found within 12s")

        time.sleep(2)

        # Screenshot
        page.screenshot(path=SCREENSHOT_PATH, full_page=False)
        print(f"\n[4] Screenshot saved to: {SCREENSHOT_PATH}")

        # HTML
        html = page.content()
        Path(HTML_PATH).write_text(html, encoding="utf-8")
        print(f"    Page HTML saved to: {HTML_PATH}")

        # Quick cookie check via JS
        js_cookies = page.evaluate("() => document.cookie")
        cookie_names = [c.split("=")[0].strip() for c in js_cookies.split(";") if "=" in c]
        print(f"\n[5] Browser-visible cookies ({len(cookie_names)}): {', '.join(cookie_names[:10])}")

        auth_in_browser = "auth_token" in cookie_names
        print(f"    auth_token in browser: {'✓ YES' if auth_in_browser else '✗ NO — not logged in!'}")

        # Check page state
        has_tweet = page.query_selector('[data-testid="tweetText"]') is not None
        has_login_btn = page.query_selector('[data-testid="loginButton"]') is not None
        has_signup = page.query_selector('[data-testid="signupButton"]') is not None
        print(f"\n[6] Page state:")
        print(f"    Tweet text found:  {'✓' if has_tweet else '✗'}")
        print(f"    Login button:      {'⚠️  YES (login wall!)' if has_login_btn else 'No'}")
        print(f"    Signup button:     {'⚠️  YES (login wall!)' if has_signup else 'No'}")

        print("\n    Keeping browser open for 5 seconds so you can see it…")
        time.sleep(5)

        browser.close()

        print("\n=== Diagnostic Complete ===")
        print(f"Screenshot: open {SCREENSHOT_PATH}")
    if not has_tweet:
        print("\nMost likely causes:")
        if not auth_in_browser:
            print("  → auth_token not in browser: cookies were extracted but may be corrupted/encrypted")
            print("    Fix: run 'python3 -c \"import browser_cookie3; [print(c.name, c.value[:10]) for c in browser_cookie3.chrome(domain_name=\\'.x.com\\')]\"'")
        elif has_login_btn or has_signup:
            print("  → X is showing a login wall despite cookies: cookies may be expired")
            print("    Fix: log out and back into X in Chrome, then retry")
        else:
            print("  → Unknown render issue — check the screenshot for details")


if __name__ == "__main__":
    main()
