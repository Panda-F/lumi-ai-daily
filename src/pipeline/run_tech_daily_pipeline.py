#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
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
    tech_daily_bgm_analysis_path,
    tech_daily_build_summary_path,
    tech_daily_collection_summary_path,
    tech_daily_cover_copy_path,
    tech_daily_cover_lab_dir,
    tech_daily_cover_review_path,
    tech_daily_day_dir,
    tech_daily_discovery_dir,
    tech_daily_content_manifest_path,
    tech_daily_editorial_brief_path,
    tech_daily_final_dir,
    tech_daily_final_report_json_path,
    tech_daily_final_report_path,
    tech_daily_final_social_urls_path,
    tech_daily_final_srt_path,
    tech_daily_final_video_path,
    tech_daily_publish_v2_dir,
    tech_daily_qa_dir,
    tech_daily_reference_pack_dir,
    tech_daily_source_pack_dir,
    tech_daily_story_assets_dir,
    tech_daily_title_pack_path,
    tech_daily_video_build_dir,
    tech_daily_video_script_path,
    tech_daily_video_style_review_path,
    resolve_tech_daily_report_path,
    resolve_tech_daily_social_urls_path,
)
from tech_daily_collection_contract import (
    build_hashes,
    load_collection_summary,
    resolve_collection_paths,
    validate_collection_summary,
)

WORKSPACE_DIR = Path(__file__).resolve().parents[1]
TEXT_COMPILE_SCRIPT = WORKSPACE_DIR / "scripts" / "tech_daily_text_compile.py"
DISCOVERY_SCRIPT = WORKSPACE_DIR / "scripts" / "tech_daily_prepare_discovery.py"
REPORT_BUILDER_SCRIPT = WORKSPACE_DIR / "scripts" / "build_ai_daily_report_from_collection.py"
ENV_PREFLIGHT_SCRIPT = WORKSPACE_DIR / "scripts" / "preflight_ai_daily_environment.py"
ARCHIVE_SOCIAL_SCRIPT = WORKSPACE_DIR / "scripts" / "archive_social_sources.py"
FETCH_STORY_IMAGES_SCRIPT = WORKSPACE_DIR / "skills" / "plus-media-factory" / "scripts" / "fetch_story_images.py"
IMAGEGEN_COVER_BRIEF_SCRIPT = (
    WORKSPACE_DIR / "skills" / "plus-media-factory" / "scripts" / "prepare_imagegen_cover_brief.py"
)
COVER_COPY_SCRIPT = WORKSPACE_DIR / "scripts" / "generate_tech_daily_cover_copy.py"
TITLE_PACK_SCRIPT = WORKSPACE_DIR / "scripts" / "generate_tech_daily_title_pack.py"
BGM_ANALYSIS_SCRIPT = WORKSPACE_DIR / "scripts" / "analyze_bgm_cutpoints.py"
VIDEO_STYLE_REVIEW_SCRIPT = WORKSPACE_DIR / "scripts" / "review_daily_video_style.py"
VIDEO_SCREENSHOT_SCRIPT = WORKSPACE_DIR / "scripts" / "generate_tech_daily_video_screenshots.py"
VIDEO_BUILD_SCRIPT = WORKSPACE_DIR / "scripts" / "tech-daily-video-build"
PUBLISH_SCRIPT = WORKSPACE_DIR / "scripts" / "tech-daily-publish-bundle"
COVER_REVIEW_SCRIPT = WORKSPACE_DIR / "scripts" / "review_daily_cover.swift"
ASSEMBLE_COVER_SCRIPT = WORKSPACE_DIR / "skills" / "plus-media-factory" / "scripts" / "assemble_magazine_cover.swift"
DEFAULT_BGM_PATH = WORKSPACE_DIR / "assets" / "bgm-lofi-morning.mp3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the stable daily AI report pipeline on an existing tech-daily report.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--overwrite", action="store_true", help="Replace generated artifacts in final/publish/qa and cover-lab.")
    parser.add_argument("--augment-sources", choices=("auto", "off", "force"), default="auto")
    parser.add_argument("--skip-delivery", action="store_true", help="Do not perform any external delivery side effects.")
    parser.add_argument("--reuse-discovery", choices=("auto", "always", "never"), default="auto")
    parser.add_argument("--reuse-collection", choices=("auto", "always", "never"), default="auto")
    return parser.parse_args()


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    resolved_env = None
    if env:
        resolved_env = os.environ.copy()
        resolved_env.update(env)
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=resolved_env,
        text=True,
        capture_output=True,
        check=True,
    )


