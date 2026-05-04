#!/usr/bin/env python3
"""
X-Reader v2 — Cookie-based extraction via Playwright.

Strategy: reads X (Twitter) cookies from the user's existing logged-in Chrome
profile using browser_cookie3, then injects them into a Playwright context.
No login flow needed — works as long as the user is logged into X in Chrome.

Anti-ban safeguards:
  - Hard cap: max 15 URLs per invocation
  - Random human-like delay (5–12 s) between page loads
  - Only navigates to individual /status/ pages — never timelines or search
  - Zero automated interactions (no likes, retweets, follows)
  - Closes each page after extraction

Usage:
  python3 x-reader.py https://x.com/karpathy/status/2026731645169185220
  python3 x-reader.py --batch urls.txt --out results.json
"""

from __future__ import annotations

import sys
from pathlib import Path

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = next(parent for parent in (_THIS_FILE.parent, *_THIS_FILE.parents) if parent.name == "src")
for _IMPORT_DIR in (
    _SRC_DIR / "common",
    _SRC_DIR / "content",
    _SRC_DIR / "discovery",
    _SRC_DIR / "visuals",
    _SRC_DIR / "video",
):
    if str(_IMPORT_DIR) not in sys.path:
        sys.path.insert(0, str(_IMPORT_DIR))

import argparse
import json
import os
import random
import re
import time
from html import unescape
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_URLS_PER_SESSION = 15
DEFAULT_MIN_DELAY = 5
DEFAULT_MAX_DELAY = 12
PAGE_LOAD_TIMEOUT_MS = 25_000
CONTENT_WAIT_TIMEOUT_MS = 15_000

VIEWPORT = {"width": 1440, "height": 900}
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Real browser paths (used as Playwright executable)
CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]

GENERIC_TEXT_FRAGMENTS = (
    "something went wrong",
    "this page doesn",
    "page isn't available",
    "try again",
    "sign in to x",
    "log in to twitter",
)
LOW_SIGNAL_REPLY_FRAGMENTS = (
    "follow us",
    "supplier",
    "cheap but",
    "miracle factories",
    "delivery promises",
    "dm me",
    "link in bio",
    "promo code",
    "subscribe for",
    "no email",
    "brand strategy",
    "launch plan",
    "competitive risks",
    "demand opportunities",
    "free market scan",
)
REPLY_CONTEXT_STOPWORDS = {
    "about",
    "after",
    "before",
    "build",
    "built",
    "could",
    "daily",
    "does",
    "from",
    "have",
    "just",
    "more",
    "than",
    "that",
    "this",
    "they",
    "what",
    "when",
    "with",
    "your",
}

STATUS_URL_RE = re.compile(
    r"https?://(?:x\.com|twitter\.com)/([^/]+)/status/(\d+)"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalize_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", unescape(text or "")).strip()


def is_valid_tweet_text(text: str) -> bool:
    clean = normalize_text(text)
    if len(clean) < 20:
        return False
    lower = clean.lower()
    return not any(frag in lower for frag in GENERIC_TEXT_FRAGMENTS)


def is_valid_reply_text(text: str) -> bool:
    clean = normalize_text(text)
    if len(clean) < 30:
        return False
    lower = clean.lower()
    if any(frag in lower for frag in GENERIC_TEXT_FRAGMENTS):
        return False
    if any(frag in lower for frag in LOW_SIGNAL_REPLY_FRAGMENTS):
        return False
    return True


def duplicate_key_for_tweet(tweet_id: str) -> str:
    return f"x:{tweet_id}" if tweet_id else ""


def context_keywords(text: str) -> set[str]:
    raw_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_/-]{3,}", normalize_text(text).lower())
    keywords: set[str] = set()
    for token in raw_tokens:
        clean = token.strip("_-/")
        if len(clean) < 4 or clean in REPLY_CONTEXT_STOPWORDS:
            continue
        keywords.add(clean)
    return keywords


