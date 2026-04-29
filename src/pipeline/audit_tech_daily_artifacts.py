#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from ai_daily_paths import (
    ai_daily_root,
    tech_daily_collection_summary_path,
    tech_daily_day_dir,
    tech_daily_final_dir,
    tech_daily_publish_dir,
    tech_daily_publish_v2_dir,
    tech_daily_sources_dir,
    tech_daily_title_pack_path,
    tech_daily_content_manifest_path,
)
from tech_daily_collection_contract import read_json, validate_collection_summary

DATE_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run audit for redundant or invalid tech-daily artifacts.")
    parser.add_argument("dates", nargs="*", help="Specific YYYY-MM-DD report dates. Defaults to every dated directory.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when findings are present.")
    return parser.parse_args()


def finding(code: str, path: Path, detail: str = "", *, severity: str = "warn") -> dict[str, str]:
    payload = {
        "severity": severity,
        "code": code,
        "path": str(path),
    }
    if detail:
        payload["detail"] = detail
    return payload


def existing_dates() -> list[str]:
    root = ai_daily_root()
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir() and DATE_RE.match(path.name))


def video_manifest_findings(date: str, publish_dir: Path, name: str) -> list[dict[str, str]]:
    path = publish_dir / name
    label = name.removesuffix(".json").replace("-", "_")
    if not publish_dir.exists():
        return []
    if not path.exists():
        return [finding(f"missing_{label}", path)]
    try:
        payload = read_json(path)
    except Exception as exc:  # noqa: BLE001
        return [finding(f"{label}_unreadable", path, str(exc))]
    raw_video = payload.get("video_file")
    if raw_video in (None, "", []):
        return [finding(f"{label}_video_file_null", path, "video_file is empty")]
    if not isinstance(raw_video, str):
        return [finding(f"{label}_video_file_invalid", path, "video_file is not a string")]
    video_path = Path(raw_video).expanduser()
    if not video_path.exists():
        return [finding(f"{label}_video_file_missing", path, raw_video)]
    title_pack = read_json(tech_daily_title_pack_path(date)) if tech_daily_title_pack_path(date).exists() else {}
    video_filename = Path(str(title_pack.get("video_filename") or "")).name
    if video_filename:
        expected = (tech_daily_publish_v2_dir(date) / video_filename).resolve()
        if video_path.resolve() != expected:
            return [finding(f"{label}_video_file_not_publish_titled_mp4", path, raw_video, severity="error")]
    elif video_path.resolve() != (tech_daily_final_dir(date) / "video.mp4").resolve():
        return [finding(f"{label}_video_file_unexpected", path, raw_video)]
    return []


def audit_collection(date: str) -> list[dict[str, str]]:
    summary_path = tech_daily_collection_summary_path(date)
    if not summary_path.exists():
        return [finding("missing_collection_summary", summary_path, severity="error")]
    try:
        payload = read_json(summary_path)
        findings = validate_collection_summary(date, payload)
    except Exception as exc:  # noqa: BLE001
        return [finding("collection_summary_unreadable", summary_path, str(exc), severity="error")]
    return [
        finding("invalid_collection_summary", summary_path, item, severity="error")
        for item in findings
    ]


