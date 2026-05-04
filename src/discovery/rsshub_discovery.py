#!/usr/bin/env python3

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
import concurrent.futures
import hashlib
import json
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

import requests


REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

REDDIT_REQUEST_HEADERS = [
    REQUEST_HEADERS,
    {
        **REQUEST_HEADERS,
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    },
]


@dataclass
class FeedConfig:
    name: str
    kind: str
    feed_url: str
    author: str
    seed: bool
    tier: str = ""
    alternate_feed_urls: tuple[str, ...] = field(default_factory=tuple)


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    query = parsed.query
    if netloc in {"twitter.com", "www.twitter.com"}:
        netloc = "x.com"
    if netloc in {"x.com", "www.x.com"}:
        query = ""
    return urlunparse((scheme, netloc, path, "", query, ""))


def extract_platform_id(kind: str, url: str) -> str:
    if kind == "x":
        import re

        match = re.search(r"/status/(\d+)", url)
        return match.group(1) if match else ""
    if kind == "zhihu":
        import re

        match = re.search(r"/p/(\d+)", url)
        return match.group(1) if match else ""
    if kind == "wechat":
        parsed = urlparse(url)
        if parsed.path.startswith("/s/"):
            return parsed.path.removeprefix("/s/").strip("/")
        return parsed.query or parsed.path.strip("/")
    return urlparse(url).path.strip("/")


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def first_child_text(parent: ET.Element, *names: str) -> str:
    wanted = set(names)
    for child in list(parent):
        if local_name(child.tag) in wanted:
            return "".join(child.itertext()).strip()
    return ""


def parse_timestamp(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    try:
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        return datetime.fromisoformat(value).astimezone(timezone.utc).isoformat()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        return ""


def load_config(path: Path) -> tuple[dict[str, Any], list[FeedConfig]]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    base_urls: list[str] = []
    configured_base_urls = raw.get("rsshub_base_urls")
    if isinstance(configured_base_urls, list):
        for value in configured_base_urls:
            candidate = str(value).strip().rstrip("/")
            if candidate and candidate not in base_urls:
                base_urls.append(candidate)
    legacy_base_url = str(raw.get("rsshub_base_url", "")).strip().rstrip("/")
    if legacy_base_url and legacy_base_url not in base_urls:
        base_urls.insert(0, legacy_base_url)
    feeds: list[FeedConfig] = []
    for entry in raw.get("feeds", []):
        feed_url = str(entry.get("feed_url", "")).strip()
        feed_path = str(entry.get("feed_path", "")).strip()
        alternate_feed_urls: list[str] = []
        if not feed_url and feed_path:
            built_urls = [urljoin(base_url + "/", feed_path.lstrip("/")) for base_url in base_urls]
            if built_urls:
                feed_url = built_urls[0]
                alternate_feed_urls = built_urls[1:]
        if not feed_url:
            continue
        feeds.append(
            FeedConfig(
                name=str(entry.get("name", "")).strip() or Path(feed_path).name or "feed",
                kind=str(entry.get("kind", "")).strip() or "unknown",
                feed_url=feed_url,
                author=str(entry.get("author", "")).strip(),
                seed=bool(entry.get("seed", False)),
                tier=str(entry.get("tier", "")).strip(),
                alternate_feed_urls=tuple(alternate_feed_urls),
            )
        )
    return raw, feeds


def parse_feed_items(xml_text: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, str]] = []
    for node in root.iter():
        name = local_name(node.tag)
        if name not in {"item", "entry"}:
            continue

        title = first_child_text(node, "title")
        link = ""
        summary = first_child_text(node, "description", "summary", "content", "content:encoded")
        published = first_child_text(node, "pubDate", "published", "updated")
        author = first_child_text(node, "author", "creator", "dc:creator")

        for child in list(node):
            child_name = local_name(child.tag)
            if child_name == "link":
                href = child.attrib.get("href", "").strip()
                if href:
                    link = href
                    break
                child_text = "".join(child.itertext()).strip()
                if child_text:
                    link = child_text
                    break

        if not link:
            continue

        items.append(
            {
                "title": title,
                "link": link,
                "summary": summary,
                "published_at": parse_timestamp(published),
                "author": author,
            }
        )
    return items