def extraction_confidence(raw: dict[str, Any], full_text: str) -> float:
    score = 0.55
    if raw.get("author"):
        score += 0.08
    if raw.get("username"):
        score += 0.08
    if raw.get("created_at"):
        score += 0.08
    if raw.get("thread_texts"):
        score += 0.05
    if raw.get("reply_contexts"):
        score += 0.04
    score += min(len(normalize_text(full_text)) / 800, 0.16)
    return round(max(0.0, min(1.0, score)), 3)


def extract_info_from_url(url: str) -> tuple[str, str]:
    m = STATUS_URL_RE.search(url)
    if m:
        return m.group(1), m.group(2)
    stripped = url.strip()
    if stripped.isdigit():
        return "", stripped
    return "", ""


def find_real_browser() -> str | None:
    for p in CHROME_PATHS:
        if Path(p).exists():
            return p
    return None


def human_delay(min_s: float, max_s: float) -> None:
    time.sleep(random.uniform(min_s, max_s))


# ---------------------------------------------------------------------------
# Cookie extraction from real Chrome
# ---------------------------------------------------------------------------


def get_x_cookies() -> list[dict[str, Any]]:
    """Extract X (Twitter) cookies from the user's real Chrome install."""
    try:
        import browser_cookie3
    except ImportError:
        print("[x-reader] browser_cookie3 not found — installing…", file=sys.stderr)
        import subprocess
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "browser-cookie3", "--break-system-packages", "-q",
        ])
        import browser_cookie3  # noqa: F811

    cookies: list[dict[str, Any]] = []

    # Try Chrome first, then other browsers
    loaders = [
        ("Chrome",  browser_cookie3.chrome),
        ("Brave",   browser_cookie3.brave),
        ("Edge",    browser_cookie3.edge),
        ("Firefox", browser_cookie3.firefox),
        ("Safari",  browser_cookie3.safari),
    ]

    for browser_name, loader in loaders:
        try:
            jar = loader(domain_name=".x.com")
            extracted = []
            for c in jar:
                extracted.append({
                    "name":    c.name,
                    "value":   c.value,
                    "domain":  c.domain if c.domain.startswith(".") else f".{c.domain}",
                    "path":    c.path or "/",
                    "secure":  bool(c.secure),
                    "httpOnly": False,
                    "sameSite": "None",
                })
            if extracted:
                print(
                    f"[x-reader] Got {len(extracted)} X cookies from {browser_name}.",
                    file=sys.stderr,
                )
                cookies = extracted
                break
        except Exception as exc:
            print(f"[x-reader] {browser_name} cookie load failed: {exc}", file=sys.stderr)
            continue

    if not cookies:
        print(
            "[x-reader] ⚠️  No X cookies found. Make sure you're logged into X in Chrome.",
            file=sys.stderr,
        )

    return cookies


# ---------------------------------------------------------------------------
# DOM extraction JS
# ---------------------------------------------------------------------------

