#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_daily_paths import (
    tech_daily_collection_summary_path,
    tech_daily_content_manifest_path,
    tech_daily_day_dir,
    tech_daily_discovery_dir,
    tech_daily_final_report_json_path,
    tech_daily_final_report_path,
    tech_daily_final_social_urls_path,
    tech_daily_reference_pack_dir,
    tech_daily_report_path,
    tech_daily_social_urls_path,
    tech_daily_source_pack_dir,
    tech_daily_story_assets_dir,
)
from tech_daily_collection_contract import (
    build_hashes,
    default_collection_paths,
    report_publication_contract,
    resolve_collection_paths,
    story_asset_count,
    validate_collection_summary,
)
from tech_daily_parser import TechDailyReport, parse_report

WORKSPACE_DIR = Path(__file__).resolve().parents[1]
ARCHIVE_SOCIAL_SCRIPT = WORKSPACE_DIR / "scripts" / "archive_social_sources.py"
TEXT_COMPILE_SCRIPT = WORKSPACE_DIR / "scripts" / "tech_daily_text_compile.py"
FETCH_STORY_IMAGES_SCRIPT = WORKSPACE_DIR / "skills" / "plus-media-factory" / "scripts" / "fetch_story_images.py"
DEFAULT_MAX_REPORT_ITEMS = 6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Finalize the 03:00 tech-daily collection handoff contract.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--report", help="Optional report path. Defaults to final/report.md, then the legacy root report.")
    parser.add_argument("--social-urls", help="Optional social URL file. Defaults to final/social-urls.txt, then the legacy root sidecar.")
    parser.add_argument("--overwrite", action="store_true", help="Refresh generated packs, story assets, and collection summary.")
    parser.add_argument("--enable-writer-layer", action="store_true", help="Deprecated; content now comes from Markdown content generation.")
    parser.add_argument("--min-confirmed", type=int, default=6)
    parser.add_argument("--fallback-action", action="append", default=[], help="Record a collection fallback action.")
    parser.add_argument("--blocked-feed", action="append", default=[], help="Record a blocked or degraded feed.")
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def extract_json_payload(raw_text: str) -> dict[str, Any]:
    stdout = raw_text.strip()
    if not stdout:
        return {}
    decoder = json.JSONDecoder()
    payload: dict[str, Any] = {}
    index = 0
    while index < len(stdout):
        start = stdout.find("{", index)
        if start < 0:
            break
        try:
            candidate, length = decoder.raw_decode(stdout[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(candidate, dict):
            payload = candidate
        index = start + length
    return payload


def run_stage(stage_records: list[dict[str, Any]], name: str, cmd: list[str]) -> dict[str, Any]:
    started = time.monotonic()
    entry: dict[str, Any] = {
        "name": name,
        "command": shlex.join(cmd),
        "started_at": utc_now_iso(),
    }
    stage_records.append(entry)
    completed = subprocess.run(cmd, text=True, capture_output=True)
    entry.update(
        {
            "finished_at": utc_now_iso(),
            "duration_sec": round(time.monotonic() - started, 2),
            "returncode": completed.returncode,
            "stdout_tail": (completed.stdout or "")[-4000:],
            "stderr_tail": (completed.stderr or "")[-4000:],
        }
    )
    if completed.returncode != 0:
        entry["status"] = "failed"
        raise RuntimeError(f"{name} failed ({completed.returncode}): {(completed.stderr or completed.stdout)[-1200:]}")
    entry["status"] = "success"
    payload = extract_json_payload(completed.stdout)
    if payload:
        entry["payload_summary"] = {
            key: payload[key]
            for key in (
                "result",
                "report_json",
                "reference_pack",
                "manifest",
                "asset_count",
                "failure_count",
                "confirmed_item_count",
                "publication_contract_status",
            )
            if key in payload
        }
    return payload


def copy_if_needed(src: Path, dest: Path) -> Path:
    ensure_dir(dest.parent)
    if src.resolve() == dest.resolve():
        return dest
    shutil.copy2(src, dest)
    return dest


def render_report_markdown(report: TechDailyReport) -> str:
    lines: list[str] = [f"# {report.title or 'AI 科技日报'}", ""]
    if report.trend_lines:
        lines.append("## 硅谷风向词")
        for line in report.trend_lines[:3]:
            lines.append(f"- {line}")
        lines.append("")
    for index, item in enumerate(report.items, start=1):
        lines.append(f"## {index}. {item.title}")
        if item.content:
            lines.append(f"**内容**：{item.content}")
        if item.interpretation:
            lines.append(f"**解读**：{item.interpretation}")
        if item.source_url:
            lines.append(f"**原文链接**：{item.source_url}")
        if item.quote:
            lines.append(f"【短引文】{item.quote}")
        if item.status:
            lines.append(f"状态：{item.status}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def normalize_report_item_count(report_path: Path, *, max_items: int = DEFAULT_MAX_REPORT_ITEMS) -> dict[str, Any]:
    report = parse_report(report_path)
    original_count = len(report.items)
    if original_count <= max_items:
        return {"changed": False, "original_count": original_count, "final_count": original_count}
    kept_items = []
    for index, item in enumerate(report.items[:max_items], start=1):
        item.index = index
        kept_items.append(item)
    report.items = kept_items
    report_path.write_text(render_report_markdown(report), encoding="utf-8")
    return {"changed": True, "original_count": original_count, "final_count": len(report.items)}


def resolve_report_input(date: str, explicit: str | None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser().resolve())
    candidates.extend([tech_daily_final_report_path(date), tech_daily_report_path(date)])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No report found for {date}")


def resolve_social_input(date: str, explicit: str | None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser().resolve())
    candidates.extend([tech_daily_final_social_urls_path(date), tech_daily_social_urls_path(date)])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No social URL sidecar found for {date}")


def candidate_count(date: str) -> int:
    discovery = read_json(tech_daily_discovery_dir(date) / "rsshub-candidates.json")
    raw_count = discovery.get("candidate_count")
    if isinstance(raw_count, int):
        return raw_count
    candidates = discovery.get("candidates")
    return len(candidates) if isinstance(candidates, list) else 0


def read_health_notes(date: str) -> tuple[list[str], list[str]]:
    payload = read_json(tech_daily_discovery_dir(date) / "feed-healthcheck.json")
    fallback_actions: list[str] = []
    blocked_feeds: list[str] = []
    if not payload:
        return fallback_actions, blocked_feeds
    if payload.get("status") and payload.get("status") != "ok":
        fallback_actions.append(f"feed_healthcheck_status:{payload.get('status')}")
    feeds = payload.get("feeds")
    if isinstance(feeds, list):
        for feed in feeds:
            if not isinstance(feed, dict):
                continue
            status = str(feed.get("status") or "").lower()
            if status and status not in {"ok", "pass", "success"}:
                name = str(feed.get("name") or feed.get("feed_url") or feed.get("url") or "unknown")
                blocked_feeds.append(name)
    return fallback_actions, blocked_feeds


def main() -> int:
    args = parse_args()
    date = args.date
    started = time.monotonic()
    stage_records: list[dict[str, Any]] = []
    summary_path = tech_daily_collection_summary_path(date)
    return_code = 1

    payload: dict[str, Any] = {
        "result": "running",
        "date": date,
        "day_dir": str(tech_daily_day_dir(date)),
        "started_at": utc_now_iso(),
        "stages": stage_records,
    }

    try:
        day_dir = ensure_dir(tech_daily_day_dir(date))
        final_report = tech_daily_final_report_path(date)
        final_social_urls = tech_daily_final_social_urls_path(date)
        source_pack = tech_daily_source_pack_dir(date)
        reference_pack = tech_daily_reference_pack_dir(date)
        story_assets = tech_daily_story_assets_dir(date)

        report_input = resolve_report_input(date, args.report)
        social_input = resolve_social_input(date, args.social_urls)
        copy_if_needed(report_input, final_report)
        copy_if_needed(social_input, final_social_urls)
        item_count_normalization = normalize_report_item_count(final_report)

        if args.overwrite:
            for path in (source_pack, reference_pack, story_assets):
                if path.exists():
                    shutil.rmtree(path)
            for path in (tech_daily_final_report_json_path(date), summary_path):
                path.unlink(missing_ok=True)

        archive_payload = run_stage(
            stage_records,
            "archive_social_sources",
            [
                sys.executable,
                str(ARCHIVE_SOCIAL_SCRIPT),
                "--report",
                str(final_report),
                "--urls-file",
                str(final_social_urls),
                "--out-dir",
                str(source_pack),
            ],
        )

        text_compile_cmd = [
            sys.executable,
            str(TEXT_COMPILE_SCRIPT),
            "--report",
            str(final_report),
            "--date",
            date,
            "--report-json-out",
            str(tech_daily_final_report_json_path(date)),
            "--content-manifest-out",
            str(tech_daily_content_manifest_path(date)),
            "--reference-pack-out",
            str(reference_pack),
            "--source-pack",
            str(source_pack),
            "--skip-illustrated-report",
        ]
        text_payload = run_stage(stage_records, "text_compile", text_compile_cmd)

        story_payload = run_stage(
            stage_records,
            "fetch_story_images",
            [
                sys.executable,
                str(FETCH_STORY_IMAGES_SCRIPT),
                "--report",
                str(final_report),
                "--out-dir",
                str(story_assets),
                "--limit",
                "48",
                "--per-url-limit",
                "4",
            ],
        )

        paths = default_collection_paths(date)
        contract = report_publication_contract(paths["report_json"])
        top_story = contract.get("top_story") if isinstance(contract.get("top_story"), dict) else {}
        health_actions, health_blocked = read_health_notes(date)
        visual_seed_count = story_asset_count(paths["story_manifest"])

        payload.update(
            {
                "result": "success",
                "finished_at": utc_now_iso(),
                "duration_sec": round(time.monotonic() - started, 2),
                "targets_met": True,
                "candidate_count": candidate_count(date),
                "confirmed_count": int(contract.get("confirmed_item_count") or text_payload.get("confirmed_item_count") or 0),
                "top_story_title": str(top_story.get("title") or ""),
                "top_story_confirmed": bool(top_story.get("top_story_confirmed")),
                "source_pack_status": "ok" if (source_pack / "index.json").exists() else "missing",
                "reference_pack_status": "ok" if (reference_pack / "index.json").exists() else "missing",
                "visual_seed_count": visual_seed_count,
                "fallback_actions": [*args.fallback_action, *health_actions],
                "blocked_feeds": [*args.blocked_feed, *health_blocked],
                "paths": {key: str(path) for key, path in paths.items()},
                "hashes": build_hashes(resolve_collection_paths(date, {"paths": {key: str(path) for key, path in paths.items()}})),
                "item_count_normalization": item_count_normalization,
                "archive_social_sources": archive_payload,
                "text_compile": text_payload,
                "story_assets": story_payload,
            }
        )
        validation_findings = validate_collection_summary(date, payload, min_confirmed=args.min_confirmed)
        payload["validation_findings"] = validation_findings
        if validation_findings:
            payload["targets_met"] = False
            payload["result"] = "failed"
            return_code = 1
        else:
            return_code = 0
    except Exception as exc:
        payload.update(
            {
                "result": "failed",
                "targets_met": False,
                "finished_at": utc_now_iso(),
                "duration_sec": round(time.monotonic() - started, 2),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(limit=20),
            }
        )
    finally:
        write_json(summary_path, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