def fetch_feed(session: requests.Session, feed: FeedConfig, timeout: int) -> tuple[list[dict[str, str]], str]:
    candidate_urls: list[str] = []
    for value in (feed.feed_url, *feed.alternate_feed_urls):
        if value and value not in candidate_urls:
            candidate_urls.append(value)

    last_error: Exception | None = None
    for candidate_url in candidate_urls:
        header_candidates = REDDIT_REQUEST_HEADERS if "reddit.com" in candidate_url else [REQUEST_HEADERS]
        attempts = max(3, len(header_candidates))

        for attempt in range(attempts):
            headers = header_candidates[min(attempt, len(header_candidates) - 1)]
            response: requests.Response | None = None
            try:
                response = session.get(candidate_url, headers=headers, timeout=timeout)
                response.raise_for_status()
                return parse_feed_items(response.text), candidate_url
            except requests.HTTPError as exc:
                last_error = exc
                status_code = response.status_code if response is not None else None
                if status_code not in {403, 429, 500, 502, 503, 504}:
                    break
            except requests.RequestException as exc:
                last_error = exc

            if attempt < attempts - 1:
                time.sleep(1.0 + attempt)

    if last_error is not None:
        tried = ", ".join(candidate_urls)
        raise RuntimeError(f"{last_error} (tried: {tried})")
    raise RuntimeError(f"failed to fetch feed: {feed.feed_url}")


def discovery_method_for_feed(feed: FeedConfig) -> str:
    lower_url = feed.feed_url.lower()
    if "127.0.0.1" in lower_url or "rsshub" in lower_url:
        return "rsshub"
    if lower_url.endswith(".atom") or "/releases.atom" in lower_url or "atom" in lower_url:
        return "atom"
    return "rss"


def feed_validation(
    feed: FeedConfig,
    items: list[dict[str, str]],
    *,
    freshness_hours: int = 24 * 7,
    resolved_feed_url: str | None = None,
) -> dict[str, Any]:
    latest_published = next((item.get("published_at", "") for item in items if item.get("published_at")), "")
    recent_count = sum(1 for item in items if within_window(str(item.get("published_at", "")), freshness_hours))
    complete_count = sum(1 for item in items if item.get("title") and item.get("link"))
    if not items:
        status = "empty"
    elif recent_count == 0:
        status = "stale"
    elif complete_count == 0:
        status = "invalid"
    else:
        status = "ok"
    return {
        "name": feed.name,
        "kind": feed.kind,
        "tier": feed.tier,
        "feed_url": resolved_feed_url or feed.feed_url,
        "author": feed.author,
        "status": status,
        "enabled": status == "ok",
        "item_count": len(items),
        "complete_count": complete_count,
        "recent_item_count": recent_count,
        "latest_published_at": latest_published,
        "discovery_method": discovery_method_for_feed(feed),
    }


def build_candidate(feed: FeedConfig, item: dict[str, str], *, resolved_feed_url: str | None = None) -> dict[str, Any]:
    canonical_url = canonicalize_url(item["link"])
    item_id = extract_platform_id(feed.kind, canonical_url)
    candidate_hash = hashlib.sha1(
        "|".join(
            [
                canonical_url,
                item.get("title", ""),
                item.get("published_at", ""),
            ]
        ).encode("utf-8")
    ).hexdigest()[:16]
    payload: dict[str, Any] = {
        "canonical_url": canonical_url,
        "source_kind": feed.kind,
        "source_author": item.get("author") or feed.author,
        "published_at": item.get("published_at", ""),
        "discovery_method": discovery_method_for_feed(feed),
        "feed_name": feed.name,
        "feed_url": resolved_feed_url or feed.feed_url,
        "title": item.get("title", "").strip(),
        "snippet": item.get("summary", "").strip(),
        "candidate_hash": candidate_hash,
        "seed": feed.seed,
        "source_tier": feed.tier,
        "item_id": item_id,
    }
    if feed.kind == "x":
        payload["tweet_id"] = item_id
    else:
        payload["article_id"] = item_id
    return payload


def within_window(published_at: str, window_hours: int) -> bool:
    if not published_at:
        return True
    try:
        published = datetime.fromisoformat(published_at)
    except ValueError:
        return True
    return published >= datetime.now(timezone.utc) - timedelta(hours=window_hours)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an RSSHub-backed discovery cache for tech-daily candidates.")
    parser.add_argument("--config", required=True, help="Path to rsshub-discovery TOML config.")
    parser.add_argument("--out", required=True, help="Where to write the normalized candidate JSON.")
    parser.add_argument("--window-hours", type=int, help="Override lookback window in hours.")
    parser.add_argument("--max-items-per-feed", type=int, help="Override max items per feed.")
    parser.add_argument("--parallelism", type=int, help="Number of feeds to fetch concurrently.")
    return parser.parse_args()


