#!/usr/bin/env python3

from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


URL_RE = re.compile(r"https?://\S+")
HTML_RE = re.compile(r"<[^>]+>")
ASCII_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+._-]{2,}")
CJK_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,10}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build search terms from daily discovery facts without topic hardcoding.")
    parser.add_argument("--discovery-json", required=True, help="Input discovery candidate JSON.")
    parser.add_argument("--out", help="Optional output JSON path.")
    parser.add_argument("--top-topics", type=int, default=20, help="Maximum topic rows.")
    return parser.parse_args()


def load_discovery(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        candidates = raw.get("candidates") or raw.get("items") or []
        return [item for item in candidates if isinstance(item, dict)]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def strip_markup(value: str) -> str:
    text = html.unescape(value or "")
    text = HTML_RE.sub(" ", text)
    text = URL_RE.sub(" ", text)
    return normalize_spaces(text)


def canonical_url(candidate: dict[str, Any]) -> str:
    return normalize_spaces(str(candidate.get("canonical_url") or candidate.get("url") or ""))


def source_host(url: str) -> str:
    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    host = parsed.netloc.lower()
    return host.removeprefix("www.")


def clean_title(value: str) -> str:
    text = strip_markup(value)
    text = re.sub(r"^\[[^\]]+\]\s*", "", text)
    text = re.sub(r"\s*[|｜]\s*", " | ", text)
    parts = [part.strip(" -|") for part in text.split(" | ") if part.strip(" -|")]
    if parts:
        text = max(parts, key=len)
    return text[:140].strip()


def token_counter(*parts: str) -> Counter[str]:
    text = " ".join(strip_markup(part) for part in parts if part)
    counter: Counter[str] = Counter()
    for token in ASCII_TOKEN_RE.findall(text):
        if token.lower().startswith(("http", "www")):
            continue
        counter[token] += 1
    for token in CJK_TOKEN_RE.findall(text):
        counter[token] += 1
    return counter


def keyword_list(candidate: dict[str, Any], limit: int = 6) -> list[str]:
    counter = token_counter(
        str(candidate.get("title") or ""),
        str(candidate.get("summary") or ""),
        str(candidate.get("excerpt") or ""),
        str(candidate.get("snippet") or ""),
        str(candidate.get("note") or ""),
    )
    keywords: list[str] = []
    for token, _count in counter.most_common(limit * 4):
        value = token.strip("._- ")
        if len(value) < 3 and not re.search(r"[\u4e00-\u9fff]", value):
            continue
        if value not in keywords:
            keywords.append(value)
        if len(keywords) >= limit:
            break
    return keywords


def search_seed(title: str, keywords: list[str], url: str) -> str:
    parts: list[str] = []
    for keyword in keywords:
        if keyword not in parts:
            parts.append(keyword)
        if len(parts) >= 3:
            break
    if len(parts) < 2:
        title_tokens = token_counter(title).most_common(4)
        for token, _count in title_tokens:
            if token not in parts:
                parts.append(token)
            if len(parts) >= 3:
                break
    host = source_host(url)
    if host and len(parts) < 3:
        parts.append(host)
    return " ".join(parts[:4]).strip() or title[:80].strip()


def candidate_topic_row(candidate: dict[str, Any]) -> dict[str, Any] | None:
    title = clean_title(str(candidate.get("title") or ""))
    url = canonical_url(candidate)
    if not title or not url:
        return None
    keywords = keyword_list(candidate)
    seed = search_seed(title, keywords, url)
    score = float(candidate.get("score") or candidate.get("hot_score") or 0.0)
    if not score:
        score = 1.0 + min(len(strip_markup(str(candidate.get("summary") or candidate.get("excerpt") or ""))) / 400.0, 3.0)
    return {
        "topic": seed,
        "search_seed": seed,
        "score": round(score, 3),
        "title": title,
        "canonical_url": url,
        "source_kind": str(candidate.get("source_kind") or candidate.get("kind") or ""),
        "feed_name": str(candidate.get("feed_name") or candidate.get("source") or ""),
        "published_at": str(candidate.get("published_at") or candidate.get("updated_at") or ""),
        "source_host": source_host(url),
        "keywords": keywords,
    }


def dedupe_topics(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: float(item.get("score") or 0), reverse=True):
        key = (str(row.get("canonical_url") or "") or str(row.get("search_seed") or "")).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
        if len(deduped) >= limit:
            break
    return deduped


def query_rows(topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for topic in topics:
        seed = str(topic.get("search_seed") or topic.get("topic") or "").strip()
        url = str(topic.get("canonical_url") or "").strip()
        host = str(topic.get("source_host") or "").strip()
        queries = [{"lane": "topic", "query": seed}]
        if host:
            queries.append({"lane": "source_host", "query": f"{seed} site:{host}"})
        if url:
            queries.append({"lane": "source_url", "query": url})
        rows.append(
            {
                "topic": topic.get("topic"),
                "search_seed": seed,
                "canonical_url": url,
                "queries": queries,
            }
        )
    return rows


def build_payload(discovery_json: Path, candidates: list[dict[str, Any]], top_topics: int) -> dict[str, Any]:
    rows = [row for candidate in candidates for row in [candidate_topic_row(candidate)] if row]
    topics = dedupe_topics(rows, top_topics)
    return {
        "discovery_json": str(discovery_json),
        "topic_count": len(topics),
        "hot_topics": topics,
        "x_queries": [str(row.get("search_seed") or "") for row in topics if str(row.get("search_seed") or "").strip()],
        "queries": query_rows(topics),
        "author_queries": [],
    }


def main() -> int:
    args = parse_args()
    discovery_json = Path(args.discovery_json).expanduser().resolve()
    payload = build_payload(discovery_json, load_discovery(discovery_json), args.top_topics)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        out_path = Path(args.out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