def audit_redundant_paths(date: str) -> list[dict[str, str]]:
    day_dir = tech_daily_day_dir(date)
    final_dir = tech_daily_final_dir(date)
    publish_dir = tech_daily_publish_v2_dir(date)
    findings: list[dict[str, str]] = []
    title_pack = read_json(tech_daily_title_pack_path(date)) if tech_daily_title_pack_path(date).exists() else {}
    allowed_docx = {"wechat.docx"}
    allowed_mp4 = {"video.mp4"}
    wechat_filename = Path(str(title_pack.get("wechat_filename") or "")).name
    video_filename = Path(str(title_pack.get("video_filename") or "")).name
    if wechat_filename:
        allowed_docx.add(wechat_filename)
    if video_filename:
        allowed_mp4.add(video_filename)

    for path, code in (
        (tech_daily_sources_dir(date), "legacy_sources_dir"),
        (tech_daily_publish_dir(date), "legacy_publish_bundle_dir"),
    ):
        if path.exists():
            findings.append(finding(code, path))

    if day_dir.exists():
        for child in day_dir.iterdir():
            if child.name.startswith(("source-pack.pre-", "sources.pre-")) or ".pre-" in child.name:
                findings.append(finding("legacy_pre_fix_artifact", child))

    if publish_dir.exists():
        stale_patterns = (
            "youtube*",
            "x-thread*",
            "x-post*",
            "zhihu.md",
            "xiaohongshu.md",
            "wechat.md",
            "wechat-article.*",
            "publish-strategy.json",
            "summary.json",
        )
        for pattern in stale_patterns:
            for stale in publish_dir.glob(pattern):
                findings.append(finding("legacy_publish_file", stale))
        if (publish_dir / "assets").exists():
            findings.append(finding("publish_assets_dir", publish_dir / "assets"))
        for docx in publish_dir.glob("*.docx"):
            if docx.name not in allowed_docx:
                findings.append(finding("duplicate_human_title_docx", docx))

    if final_dir.exists():
        if video_filename:
            final_named = final_dir / video_filename
            publish_named = publish_dir / video_filename
            if not final_named.exists():
                findings.append(finding("missing_final_titled_mp4", final_named, severity="error"))
            if not publish_named.exists():
                findings.append(finding("missing_publish_titled_mp4", publish_named, severity="error"))
        for mp4 in final_dir.glob("*.mp4"):
            if mp4.name not in allowed_mp4:
                findings.append(finding("duplicate_human_title_mp4", mp4))
        for intermediate in (
            "assets",
            "audio",
            "build-internals",
            "slides",
            "build-summary.json",
            "timeline.json",
            "remotion-manifest.json",
            "remotion-stills.json",
            "video-script.json",
            "video-review.json",
            "writer-output.json",
            "report.illustrated.md",
            "report.image-manifest.json",
        ):
            path = final_dir / intermediate
            if path.exists():
                findings.append(finding("final_build_intermediate", path))

    return findings


def audit_video_screenshot_package(date: str) -> list[dict[str, str]]:
    publish_dir = tech_daily_publish_v2_dir(date)
    package_dir = publish_dir / "video-screenshots"
    manifest_path = package_dir / "manifest.json"
    if not publish_dir.exists():
        return []
    if not manifest_path.exists():
        return [finding("missing_video_screenshot_manifest", manifest_path, severity="error")]
    try:
        payload = read_json(manifest_path)
    except Exception as exc:  # noqa: BLE001
        return [finding("video_screenshot_manifest_unreadable", manifest_path, str(exc), severity="error")]
    findings: list[dict[str, str]] = []
    if payload.get("status") != "pass" or payload.get("blocking_findings"):
        findings.append(
            finding(
                "video_screenshot_review_not_pass",
                manifest_path,
                json.dumps(payload.get("blocking_findings") or [], ensure_ascii=False),
                severity="error",
            )
        )
    expected_content = tech_daily_content_manifest_path(date)
    raw_content = str(payload.get("content_manifest") or "")
    if expected_content.exists() and raw_content and Path(raw_content).expanduser().resolve() != expected_content.resolve():
        findings.append(finding("video_screenshot_content_manifest_mismatch", manifest_path, raw_content, severity="error"))
    files = payload.get("files") if isinstance(payload.get("files"), dict) else {}
    required_names = ["cover.png", "00-intro.png", "01-item.png", "contact-sheet.png"]
    for name in required_names:
        raw_path = str((files.get(name) or {}).get("published") or package_dir / name)
        path = Path(raw_path).expanduser()
        if not path.exists():
            findings.append(finding("missing_video_screenshot_file", path, name, severity="error"))
    return findings


def audit_date(date: str) -> dict[str, Any]:
    publish_dir = tech_daily_publish_v2_dir(date)
    findings = [
        *audit_collection(date),
        *video_manifest_findings(date, publish_dir, "telegram-send.json"),
        *video_manifest_findings(date, publish_dir, "bilibili-upload.json"),
        *audit_video_screenshot_package(date),
        *audit_redundant_paths(date),
    ]
    return {
        "date": date,
        "day_dir": str(tech_daily_day_dir(date)),
        "finding_count": len(findings),
        "findings": findings,
    }


def main() -> int:
    args = parse_args()
    dates = args.dates or existing_dates()
    invalid = [date for date in dates if not DATE_RE.match(date)]
    if invalid:
        raise SystemExit(f"Invalid date(s): {', '.join(invalid)}")

    results = [audit_date(date) for date in dates]
    finding_count = sum(result["finding_count"] for result in results)
    payload = {
        "result": "findings" if finding_count else "clean",
        "finding_count": finding_count,
        "dates": results,
        "dry_run": True,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if args.strict and finding_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
