#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ai_daily_paths import ai_daily_root, tech_daily_source_pack_dir


URL_RE = re.compile(r"https?://[^\s<>()\"']+")
ASCII_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+._-]{2,}")
CJK_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,10}")


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
        if not key.lower().startswith("utm_") and key.lower() not in {"ref", "source", "fbclid", "gclid"}
    ]
    if netloc in {"twitter.com", "x.com"}:
        netloc = "x.com"
        query_pairs = []
    query = urlencode(query_pairs, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def extract_platform_id(kind: str, url: str) -> str:
    parsed = urlparse(url or "")
    if not parsed.netloc:
        return ""
    return parsed.path.strip("/") or parsed.query


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


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
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def candidate_text(candidate: dict[str, Any]) -> str:
    return " ".join(
        clean_text(str(candidate.get(key) or ""))
        for key in ("title", "summary", "excerpt", "snippet", "note", "text")
    ).strip()


def source_kind(candidate: dict[str, Any]) -> str:
    return str(candidate.get("source_kind") or candidate.get("kind") or "").strip().lower()


def source_host(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host.removeprefix("www.")


def text_tokens(*parts: str, limit: int = 8) -> list[str]:
    text = " ".join(clean_text(part) for part in parts if part)
    counts: Counter[str] = Counter()
    for token in ASCII_TOKEN_RE.findall(text):
        if token.lower().startswith(("http", "www")):
            continue
        counts[token] += 1
    for token in CJK_TOKEN_RE.findall(text):
        counts[token] += 1
    result: list[str] = []
    for token, _count in counts.most_common(limit * 4):
        value = token.strip("._- ")
        if len(value) < 3 and not re.search(r"[\u4e00-\u9fff]", value):
            continue
        if value not in result:
            result.append(value)
        if len(result) >= limit:
            break
    return result


def summarize_text(text: str, limit: int = 220) -> str:
    value = clean_text(text)
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 1)].rstrip() + "…"