_EXTRACTION_JS = """
() => {
    const result = {text: '', author: '', username: '', created_at: '',
                    likes: 0, retweets: 0, replies: 0, quotes: 0,
                    thread_texts: [], reply_contexts: [], media_urls: []};

    const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
    let focalArticle = null;
    let focalIndex = -1;

    const articleSpans = (article) => article ? article.querySelectorAll('a[role="link"] span') : [];
    const articleUsername = (article) => {
        for (const sp of articleSpans(article)) {
            const value = (sp.textContent || '').trim();
            if (value.startsWith('@')) {
                return value.replace('@', '');
            }
        }
        return '';
    };

    const articleAuthor = (article) => {
        let fallback = '';
        for (const nl of article.querySelectorAll('a[role="link"]')) {
            const spans = nl.querySelectorAll('span');
            for (const sp of spans) {
                const value = (sp.textContent || '').trim();
                if (!value || value === '·' || value.match(/^[0-9,]+$/)) {
                    continue;
                }
                if (value.startsWith('@')) {
                    if (!fallback) {
                        fallback = value.replace('@', '');
                    }
                    continue;
                }
                return value;
            }
        }
        return fallback;
    };

    const fillEngagement = (article, target) => {
        const groupEl = article.querySelector('[role="group"]');
        if (!groupEl) return;
        const label = groupEl.getAttribute('aria-label') || '';
        const chunks = label.match(/([\\d,]+)\\s+(repl|repost|like|bookmark|quote|view)/gi) || [];
        for (const chunk of chunks) {
            const m = chunk.match(/([\\d,]+)\\s+(\\w+)/);
            if (!m) continue;
            const n = parseInt(m[1].replace(/,/g, ''), 10) || 0;
            const key = m[2].toLowerCase();
            if (key.startsWith('repl')) target.replies = n;
            else if (key.startsWith('repost')) target.retweets = n;
            else if (key.startsWith('like')) target.likes = n;
            else if (key.startsWith('quote')) target.quotes = n;
        }
    };

    for (let index = 0; index < articles.length; index++) {
        const art = articles[index];
        if (art.querySelector('[data-testid="tweetText"]')) {
            focalArticle = art;
            focalIndex = index;
            break;
        }
    }

    if (focalArticle) {
        const textEl = focalArticle.querySelector('[data-testid="tweetText"]');
        if (textEl) result.text = textEl.innerText.trim();
        result.username = articleUsername(focalArticle);
        result.author = articleAuthor(focalArticle);

        const timeEl = focalArticle.querySelector('time');
        if (timeEl) result.created_at = timeEl.getAttribute('datetime') || timeEl.textContent || '';

        fillEngagement(focalArticle, result);

        const imgs = focalArticle.querySelectorAll('img[src*="pbs.twimg.com/media"]');
        for (const img of imgs) result.media_urls.push(img.src);
    }

    if (result.username && focalIndex >= 0 && articles.length > focalIndex + 1) {
        let threadCount = 0;
        let replyCount = 0;
        const seenReplies = new Set();
        for (let i = focalIndex + 1; i < articles.length; i++) {
            const art = articles[i];
            const textEl = art.querySelector('[data-testid="tweetText"]');
            if (!textEl) continue;

            const text = textEl.innerText.trim();
            if (!text) continue;

            const username = articleUsername(art);
            if (username && username.toLowerCase() === result.username.toLowerCase()) {
                if (threadCount < 3) {
                    result.thread_texts.push(text);
                    threadCount += 1;
                }
                continue;
            }

            if (replyCount >= 12) continue;

            const dedupeKey = `${username}|${text}`;
            if (seenReplies.has(dedupeKey)) continue;
            seenReplies.add(dedupeKey);

            const reply = {
                author: articleAuthor(art),
                username,
                text,
                created_at: '',
                likes: 0,
                retweets: 0,
                replies: 0,
                quotes: 0,
            };
            const timeEl = art.querySelector('time');
            if (timeEl) reply.created_at = timeEl.getAttribute('datetime') || timeEl.textContent || '';
            fillEngagement(art, reply);
            result.reply_contexts.push(reply);
            replyCount += 1;
        }
    }

    if (!result.author && result.username) {
        result.author = result.username;
    }

    if (!result.username && focalArticle) {
        for (const sp of articleSpans(focalArticle)) {
            const value = (sp.textContent || '').trim();
            if (value.startsWith('@')) {
                result.username = value.replace('@', '');
                break;
            }
        }
    }

    return result;
}
"""

# ---------------------------------------------------------------------------
# Page reading
# ---------------------------------------------------------------------------


