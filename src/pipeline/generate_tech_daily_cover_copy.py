#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ai_daily_llm_content import load_content_manifest
from ai_daily_paths import extract_tech_daily_date, tech_daily_cover_copy_path
from tech_daily_parser import parse_report


DEFAULT_MASTHEAD = "科技日报"
DEFAULT_KICKER = "Silicon Valley Signals"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize cover-copy JSON from Markdown content manifest.")
    parser.add_argument("--report", required=True, help="Path to a tech-daily markdown report.")
    parser.add_argument("--out", help="Optional output JSON path.")
    parser.add_argument("--content-manifest", help="Optional content-manifest.json path.")
    parser.add_argument("--editorial-bundle", help="Deprecated alias for --content-manifest.")
    parser.add_argument("--masthead", default=DEFAULT_MASTHEAD, help="Cover masthead text.")
    parser.add_argument("--headline-limit", type=int, default=96, help="Max length for the marketing headline.")
    parser.add_argument("--subhead-limit", type=int, default=36, help="Max length for the supporting headline.")
    parser.add_argument("--max-left-lines", type=int, default=3, help="Max count of left-side teaser lines.")
    parser.add_argument("--max-right-lines", type=int, default=3, help="Max count of right-side teaser lines.")
    return parser.parse_args()


def resolve_output_path(report_path: Path, explicit_out: str | None, report_date: str) -> Path:
    if explicit_out:
        return Path(explicit_out).expanduser().resolve()
    if report_date:
        return tech_daily_cover_copy_path(report_date)
    return report_path.with_suffix(".cover-copy.json")


def require_text(value: Any, field: str, *, max_len: int | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        raise SystemExit(f"content manifest missing cover_copy.{field}")
    longest_line = max((len(line.strip()) for line in text.splitlines()), default=len(text))
    if max_len is not None and longest_line > max_len:
        raise SystemExit(f"content manifest cover_copy.{field} exceeds {max_len} chars: {text}")
    return text


def clean_lines(values: Any, *, limit: int, label: str) -> list[str]:
    if not isinstance(values, list):
        raise SystemExit(f"content manifest cover_copy.{label} must be an array")
    lines = [str(value or "").strip() for value in values if str(value or "").strip()]
    if not lines:
        raise SystemExit(f"content manifest cover_copy.{label} is empty")
    return lines[: max(limit, 1)]


def main() -> None:
    args = parse_args()
    report_path = Path(args.report).expanduser().resolve()
    report = parse_report(report_path)
    report_date = report.date or extract_tech_daily_date(report_path) or ""
    output_path = resolve_output_path(report_path, args.out, report_date)
    content_manifest_path = args.content_manifest or args.editorial_bundle
    bundle = load_content_manifest(content_manifest_path, report_path=report_path, date=report_date)
    cover_copy = bundle.get("cover_copy") if isinstance(bundle.get("cover_copy"), dict) else {}
    title_pack = bundle.get("title_pack") if isinstance(bundle.get("title_pack"), dict) else {}

    headline_source = title_pack.get("wechat_title") or title_pack.get("primary_hook") or cover_copy.get("headline")
    headline = require_text(headline_source, "headline", max_len=args.headline_limit)
    subhead = require_text(cover_copy.get("subhead"), "subhead", max_len=args.subhead_limit)
    left_lines = clean_lines(cover_copy.get("left_lines"), limit=args.max_left_lines, label="left_lines")
    right_lines = clean_lines(cover_copy.get("right_lines"), limit=args.max_right_lines, label="right_lines")
    entity_anchors = clean_lines(cover_copy.get("entity_anchors"), limit=6, label="entity_anchors")
    bundle_items = bundle.get("items") if isinstance(bundle.get("items"), list) else []

    payload = {
        "report": str(report_path),
        "date": report_date,
        "masthead": args.masthead,
        "kicker": f"{report_date} · 硅谷热点追踪" if report_date else DEFAULT_KICKER,
        "copy_style": "markdown_content_manifest",
        "marketing_headline": headline,
        "headline_candidates": [headline],
        "subhead": subhead,
        "supporting_headline": subhead,
        "left_lines": left_lines,
        "right_lines": right_lines,
        "entity_anchors": entity_anchors,
        "trend_words": [str(term or "").strip() for term in report.trend_words[:3] if str(term or "").strip()],
        "hero_story": {
            "title": str((bundle_items[0] or {}).get("title") or report.items[0].title) if bundle_items and report.items else "",
            "source_url": str((bundle_items[0] or {}).get("source_url") or report.items[0].source_url) if bundle_items and report.items else "",
        },
        "items": [
            {
                "title": str(item.get("title") or ""),
                "teaser": str(item.get("content") or "")[:48],
                "source_url": str(item.get("source_url") or ""),
            }
            for item in bundle_items[:6]
            if isinstance(item, dict)
        ],
        "content_manifest": str(Path(content_manifest_path).expanduser().resolve()) if content_manifest_path else None,
        "cover_headline": str(title_pack.get("cover_headline") or headline),
        "cover_subhead": str(title_pack.get("cover_subhead") or subhead),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