def run_json(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    completed = run(cmd, cwd=cwd, env=env)
    return extract_json_payload(completed.stdout)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def read_text(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> Path:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")
    return path


def copy_if_needed(src: Path | None, dest: Path, *, default_text: str = "") -> Path:
    ensure_dir(dest.parent)
    if src and src.exists():
        if src.resolve() == dest.resolve():
            return dest
        shutil.copy2(src, dest)
        return dest
    dest.write_text(default_text, encoding="utf-8")
    return dest


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def tail_text(text: str, *, max_chars: int = 4000) -> str:
    value = (text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


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


def summarize_json_payload(payload: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in (
        "result",
        "status",
        "provider",
        "final_stage",
        "manifest",
        "report_json",
        "content_manifest",
        "cover_image",
        "video",
        "srt",
        "wechat_docx",
        "telegram_text",
        "telegram_send_manifest",
        "bilibili_text",
        "bilibili_upload_manifest",
        "video_screenshot_package",
    ):
        value = payload.get(key)
        if value is not None and value != "" and value != [] and value != {}:
            summary[key] = value
    blocking = payload.get("blocking_findings")
    if isinstance(blocking, list) and blocking:
        summary["blocking_findings"] = blocking[:5]
    return summary


def build_artifact_map(paths: list[Path]) -> dict[str, bool]:
    return {str(path): path.exists() for path in paths}


class StageExecutionError(RuntimeError):
    def __init__(
        self,
        stage_name: str,
        cmd: list[str],
        *,
        returncode: int | None,
        stdout: str,
        stderr: str,
    ) -> None:
        super().__init__(f"Stage {stage_name} failed with exit code {returncode}")
        self.stage_name = stage_name
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run_stage(
    stage_records: list[dict[str, Any]],
    stage_name: str,
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    stage_entry: dict[str, Any] = {
        "name": stage_name,
        "command": shlex.join(cmd),
        "started_at": utc_now_iso(),
    }
    if cwd:
        stage_entry["cwd"] = str(cwd)
    if env:
        stage_entry["env_overrides"] = env
    stage_records.append(stage_entry)
    started = time.monotonic()
    try:
        completed = run(cmd, cwd=cwd, env=env)
    except subprocess.CalledProcessError as exc:
        stage_entry.update(
            {
                "status": "failed",
                "finished_at": utc_now_iso(),
                "duration_sec": round(time.monotonic() - started, 2),
                "returncode": exc.returncode,
                "stdout_tail": tail_text(exc.stdout or ""),
                "stderr_tail": tail_text(exc.stderr or ""),
            }
        )
        raise StageExecutionError(
            stage_name,
            cmd,
            returncode=exc.returncode,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
        ) from exc
    stage_entry.update(
        {
            "status": "success",
            "finished_at": utc_now_iso(),
            "duration_sec": round(time.monotonic() - started, 2),
            "stdout_tail": tail_text(completed.stdout),
            "stderr_tail": tail_text(completed.stderr),
        }
    )
    return completed, stage_entry


def run_stage_json(
    stage_records: list[dict[str, Any]],
    stage_name: str,
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    completed, stage_entry = run_stage(stage_records, stage_name, cmd, cwd=cwd, env=env)
    payload = extract_json_payload(completed.stdout)
    payload_summary = summarize_json_payload(payload)
    if payload_summary:
        stage_entry["payload_summary"] = payload_summary
    return payload


def clean_generated_outputs(
    date: str,
    report_text: str,
    social_text: str,
    *,
    preserve_content_manifest: bool = False,
) -> None:
    final_dir = tech_daily_final_dir(date)
    publish_dir = tech_daily_publish_v2_dir(date)
    qa_dir = tech_daily_qa_dir(date)
    cover_lab_dir = tech_daily_cover_lab_dir(date)
    video_build_dir = tech_daily_video_build_dir(date)
    ensure_dir(final_dir)

    stale_paths = [
        final_dir / "assets",
        final_dir / "audio",
        final_dir / "slides",
        final_dir / "build-internals",
        final_dir / "build-summary.json",
        final_dir / "editorial-brief.json",
        final_dir / "timeline.json",
        final_dir / "remotion-manifest.json",
        final_dir / "remotion-stills.json",
        final_dir / "video-review.json",
        final_dir / "video-script.json",
        final_dir / "video.mp4",
        final_dir / "video.srt",
        final_dir / "writer-output.json",
        final_dir / "editorial-bundle.json",
        final_dir / "content-manifest.json",
        final_dir / "report.illustrated.md",
        final_dir / "report.image-manifest.json",
    ]
    stale_paths.extend(final_dir.glob("*.mp4"))
    stale_paths.extend(final_dir.glob("*.srt"))
    stale_paths.extend(final_dir.glob("tech-daily-video-*.mp4"))
    stale_paths.extend(final_dir.glob("tech-daily-video-*.srt"))
    for stale in stale_paths:
        if stale.name in {"report.md", "report.json", "social-urls.txt"}:
            continue
        if preserve_content_manifest and stale.name in {"content-manifest.json", "editorial-brief.json"}:
            continue
        remove_path(stale)

    remove_path(publish_dir)
    remove_path(video_build_dir)
    for stale in [
        tech_daily_bgm_analysis_path(date),
        tech_daily_cover_review_path(date),
        tech_daily_video_style_review_path(date),
        qa_dir / "pipeline-summary.json",
    ]:
        remove_path(stale)
    for stale in [
        cover_lab_dir / "final-cover.png",
        cover_lab_dir / "final-cover.jpg",
        cover_lab_dir / "final-cover.jpeg",
        cover_lab_dir / "final-cover.webp",
        cover_lab_dir / "final-cover.json",
        cover_lab_dir / "diagnostics",
    ]:
        remove_path(stale)

    if report_text:
        write_text(tech_daily_final_report_path(date), report_text)
    if social_text:
        write_text(tech_daily_final_social_urls_path(date), social_text)


def resolve_sources(
    date: str,
    report_path: Path,
    social_urls_path: Path,
    mode: str,
    stage_records: list[dict[str, Any]] | None = None,
) -> Path:
    target_dir = tech_daily_source_pack_dir(date)
    ensure_dir(target_dir.parent)
    if target_dir.exists() and mode != "force":
        return target_dir
    if target_dir.exists() and mode == "force":
        shutil.rmtree(target_dir)
    if mode == "off":
        ensure_dir(target_dir)
        return target_dir
    if not social_urls_path.exists():
        ensure_dir(target_dir)
        return target_dir
    cmd = [
        sys.executable,
        str(ARCHIVE_SOCIAL_SCRIPT),
        "--report",
        str(report_path),
        "--urls-file",
        str(social_urls_path),
        "--out-dir",
        str(target_dir),
    ]
    if stage_records is None:
        run_json(cmd)
    else:
        run_stage_json(stage_records, "archive_social_sources", cmd)
    return target_dir


def maybe_prepare_discovery(date: str, mode: str, stage_records: list[dict[str, Any]] | None = None) -> None:
    discovery_dir = tech_daily_discovery_dir(date)
    merged_json = discovery_dir / "merged-candidates.json"
    rsshub_json = discovery_dir / "rsshub-candidates.json"
    reusable_json = merged_json if merged_json.exists() else rsshub_json
    if mode in {"always", "auto"} and reusable_json.exists() and discovery_cache_is_reusable(reusable_json):
        return
    if mode == "always":
        raise RuntimeError(
            "reuse_discovery_always_missing_or_stale: expected a validated same-day discovery cache; "
            "refusing to refresh during production"
        )
    cmd = [sys.executable, str(DISCOVERY_SCRIPT), "--date", date, "--window-hours", "24"]
    if mode == "never":
        cmd.append("--refresh")
    if stage_records is None:
        run_json(cmd)
    else:
        run_stage_json(stage_records, "prepare_discovery", cmd)


def build_report_from_collection_if_missing(
    date: str,
    stage_records: list[dict[str, Any]],
) -> tuple[Path | None, Path | None]:
    report_input = resolve_tech_daily_report_path(date)
    social_input = resolve_tech_daily_social_urls_path(date)
    if report_input and social_input:
        return report_input, social_input
    discovery_path = tech_daily_discovery_dir(date) / "merged-candidates.json"
    if not discovery_path.exists():
        discovery_path = tech_daily_discovery_dir(date) / "rsshub-candidates.json"
    if not discovery_path.exists():
        return report_input, social_input
    run_stage_json(
        stage_records,
        "build_report_from_collection",
        [
            sys.executable,
            str(REPORT_BUILDER_SCRIPT),
            "--date",
            date,
            "--discovery-json",
            str(discovery_path),
            "--report-out",
            str(tech_daily_final_report_path(date)),
            "--social-urls-out",
            str(tech_daily_final_social_urls_path(date)),
        ],
    )
    return resolve_tech_daily_report_path(date), resolve_tech_daily_social_urls_path(date)


def maybe_load_collection(date: str, mode: str) -> dict[str, Any] | None:
    if mode == "never":
        return None
    summary_path = tech_daily_collection_summary_path(date)
    if not summary_path.exists():
        if mode == "always":
            raise RuntimeError(f"reuse_collection_always_missing: {summary_path}")
        return None
    payload = load_collection_summary(date)
    findings = validate_collection_summary(date, payload)
    if findings:
        recoverable_after_partial_production = {
            "report_json_hash_mismatch",
            "content_manifest_hash_mismatch",
        }
        if set(findings).issubset(recoverable_after_partial_production):
            payload["_validation_warnings"] = findings
            return payload
        raise RuntimeError(f"Collection summary failed validation: {findings}")
    return payload


def write_cover_metadata(date: str, image_path: Path, *, provider: str, final_stage: str = "cover_ready") -> Path:
    payload = {
        "ok": True,
        "provider": provider,
        "final_stage": final_stage,
        "image": str(image_path),
        "downloaded": str(image_path),
        "artifacts": {
            "result_json": str(tech_daily_cover_lab_dir(date) / "final-cover.json"),
        },
    }
    return write_json(tech_daily_cover_lab_dir(date) / "final-cover.json", payload)


def patch_cover_copy(cover_copy_path: Path, title_pack_path: Path) -> None:
    payload = load_json(cover_copy_path)
    title_pack = load_json(title_pack_path)
    changed = False
    if title_pack.get("cover_headline"):
        payload["marketing_headline"] = title_pack["cover_headline"]
        changed = True
    if title_pack.get("cover_subhead"):
        payload["subhead"] = title_pack["cover_subhead"]
        payload["supporting_headline"] = title_pack["cover_subhead"]
        changed = True
    if changed:
        write_json(cover_copy_path, payload)


def sync_collection_summary(date: str) -> dict[str, Any] | None:
    summary_path = tech_daily_collection_summary_path(date)
    if not summary_path.exists():
        return None
    payload = load_json(summary_path)
    if not payload:
        return None
    paths = resolve_collection_paths(date, payload)
    payload["hashes"] = build_hashes(paths)
    validation_findings = validate_collection_summary(date, payload)
    payload["validation_findings"] = validation_findings
    if not validation_findings:
        payload["result"] = "success"
        payload["targets_met"] = True
    write_json(summary_path, payload)
    return payload


def parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def discovery_cache_is_reusable(path: Path, *, max_age_minutes: int = 120, window_hours: int = 24) -> bool:
    payload = load_json(path)
    if not payload:
        return False
    if int(payload.get("window_hours") or 0) != window_hours:
        return False
    generated_at = parse_iso_datetime(payload.get("generated_at") or payload.get("created_at"))
    if not generated_at:
        return False
    age_minutes = (datetime.now(timezone.utc) - generated_at).total_seconds() / 60.0
    if age_minutes < 0 or age_minutes > max(float(max_age_minutes), 1.0):
        return False
    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        return len(candidates) >= 20
    return int(payload.get("candidate_count") or 0) >= 20


def validate_publish_manifests(publish_dir: Path, expected_video: Path) -> dict[str, Any]:
    expected_video = expected_video.expanduser().resolve()
    manifest_specs = {
        "telegram_send_manifest": publish_dir / "telegram-send.json",
        "bilibili_upload_manifest": publish_dir / "bilibili-upload.json",
    }
    file_reference_keys = {
        "cover_file",
        "cover_image_file",
        "captions_file",
        "summary_file",
        "text_file",
        "video_cover_image_file",
        "video_file",
    }
    findings: list[str] = []
    for name, path in manifest_specs.items():
        if not path.exists():
            findings.append(f"missing_{name}")
            continue
        manifest = load_json(path)
        raw_video = str(manifest.get("video_file") or "").strip()
        if not raw_video:
            findings.append(f"{name}_missing_video_file")
        else:
            video_path = Path(raw_video).expanduser().resolve()
            if video_path != expected_video:
                findings.append(f"{name}_video_file_not_expected_delivery_video")
            if not video_path.exists():
                findings.append(f"{name}_video_file_missing_on_disk")
        for key in file_reference_keys:
            raw_value = manifest.get(key)
            if raw_value in (None, "", []):
                continue
            if not isinstance(raw_value, str):
                findings.append(f"{name}_{key}_not_string")
                continue
            referenced = Path(raw_value).expanduser().resolve()
            if not referenced.exists():
                findings.append(f"{name}_{key}_missing_on_disk")
    if findings:
        raise RuntimeError(f"Publish manifest validation failed: {sorted(set(findings))}")
    return {
        "status": "pass",
        "expected_delivery_video": str(expected_video),
        "manifests": {
            name: str(path)
            for name, path in manifest_specs.items()
        },
    }


def rewrite_publish_video_references(
    *,
    publish_dir: Path,
    delivery_video: Path,
    cover_image: Path,
) -> None:
    for manifest_name in ("telegram-send.json", "bilibili-upload.json"):
        manifest_path = publish_dir / manifest_name
        if not manifest_path.exists():
            continue
        payload = load_json(manifest_path)
        payload["video_file"] = str(delivery_video)
        payload["cover_image_file"] = str(cover_image)
        if "video_cover_image_file" in payload:
            payload["video_cover_image_file"] = str(cover_image)
        write_json(manifest_path, payload)


def validate_video_build_quality(date: str) -> dict[str, Any]:
    summary_path = tech_daily_build_summary_path(date)
    if not summary_path.exists():
        raise RuntimeError(f"Video build summary missing: {summary_path}")
    summary = load_json(summary_path)
    findings: list[str] = []
    if summary.get("result") != "success":
        findings.append("video_build_not_success")
    if summary.get("fallback_render"):
        findings.append("video_fallback_render_used")
    note = " ".join(
        str(summary.get(key) or "")
        for key in ("fallback_note", "audio_note")
    ).lower()
    if "silent" in note or "placeholder" in note:
        findings.append("video_silent_placeholder")
    tts = summary.get("tts") if isinstance(summary.get("tts"), dict) else {}
    effective_provider = str(tts.get("effective_provider") or summary.get("voice_engine") or "").strip()
    if effective_provider != "fish-speech":
        findings.append(f"tts_provider_not_fish:{effective_provider or 'missing'}")
    if int(tts.get("remote_fallback_segments") or 0) > 0:
        findings.append("tts_remote_fallback_segments_present")
    if bool(tts.get("remote_preflight_checked")) and not bool(tts.get("remote_preflight_ok")):
        findings.append("tts_remote_preflight_failed")
    if not bool(tts.get("remote_audio_probe_ok")):
        findings.append("tts_remote_audio_probe_missing_or_failed")
    if findings:
        raise RuntimeError(f"Video build quality failed: {sorted(set(findings))}")
    return {
        "status": "pass",
        "summary": str(summary_path),
        "voice_engine": effective_provider,
        "tts": tts,
    }


def copy_named_publish_artifacts(
    *,
    date: str,
    title_pack_path: Path,
    final_video: Path,
    publish_dir: Path,
    cover_image: Path,
) -> dict[str, str]:
    del date, cover_image
    title_pack = load_json(title_pack_path)
    artifacts: dict[str, str] = {}

    wechat_filename = Path(str(title_pack.get("wechat_filename") or "")).name
    if wechat_filename:
        canonical_wechat = publish_dir / "wechat.docx"
        titled_wechat = publish_dir / wechat_filename
        if canonical_wechat.exists() and titled_wechat != canonical_wechat:
            shutil.copy2(canonical_wechat, titled_wechat)
        if titled_wechat.exists():
            artifacts["wechat_docx_named"] = str(titled_wechat)

    video_filename = Path(str(title_pack.get("video_filename") or "")).name
    if video_filename:
        titled_final_video = final_video.parent / video_filename
        titled_publish_video = publish_dir / video_filename
        if final_video.exists() and titled_final_video != final_video:
            shutil.copy2(final_video, titled_final_video)
        if final_video.exists():
            shutil.copy2(final_video, titled_publish_video)
        if titled_final_video.exists():
            artifacts["video_mp4_named_final"] = str(titled_final_video)
        if titled_publish_video.exists():
            artifacts["video_mp4_named_publish"] = str(titled_publish_video)

    return artifacts


def run_video_build_with_fallback(
    *,
    stage_records: list[dict[str, Any]],
    final_report: Path,
    video_build_dir: Path,
    title_pack_path: Path,
    content_manifest_path: Path,
    bgm_analysis_path: Path,
    story_manifest_path: Path | None = None,
) -> tuple[dict[str, Any], str]:
    env: dict[str, str] = {
        "AI_DAILY_SKIP_LIVE_SEARCH_FALLBACK": "0",
        "AI_DAILY_ALLOW_LIVE_SEARCH_SKIP": "0",
        "AI_DAILY_REMOTION_PUBLIC_DIR": str(video_build_dir / "remotion-public"),
    }
    allow_video_degradation = os.environ.get("AI_DAILY_ALLOW_VIDEO_DEGRADATION", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    primary_cmd = [
        sys.executable,
        str(VIDEO_BUILD_SCRIPT),
        "--report",
        str(final_report),
        "--out-dir",
        str(video_build_dir),
        "--title-pack",
        str(title_pack_path),
        "--content-manifest",
        str(content_manifest_path),
        "--bgm-analysis",
        str(bgm_analysis_path),
        "--disable-outro-bgm",
        "--require-fish",
        "--remotion-public-dir",
        str(video_build_dir / "remotion-public"),
    ]
    if story_manifest_path and story_manifest_path.exists():
        primary_cmd.extend(["--manifest", str(story_manifest_path)])
    try:
        return run_stage_json(stage_records, "video_build_primary", primary_cmd, env=env), "primary"
    except StageExecutionError:
        if not allow_video_degradation:
            raise
        whisper_retry_cmd = [*primary_cmd, "--no-whisper"]
        try:
            return (
                run_stage_json(stage_records, "video_build_no_whisper_retry", whisper_retry_cmd, env=env),
                "no_whisper_retry",
            )
        except StageExecutionError:
            raise


def reuse_existing_video_build_payload(
    *,
    date: str,
    content_manifest_path: Path,
    title_pack_path: Path,
) -> dict[str, Any] | None:
    del title_pack_path
    built_video = tech_daily_video_build_dir(date) / "video.mp4"
    built_srt = tech_daily_video_build_dir(date) / "video.srt"
    required_outputs = [
        built_video,
        built_srt,
        tech_daily_build_summary_path(date),
        tech_daily_video_script_path(date),
        tech_daily_final_video_path(date),
        tech_daily_final_srt_path(date),
    ]
    if not all(path.exists() and path.stat().st_size > 0 for path in required_outputs):
        return None
    required_inputs = [path for path in [content_manifest_path] if path.exists()]
    if required_inputs:
        newest_input_mtime = max(path.stat().st_mtime for path in required_inputs)
        oldest_output_mtime = min(path.stat().st_mtime for path in required_outputs)
        if oldest_output_mtime < newest_input_mtime:
            return None
    return {
        "result": "reused",
        "reason": "existing_video_build_is_newer_than_content_inputs",
        "video": str(built_video),
        "srt": str(built_srt),
        "build_summary": str(tech_daily_build_summary_path(date)),
        "video_script": str(tech_daily_video_script_path(date)),
        "final_video": str(tech_daily_final_video_path(date)),
        "final_srt": str(tech_daily_final_srt_path(date)),
    }


def main() -> int:
    args = parse_args()
    date = args.date
    day_dir = tech_daily_day_dir(date)
    ensure_dir(tech_daily_final_dir(date))
    video_build_dir = ensure_dir(tech_daily_video_build_dir(date))
    publish_dir = ensure_dir(tech_daily_publish_v2_dir(date))
    qa_dir = ensure_dir(tech_daily_qa_dir(date))
    reference_pack_dir = ensure_dir(tech_daily_reference_pack_dir(date))
    ensure_dir(tech_daily_source_pack_dir(date))
    cover_lab_dir = ensure_dir(tech_daily_cover_lab_dir(date))

    pipeline_summary_path = qa_dir / "pipeline-summary.json"
    artifact_paths = [
        tech_daily_final_report_path(date),
        tech_daily_final_report_json_path(date),
        tech_daily_editorial_brief_path(date),
        tech_daily_content_manifest_path(date),
        tech_daily_final_social_urls_path(date),
        cover_lab_dir / "final-cover.png",
        tech_daily_final_video_path(date),
        tech_daily_final_srt_path(date),
        publish_dir / "telegram.txt",
        publish_dir / "telegram-send.json",
        publish_dir / "wechat.docx",
        publish_dir / "bilibili.txt",
        publish_dir / "bilibili-upload.json",
        tech_daily_title_pack_path(date),
        tech_daily_bgm_analysis_path(date),
        tech_daily_cover_review_path(date),
        tech_daily_video_style_review_path(date),
        qa_dir / "video-screenshot-review.json",
        tech_daily_build_summary_path(date),
        tech_daily_video_script_path(date),
        publish_dir / "video-screenshots" / "manifest.json",
    ]
    started_at = utc_now_iso()
    started_monotonic = time.monotonic()
    stage_records: list[dict[str, Any]] = []
    named_artifacts: dict[str, str] = {}
    current_stage = "bootstrap"
    payload: dict[str, Any] = {
        "result": "running",
        "date": date,
        "day_dir": str(day_dir),
        "started_at": started_at,
        "skip_delivery": args.skip_delivery,
        "stages": stage_records,
    }
    return_code = 1

    try:
        content_manifest_path = tech_daily_content_manifest_path(date)
        current_stage = "load_collection"
        collection_payload = maybe_load_collection(date, args.reuse_collection)
        collection_paths = resolve_collection_paths(date, collection_payload) if collection_payload else {}

        if collection_payload:
            report_input = collection_paths["report"]
            social_input = collection_paths["social_urls"]
            final_report = report_input
            final_social_urls = social_input
            manifest_path = collection_paths["story_manifest"]
            sources_dir = collection_paths["source_pack"]
            reference_pack_dir = collection_paths["reference_pack"]
            content_manifest_path = collection_paths["content_manifest"]
            text_compile_payload = {
                "result": "reused",
                "collection_summary": str(tech_daily_collection_summary_path(date)),
                "report_json": str(collection_paths["report_json"]),
            }
            fetch_story_payload = {
                "result": "reused",
                "manifest": str(manifest_path),
                "asset_count": len(load_json(manifest_path).get("assets", [])) if manifest_path.exists() else 0,
            }
        else:
            current_stage = "prepare_discovery"
            maybe_prepare_discovery(date, args.reuse_discovery, stage_records)

            current_stage = "resolve_inputs"
            report_input, social_input = build_report_from_collection_if_missing(date, stage_records)
            if not report_input:
                raise FileNotFoundError(f"No tech-daily report found for {date}")
            if not social_input:
                raise FileNotFoundError(f"No tech-daily social URLs found for {date}")

            report_text = read_text(report_input)
            social_text = read_text(social_input)
            if args.overwrite:
                current_stage = "clean_generated_outputs"
                clean_generated_outputs(date, report_text, social_text)

            current_stage = "stage_inputs"
            final_report = copy_if_needed(report_input, tech_daily_final_report_path(date), default_text=report_text)
            final_social_urls = copy_if_needed(social_input, tech_daily_final_social_urls_path(date), default_text=social_text)

            current_stage = "resolve_source_pack"
            sources_dir = resolve_sources(date, final_report, final_social_urls, args.augment_sources, stage_records)

            current_stage = "text_compile"
            text_compile_payload = run_stage_json(
                stage_records,
                "text_compile",
                [
                    sys.executable,
                    str(TEXT_COMPILE_SCRIPT),
                    "--report",
                    str(final_report),
                    "--date",
                    date,
                    "--report-json-out",
                    str(tech_daily_final_report_json_path(date)),
                    "--editorial-brief-out",
                    str(tech_daily_editorial_brief_path(date)),
                    "--content-manifest-out",
                    str(content_manifest_path),
                    "--reference-pack-out",
                    str(reference_pack_dir),
                    "--source-pack",
                    str(sources_dir),
                    "--skip-illustrated-report",
                ],
            )

            story_assets_dir = tech_daily_story_assets_dir(date)
            if story_assets_dir.exists() and args.overwrite:
                shutil.rmtree(story_assets_dir)
            current_stage = "fetch_story_images"
            fetch_story_payload = run_stage_json(
                stage_records,
                "fetch_story_images",
                [
                    sys.executable,
                    str(FETCH_STORY_IMAGES_SCRIPT),
                    "--report",
                    str(final_report),
                    "--out-dir",
                    str(story_assets_dir),
                    "--limit",
                    "48",
                    "--per-url-limit",
                    "4",
                ],
            )
            manifest_path = story_assets_dir / "manifest.json"

        payload["inputs"] = {
            "report_input": str(report_input),
            "social_input": str(social_input) if social_input else None,
            "overwrite": args.overwrite,
            "augment_sources": args.augment_sources,
            "reuse_discovery": args.reuse_discovery,
            "reuse_collection": args.reuse_collection,
            "collection_summary": str(tech_daily_collection_summary_path(date)) if collection_payload else None,
        }

        if args.overwrite and collection_payload:
            report_text = read_text(report_input)
            social_text = read_text(social_input)
            current_stage = "clean_generated_outputs"
            clean_generated_outputs(date, report_text, social_text, preserve_content_manifest=True)
            final_report = tech_daily_final_report_path(date)
            final_social_urls = tech_daily_final_social_urls_path(date)

        if not content_manifest_path.exists():
            current_stage = "text_compile_content_manifest"
            text_compile_payload = run_stage_json(
                stage_records,
                "text_compile_content_manifest",
                [
                    sys.executable,
                    str(TEXT_COMPILE_SCRIPT),
                    "--report",
                    str(final_report),
                    "--date",
                    date,
                    "--report-json-out",
                    str(tech_daily_final_report_json_path(date)),
                    "--editorial-brief-out",
                    str(tech_daily_editorial_brief_path(date)),
                    "--content-manifest-out",
                    str(content_manifest_path),
                    "--reference-pack-out",
                    str(reference_pack_dir),
                    "--source-pack",
                    str(sources_dir),
                    "--skip-search-terms",
                    "--skip-candidate-review",
                    "--skip-reference-pack",
                    "--skip-illustrated-report",
                ],
            )
        cover_copy_path = tech_daily_cover_copy_path(date)

        current_stage = "generate_cover_copy"
        run_stage_json(
            stage_records,
            "generate_cover_copy",
            [
                sys.executable,
                str(COVER_COPY_SCRIPT),
                "--report",
                str(final_report),
                "--content-manifest",
                str(content_manifest_path),
                "--out",
                str(cover_copy_path),
            ],
        )

        title_pack_path = tech_daily_title_pack_path(date)
        current_stage = "generate_title_pack"
        title_pack_payload = run_stage_json(
            stage_records,
            "generate_title_pack",
            [
                sys.executable,
                str(TITLE_PACK_SCRIPT),
                "--report",
                str(final_report),
                "--date",
                date,
                "--cover-copy",
                str(cover_copy_path),
                "--content-manifest",
                str(content_manifest_path),
                "--out",
                str(title_pack_path),
            ],
        )
        patch_cover_copy(cover_copy_path, title_pack_path)

        deterministic_cover = cover_lab_dir / "final-cover.png"
        cover_provider = os.environ.get("AI_DAILY_COVER_PROVIDER", "imagegen_skill").strip().lower()
        imagegen_requested = cover_provider in {"imagegen", "imagegen_skill", "image_generation"}
        imagegen_required = os.environ.get("AI_DAILY_REQUIRE_IMAGEGEN_COVER", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if imagegen_requested:
            current_stage = "prepare_imagegen_cover_brief"
            run_stage_json(
                stage_records,
                "prepare_imagegen_cover_brief",
                [
                    sys.executable,
                    str(IMAGEGEN_COVER_BRIEF_SCRIPT),
                    "--date",
                    date,
                    "--report",
                    str(final_report),
                    "--cover-copy",
                    str(cover_copy_path),
                    "--title-pack",
                    str(title_pack_path),
                    "--story-manifest",
                    str(manifest_path),
                    "--final-cover",
                    str(deterministic_cover),
                    "--out-json",
                    str(cover_lab_dir / "imagegen-cover-brief.json"),
                    "--out-md",
                    str(cover_lab_dir / "imagegen-cover-brief.md"),
                ],
            )

        if imagegen_requested and deterministic_cover.exists():
            cover_meta_path = write_cover_metadata(
                date,
                deterministic_cover,
                provider="imagegen_skill_or_existing_cover",
                final_stage="imagegen_or_existing_cover_ready",
            )
        elif imagegen_requested and imagegen_required:
            raise RuntimeError(
                "imagegen_cover_required: generated cover is missing. "
                f"Use the imagegen skill with {cover_lab_dir / 'imagegen-cover-brief.md'} "
                f"and save the selected image to {deterministic_cover}, then rerun the pipeline."
            )
        else:
            current_stage = "assemble_cover"
            run_stage(
                stage_records,
                "assemble_cover",
                [
                    "swift",
                    str(ASSEMBLE_COVER_SCRIPT),
                    "--manifest",
                    str(manifest_path),
                    "--out",
                    str(deterministic_cover),
                    "--copy-json",
                    str(cover_copy_path),
                ],
            )
            cover_meta_path = write_cover_metadata(
                date,
                deterministic_cover,
                provider="deterministic_cover",
                final_stage="deterministic_cover_ready",
            )

        current_stage = "review_cover"
        cover_review_payload = run_stage_json(
            stage_records,
            "review_cover",
            [
                "swift",
                str(COVER_REVIEW_SCRIPT),
                "--image",
                str(deterministic_cover),
                "--copy-json",
                str(cover_copy_path),
                "--title-pack",
                str(title_pack_path),
                "--provider",
                "deterministic_cover",
                "--out",
                str(tech_daily_cover_review_path(date)),
            ],
        )
        if cover_review_payload.get("status") != "pass":
            raise RuntimeError(f"Cover review failed: {cover_review_payload.get('blocking_findings')}")

        current_stage = "bgm_analysis"
        bgm_analysis_payload = run_stage_json(
            stage_records,
            "bgm_analysis",
            [
                sys.executable,
                str(BGM_ANALYSIS_SCRIPT),
                "--bgm",
                str(DEFAULT_BGM_PATH),
                "--out",
                str(tech_daily_bgm_analysis_path(date)),
            ],
        )

        current_stage = "environment_preflight"
        environment_preflight_payload = run_stage_json(
            stage_records,
            "environment_preflight",
            [
                sys.executable,
                str(ENV_PREFLIGHT_SCRIPT),
                "--date",
                date,
                "--out",
                str(qa_dir / "environment-preflight.json"),
                "--require-fish",
                "--require-network",
                "--require-remotion-public",
                "--require-video-tools",
                "--remotion-public-dir",
                str(video_build_dir / "remotion-public"),
            ],
        )

        current_stage = "video_build"
        reused_video_payload = reuse_existing_video_build_payload(
            date=date,
            content_manifest_path=content_manifest_path,
            title_pack_path=title_pack_path,
        )
        if reused_video_payload:
            video_build_payload, video_build_mode = reused_video_payload, "reused_existing"
            stage_records.append(
                {
                    "name": "video_build_reuse_existing",
                    "status": "success",
                    "payload_summary": summarize_json_payload(reused_video_payload),
                }
            )
        else:
            video_build_payload, video_build_mode = run_video_build_with_fallback(
                stage_records=stage_records,
                final_report=final_report,
                video_build_dir=video_build_dir,
                title_pack_path=title_pack_path,
                content_manifest_path=content_manifest_path,
                bgm_analysis_path=tech_daily_bgm_analysis_path(date),
                story_manifest_path=manifest_path,
            )
        built_video = video_build_dir / "video.mp4"
        built_srt = video_build_dir / "video.srt"
        if not built_video.exists() or not built_srt.exists():
            raise RuntimeError(f"Video build missing formal outputs: video={built_video.exists()} srt={built_srt.exists()}")
        copy_if_needed(built_video, tech_daily_final_video_path(date))
        copy_if_needed(built_srt, tech_daily_final_srt_path(date))
        video_build_quality = validate_video_build_quality(date)

        current_stage = "video_style_review"
        video_style_payload = run_stage_json(
            stage_records,
            "video_style_review",
            [
                sys.executable,
                str(VIDEO_STYLE_REVIEW_SCRIPT),
                "--report-json",
                str(tech_daily_final_report_json_path(date)),
                "--video-script",
                str(tech_daily_video_script_path(date)),
                "--srt",
                str(tech_daily_final_srt_path(date)),
                "--title-pack",
                str(title_pack_path),
                "--build-summary",
                str(tech_daily_build_summary_path(date)),
                "--out",
                str(tech_daily_video_style_review_path(date)),
            ],
        )
        if video_style_payload.get("status") != "pass":
            raise RuntimeError(f"Video style review failed: {video_style_payload.get('blocking_findings')}")

        current_stage = "publish_final"
        publish_payload = run_stage_json(
            stage_records,
            "publish_final",
            [
                sys.executable,
                str(PUBLISH_SCRIPT),
                "--report",
                str(final_report),
                "--out-dir",
                str(publish_dir),
                "--video-file",
                str(tech_daily_final_video_path(date)),
                "--video-summary",
                str(tech_daily_build_summary_path(date)),
                "--cover-image",
                str(deterministic_cover),
                "--cover-result",
                str(cover_meta_path),
                "--title-pack",
                str(title_pack_path),
                "--content-manifest",
                str(content_manifest_path),
                "--require-video",
            ],
        )
        named_artifacts = copy_named_publish_artifacts(
            date=date,
            title_pack_path=title_pack_path,
            final_video=tech_daily_final_video_path(date),
            publish_dir=publish_dir,
            cover_image=deterministic_cover,
        )
        delivery_video = Path(
            named_artifacts.get("video_mp4_named_publish") or str(tech_daily_final_video_path(date))
        ).expanduser().resolve()
        rewrite_publish_video_references(
            publish_dir=publish_dir,
            delivery_video=delivery_video,
            cover_image=deterministic_cover,
        )
        publish_manifest_validation = validate_publish_manifests(publish_dir, delivery_video)

        current_stage = "video_screenshot_package"
        screenshot_payload = run_stage_json(
            stage_records,
            "video_screenshot_package",
            [
                sys.executable,
                str(VIDEO_SCREENSHOT_SCRIPT),
                "--date",
                date,
                "--report",
                str(final_report),
                "--content-manifest",
                str(content_manifest_path),
                "--title-pack",
                str(title_pack_path),
                "--build-dir",
                str(video_build_dir),
                "--out-dir",
                str(publish_dir / "video-screenshots"),
                "--review-out",
                str(qa_dir / "video-screenshot-review.json"),
                "--max-items",
                "6",
            ],
        )
        collection_summary_payload = sync_collection_summary(date)
        if collection_summary_payload:
            validation_findings = list(collection_summary_payload.get("validation_findings") or [])
            if validation_findings:
                raise RuntimeError(f"Collection summary drifted after production: {validation_findings}")

        missing = [str(path) for path in artifact_paths if not path.exists()]
        if missing:
            raise RuntimeError(f"Pipeline missing required artifacts: {missing}")

        payload.update(
            {
                "result": "success",
                "report": str(final_report),
                "report_json": str(tech_daily_final_report_json_path(date)),
                "social_urls": str(final_social_urls),
                "discovery_dir": str(tech_daily_discovery_dir(date)),
                "source_pack": str(sources_dir),
                "reference_pack": str(reference_pack_dir),
                "story_manifest": str(manifest_path),
                "editorial_brief": str(tech_daily_editorial_brief_path(date)),
                "content_manifest": str(content_manifest_path),
                "cover_copy": str(cover_copy_path),
                "title_pack": str(title_pack_path),
                "cover_image": str(deterministic_cover),
                "video_build_dir": str(video_build_dir),
                "video": str(tech_daily_final_video_path(date)),
                "srt": str(tech_daily_final_srt_path(date)),
                "telegram_text": str(publish_dir / "telegram.txt"),
                "telegram_send_manifest": str(publish_dir / "telegram-send.json"),
                "wechat_docx": str(publish_dir / "wechat.docx"),
                "bilibili_text": str(publish_dir / "bilibili.txt"),
                "bilibili_upload_manifest": str(publish_dir / "bilibili-upload.json"),
                "video_screenshot_package": str(publish_dir / "video-screenshots"),
                "build_summary": str(tech_daily_build_summary_path(date)),
                "video_build_mode": video_build_mode,
                "qa": {
                    "bgm_analysis": str(tech_daily_bgm_analysis_path(date)),
                    "cover_review": str(tech_daily_cover_review_path(date)),
                    "video_style_review": str(tech_daily_video_style_review_path(date)),
                },
                "text_compile": text_compile_payload,
                "story_assets": fetch_story_payload,
                "title_pack_payload": title_pack_payload,
                "cover_review_payload": cover_review_payload,
                "bgm_analysis_payload": bgm_analysis_payload,
                "environment_preflight_payload": environment_preflight_payload,
                "video_build_payload": video_build_payload,
                "video_style_payload": video_style_payload,
                "publish_payload": publish_payload,
                "publish_manifest_validation": publish_manifest_validation,
                "video_build_quality": video_build_quality,
                "video_screenshot_payload": screenshot_payload,
                "collection_summary_payload": collection_summary_payload,
                "named_artifacts": named_artifacts,
            }
        )
        return_code = 0
    except Exception as exc:
        payload.update(
            {
                "result": "failed",
                "failed_stage": current_stage,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(limit=20),
            }
        )
        if isinstance(exc, StageExecutionError):
            payload.update(
                {
                    "failed_command": shlex.join(exc.cmd),
                    "failed_returncode": exc.returncode,
                    "failed_stdout_tail": tail_text(exc.stdout),
                    "failed_stderr_tail": tail_text(exc.stderr),
                }
            )
    finally:
        named_artifact_paths = [Path(path) for path in named_artifacts.values()]
        payload["artifacts"] = build_artifact_map(artifact_paths + named_artifact_paths)
        payload["finished_at"] = utc_now_iso()
        payload["duration_sec"] = round(time.monotonic() - started_monotonic, 2)
        write_json(pipeline_summary_path, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
