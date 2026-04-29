#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

import requests
from bs4 import BeautifulSoup


WORKSPACE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = WORKSPACE_DIR / "skills" / "ai-daily-intel" / "references" / "early-signal-discovery.toml"

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

HTML_RE = re.compile(r"<[^>]+>")
WORD_RE = re.compile(r"[a-z0-9][a-z0-9+._-]{2,}", re.I)
AI_TERMS_RE = re.compile(
    r"\b(ai|agent|agents|llm|model|models|inference|eval|evals|multimodal|"
    r"claude|gpt|gemini|mistral|cursor|codex|mcp|rag|voice|video|diffusion)\b",
    re.I,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build early-signal AI daily discovery candidates.")
    parser.add_argument("--date", help="YYYY-MM-DD. Defaults to local today.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="early-signal TOML config path.")
    parser.add_argument("--rsshub-json", help="Optional existing RSSHub discovery JSON used for overlap scoring.")
    parser.add_argument("--out", required=True, help="Output early-signal candidate JSON.")
    parser.add_argument("--summary-out", help="Optional early-signal preflight summary JSON.")
    parser.add_argument("--window-hours", type=int, default=24, help="Hot window for candidates.")
    parser.add_argument("--research-window-hours", type=int, default=72, help="Wider research velocity window.")
    parser.add_argument("--timeout-seconds", type=int, default=720, help="Wall-clock budget for this script.")
    parser.add_argument("--max-candidates", type=int, help="Override max_total_candidates from config.")
    return parser.parse_args()


def local_today() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        return {}
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return raw if isinstance(raw, dict) else {}


def load_config(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


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


def parse_iso(raw: str) -> datetime | None:
    value = (raw or "").strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def within_window(published_at: str, hours: int) -> bool:
    parsed = parse_iso(published_at)
    if not parsed:
        return True
    return parsed >= datetime.now(timezone.utc) - timedelta(hours=max(hours, 1))


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def strip_markup(value: str) -> str:
    return normalize_spaces(HTML_RE.sub(" ", html.unescape(value or "")))


def canonicalize_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path or "/"
    query_pairs = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid", "ref", "source"}
    ]
    if netloc in {"twitter.com", "x.com"}:
        netloc = "x.com"
        query_pairs = []
    query = urlencode(query_pairs, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def source_host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def title_tokens(title: str) -> set[str]:
    return {token.lower() for token in WORD_RE.findall(strip_markup(title)) if len(token) >= 4}


def candidate_hash(url: str, title: str, published_at: str) -> str:
    return hashlib.sha1("|".join([url, title, published_at]).encode("utf-8")).hexdigest()[:16]


def make_candidate(
    *,
    lane: str,
    kind: str,
    feed_name: str,
    title: str,
    url: str,
    author: str = "",
    summary: str = "",
    published_at: str = "",
    score: float = 1.0,
    reason: str = "",
    evidence_count: int = 1,
    source_independence: int = 1,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    clean_title = strip_markup(title)[:220]
    canonical_url = canonicalize_url(url)
    if not clean_title or not canonical_url:
        return None
    payload: dict[str, Any] = {
        "canonical_url": canonical_url,
        "source_kind": kind,
        "source_author": author,
        "published_at": published_at,
        "discovery_method": "early_signal",
        "feed_name": feed_name,
        "feed_url": canonical_url,
        "title": clean_title,
        "snippet": strip_markup(summary)[:1600],
        "candidate_hash": candidate_hash(canonical_url, clean_title, published_at),
        "seed": True,
        "source_tier": "early_signal",
        "item_id": urlparse(canonical_url).path.strip("/") or canonical_url,
        "article_id": urlparse(canonical_url).path.strip("/") or canonical_url,
        "signal_lane": lane,
        "signal_score": round(max(score, 0.0), 3),
        "evidence_count": max(int(evidence_count or 1), 1),
        "source_independence": max(int(source_independence or 1), 1),
        "discovery_reason": reason or lane,
    }
    if extra:
        payload.update(extra)
    return payload


def fetch_text(session: requests.Session, url: str, *, timeout: int, headers: dict[str, str] | None = None) -> str:
    response = session.get(url, headers=headers or REQUEST_HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text


def parse_feed_items(xml_text: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, str]] = []
    for node in root.iter():
        if local_name(node.tag) not in {"item", "entry"}:
            continue
        title = first_child_text(node, "title")
        summary = first_child_text(node, "description", "summary", "content", "content:encoded")
        published = first_child_text(node, "pubDate", "published", "updated")
        author = first_child_text(node, "author", "creator", "dc:creator")
        link = ""
        for child in list(node):
            if local_name(child.tag) == "link":
                href = child.attrib.get("href", "").strip()
                text = "".join(child.itertext()).strip()
                link = href or text
                if link:
                    break
        if title and link:
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


def fetch_feed_candidates(
    session: requests.Session,
    *,
    lane: str,
    kind: str,
    feed_name: str,
    url: str,
    author: str,
    timeout: int,
    window_hours: int,
    max_items: int,
    reason: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        items = parse_feed_items(fetch_text(session, url, timeout=timeout))
    except Exception as exc:  # noqa: BLE001
        return [], {"name": feed_name, "lane": lane, "status": "error", "url": url, "error": str(exc)[:500]}

    candidates: list[dict[str, Any]] = []
    for item in items[: max(max_items * 2, max_items)]:
        if not within_window(item.get("published_at", ""), window_hours):
            continue
        candidate = make_candidate(
            lane=lane,
            kind=kind,
            feed_name=feed_name,
            title=item["title"],
            url=item["link"],
            author=item.get("author") or author,
            summary=item.get("summary", ""),
            published_at=item.get("published_at", ""),
            score=3.0,
            reason=reason,
        )
        if candidate:
            candidates.append(candidate)
        if len(candidates) >= max_items:
            break
    return candidates, {
        "name": feed_name,
        "lane": lane,
        "status": "ok" if candidates else "empty",
        "url": url,
        "item_count": len(items),
        "candidate_count": len(candidates),
    }


def discover_hn(
    session: requests.Session,
    queries: list[str],
    *,
    timeout: int,
    window_hours: int,
    max_items: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    since = int((datetime.now(timezone.utc) - timedelta(hours=window_hours)).timestamp())
    candidates: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in queries:
        params = {
            "query": query,
            "tags": "story",
            "numericFilters": f"created_at_i>{since}",
            "hitsPerPage": "12",
        }
        url = "https://hn.algolia.com/api/v1/search_by_date?" + urlencode(params)
        try:
            payload = session.get(url, headers=REQUEST_HEADERS, timeout=timeout).json()
        except Exception as exc:  # noqa: BLE001
            reports.append({"name": f"hn:{query}", "lane": "people_voice", "status": "error", "error": str(exc)[:500]})
            continue
        hits = payload.get("hits") if isinstance(payload, dict) else []
        kept = 0
        for hit in hits if isinstance(hits, list) else []:
            if not isinstance(hit, dict):
                continue
            title = str(hit.get("title") or hit.get("story_title") or "")
            target = str(hit.get("url") or "")
            object_id = str(hit.get("objectID") or "")
            if not target and object_id:
                target = f"https://news.ycombinator.com/item?id={object_id}"
            canonical = canonicalize_url(target)
            if not title or not canonical or canonical in seen:
                continue
            seen.add(canonical)
            points = int(hit.get("points") or 0)
            comments = int(hit.get("num_comments") or 0)
            score = 3.5 + min(points / 120.0, 2.0) + min(comments / 80.0, 2.0)
            hn_url = f"https://news.ycombinator.com/item?id={object_id}" if object_id else ""
            candidate = make_candidate(
                lane="people_voice",
                kind="hacker_news",
                feed_name="hn-algolia",
                title=title,
                url=canonical,
                author=str(hit.get("author") or "Hacker News"),
                summary=f"HN query={query}; points={points}; comments={comments}; discussion={hn_url}",
                published_at=parse_timestamp(str(hit.get("created_at") or "")),
                score=score,
                reason="HN discussion velocity around AI/operator topics",
                evidence_count=1 + int(bool(hn_url)),
                source_independence=1,
                extra={"hn_object_id": object_id, "hn_points": points, "hn_comments": comments, "hn_discussion_url": hn_url},
            )
            if candidate:
                candidates.append(candidate)
                kept += 1
            if len(candidates) >= max_items:
                break
        reports.append({"name": f"hn:{query}", "lane": "people_voice", "status": "ok", "hit_count": len(hits), "candidate_count": kept})
        if len(candidates) >= max_items:
            break
    return candidates, reports


def discover_product_shadow(
    session: requests.Session,
    monitors: list[dict[str, Any]],
    keywords: list[str],
    *,
    timeout: int,
    max_items: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    keyword_re = re.compile("|".join(re.escape(word) for word in keywords if word), re.I)
    candidates: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    seen: set[str] = set()
    for monitor in monitors:
        name = str(monitor.get("name") or "product-monitor")
        company = str(monitor.get("company") or name)
        url = str(monitor.get("url") or "")
        try:
            raw_html = fetch_text(session, url, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            reports.append({"name": name, "lane": "product_shadow", "status": "error", "url": url, "error": str(exc)[:500]})
            continue
        soup = BeautifulSoup(raw_html, "html.parser")
        page_title = normalize_spaces(soup.title.get_text(" ", strip=True) if soup.title else company)
        links: list[tuple[str, str]] = []
        for anchor in soup.find_all("a", href=True):
            href = urljoin(url, str(anchor.get("href") or ""))
            parsed = urlparse(href)
            if parsed.scheme not in {"http", "https"}:
                continue
            if source_host(href) != source_host(url):
                continue
            label = normalize_spaces(anchor.get_text(" ", strip=True))
            path_text = parsed.path.replace("-", " ").replace("_", " ")
            combined = f"{label} {path_text}"
            if not label or len(label) < 4:
                continue
            if keyword_re.search(combined) or AI_TERMS_RE.search(combined):
                links.append((label, canonicalize_url(href)))
        if not links:
            links.append((page_title, canonicalize_url(url)))
        kept = 0
        for label, href in links:
            if not href or href in seen:
                continue
            seen.add(href)
            candidate = make_candidate(
                lane="product_shadow",
                kind="product_shadow",
                feed_name=name,
                title=f"{company}: {label}",
                url=href,
                author=company,
                summary=f"First-party monitored page: {url}",
                published_at="",
                score=3.2 + min(len(title_tokens(label)) / 6.0, 1.5),
                reason="first-party product/docs/changelog page monitor",
                evidence_count=1,
                source_independence=1,
                extra={"monitor_url": url, "page_fingerprint": hashlib.sha1(raw_html[:8000].encode("utf-8")).hexdigest()[:16]},
            )
            if candidate:
                candidates.append(candidate)
                kept += 1
            if kept >= 3 or len(candidates) >= max_items:
                break
        reports.append({"name": name, "lane": "product_shadow", "status": "ok", "url": url, "candidate_count": kept})
        if len(candidates) >= max_items:
            break
    return candidates, reports


def discover_arxiv(
    session: requests.Session,
    categories: list[str],
    *,
    timeout: int,
    window_hours: int,
    max_results: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    query = " OR ".join(f"cat:{category}" for category in categories)
    params = {
        "search_query": query,
        "start": "0",
        "max_results": str(max_results),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = "https://export.arxiv.org/api/query?" + urlencode(params)
    try:
        items = parse_feed_items(fetch_text(session, url, timeout=timeout))
    except Exception as exc:  # noqa: BLE001
        return [], {"name": "arxiv", "lane": "research_velocity", "status": "error", "url": url, "error": str(exc)[:500]}
    candidates: list[dict[str, Any]] = []
    for item in items:
        if not within_window(item.get("published_at", ""), window_hours):
            continue
        candidate = make_candidate(
            lane="research_velocity",
            kind="arxiv",
            feed_name="arxiv-submitted",
            title=item["title"],
            url=item["link"],
            author=item.get("author") or "arXiv",
            summary=item.get("summary", ""),
            published_at=item.get("published_at", ""),
            score=4.0,
            reason="fresh arXiv submission in AI/ML categories",
        )
        if candidate:
            candidates.append(candidate)
    return candidates, {"name": "arxiv", "lane": "research_velocity", "status": "ok", "item_count": len(items), "candidate_count": len(candidates)}


def discover_hf_papers(session: requests.Session, url: str, *, timeout: int, max_items: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        raw_html = fetch_text(session, url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return [], {"name": "huggingface-papers", "lane": "research_velocity", "status": "error", "url": url, "error": str(exc)[:500]}
    soup = BeautifulSoup(raw_html, "html.parser")
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if not href.startswith("/papers/"):
            continue
        title = normalize_spaces(anchor.get_text(" ", strip=True))
        if not title or len(title) < 12:
            continue
        target = canonicalize_url(urljoin("https://huggingface.co", href))
        if target in seen:
            continue
        seen.add(target)
        candidate = make_candidate(
            lane="research_velocity",
            kind="huggingface_paper",
            feed_name="huggingface-papers-trending",
            title=title,
            url=target,
            author="Hugging Face Papers",
            summary="Trending paper surfaced by Hugging Face Papers.",
            published_at="",
            score=3.8,
            reason="HF Papers trending diffusion signal",
        )
        if candidate:
            candidates.append(candidate)
        if len(candidates) >= max_items:
            break
    return candidates, {"name": "huggingface-papers", "lane": "research_velocity", "status": "ok" if candidates else "empty", "candidate_count": len(candidates)}


def github_headers(config: dict[str, Any]) -> dict[str, str]:
    optional_auth = config.get("optional_auth") if isinstance(config.get("optional_auth"), dict) else {}
    token = os.environ.get(str(optional_auth.get("github_token_env") or "GITHUB_TOKEN")) or os.environ.get(
        str(optional_auth.get("github_fallback_token_env") or "GH_TOKEN")
    )
    headers = {**REQUEST_HEADERS, "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def discover_github_search(
    session: requests.Session,
    queries: list[str],
    *,
    config: dict[str, Any],
    timeout: int,
    min_stars: int,
    created_days: int,
    max_items: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    since = (datetime.now(timezone.utc) - timedelta(days=max(created_days, 1))).date().isoformat()
    candidates: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    seen: set[str] = set()
    headers = github_headers(config)
    for query in queries:
        q = f"{query} created:>={since} stars:>={max(min_stars, 0)}"
        params = {"q": q, "sort": "stars", "order": "desc", "per_page": "10"}
        url = "https://api.github.com/search/repositories?" + urlencode(params)
        try:
            payload = session.get(url, headers=headers, timeout=timeout).json()
        except Exception as exc:  # noqa: BLE001
            reports.append({"name": f"github:{query}", "lane": "research_velocity", "status": "error", "error": str(exc)[:500]})
            continue
        items = payload.get("items") if isinstance(payload, dict) else []
        kept = 0
        for repo in items if isinstance(items, list) else []:
            if not isinstance(repo, dict):
                continue
            html_url = str(repo.get("html_url") or "")
            if not html_url or html_url in seen:
                continue
            seen.add(html_url)
            stars = int(repo.get("stargazers_count") or 0)
            forks = int(repo.get("forks_count") or 0)
            score = 4.0 + min(stars / 500.0, 2.0) + min(forks / 100.0, 1.0)
            candidate = make_candidate(
                lane="research_velocity",
                kind="github_repo",
                feed_name="github-search",
                title=str(repo.get("full_name") or repo.get("name") or ""),
                url=html_url,
                author=str(repo.get("owner", {}).get("login") if isinstance(repo.get("owner"), dict) else "GitHub"),
                summary=str(repo.get("description") or ""),
                published_at=parse_timestamp(str(repo.get("created_at") or repo.get("pushed_at") or "")),
                score=score,
                reason="new GitHub repository with early star velocity",
                evidence_count=1,
                source_independence=1,
                extra={"github_stars": stars, "github_forks": forks, "github_query": query},
            )
            if candidate:
                candidates.append(candidate)
                kept += 1
            if len(candidates) >= max_items:
                break
        reports.append({"name": f"github:{query}", "lane": "research_velocity", "status": "ok", "candidate_count": kept})
        if len(candidates) >= max_items:
            break
    return candidates, reports


def overlap_terms(payload: dict[str, Any]) -> Counter[str]:
    counter: Counter[str] = Counter()
    candidates = payload.get("candidates") if isinstance(payload, dict) else []
    for candidate in candidates if isinstance(candidates, list) else []:
        if not isinstance(candidate, dict):
            continue
        text = f"{candidate.get('title') or ''} {candidate.get('snippet') or ''}"
        for token in title_tokens(text):
            counter[token] += 1
    return counter


def apply_overlap_scores(candidates: list[dict[str, Any]], rsshub_payload: dict[str, Any]) -> None:
    terms = overlap_terms(rsshub_payload)
    if not terms:
        return
    for candidate in candidates:
        shared = sum(1 for token in title_tokens(str(candidate.get("title") or "")) if terms[token] > 0)
        if shared <= 0:
            continue
        candidate["signal_score"] = round(float(candidate.get("signal_score") or 0.0) + min(shared * 0.35, 1.5), 3)
        candidate["evidence_count"] = int(candidate.get("evidence_count") or 1) + 1
        candidate["source_independence"] = int(candidate.get("source_independence") or 1) + 1
        candidate["discovery_reason"] = f"{candidate.get('discovery_reason')}; overlaps with RSS/community terms"


def title_similarity(left: str, right: str) -> float:
    a = title_tokens(left)
    b = title_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a | b), 1)


def dedupe_candidates(candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    ranked = sorted(
        candidates,
        key=lambda item: (
            float(item.get("signal_score") or 0.0),
            int(item.get("evidence_count") or 1),
            str(item.get("published_at") or ""),
        ),
        reverse=True,
    )
    kept: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for candidate in ranked:
        url = str(candidate.get("canonical_url") or "")
        if not url or url in seen_urls:
            continue
        duplicate = None
        for existing in kept:
            if source_host(url) == source_host(str(existing.get("canonical_url") or "")) and title_similarity(
                str(candidate.get("title") or ""), str(existing.get("title") or "")
            ) >= 0.72:
                duplicate = existing
                break
        if duplicate:
            evidence = duplicate.setdefault("secondary_evidence", [])
            if isinstance(evidence, list):
                evidence.append(
                    {
                        "title": candidate.get("title"),
                        "url": url,
                        "signal_lane": candidate.get("signal_lane"),
                        "signal_score": candidate.get("signal_score"),
                    }
                )
            duplicate["evidence_count"] = int(duplicate.get("evidence_count") or 1) + int(candidate.get("evidence_count") or 1)
            duplicate["source_independence"] = max(
                int(duplicate.get("source_independence") or 1), int(candidate.get("source_independence") or 1)
            )
            continue
        seen_urls.add(url)
        kept.append(candidate)
        if len(kept) >= limit:
            break
    return kept


def lane_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for candidate in candidates:
        counts[str(candidate.get("signal_lane") or "unknown")] += 1
    return dict(counts)


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    run_date = args.date or local_today()
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    timeout = int(config.get("request_timeout_seconds") or 16)
    max_items_per_lane = int(config.get("max_items_per_lane") or 30)
    max_total = int(args.max_candidates or config.get("max_total_candidates") or 160)
    window_hours = max(int(args.window_hours or 24), 1)
    research_window_hours = max(int(args.research_window_hours or 72), window_hours)
    session = requests.Session()

    candidates: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def budget_ok() -> bool:
        return (time.monotonic() - started) < max(int(args.timeout_seconds or 720) - 5, 10)

    people = config.get("people_voice") if isinstance(config.get("people_voice"), dict) else {}
    if budget_ok():
        hn_candidates, hn_reports = discover_hn(
            session,
            [str(value) for value in people.get("hn_queries", [])],
            timeout=timeout,
            window_hours=window_hours,
            max_items=max_items_per_lane,
        )
        candidates.extend(hn_candidates)
        reports.extend(hn_reports)

    for feed in people.get("reddit_feeds", []) if isinstance(people.get("reddit_feeds"), list) else []:
        if not budget_ok():
            break
        feed_candidates, report = fetch_feed_candidates(
            session,
            lane="people_voice",
            kind="reddit",
            feed_name=str(feed.get("name") or "reddit"),
            url=str(feed.get("url") or ""),
            author=str(feed.get("author") or ""),
            timeout=timeout,
            window_hours=window_hours,
            max_items=8,
            reason="Reddit practitioner discussion velocity",
        )
        candidates.extend(feed_candidates)
        reports.append(report)

    for feed in people.get("blog_feeds", []) if isinstance(people.get("blog_feeds"), list) else []:
        if not budget_ok():
            break
        feed_candidates, report = fetch_feed_candidates(
            session,
            lane="people_voice",
            kind="blog",
            feed_name=str(feed.get("name") or "blog"),
            url=str(feed.get("url") or ""),
            author=str(feed.get("author") or ""),
            timeout=timeout,
            window_hours=research_window_hours,
            max_items=6,
            reason="curated founder/researcher/operator longform signal",
        )
        candidates.extend(feed_candidates)
        reports.append(report)

    product = config.get("product_shadow") if isinstance(config.get("product_shadow"), dict) else {}
    if budget_ok():
        product_candidates, product_reports = discover_product_shadow(
            session,
            product.get("monitors", []) if isinstance(product.get("monitors"), list) else [],
            [str(value) for value in product.get("keywords", [])],
            timeout=timeout,
            max_items=max_items_per_lane,
        )
        candidates.extend(product_candidates)
        reports.extend(product_reports)

    research = config.get("research_velocity") if isinstance(config.get("research_velocity"), dict) else {}
    if budget_ok():
        arxiv_candidates, arxiv_report = discover_arxiv(
            session,
            [str(value) for value in research.get("arxiv_categories", [])],
            timeout=timeout,
            window_hours=research_window_hours,
            max_results=int(research.get("arxiv_max_results") or 40),
        )
        candidates.extend(arxiv_candidates)
        reports.append(arxiv_report)

    if budget_ok():
        hf_candidates, hf_report = discover_hf_papers(
            session,
            str(research.get("huggingface_papers_url") or "https://huggingface.co/papers/trending"),
            timeout=timeout,
            max_items=12,
        )
        candidates.extend(hf_candidates)
        reports.append(hf_report)

    if budget_ok():
        github_candidates, github_reports = discover_github_search(
            session,
            [str(value) for value in research.get("github_queries", [])],
            config=config,
            timeout=timeout,
            min_stars=int(research.get("github_min_stars") or 25),
            created_days=int(research.get("github_created_days") or 7),
            max_items=max_items_per_lane,
        )
        candidates.extend(github_candidates)
        reports.extend(github_reports)

    for feed in research.get("release_feeds", []) if isinstance(research.get("release_feeds"), list) else []:
        if not budget_ok():
            break
        feed_candidates, report = fetch_feed_candidates(
            session,
            lane="research_velocity",
            kind="github_release",
            feed_name=str(feed.get("name") or "github-release"),
            url=str(feed.get("url") or ""),
            author=str(feed.get("author") or ""),
            timeout=timeout,
            window_hours=research_window_hours,
            max_items=6,
            reason="release velocity in AI tooling stack",
        )
        candidates.extend(feed_candidates)
        reports.append(report)

    if not budget_ok():
        warnings.append({"kind": "timeout_budget", "message": "Stopped early due to configured early-signal wall-clock budget."})

    apply_overlap_scores(candidates, load_json(args.rsshub_json))
    candidates = dedupe_candidates(candidates, max_total)
    counts = lane_counts(candidates)
    thresholds = config.get("thresholds") if isinstance(config.get("thresholds"), dict) else {}
    targets_met = (
        len(candidates) >= int(thresholds.get("min_total_candidates") or 0)
        and counts.get("people_voice", 0) >= int(thresholds.get("min_people_voice") or 0)
        and counts.get("product_shadow", 0) >= int(thresholds.get("min_product_shadow") or 0)
        and counts.get("research_velocity", 0) >= int(thresholds.get("min_research_velocity") or 0)
    )
    payload = {
        "generated_at": utc_now_iso(),
        "date": run_date,
        "config": str(config_path),
        "window_hours": window_hours,
        "research_window_hours": research_window_hours,
        "candidate_count": len(candidates),
        "lane_counts": counts,
        "targets": {
            "min_total_candidates": int(thresholds.get("min_total_candidates") or 0),
            "min_people_voice": int(thresholds.get("min_people_voice") or 0),
            "min_product_shadow": int(thresholds.get("min_product_shadow") or 0),
            "min_research_velocity": int(thresholds.get("min_research_velocity") or 0),
        },
        "targets_met": targets_met,
        "status": "pass" if targets_met else "warn",
        "reports": reports,
        "warnings": warnings,
        "candidates": candidates,
    }

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.summary_out:
        summary_path = Path(args.summary_out).expanduser().resolve()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary = dict(payload)
        summary.pop("candidates", None)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
