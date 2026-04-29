#!/usr/bin/env python3

from __future__ import annotations

import re
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_AI_DAILY_ROOT = Path("/Users/dystopia/Desktop/AI-Daily-Reports")
DEFAULT_TECH_DAILY_WRITING_PROFILE = (
    WORKSPACE_DIR / "skills" / "ai-daily-intel" / "references" / "writing-profile.yaml"
)
DEFAULT_TECH_DAILY_STYLE_CORPUS_DIR = (
    WORKSPACE_DIR / "skills" / "ai-daily-intel" / "references" / "style-corpus"
)
DEFAULT_TECH_DAILY_PLAYBOOK = (
    WORKSPACE_DIR / "skills" / "ai-daily-intel" / "references" / "writing-playbook.json"
)
TECH_DAILY_RE = re.compile(r"tech-daily-(20\d{2}-\d{2}-\d{2})\.md$")
DATE_SEGMENT_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}$")


def ai_daily_root() -> Path:
    return DEFAULT_AI_DAILY_ROOT


def ensure_ai_daily_root() -> Path:
    root = ai_daily_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def extract_tech_daily_date(path: str | Path) -> str | None:
    resolved = Path(path)
    name = resolved.name
    match = TECH_DAILY_RE.match(name)
    if match:
        return match.group(1)
    for part in reversed(resolved.parts):
        if DATE_SEGMENT_RE.match(part):
            return part
    return None


def tech_daily_day_dir(date: str) -> Path:
    return ensure_ai_daily_root() / date


def tech_daily_final_dir(date: str) -> Path:
    return tech_daily_day_dir(date) / "final"


def tech_daily_publish_v2_dir(date: str) -> Path:
    return tech_daily_day_dir(date) / "publish"


def tech_daily_qa_dir(date: str) -> Path:
    return tech_daily_day_dir(date) / "qa"


def tech_daily_sources_dir(date: str) -> Path:
    # Legacy only. New daily runs should use source-pack/ and reference-pack/.
    return tech_daily_day_dir(date) / "sources"


def tech_daily_build_dir(date: str) -> Path:
    return tech_daily_day_dir(date) / "build"


def tech_daily_video_build_dir(date: str) -> Path:
    return tech_daily_build_dir(date) / "video"


def tech_daily_story_assets_dir(date: str) -> Path:
    return tech_daily_day_dir(date) / "assets" / "story"


def tech_daily_report_path(date: str) -> Path:
    return tech_daily_day_dir(date) / f"tech-daily-{date}.md"


def tech_daily_final_report_path(date: str) -> Path:
    return tech_daily_final_dir(date) / "report.md"


def tech_daily_social_urls_path(date: str) -> Path:
    return tech_daily_day_dir(date) / f"tech-daily-{date}.social-urls.txt"


def tech_daily_final_social_urls_path(date: str) -> Path:
    return tech_daily_final_dir(date) / "social-urls.txt"


def tech_daily_discovery_dir(date: str) -> Path:
    return tech_daily_day_dir(date) / "discovery"


def tech_daily_source_pack_dir(date: str) -> Path:
    return tech_daily_day_dir(date) / "source-pack"


def tech_daily_reference_pack_dir(date: str) -> Path:
    return tech_daily_day_dir(date) / "reference-pack"


def tech_daily_collection_summary_path(date: str) -> Path:
    return tech_daily_qa_dir(date) / "collection-summary.json"


def tech_daily_report_json_path(date: str) -> Path:
    return tech_daily_day_dir(date) / f"tech-daily-{date}.report.json"


def tech_daily_final_report_json_path(date: str) -> Path:
    return tech_daily_final_dir(date) / "report.json"


def tech_daily_writer_output_path(date: str) -> Path:
    return tech_daily_final_dir(date) / "writer-output.json"


def tech_daily_content_dir(date: str) -> Path:
    return tech_daily_final_dir(date) / "content"


