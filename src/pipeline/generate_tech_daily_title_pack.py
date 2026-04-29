#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from ai_daily_llm_content import load_content_manifest
from ai_daily_paths import ai_daily_root
from tech_daily_parser import load_report_json_sidecar, parse_report
from tech_daily_publication_contract import sanitize_display_title


OFFICIAL_ISSUE_START_DATE = os.environ.get("AI_DAILY_OFFICIAL_START_DATE", "2026-04-13").strip()
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
MAX_NAMED_ARTIFACT_STEM_CHARS = 96


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize title-pack JSON from Markdown content manifest.")
    parser.add_argument("--report", required=True, help="Path to the tech daily Markdown report.")
    parser.add_argument("--date", help="Optional explicit YYYY-MM-DD date.")
    parser.add_argument("--cover-copy", help="Optional cover copy JSON path retained for artifact traceability.")
    parser.add_argument("--content-manifest", help="Optional content-manifest.json path.")
    parser.add_argument("--editorial-bundle", help="Deprecated alias for --content-manifest.")
    parser.add_argument("--out", required=True, help="Output title-pack JSON path.")
    return parser.parse_args()


def load_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        return {}
    raw = json.loads(resolved.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def count_issue_number(report_date: str) -> int:
    root = ai_daily_root()
    dates: list[str] = []
    for day_dir in sorted(root.glob("20??-??-??")):
        date = day_dir.name
        if OFFICIAL_ISSUE_START_DATE and date < OFFICIAL_ISSUE_START_DATE:
            continue
        if (day_dir / f"tech-daily-{date}.md").exists() or (day_dir / "final" / "report.md").exists():
            dates.append(date)
    if report_date not in dates and (not OFFICIAL_ISSUE_START_DATE or report_date >= OFFICIAL_ISSUE_START_DATE):
        dates.append(report_date)
    dates = sorted(set(dates))
    try:
        return dates.index(report_date) + 1
    except ValueError:
        return max(len(dates), 1)


def sanitize_filename_component(text: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned


def named_artifact_filename(title: str, trailer: str, suffix: str) -> str:
    clean_title = sanitize_filename_component(title)
    clean_trailer = sanitize_filename_component(trailer)
    if not clean_title:
        raise SystemExit("named artifact title is empty after sanitization")
    max_title_chars = max(12, MAX_NAMED_ARTIFACT_STEM_CHARS - len(clean_trailer))
    if len(clean_title) > max_title_chars:
        clean_title = clean_title[:max_title_chars].rstrip(" .")
    return f"{clean_title}{clean_trailer}{suffix}"


def resolve_publication_contract(report_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    sidecar = load_report_json_sidecar(report_path)
    machine_review = sidecar.get("machine_review") if isinstance(sidecar.get("machine_review"), dict) else {}
    publication_contract = machine_review.get("publication_contract") if isinstance(machine_review.get("publication_contract"), dict) else {}
    return sidecar, publication_contract


def require_title(title_pack: dict[str, Any], key: str, *, max_len: int | None = None) -> str:
    value = sanitize_display_title(str(title_pack.get(key) or "").strip())
    if not value:
        raise SystemExit(f"content manifest missing title_pack.{key}")
    if max_len is not None and len(value) > max_len:
        raise SystemExit(f"content manifest title_pack.{key} exceeds {max_len} chars: {value}")
    return value


def sanitize_confirmation_sources(raw_sources: list[Any]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for source in raw_sources:
        if not isinstance(source, dict):
            continue
        item = dict(source)
        item["title"] = sanitize_display_title(str(item.get("title") or "").strip())
        item["source_label"] = sanitize_display_title(str(item.get("source_label") or "").strip())
        cleaned.append(item)
    return cleaned


def main() -> int:
    args = parse_args()
    report_path = Path(args.report).expanduser().resolve()
    report = parse_report(report_path)
    report_json, publication_contract = resolve_publication_contract(report_path)
    run_date = args.date or report.date
    if not run_date:
        raise SystemExit("Could not determine report date for title pack")

    blocking_findings = list(publication_contract.get("blocking_findings") or [])
    if publication_contract and publication_contract.get("status") != "pass":
        raise SystemExit(f"Publication contract failed: {blocking_findings}")

    top_story = publication_contract.get("top_story") if isinstance(publication_contract.get("top_story"), dict) else {}
    fallback_item = report.items[0] if report.items else None
    raw_top_story_title = str(top_story.get("title") or (fallback_item.title if fallback_item else ""))
    raw_top_story_url = str(top_story.get("source_url") or (fallback_item.source_url if fallback_item else ""))
    top_story_title = sanitize_display_title(raw_top_story_title)
    top_story_url = raw_top_story_url.strip()
    top_story_confirmed = bool(top_story.get("top_story_confirmed"))
    confirmation_sources = sanitize_confirmation_sources(list(top_story.get("confirmation_sources") or []))
    if publication_contract and (not top_story_title or not top_story_confirmed):
        raise SystemExit("Publication contract failed: top_story_not_cross_confirmed")

    content_manifest_path = args.content_manifest or args.editorial_bundle
    bundle = load_content_manifest(content_manifest_path, report_path=report_path, date=run_date)
    title_pack = bundle.get("title_pack") if isinstance(bundle.get("title_pack"), dict) else {}
    cover_copy = bundle.get("cover_copy") if isinstance(bundle.get("cover_copy"), dict) else {}

    primary_hook = require_title(title_pack, "primary_hook", max_len=96)
    wechat_title = primary_hook
    primary_entities = [str(entity).strip() for entity in title_pack.get("primary_entities") or [] if str(entity).strip()]
    if not primary_entities:
        raise SystemExit("content manifest missing title_pack.primary_entities")
    headline_subject = require_title(title_pack, "headline_subject", max_len=32)
    issue_no = count_issue_number(run_date)
    issue_label = f"第 {issue_no} 期"
    video_title = primary_hook
    bilibili_title = primary_hook
    compact_issue_label = f"第{issue_no}期"
    video_filename = named_artifact_filename(video_title, f"【Lumi的AI速递{compact_issue_label}】", ".mp4")
    wechat_filename = named_artifact_filename(wechat_title, f"｜Lumi的AI速递｜{run_date}", ".docx")

    cover_headline = require_title(cover_copy, "headline", max_len=24)
    payload = {
        "result": "success",
        "date": run_date,
        "issue_no": issue_no,
        "issue_label": issue_label,
        "items_count": len(report.items),
        "primary_entities": primary_entities,
        "headline_subject": headline_subject,
        "headline_action": require_title(title_pack, "headline_action", max_len=48),
        "headline_stakes": require_title(title_pack, "headline_stakes", max_len=64),
        "primary_hook": primary_hook,
        "cover_headline": cover_headline,
        "cover_subhead": require_title(title_pack, "cover_subhead", max_len=36),
        "top_story_title": top_story_title,
        "top_story_url": top_story_url,
        "top_story_confirmed": top_story_confirmed,
        "confirmation_sources": confirmation_sources,
        "video_title": video_title,
        "bilibili_title": bilibili_title,
        "wechat_title": wechat_title,
        "video_filename": video_filename,
        "wechat_filename": wechat_filename,
        "report": str(report_path),
        "cover_copy": str(Path(args.cover_copy).expanduser().resolve()) if args.cover_copy else None,
        "content_manifest": str(Path(content_manifest_path).expanduser().resolve()) if content_manifest_path else None,
        "report_json_item_count": len(report_json.get("items") or []) if isinstance(report_json, dict) else 0,
        "cover_copy_headline": cover_headline,
    }

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
