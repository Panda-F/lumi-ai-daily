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

import os
import re
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKSPACE_DIR.parent
DEFAULT_AI_DAILY_ROOT = Path(os.environ.get("AI_DAILY_REPORTS_ROOT", REPO_ROOT.parent)).expanduser().resolve()
DEFAULT_TECH_DAILY_WRITING_PROFILE = WORKSPACE_DIR / "intelligence" / "writing_profile.yaml"
DEFAULT_TECH_DAILY_STYLE_CORPUS_DIR = WORKSPACE_DIR / "intelligence" / "style_corpus"
DEFAULT_TECH_DAILY_PLAYBOOK = WORKSPACE_DIR / "intelligence" / "writing_playbook.json"
TECH_DAILY_RE = re.compile(r"tech-daily-(20\d{2}-\d{2}-\d{2})\.md$")
DATE_SEGMENT_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}$")
INVALID_ARTIFACT_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


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


def tech_daily_process_dir(date: str) -> Path:
    return tech_daily_day_dir(date) / "process"


def tech_daily_final_dir(date: str) -> Path:
    return tech_daily_day_dir(date) / "final"


def tech_daily_build_dir(date: str) -> Path:
    return tech_daily_process_dir(date) / "build"


def tech_daily_video_build_dir(date: str) -> Path:
    return tech_daily_process_dir(date) / "video"


def tech_daily_qa_dir(date: str) -> Path:
    return tech_daily_process_dir(date) / "qa"


def tech_daily_report_path(date: str) -> Path:
    return tech_daily_process_dir(date) / "report.md"


def tech_daily_social_urls_path(date: str) -> Path:
    return tech_daily_process_dir(date) / "social-urls.txt"


def tech_daily_discovery_dir(date: str) -> Path:
    return tech_daily_process_dir(date) / "discovery"


def tech_daily_source_pack_dir(date: str) -> Path:
    return tech_daily_process_dir(date) / "source-pack"


def tech_daily_reference_pack_dir(date: str) -> Path:
    return tech_daily_process_dir(date) / "reference-pack"


def tech_daily_report_json_path(date: str) -> Path:
    return tech_daily_process_dir(date) / "report.json"


def tech_daily_content_dir(date: str) -> Path:
    return tech_daily_process_dir(date) / "content"


def tech_daily_content_manifest_path(date: str) -> Path:
    return tech_daily_process_dir(date) / "content-manifest.json"


def tech_daily_editorial_brief_path(date: str) -> Path:
    return tech_daily_process_dir(date) / "editorial-brief.json"


def tech_daily_build_summary_path(date: str) -> Path:
    return tech_daily_video_build_dir(date) / "build-summary.json"


def clean_final_artifact_filename(filename: object, *, fallback: str, suffix: str) -> str:
    raw = Path(str(filename or "").strip()).name
    cleaned = INVALID_ARTIFACT_FILENAME_CHARS.sub(" ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        cleaned = fallback
    if not cleaned.lower().endswith(suffix.lower()):
        cleaned = cleaned.removesuffix(".") + suffix
    return cleaned


def title_pack_filename(title_pack: dict[str, object] | None, key: str, *, fallback: str, suffix: str) -> str:
    raw = title_pack.get(key) if isinstance(title_pack, dict) else ""
    return clean_final_artifact_filename(raw, fallback=fallback, suffix=suffix)


def tech_daily_final_video_path(date: str, title_pack: dict[str, object] | None = None) -> Path:
    filename = title_pack_filename(title_pack, "video_filename", fallback="video.mp4", suffix=".mp4")
    return tech_daily_final_dir(date) / filename


def tech_daily_final_wechat_docx_path(date: str, title_pack: dict[str, object] | None = None) -> Path:
    filename = title_pack_filename(title_pack, "wechat_filename", fallback="wechat.docx", suffix=".docx")
    return tech_daily_final_dir(date) / filename


def tech_daily_final_srt_path(date: str) -> Path:
    return tech_daily_final_dir(date) / "video.srt"


def tech_daily_title_pack_path(date: str) -> Path:
    return tech_daily_final_dir(date) / "title-pack.json"


def tech_daily_bgm_analysis_path(date: str) -> Path:
    return tech_daily_process_dir(date) / "bgm-analysis.json"


def tech_daily_cover_copy_path(date: str) -> Path:
    return tech_daily_process_dir(date) / "cover-copy.json"


def tech_daily_cover_lab_dir(date: str) -> Path:
    return tech_daily_process_dir(date) / "cover"


def tech_daily_final_cover_path(date: str) -> Path:
    return tech_daily_final_dir(date) / "cover.png"


def tech_daily_final_cover_result_path(date: str) -> Path:
    return tech_daily_final_dir(date) / "cover.json"


def tech_daily_writing_profile_path() -> Path:
    return DEFAULT_TECH_DAILY_WRITING_PROFILE


def tech_daily_style_corpus_dir() -> Path:
    return DEFAULT_TECH_DAILY_STYLE_CORPUS_DIR


def tech_daily_writing_playbook_path() -> Path:
    return DEFAULT_TECH_DAILY_PLAYBOOK


def tech_daily_latest_report() -> Path | None:
    process_candidates = sorted(ai_daily_root().glob("20??-??-??/process/report.md"))
    if process_candidates:
        return process_candidates[-1]

    workspace_candidates = sorted((WORKSPACE_DIR / "reports").glob("tech-daily-20??-??-??.md"))
    if workspace_candidates:
        return workspace_candidates[-1]
    return None


def resolve_tech_daily_report_path(date: str) -> Path | None:
    candidates = [tech_daily_report_path(date)]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def resolve_tech_daily_social_urls_path(date: str) -> Path | None:
    candidates = [tech_daily_social_urls_path(date)]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def resolve_tech_daily_report_json_path(date: str) -> Path | None:
    candidates = [tech_daily_report_json_path(date)]
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