def load_discovery(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        candidates = raw.get("candidates") or raw.get("items") or []
        return [item for item in candidates if isinstance(item, dict)]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def load_source_pack(path: Path) -> dict[str, dict[str, Any]]:
    index_path = Path(path).expanduser().resolve() / "index.json"
    if not index_path.exists():
        return {}
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    sources = raw.get("sources") if isinstance(raw, dict) else []
    by_url: dict[str, dict[str, Any]] = {}
    for source in sources if isinstance(sources, list) else []:
        if not isinstance(source, dict):
            continue
        for raw_url in (source.get("url"), source.get("final_url"), source.get("canonical_url")):
            url = canonicalize_url(str(raw_url or ""))
            if url and url not in by_url:
                enriched = dict(source)
                enriched["_source_pack_dir"] = str(path)
                by_url[url] = enriched
    return by_url


def published_at(candidate: dict[str, Any]) -> datetime | None:
    return parse_iso(str(candidate.get("published_at") or candidate.get("updated_at") or candidate.get("created_at") or ""))


def duplicate_key(candidate: dict[str, Any]) -> str:
    explicit = str(candidate.get("duplicate_key") or "").strip()
    if explicit:
        return explicit
    url = canonicalize_url(str(candidate.get("canonical_url") or candidate.get("url") or ""))
    if url:
        return url
    title = clean_text(str(candidate.get("title") or "")).lower()
    return re.sub(r"\W+", "", title)[:120]


def source_depth(candidate: dict[str, Any], source_meta: dict[str, Any]) -> float:
    text = candidate_text(candidate)
    text_chars = candidate.get("text_chars")
    try:
        chars = int(text_chars or 0)
    except (TypeError, ValueError):
        chars = 0
    chars = max(chars, len(text), len(str(source_meta.get("text_excerpt") or source_meta.get("summary") or "")))
    score = min(chars / 1200.0, 1.0) * 4.0
    if source_meta:
        score += 2.0
    if source_meta.get("hero_image_file") or source_meta.get("image_files"):
        score += 0.6
    if str(source_meta.get("status") or "").lower() in {"ok", "success", "archived"}:
        score += 0.8
    return round(max(0.0, min(10.0, score + 2.0)), 2)


def recency_score(candidate: dict[str, Any], now: datetime, lookback_hours: int) -> float:
    published = published_at(candidate)
    if not published:
        return 4.0
    age_hours = max(0.0, (now - published).total_seconds() / 3600.0)
    window = max(float(lookback_hours), 1.0)
    return round(max(0.0, 10.0 * (1.0 - min(age_hours, window) / window)), 2)


def traceability_score(candidate: dict[str, Any], source_meta: dict[str, Any]) -> float:
    url = canonicalize_url(str(candidate.get("canonical_url") or candidate.get("url") or ""))
    score = 0.0
    if url:
        score += 3.0
    if source_meta:
        score += 3.0
    if candidate.get("usable_for_scoring") or source_meta.get("usable_for_scoring"):
        score += 2.0
    if candidate.get("source") or candidate.get("feed_name"):
        score += 1.0
    if source_host(url):
        score += 1.0
    return round(max(0.0, min(10.0, score)), 2)


def candidate_score(candidate: dict[str, Any], source_meta: dict[str, Any], now: datetime, lookback_hours: int) -> float:
    recency = recency_score(candidate, now, lookback_hours)
    depth = source_depth(candidate, source_meta)
    trace = traceability_score(candidate, source_meta)
    return round(recency * 0.35 + depth * 0.35 + trace * 0.30, 2)


def selection_fit(candidate: dict[str, Any]) -> str:
    score = float(candidate.get("review_score") or 0.0)
    trace = float(candidate.get("traceability_score") or 0.0)
    depth = float(candidate.get("source_depth_score") or 0.0)
    recency = float(candidate.get("recency_score") or 0.0)
    if score >= 7.4 and depth >= 6.0:
        return "deep_traceable_source"
    if score >= 7.0 and recency >= 6.0:
        return "fresh_traceable_source"
    if trace >= 8.0:
        return "traceable_source"
    return "secondary_trace"


def is_fresh_candidate(candidate: dict[str, Any], now: datetime, lookback_hours: int) -> bool:
    published = published_at(candidate)
    if not published:
        return False
    age_hours = (now - published).total_seconds() / 3600.0
    return -1.0 <= age_hours <= max(float(lookback_hours), 1.0)


def passes_body_gate(candidate: dict[str, Any], now: datetime, lookback_hours: int) -> bool:
    title = clean_text(str(candidate.get("title") or ""))
    url = canonicalize_url(str(candidate.get("canonical_url") or candidate.get("url") or ""))
    if not title or not url:
        return False
    if not is_fresh_candidate(candidate, now, lookback_hours):
        return False
    return float(candidate.get("traceability_score") or 0.0) >= 3.0


def recent_history(root: Path, current_date: str, days: int) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    current = parse_iso(f"{current_date}T00:00:00+00:00")
    if not current:
        return history
    for offset in range(1, days + 1):
        day = (current - timedelta(days=offset)).date().isoformat()
        path = root / day / "final" / "report.json"
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for item in raw.get("items", []) if isinstance(raw, dict) else []:
            if isinstance(item, dict):
                history.append(item)
    return history


def hamming_distance(left: str, right: str) -> int:
    max_len = max(len(left), len(right))
    if max_len == 0:
        return 0
    left_padded = left.ljust(max_len)
    right_padded = right.ljust(max_len)
    return sum(1 for a, b in zip(left_padded, right_padded) if a != b)


def enrich_candidate(candidate: dict[str, Any], source_pack: dict[str, dict[str, Any]], now: datetime, lookback_hours: int) -> dict[str, Any]:
    url = canonicalize_url(str(candidate.get("canonical_url") or candidate.get("url") or ""))
    source_meta = source_pack.get(url, {})
    enriched = dict(candidate)
    enriched["canonical_url"] = url
    enriched["source_kind"] = source_kind(candidate)
    enriched["source_host"] = source_host(url)
    enriched["duplicate_key"] = duplicate_key(candidate)
    enriched["keywords"] = text_tokens(str(candidate.get("title") or ""), candidate_text(candidate))
    enriched["summary_for_editor"] = summarize_text(
        " ".join(
            part
            for part in [
                str(candidate.get("summary") or candidate.get("excerpt") or candidate.get("snippet") or ""),
                str(source_meta.get("summary") or source_meta.get("text_excerpt") or ""),
            ]
            if part
        ),
        320,
    )
    enriched["recency_score"] = recency_score(candidate, now, lookback_hours)
    enriched["fresh_within_hot_window"] = is_fresh_candidate(candidate, now, lookback_hours)
    enriched["source_depth_score"] = source_depth(candidate, source_meta)
    enriched["traceability_score"] = traceability_score(candidate, source_meta)
    enriched["review_score"] = candidate_score(candidate, source_meta, now, lookback_hours)
    enriched["selection_fit"] = selection_fit(enriched)
    enriched["passes_body_gate"] = passes_body_gate(enriched, now, lookback_hours)
    return enriched


def mark_duplicates(candidates: list[dict[str, Any]]) -> int:
    seen: set[str] = set()
    duplicate_count = 0
    for candidate in candidates:
        key = str(candidate.get("duplicate_key") or "")
        if key and key in seen:
            candidate["duplicate_within_hot_window"] = True
            duplicate_count += 1
        else:
            candidate["duplicate_within_hot_window"] = False
            if key:
                seen.add(key)
    return duplicate_count


def build_payload(
    *,
    discovery_json: Path,
    candidates: list[dict[str, Any]],
    source_pack: dict[str, dict[str, Any]],
    lookback_hours: int,
    top_n: int,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    enriched = [enrich_candidate(candidate, source_pack, now, lookback_hours) for candidate in candidates]
    duplicate_count = mark_duplicates(enriched)
    ranked = sorted(
        enriched,
        key=lambda item: (
            bool(item.get("passes_body_gate")),
            float(item.get("review_score") or 0.0),
            float(item.get("recency_score") or 0.0),
        ),
        reverse=True,
    )
    eligible = [candidate for candidate in ranked if candidate.get("passes_body_gate") and not candidate.get("duplicate_within_hot_window")]
    fit_counts = Counter(str(candidate.get("selection_fit") or "") for candidate in eligible)
    return {
        "generated_at": now.isoformat(),
        "discovery_json": str(discovery_json),
        "history_root": str(ai_daily_root()),
        "hot_window_hours": lookback_hours,
        "candidate_count": len(candidates),
        "duplicate_within_hot_window_count": duplicate_count,
        "same_day_trend_conflict_count": 0,
        "eligible_count": len(eligible),
        "selection_fit_counts": dict(fit_counts),
        "ranked_candidates": ranked[:top_n],
        "selected_candidates": eligible[:top_n],
        "all_candidates": ranked,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rank daily discovery candidates by traceable source facts.")
    parser.add_argument("--discovery-json", required=True, help="Input discovery candidate JSON.")
    parser.add_argument("--lookback-hours", type=int, default=24, help="Freshness window.")
    parser.add_argument("--top-n", type=int, default=20, help="Shortlist size.")
    parser.add_argument("--source-pack", action="append", default=[], help="Source-pack directory. Can be repeated.")
    parser.add_argument("--out", help="Optional output JSON path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    discovery_json = Path(args.discovery_json).expanduser().resolve()
    source_pack: dict[str, dict[str, Any]] = {}
    source_dirs = [Path(raw).expanduser().resolve() for raw in args.source_pack]
    if not source_dirs:
        date_match = re.search(r"(20\d{2}-\d{2}-\d{2})", str(discovery_json))
        if date_match:
            source_dirs.append(tech_daily_source_pack_dir(date_match.group(1)))
    for source_dir in source_dirs:
        source_pack.update(load_source_pack(source_dir))
    payload = build_payload(
        discovery_json=discovery_json,
        candidates=load_discovery(discovery_json),
        source_pack=source_pack,
        lookback_hours=args.lookback_hours,
        top_n=args.top_n,
    )
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        out_path = Path(args.out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
