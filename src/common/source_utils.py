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

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


SPACE_RE = re.compile(r"\s+")
LEAD_DECOR_RE = re.compile(r"^[^A-Za-z0-9\u4e00-\u9fff]+", re.U)


def canonicalize_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path or "/"
    query_pairs = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"ref", "source", "fbclid", "gclid"}
    ]
    if netloc in {"twitter.com", "x.com"}:
        netloc = "x.com"
        query_pairs = []
    return urlunparse((scheme, netloc, path, "", urlencode(query_pairs, doseq=True), ""))


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


def normalize_space(text: str) -> str:
    return SPACE_RE.sub(" ", text or "").strip()


def strip_leading_decor(text: str) -> str:
    return LEAD_DECOR_RE.sub("", normalize_space(text))


def emoji_icon_map_path() -> Path:
    return Path(__file__).resolve().parents[1] / "video" / "remotion" / "src" / "emoji-icon-map.json"


def load_emoji_icon_map() -> dict[str, str]:
    path = emoji_icon_map_path()
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {str(key): str(value) for key, value in raw.items() if str(key).strip() and str(value).strip()}


def extract_leading_emoji(text: str, emoji_map: dict[str, str] | None = None) -> str | None:
    value = normalize_space(text)
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


def build_publication_summary(report, *, source_pack_dirs: list[Path] | None = None) -> dict[str, Any]:
    source_pack_dirs = source_pack_dirs or []
    packed: dict[str, dict[str, Any]] = {}
    for source_pack_dir in source_pack_dirs:
        packed.update(load_source_pack(source_pack_dir))

    items: list[dict[str, Any]] = []
    for item in report.items:
        urls = [*(item.source_refs or []), item.source_url]
        confirmations = [
            {"url": url}
            for url in (canonicalize_url(str(url)) for url in urls)
            if url
        ]
        items.append(
            {
                "index": item.index,
                "title": sanitize_display_title(item.title),
                "source_url": item.source_url,
                "rail_label": compact_label(item.title),
                "confirmation_sources": confirmations,
                "confirmed_source_count": len(confirmations),
                "cross_confirmed": bool(confirmations),
            }
        )
    top_story = items[0] if items else {}
    return {
        "confirmed_item_count": sum(1 for item in items if item["cross_confirmed"]),
        "items": items,
        "top_story": {**top_story, "top_story_confirmed": bool(top_story.get("cross_confirmed"))} if top_story else {},
        "status": "ready",
        "source_pack_count": len(packed),
    }
