#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ai_daily_paths import WORKSPACE_DIR
from tech_daily_candidate_review import canonicalize_url, load_source_pack
from tech_daily_parser import TechDailyReport


EMOJI_ICON_MAP_PATH = (
    WORKSPACE_DIR / "skills" / "tech-daily-video-factory" / "remotion" / "src" / "emoji-icon-map.json"
)
LEAD_DECOR_RE = re.compile(r"^[^A-Za-z0-9\u4e00-\u9fff]+", re.U)
SPACE_RE = re.compile(r"\s+")


def load_emoji_icon_map() -> dict[str, str]:
    if not EMOJI_ICON_MAP_PATH.exists():
        return {}
    raw = json.loads(EMOJI_ICON_MAP_PATH.read_text(encoding="utf-8"))
    return {str(key): str(value) for key, value in raw.items() if str(key).strip() and str(value).strip()}


def normalize_space(text: str) -> str:
    return SPACE_RE.sub(" ", text or "").strip()


def strip_leading_decor(text: str) -> str:
    return LEAD_DECOR_RE.sub("", normalize_space(text))


def extract_leading_emoji(text: str, emoji_map: dict[str, str] | None = None) -> str | None:
    value = normalize_space(text)
    if not value:
        return None
    mapping = emoji_map or load_emoji_icon_map()
    for emoji in sorted(mapping, key=len, reverse=True):
        if value.startswith(emoji):
            return emoji
    return None


def sanitize_display_title(text: str, emoji_map: dict[str, str] | None = None) -> str:
    value = normalize_space(str(text or "").replace("...", " ").replace("…", " "))
    mapping = emoji_map or load_emoji_icon_map()
    for emoji in sorted(mapping, key=len, reverse=True):
        if value.startswith(emoji):
            value = value[len(emoji) :].lstrip()
            break
    return strip_leading_decor(value).strip(" -|")


def require_mapped_emoji(text: str, emoji_map: dict[str, str] | None = None) -> str | None:
    mapping = emoji_map or load_emoji_icon_map()
    emoji = extract_leading_emoji(text, mapping)
    if emoji and emoji not in mapping:
        raise ValueError(f"unmapped_emoji_found: {emoji} :: {text}")
    return mapping.get(emoji) if emoji else None


def localize_trend_term(text: str) -> str:
    return normalize_space(text)


def localize_trend_line(text: str) -> str:
    return normalize_space(text)


def source_host(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host.removeprefix("www.")


def compact_label(text: str, *, limit: int = 6) -> str:
    cleaned = sanitize_display_title(text)
    if not cleaned:
        return "热点"
    lead = re.split(r"[：:，,。;；|｜]", cleaned, maxsplit=1)[0].strip(" -|.,。；：、")
    if not lead:
        lead = cleaned
    ascii_tokens = re.findall(r"[A-Za-z0-9.+-]+", lead)
    if ascii_tokens:
        label = "".join(re.sub(r"[^A-Za-z0-9]+", "", token) for token in ascii_tokens[:2]).strip()
        if label:
            return label[:limit]
    chars = [char for char in lead if not char.isspace()]
    return "".join(chars[:limit]) or "热点"


def source_summary(source: dict[str, Any], url: str) -> dict[str, Any]:
    return {
        "url": url,
        "source_kind": str(source.get("source_kind") or source.get("kind") or source.get("status") or ""),
        "title": normalize_space(str(source.get("title") or source.get("source_title") or "")),
        "source_label": normalize_space(str(source.get("source_author") or source.get("feed_name") or source_host(url))),
        "official": bool(source.get("official")) or bool(url),
        "usable_for_scoring": bool(source.get("usable_for_scoring")) or bool(source.get("text_excerpt") or source.get("summary")),
    }


def candidate_sources(candidate_review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for raw in candidate_review.get("selected_candidates") or candidate_review.get("ranked_candidates") or candidate_review.get("all_candidates") or []:
        if not isinstance(raw, dict):
            continue
        url = canonicalize_url(str(raw.get("canonical_url") or raw.get("url") or ""))
        if url and url not in sources:
            sources[url] = raw
    return sources


def packed_sources(source_pack_dirs: list[Path]) -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for source_pack_dir in source_pack_dirs:
        sources.update(load_source_pack(source_pack_dir))
    return sources


def build_confirmation_sources(
    source_urls: list[str],
    *,
    candidate_review: dict[str, Any],
    source_pack_dirs: list[Path],
) -> list[dict[str, Any]]:
    candidate_by_url = candidate_sources(candidate_review)
    pack_by_url = packed_sources(source_pack_dirs)
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_url in source_urls:
        url = canonicalize_url(raw_url)
        if not url or url in seen:
            continue
        seen.add(url)
        source = {}
        source.update(candidate_by_url.get(url, {}))
        source.update(pack_by_url.get(url, {}))
        if not source:
            source = {"title": "", "source_kind": "source_url"}
        selected.append(source_summary(source, url))
    return selected


def build_publication_contract(
    report: TechDailyReport,
    *,
    candidate_review: dict[str, Any],
    source_pack_dirs: list[Path],
    minimum_items: int = 6,
) -> dict[str, Any]:
    item_contracts: list[dict[str, Any]] = []
    for item in report.items:
        refs = [*(item.source_refs or []), item.source_url]
        confirmation_sources = build_confirmation_sources(
            refs,
            candidate_review=candidate_review,
            source_pack_dirs=source_pack_dirs,
        )
        item_contracts.append(
            {
                "index": item.index,
                "title": sanitize_display_title(item.title),
                "source_url": item.source_url,
                "rail_label": compact_label(item.title),
                "confirmation_sources": confirmation_sources,
                "confirmed_source_count": len(confirmation_sources),
                "official_source_present": bool(item.source_url),
                "cross_confirmed": bool(confirmation_sources),
            }
        )

    confirmed_items = [item for item in item_contracts if item["cross_confirmed"]]
    blocking_findings: list[str] = []
    if len(report.items) < minimum_items:
        blocking_findings.append("not_enough_report_items")
    if len(confirmed_items) < len(report.items):
        blocking_findings.append("some_items_missing_source_url")

    top_story = item_contracts[0] if item_contracts else {}
    return {
        "minimum_required_items": minimum_items,
        "confirmed_item_count": len(confirmed_items),
        "items": item_contracts,
        "top_story": {**top_story, "top_story_confirmed": bool(top_story.get("cross_confirmed"))} if top_story else {},
        "status": "pass" if not blocking_findings else "fail",
        "blocking_findings": blocking_findings,
    }