def tech_daily_content_manifest_path(date: str) -> Path:
    return tech_daily_final_dir(date) / "content-manifest.json"


def tech_daily_editorial_bundle_path(date: str) -> Path:
    # Deprecated compatibility alias. The file is now a deterministic
    # manifest built from Markdown content sources, not model-generated JSON.
    return tech_daily_content_manifest_path(date)


def tech_daily_editorial_brief_path(date: str) -> Path:
    return tech_daily_final_dir(date) / "editorial-brief.json"


def tech_daily_video_dir(date: str) -> Path:
    return tech_daily_day_dir(date) / "video-build"


def tech_daily_publish_dir(date: str) -> Path:
    return tech_daily_day_dir(date) / "publish-bundle"


def tech_daily_build_summary_path(date: str) -> Path:
    return tech_daily_video_build_dir(date) / "build-summary.json"


def tech_daily_video_script_path(date: str) -> Path:
    return tech_daily_video_build_dir(date) / "video-script.json"


def tech_daily_final_video_path(date: str) -> Path:
    return tech_daily_final_dir(date) / "video.mp4"


def tech_daily_final_srt_path(date: str) -> Path:
    return tech_daily_final_dir(date) / "video.srt"


def tech_daily_title_pack_path(date: str) -> Path:
    return tech_daily_publish_v2_dir(date) / "title-pack.json"


def tech_daily_bgm_analysis_path(date: str) -> Path:
    return tech_daily_qa_dir(date) / "bgm-analysis.json"


def tech_daily_cover_review_path(date: str) -> Path:
    return tech_daily_qa_dir(date) / "cover-review.json"


def tech_daily_video_style_review_path(date: str) -> Path:
    return tech_daily_qa_dir(date) / "video-style-review.json"


def tech_daily_cover_copy_path(date: str) -> Path:
    return tech_daily_day_dir(date) / f"tech-daily-{date}.cover-copy.json"


def tech_daily_cover_image_path(date: str) -> Path:
    return tech_daily_day_dir(date) / f"tech-daily-{date}.cover.png"


def tech_daily_cover_lab_dir(date: str) -> Path:
    return tech_daily_day_dir(date) / "cover-lab"


def tech_daily_writing_profile_path() -> Path:
    return DEFAULT_TECH_DAILY_WRITING_PROFILE


def tech_daily_style_corpus_dir() -> Path:
    return DEFAULT_TECH_DAILY_STYLE_CORPUS_DIR


def tech_daily_writing_playbook_path() -> Path:
    return DEFAULT_TECH_DAILY_PLAYBOOK


def tech_daily_latest_report() -> Path | None:
    desktop_candidates = sorted(ai_daily_root().glob("20??-??-??/tech-daily-20??-??-??.md"))
    final_candidates = sorted(ai_daily_root().glob("20??-??-??/final/report.md"))
    if final_candidates:
        return final_candidates[-1]
    if desktop_candidates:
        return desktop_candidates[-1]

    workspace_candidates = sorted((WORKSPACE_DIR / "reports").glob("tech-daily-20??-??-??.md"))
    if workspace_candidates:
        return workspace_candidates[-1]
    return None


def resolve_tech_daily_report_path(date: str) -> Path | None:
    candidates = [
        tech_daily_report_path(date),
        tech_daily_final_report_path(date),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def resolve_tech_daily_social_urls_path(date: str) -> Path | None:
    candidates = [
        tech_daily_social_urls_path(date),
        tech_daily_final_social_urls_path(date),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def resolve_tech_daily_report_json_path(date: str) -> Path | None:
    candidates = [
        tech_daily_report_json_path(date),
        tech_daily_final_report_json_path(date),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def resolve_tech_daily_sources_dirs(date: str) -> list[Path]:
    ordered: list[Path] = []
    for candidate in (
        tech_daily_source_pack_dir(date),
        tech_daily_reference_pack_dir(date),
    ):
        if candidate.exists() and candidate not in ordered:
            ordered.append(candidate)
    return ordered
