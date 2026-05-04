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

from typing import Any

from tech_daily_parser import TechDailyItem, TechDailyReport


def _clean_fact_points(points: list[str]) -> list[str]:
    return [point.strip() for point in points if point and point.strip()]


def build_video_script_payload(
    report: TechDailyReport,
    items: list[TechDailyItem],
    *,
    issue_label: str,
    intro_oral: dict[str, Any],
    item_orals: list[dict[str, Any]],
    outro_oral: dict[str, Any],
) -> dict[str, Any]:
    segments: list[dict[str, Any]] = [
        {
            "kind": "intro",
            "title": "AI速递",
            "display_title": intro_oral.get("display_title", "AI速递"),
            "spoken_title": intro_oral.get("spoken_title", "AI速递"),
            "spoken_aliases": intro_oral.get("spoken_aliases", []),
            "style_variant": intro_oral.get("style_variant", "intro_light"),
            "tts_style_tags": intro_oral.get("tts_style_tags", ""),
            "script": intro_oral["oral_script"],
            "opening": intro_oral["opening"],
            "agenda": intro_oral["agenda"],
            "transition": intro_oral["transition"],
            "oral_script": intro_oral["oral_script"],
            "tts_script": intro_oral.get("tts_script", intro_oral["oral_script"]),
            "subtitle_script": intro_oral["subtitle_script"],
            "sentence_pairs": intro_oral.get("sentence_pairs", []),
            "source_urls": [item.source_url for item in items if item.source_url],
            "trend_words": report.trend_words[:3],
        }
    ]
    for item, oral in zip(items, item_orals):
        segments.append(
            {
                "kind": "item",
                "item_index": item.index,
                "item_kind": item.item_kind,
                "title": item.title,
                "display_title": oral.get("display_title", item.title),
                "spoken_title": oral.get("spoken_title", item.title),
                "spoken_aliases": oral.get("spoken_aliases", []),
                "style_variant": oral.get("style_variant", ""),
                "tts_style_tags": oral.get("tts_style_tags", ""),
                "script": oral["oral_script"],
                "hook": oral["hook"],
                "takeaway": oral["takeaway"],
                "fact_points": _clean_fact_points(oral.get("fact_points", [])),
                "screen_cards": list(oral.get("screen_cards") or []),
                "source_note": oral.get("source_note", ""),
                "outro": oral.get("outro", ""),
                "oral_script": oral["oral_script"],
                "tts_script": oral.get("tts_script", oral["oral_script"]),
                "subtitle_script": oral["subtitle_script"],
                "sentence_pairs": oral.get("sentence_pairs", []),
                "source_url": item.source_url,
                "source_refs": list(item.source_refs),
                "decision_impact": item.decision_impact or oral.get("decision_impact") or oral.get("takeaway") or oral.get("outro", ""),
                "duplicate_key": item.duplicate_key,
                "quote": item.quote,
                "quote_text": item.quote,
                "status": item.status,
            }
        )
    segments.append(
        {
            "kind": "outro",
            "title": outro_oral.get("display_title") or outro_oral.get("spoken_title") or "片尾",
            "display_title": outro_oral.get("display_title") or "片尾",
            "spoken_title": outro_oral.get("spoken_title") or "片尾",
            "spoken_aliases": outro_oral.get("spoken_aliases", []),
            "style_variant": outro_oral.get("style_variant", "outro_light"),
            "tts_style_tags": outro_oral.get("tts_style_tags", ""),
            "script": outro_oral["oral_script"],
            "oral_script": outro_oral["oral_script"],
            "tts_script": outro_oral.get("tts_script", outro_oral["oral_script"]),
            "subtitle_script": outro_oral["subtitle_script"],
            "sentence_pairs": outro_oral.get("sentence_pairs", []),
            "line_one": outro_oral.get("line_one", ""),
            "line_two": outro_oral.get("line_two", ""),
            "quote_id": outro_oral.get("quote_id", ""),
            "quote_text": outro_oral.get("quote_text", ""),
            "quote_translation": outro_oral.get("quote_translation", ""),
            "quote_author": outro_oral.get("quote_author", ""),
            "source_urls": [],
        }
    )
    return {
        "date": report.date,
        "title": report.title,
        "issue_label": issue_label,
        "hot_window_hours": report.hot_window_hours,
        "item_count": len(items),
        "segments": segments,
    }