def read_single_tweet(page: Any, url: str) -> dict[str, Any]:
    username, tweet_id = extract_info_from_url(url)
    if not tweet_id:
        return {"error": f"Cannot parse tweet ID from: {url}", "url": url}

    canonical = (
        f"https://x.com/{username}/status/{tweet_id}"
        if username else url
    )

    try:
        page.goto(canonical, wait_until="domcontentloaded",
                  timeout=PAGE_LOAD_TIMEOUT_MS)
    except Exception as exc:
        return {"error": f"Navigation failed: {exc}", "url": canonical}

    try:
        page.wait_for_selector('[data-testid="tweetText"]',
                               timeout=CONTENT_WAIT_TIMEOUT_MS)
    except Exception:
        pass  # try extraction anyway

    time.sleep(random.uniform(0.8, 1.5))  # let JS finish rendering

    try:
        raw = page.evaluate(_EXTRACTION_JS)
    except Exception as exc:
        return {"error": f"DOM extraction failed: {exc}", "url": canonical}

    if not raw or not raw.get("text"):
        return {
            "error": "Tweet text not found on page.",
            "url": canonical,
            "tweet_id": tweet_id,
        }

    focal_text = normalize_text(raw["text"])
    if not is_valid_tweet_text(focal_text):
        return {
            "error": "Page looks like a login wall or error page.",
            "url": canonical,
            "tweet_id": tweet_id,
            "raw_text": focal_text[:200],
        }

    extracted_username = normalize_text(raw.get("username", "")).lstrip("@")
    if username and extracted_username and extracted_username.lower() != username.lower():
        return {
            "error": f"Username mismatch: expected @{username}, got @{extracted_username}",
            "url": canonical,
            "tweet_id": tweet_id,
            "raw_username": extracted_username,
        }

    if not extracted_username:
        return {
            "error": "Tweet username not found on page.",
            "url": canonical,
            "tweet_id": tweet_id,
        }

    thread_texts: list[str] = raw.get("thread_texts", [])
    normalized_thread_texts = [
        normalize_text(thread_text)
        for thread_text in thread_texts
        if is_valid_tweet_text(thread_text)
    ]
    raw_reply_contexts: list[dict[str, Any]] = raw.get("reply_contexts", [])
    normalized_reply_contexts: list[dict[str, Any]] = []
    seen_reply_contexts: set[str] = set()
    focal_keywords = context_keywords(focal_text)
    focal_keywords.add(extracted_username.lower())
    focal_keywords |= context_keywords(raw.get("author", ""))
    for reply in raw_reply_contexts:
        if not isinstance(reply, dict):
            continue
        reply_text = normalize_text(reply.get("text"))
        if not is_valid_reply_text(reply_text):
            continue
        reply_username = normalize_text(reply.get("username", "")).lstrip("@")
        if focal_keywords:
            reply_keywords = context_keywords(reply_text)
            reply_keywords.add(reply_username.lower())
            if not (reply_keywords & focal_keywords):
                continue
        dedupe_key = f"{reply_username}|{reply_text}"
        if dedupe_key in seen_reply_contexts:
            continue
        seen_reply_contexts.add(dedupe_key)
        normalized_reply_contexts.append(
            {
                "author": normalize_text(reply.get("author", "")),
                "username": reply_username,
                "text": reply_text,
                "created_at": normalize_text(reply.get("created_at", "")),
                "likes": int(reply.get("likes", 0) or 0),
                "retweets": int(reply.get("retweets", 0) or 0),
                "replies": int(reply.get("replies", 0) or 0),
                "quotes": int(reply.get("quotes", 0) or 0),
            }
        )
        if len(normalized_reply_contexts) >= 6:
            break
    full_text = focal_text
    if normalized_thread_texts:
        full_text = focal_text + "\n\n" + "\n\n".join(normalized_thread_texts)

    return {
        "id":           tweet_id,
        "text":         full_text,
        "focal_text":   focal_text,
        "thread_count": len(normalized_thread_texts),
        "reply_context_count": len(normalized_reply_contexts),
        "reply_contexts": normalized_reply_contexts,
        "author":       raw.get("author", ""),
        "username":     extracted_username or username,
        "created_at":   raw.get("created_at", ""),
        "likes":        raw.get("likes", 0),
        "retweets":     raw.get("retweets", 0),
        "replies":      raw.get("replies", 0),
        "quotes":       raw.get("quotes", 0),
        "media_urls":   raw.get("media_urls", []),
        "url":          canonical,
        "source":       "browser",
        "text_chars":   len(re.sub(r"\s+", "", full_text)),
        "duplicate_key": duplicate_key_for_tweet(tweet_id),
        "extraction_confidence": extraction_confidence(raw, full_text),
    }


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


