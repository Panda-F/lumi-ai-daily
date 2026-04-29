#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from ai_daily_paths import (
    WORKSPACE_DIR,
    ai_daily_root,
    extract_tech_daily_date,
    tech_daily_day_dir,
    tech_daily_publish_dir,
    tech_daily_report_path,
    tech_daily_social_urls_path,
    tech_daily_source_pack_dir,
    tech_daily_video_dir,
)

WORKSPACE_REPORTS_DIR = WORKSPACE_DIR / "reports"
WORKSPACE_SOURCE_PACKS_DIR = WORKSPACE_DIR / "source-packs"
PRIVATE_TMP = Path("/private/tmp")
UPLOADS_DIR = Path("/tmp/openclaw/uploads")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Move existing tech-daily artifacts into /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD.")
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without moving or copying files")
    return parser.parse_args()


def ensure_dir(path: Path, dry_run: bool) -> None:
    if dry_run:
        return
    path.mkdir(parents=True, exist_ok=True)


def record(actions: list[dict[str, str]], action: str, src: Path, dest: Path) -> None:
    actions.append(
        {
            "action": action,
            "source": str(src),
            "destination": str(dest),
        }
    )


def move_with_symlink(src: Path, dest: Path, actions: list[dict[str, str]], dry_run: bool) -> None:
    if not src.exists() and not src.is_symlink():
        return
    if src.is_symlink():
        target = src.resolve()
        if target == dest:
            return

    ensure_dir(dest.parent, dry_run)

    if dest.exists():
        record(actions, "skip_exists", src, dest)
        return

    record(actions, "move", src, dest)
    if dry_run:
        return

    shutil.move(str(src), str(dest))
    src.parent.mkdir(parents=True, exist_ok=True)
    if src.exists() or src.is_symlink():
        if src.is_dir() and not src.is_symlink():
            shutil.rmtree(src)
        else:
            src.unlink()
    src.symlink_to(dest, target_is_directory=dest.is_dir())


def copy_path(src: Path, dest: Path, actions: list[dict[str, str]], dry_run: bool) -> None:
    if not src.exists():
        return
    if dest.exists():
        record(actions, "skip_exists", src, dest)
        return

    ensure_dir(dest.parent, dry_run)
    record(actions, "copy", src, dest)
    if dry_run:
        return

    if src.is_dir():
        shutil.copytree(src, dest)
    else:
        shutil.copy2(src, dest)


def migrate_date(date: str, actions: list[dict[str, str]], dry_run: bool) -> None:
    day_dir = tech_daily_day_dir(date)
    ensure_dir(day_dir, dry_run)

    report_src = WORKSPACE_REPORTS_DIR / f"tech-daily-{date}.md"
    report_dest = tech_daily_report_path(date)
    move_with_symlink(report_src, report_dest, actions, dry_run)

    social_src = WORKSPACE_REPORTS_DIR / f"tech-daily-{date}.social-urls.txt"
    social_dest = tech_daily_social_urls_path(date)
    move_with_symlink(social_src, social_dest, actions, dry_run)

    source_pack_src = WORKSPACE_SOURCE_PACKS_DIR / f"tech-daily-{date}"
    source_pack_dest = tech_daily_source_pack_dir(date)
    move_with_symlink(source_pack_src, source_pack_dest, actions, dry_run)

    video_dir_src = PRIVATE_TMP / f"tech-daily-video-{date}"
    video_dir_dest = tech_daily_video_dir(date)
    copy_path(video_dir_src, video_dir_dest, actions, dry_run)

    pipeline_dir_src = PRIVATE_TMP / f"tech-daily-full-pipeline-{date}"
    pipeline_dir_dest = tech_daily_publish_dir(date)
    copy_path(pipeline_dir_src, pipeline_dir_dest, actions, dry_run)

    for extra_dir in sorted(PRIVATE_TMP.glob(f"publish-bundle-{date}*")):
        extra_dest = day_dir / "publish-archive" / extra_dir.name
        copy_path(extra_dir, extra_dest, actions, dry_run)

    uploads_targets = [
        UPLOADS_DIR / f"tech-daily-video-{date}.mp4",
        UPLOADS_DIR / f"tech-daily-video-{date}.srt",
        UPLOADS_DIR / f"tech-daily-cover-{date}.png",
    ]
    for upload_src in uploads_targets:
        upload_dest = day_dir / "uploads" / upload_src.name
        copy_path(upload_src, upload_dest, actions, dry_run)

    manifest_path = day_dir / "migration-manifest.json"
    manifest = {
        "date": date,
        "day_dir": str(day_dir),
        "report": str(report_dest) if report_dest.exists() or dry_run else None,
        "social_urls": str(social_dest) if social_dest.exists() or dry_run else None,
        "source_pack": str(source_pack_dest) if source_pack_dest.exists() or dry_run else None,
        "video_dir": str(video_dir_dest) if video_dir_dest.exists() or dry_run else None,
        "publish_dir": str(pipeline_dir_dest) if pipeline_dir_dest.exists() or dry_run else None,
    }
    record(actions, "write_manifest", day_dir, manifest_path)
    if not dry_run:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    root = ai_daily_root()
    actions: list[dict[str, str]] = []

    report_files = sorted(WORKSPACE_REPORTS_DIR.glob("tech-daily-20??-??-??.md"))
    dates = [date for path in report_files if (date := extract_tech_daily_date(path))]
    for date in dates:
        migrate_date(date, actions, args.dry_run)

    summary = {
        "result": "success",
        "root": str(root),
        "dates": dates,
        "dry_run": args.dry_run,
        "actions": actions,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
