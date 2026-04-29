#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from tech_daily_rsshub_discovery import REQUEST_HEADERS, fetch_feed, load_config


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def x_reader_path() -> Path:
    return workspace_root() / "skills" / "x-reader-skill" / "x-reader.py"


def extract_x_username(feed_url: str) -> str:
    parts = [part for part in urlparse(feed_url).path.split("/") if part]
    if len(parts) >= 3 and parts[-2] == "user":
        return parts[-1].lstrip("@")
    return ""


def load_x_helpers() -> tuple[Any, Any]:
    reader_path = x_reader_path()
    spec = importlib.util.spec_from_file_location("x_reader_healthcheck", reader_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load x-reader from {reader_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.get_x_cookies, module.find_real_browser


PROFILE_PROBE_JS = r"""
(username) => {
  const normalizeStatusUrl = (href) => {
    if (!href) return '';
    const full = new URL(href, location.origin).toString();
    return full.replace(/\/photo\/\d+$/, '').replace(/\/analytics$/, '');
  };
  const anchors = Array.from(document.querySelectorAll('a[href*="/status/"]'));
  const hits = [];
  const seen = new Set();
  for (const anchor of anchors) {
    const href = anchor.getAttribute('href') || '';
    if (!href.includes('/status/')) continue;
    if (!href.startsWith(`/${username}/status/`)) continue;
    const full = normalizeStatusUrl(href);
    if (seen.has(full)) continue;
    seen.add(full);
    const article = anchor.closest('article');
    const text = ((article && article.innerText) || anchor.innerText || '').replace(/\s+/g, ' ').trim();
    const time = article && article.querySelector('time');
    hits.push({
      url: full,
      text: text.slice(0, 280),
      published_at: time ? (time.getAttribute('datetime') || '') : '',
    });
    if (hits.length >= 8) break;
  }
  const bodyText = (document.body && document.body.innerText ? document.body.innerText : '').replace(/\s+/g, ' ').trim();
  return {
    currentUrl: location.href,
    title: document.title || '',
    loginWall:
      !!document.querySelector('[data-testid="loginButton"]') ||
      !!document.querySelector('[data-testid="signupButton"]'),
    primaryColumn: !!document.querySelector('[data-testid="primaryColumn"]'),
    articleCount: document.querySelectorAll('article').length,
    bodyTextChars: bodyText.length,
    shellMarkers: [
      !!document.querySelector('noscript'),
      bodyText.includes('JavaScript is not available'),
      bodyText.includes('JavaScript 不可用'),
      bodyText.includes('Grok'),
      bodyText.includes('Something went wrong'),
    ].filter(Boolean).length,
    statusLinks: hits,
  };
}
"""

STATUS_PROBE_JS = r"""
() => {
  const article = document.querySelector('article');
  const time = article && article.querySelector('time');
  const text = ((article && article.innerText) || '').replace(/\s+/g, ' ').trim();
  const bodyText = (document.body && document.body.innerText ? document.body.innerText : '').replace(/\s+/g, ' ').trim();
  return {
    currentUrl: location.href,
    title: document.title || '',
    loginWall:
      !!document.querySelector('[data-testid="loginButton"]') ||
      !!document.querySelector('[data-testid="signupButton"]'),
    articleFound: !!article,
    articleTextChars: text.length,
    articleText: text.slice(0, 320),
    published_at: time ? (time.getAttribute('datetime') || '') : '',
    bodyTextChars: bodyText.length,
  };
}
"""


def profile_probe(page: Any, username: str) -> dict[str, Any]:
    url = f"https://x.com/{username}"
    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(2_500)
    payload = page.evaluate(PROFILE_PROBE_JS, username)
    shell_like = (
        not payload.get("statusLinks")
        and not payload.get("primaryColumn")
        and int(payload.get("bodyTextChars", 0) or 0) < 80
    )
    if shell_like or (not payload.get("statusLinks") and int(payload.get("articleCount", 0) or 0) == 0):
        page.reload(wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(2_300)
        payload = page.evaluate(PROFILE_PROBE_JS, username)
    if not payload.get("statusLinks"):
        page.evaluate("window.scrollTo(0, Math.max(window.innerHeight * 1.8, 1800));")
        page.wait_for_timeout(2_200)
        payload = page.evaluate(PROFILE_PROBE_JS, username)

    status = "ok"
    if payload.get("loginWall"):
        status = "blocked"
    elif not payload.get("statusLinks"):
        status = "empty" if payload.get("primaryColumn") or int(payload.get("articleCount", 0) or 0) > 0 else "shell"
    return {
        "status": status,
        "current_url": payload.get("currentUrl", url),
        "title": payload.get("title", ""),
        "login_wall": bool(payload.get("loginWall")),
        "status_url_count": len(payload.get("statusLinks", [])),
        "status_urls": [item.get("url", "") for item in payload.get("statusLinks", [])],
        "sample_text": next((item.get("text", "") for item in payload.get("statusLinks", []) if item.get("text")), ""),
        "article_count": int(payload.get("articleCount", 0) or 0),
        "primary_column": bool(payload.get("primaryColumn")),
        "body_text_chars": int(payload.get("bodyTextChars", 0) or 0),
        "shell_markers": int(payload.get("shellMarkers", 0) or 0),
    }


def direct_status_probe(page: Any, status_url: str) -> dict[str, Any]:
    if not status_url:
        return {"status": "missing", "status_url": ""}
    page.goto(status_url, wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(2_100)
    payload = page.evaluate(STATUS_PROBE_JS)
    status = "ok"
    if payload.get("loginWall"):
        status = "blocked"
    elif not payload.get("articleFound") or int(payload.get("articleTextChars", 0) or 0) < 40:
        status = "empty"
    return {
        "status": status,
        "status_url": status_url,
        "current_url": payload.get("currentUrl", status_url),
        "title": payload.get("title", ""),
        "login_wall": bool(payload.get("loginWall")),
        "article_found": bool(payload.get("articleFound")),
        "article_text_chars": int(payload.get("articleTextChars", 0) or 0),
        "article_text": payload.get("articleText", ""),
        "published_at": payload.get("published_at", ""),
        "body_text_chars": int(payload.get("bodyTextChars", 0) or 0),
    }


def classify_x_health(*, tier: str, feed_status: str, profile_status: str, direct_status: str) -> tuple[str, bool]:
    high_value = tier == "core_account"
    if profile_status == "ok" and direct_status in {"ok", "missing"}:
        return "ok", False
    if direct_status == "ok":
        return ("flaky", high_value) if profile_status != "ok" else ("ok", False)
    if profile_status == "blocked" or direct_status == "blocked":
        if high_value or feed_status == "ok":
            return "flaky", high_value
        return "blocked", False
    if feed_status == "ok" and high_value:
        return "flaky", True
    if profile_status == "shell" and high_value:
        return "flaky", True
    if profile_status == "ok":
        return "ok", False
    return "empty", False


def check_x_accounts_via_browser(accounts: list[dict[str, Any]], headless: bool) -> dict[str, dict[str, Any]]:
    if not accounts:
        return {}

    get_x_cookies, find_real_browser = load_x_helpers()
    cookies = get_x_cookies()
    if not cookies:
        return {
            str(account["x_username"]): {
                "browser_status": "error",
                "browser_error": "no-x-cookies",
                "health_classification": "blocked",
            }
            for account in accounts
        }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        return {
            str(account["x_username"]): {
                "browser_status": "error",
                "browser_error": f"playwright-missing: {exc}",
                "health_classification": "blocked",
            }
            for account in accounts
        }

    results: dict[str, dict[str, Any]] = {}
    launch_kwargs: dict[str, Any] = {
        "headless": headless,
        "args": ["--no-first-run", "--no-default-browser-check"],
        "ignore_default_args": ["--enable-automation"],
    }
    real_browser = find_real_browser()
    if real_browser:
        launch_kwargs["executable_path"] = real_browser
    else:
        launch_kwargs["args"].append("--disable-gpu")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            viewport={"width": 1440, "height": 960},
            user_agent=REQUEST_HEADERS["User-Agent"],
        )
        context.add_cookies(cookies)
        page = context.new_page()

        try:
            for account in accounts:
                username = str(account["x_username"])
                try:
                    profile = profile_probe(page, username)
                    direct = direct_status_probe(page, str(account.get("latest_link", "")).strip())
                    health_classification, high_value_protected = classify_x_health(
                        tier=str(account.get("tier", "")),
                        feed_status=str(account.get("status", "")),
                        profile_status=str(profile.get("status", "")),
                        direct_status=str(direct.get("status", "")),
                    )
                    results[username] = {
                        "browser_status": str(profile.get("status", "")),
                        "browser_url": profile.get("current_url", ""),
                        "browser_title": profile.get("title", ""),
                        "login_wall": bool(profile.get("login_wall")),
                        "status_url_count": int(profile.get("status_url_count", 0) or 0),
                        "status_urls": list(profile.get("status_urls", [])),
                        "sample_text": str(profile.get("sample_text", "")),
                        "tier": str(account.get("tier", "")),
                        "high_value_protected": high_value_protected,
                        "health_classification": health_classification,
                        "probe_results": {
                            "profile_probe": profile,
                            "direct_status_probe": direct,
                            "feed_probe": {
                                "status": str(account.get("status", "")),
                                "latest_link": str(account.get("latest_link", "")),
                            },
                        },
                    }
                except Exception as exc:  # noqa: BLE001
                    results[username] = {
                        "browser_status": "error",
                        "browser_error": str(exc),
                        "health_classification": "blocked",
                    }
        finally:
            page.close()
            context.close()
            browser.close()

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check whether configured tech-daily discovery feeds are currently readable.")
    parser.add_argument("--config", required=True, help="Path to rsshub-discovery TOML config.")
    parser.add_argument("--out", help="Optional JSON output path.")
    parser.add_argument("--check-x-browser", action="store_true", help="Also verify X seed accounts via a logged-in browser session.")
    parser.add_argument("--headless", action="store_true", help="Run browser checks headless.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    raw_config, feeds = load_config(config_path)
    timeout = int(raw_config.get("request_timeout_seconds", 20))
    session = requests.Session()

    report: list[dict[str, Any]] = []
    x_accounts: list[dict[str, Any]] = []
    for feed in feeds:
        row: dict[str, Any] = {
            "name": feed.name,
            "kind": feed.kind,
            "feed_url": feed.feed_url,
            "author": feed.author,
            "seed": feed.seed,
            "tier": feed.tier,
        }
        try:
            items, resolved_feed_url = fetch_feed(session, feed, timeout=timeout)
            row.update(
                {
                    "status": "ok",
                    "feed_url": resolved_feed_url,
                    "item_count": len(items),
                    "latest_title": items[0].get("title", "") if items else "",
                    "latest_link": items[0].get("link", "") if items else "",
                }
            )
        except Exception as exc:  # noqa: BLE001
            row.update(
                {
                    "status": "error",
                    "item_count": 0,
                    "latest_title": "",
                    "latest_link": "",
                    "error": str(exc),
                }
            )
        if feed.kind == "x":
            username = extract_x_username(feed.feed_url)
            if username:
                row["x_username"] = username
                x_accounts.append(row)
        report.append(row)

    browser_report: dict[str, dict[str, Any]] = {}
    if args.check_x_browser:
        deduped_accounts = {str(account["x_username"]): account for account in x_accounts}
        browser_report = check_x_accounts_via_browser(list(deduped_accounts.values()), headless=args.headless)
        for row in report:
            username = row.get("x_username")
            if username and username in browser_report:
                row.update(browser_report[username])

    payload = {
        "config_path": str(config_path),
        "feed_count": len(report),
        "ok_count": sum(1 for row in report if row.get("status") == "ok"),
        "error_count": sum(1 for row in report if row.get("status") == "error"),
        "feeds": report,
    }

    output = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