def _ensure_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ModuleNotFoundError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        from playwright.sync_api import sync_playwright
        return sync_playwright


def run_batch(
    urls: list[str],
    *,
    min_delay: float,
    max_delay: float,
    headless: bool = True,
) -> list[dict[str, Any]]:
    if len(urls) > MAX_URLS_PER_SESSION:
        print(f"[x-reader] Safety cap: truncating to {MAX_URLS_PER_SESSION} URLs.",
              file=sys.stderr)
        urls = urls[:MAX_URLS_PER_SESSION]

    cookies = get_x_cookies()
    sync_playwright = _ensure_playwright()
    results: list[dict[str, Any]] = []

    real_browser = find_real_browser()
    launch_kwargs: dict[str, Any] = {
        "headless": headless,
        "args": ["--no-first-run", "--no-default-browser-check"],
        "ignore_default_args": ["--enable-automation"],
    }
    if real_browser:
        print(f"[x-reader] Using browser: {real_browser}", file=sys.stderr)
        launch_kwargs["executable_path"] = real_browser
    else:
        print("[x-reader] Using Playwright Chromium.", file=sys.stderr)
        launch_kwargs["args"].append("--disable-gpu")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            viewport=VIEWPORT,
            user_agent=USER_AGENT,
        )

        if cookies:
            context.add_cookies(cookies)

        page = context.new_page()

        try:
            for i, url in enumerate(urls):
                if i > 0:
                    delay = random.uniform(min_delay, max_delay)
                    print(
                        f"[x-reader] Waiting {delay:.1f}s… ({i+1}/{len(urls)})",
                        file=sys.stderr,
                    )
                    time.sleep(delay)

                print(f"[x-reader] Reading: {url}", file=sys.stderr)
                result = read_single_tweet(page, url)
                results.append(result)

                ok = "error" not in result
                label = "OK" if ok else f"FAIL: {result.get('error','')[:70]}"
                print(f"[x-reader]   → {label}", file=sys.stderr)

        finally:
            try:
                page.close()
            except Exception:
                pass
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Read X/Twitter posts using cookies from your logged-in Chrome.",
    )
    p.add_argument("url", nargs="?", help="Single tweet URL.")
    p.add_argument("--batch", help="File with one URL per line.")
    p.add_argument("--out", help="Write JSON to this file instead of stdout.")
    p.add_argument("--min-delay", type=float, default=DEFAULT_MIN_DELAY)
    p.add_argument("--max-delay", type=float, default=DEFAULT_MAX_DELAY)
    p.add_argument("--headless", action="store_true", default=False,
                   help="Run headless (default: False).")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    urls: list[str] = []
    if args.batch:
        with open(args.batch) as f:
            urls = [
                l.strip() for l in f
                if l.strip() and not l.strip().startswith("#")
            ]
    elif args.url:
        urls = [args.url]
    else:
        print("Error: provide a tweet URL or --batch file.", file=sys.stderr)
        sys.exit(1)

    for u in urls:
        _, tid = extract_info_from_url(u)
        if not tid:
            print(f"Error: not a valid tweet URL: {u}", file=sys.stderr)
            sys.exit(1)

    results = run_batch(
        urls,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        headless=args.headless,
    )

    output = json.dumps(
        results[0] if len(results) == 1 else results,
        indent=2,
        ensure_ascii=False,
    )

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"[x-reader] Written to {args.out}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