def fetch_feed_result(
    feed: FeedConfig,
    *,
    timeout: int,
    window_hours: int,
    max_items_per_feed: int,
) -> dict[str, Any]:
    session = requests.Session()
    try:
        items, resolved_feed_url = fetch_feed(session, feed, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return {
            "feed_report": {
                "name": feed.name,
                "kind": feed.kind,
                "tier": feed.tier,
                "feed_url": feed.feed_url,
                "alternate_feed_urls": list(feed.alternate_feed_urls),
                "author": feed.author,
                "status": "error",
                "enabled": False,
                "item_count": 0,
                "complete_count": 0,
                "recent_item_count": 0,
                "latest_published_at": "",
                "discovery_method": discovery_method_for_feed(feed),
                "error": str(exc),
            },
            "error": {
                "feed": feed.name,
                "url": feed.feed_url,
                "tried_urls": [feed.feed_url, *feed.alternate_feed_urls],
                "error": str(exc),
            },
            "candidates": [],
        }

    report = feed_validation(feed, items, resolved_feed_url=resolved_feed_url)
    feed_candidates: list[dict[str, Any]] = []
    if report["enabled"]:
        kept = 0
        for item in items:
            if kept >= max_items_per_feed:
                break
            candidate = build_candidate(feed, item, resolved_feed_url=resolved_feed_url)
            if not within_window(str(candidate.get("published_at", "")), window_hours):
                continue
            feed_candidates.append(candidate)
            kept += 1
    return {
        "feed_report": report,
        "error": None,
        "candidates": feed_candidates,
    }


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    raw_config, feeds = load_config(config_path)
    window_hours = int(args.window_hours or raw_config.get("window_hours", 24))
    max_items_per_feed = int(args.max_items_per_feed or raw_config.get("max_items_per_feed", 12))
    timeout = int(raw_config.get("request_timeout_seconds", 20))
    parallelism = max(
        1,
        int(
            args.parallelism
            or raw_config.get("parallelism")
            or os.environ.get("AI_DAILY_DISCOVERY_PARALLELISM", "8")
            or 8
        ),
    )

    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    feed_reports: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    results: list[dict[str, Any] | None] = [None] * len(feeds)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(parallelism, max(1, len(feeds)))) as executor:
        future_to_index = {
            executor.submit(
                fetch_feed_result,
                feed,
                timeout=timeout,
                window_hours=window_hours,
                max_items_per_feed=max_items_per_feed,
            ): index
            for index, feed in enumerate(feeds)
        }
        for future in concurrent.futures.as_completed(future_to_index):
            index = future_to_index[future]
            try:
                results[index] = future.result()
            except Exception as exc:  # noqa: BLE001
                feed = feeds[index]
                results[index] = {
                    "feed_report": {
                        "name": feed.name,
                        "kind": feed.kind,
                        "tier": feed.tier,
                        "feed_url": feed.feed_url,
                        "alternate_feed_urls": list(feed.alternate_feed_urls),
                        "author": feed.author,
                        "status": "error",
                        "enabled": False,
                        "item_count": 0,
                        "complete_count": 0,
                        "recent_item_count": 0,
                        "latest_published_at": "",
                        "discovery_method": discovery_method_for_feed(feed),
                        "error": str(exc),
                    },
                    "error": {
                        "feed": feed.name,
                        "url": feed.feed_url,
                        "tried_urls": [feed.feed_url, *feed.alternate_feed_urls],
                        "error": str(exc),
                    },
                    "candidates": [],
                }

    for result in results:
        if not result:
            continue
        feed_reports.append(result["feed_report"])
        if result.get("error"):
            errors.append(result["error"])
        for candidate in result.get("candidates") or []:
            if candidate["canonical_url"] in seen_urls:
                continue
            seen_urls.add(candidate["canonical_url"])
            candidates.append(candidate)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config_path),
        "rsshub_base_url": str(raw_config.get("rsshub_base_url", "")),
        "rsshub_base_urls": [str(value).rstrip("/") for value in raw_config.get("rsshub_base_urls", [])],
        "window_hours": window_hours,
        "parallelism": parallelism,
        "feed_count": len(feeds),
        "enabled_feed_count": sum(1 for report in feed_reports if report.get("enabled")),
        "candidate_count": len(candidates),
        "error_count": len(errors),
        "feed_reports": feed_reports,
        "candidates": candidates,
        "errors": errors,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
