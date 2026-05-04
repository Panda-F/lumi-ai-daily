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
    tech_daily_bgm_analysis_path,
    tech_daily_build_summary_path,
    tech_daily_content_manifest_path,
    tech_daily_cover_copy_path,
    tech_daily_cover_lab_dir,
    tech_daily_discovery_dir,
    tech_daily_editorial_brief_path,
    tech_daily_final_cover_path,
    tech_daily_final_cover_result_path,
    tech_daily_final_dir,
    tech_daily_final_srt_path,
    tech_daily_final_video_path,
    tech_daily_final_wechat_docx_path,
    tech_daily_process_dir,
    tech_daily_qa_dir,
    tech_daily_reference_pack_dir,
    tech_daily_report_json_path,
    tech_daily_report_path,
    tech_daily_source_pack_dir,
    tech_daily_social_urls_path,
    tech_daily_title_pack_path,
    tech_daily_video_build_dir,
    resolve_tech_daily_report_path,
    resolve_tech_daily_social_urls_path,
)


SRC_DIR = Path(__file__).resolve().parent
REPO_ROOT = SRC_DIR.parent

DISCOVERY_DIR = SRC_DIR / "discovery"
CONTENT_DIR = SRC_DIR / "content"
VISUALS_DIR = SRC_DIR / "visuals"
VIDEO_DIR = SRC_DIR / "video"

DISCOVERY_SCRIPT = DISCOVERY_DIR / "prepare_discovery.py"
REPORT_BUILDER_SCRIPT = CONTENT_DIR / "build_report.py"
TEXT_COMPILE_SCRIPT = CONTENT_DIR / "compile_content.py"
COVER_COPY_SCRIPT = CONTENT_DIR / "generate_cover_copy.py"
TITLE_PACK_SCRIPT = CONTENT_DIR / "generate_title_pack.py"
BGM_ANALYSIS_SCRIPT = VIDEO_DIR / "analyze_bgm_cutpoints.py"
IMAGEGEN_COVER_BRIEF_SCRIPT = VISUALS_DIR / "prepare_cover_brief.py"
VIDEO_BUILD_SCRIPT = VIDEO_DIR / "build_video.py"
WECHAT_SCRIPT = CONTENT_DIR / "render_wechat.py"
BILIBILI_SCRIPT = VIDEO_DIR / "render_bilibili.py"
DEFAULT_BGM_PATH = REPO_ROOT / "assets" / "bgm-lofi-morning.mp3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the simplified Lumi AI Daily production path.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--reuse-discovery", choices=("auto", "always", "never"), default="auto")
    parser.add_argument("--augment-sources", choices=("auto", "off"), default="auto")
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_text(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_json(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def extract_json_payload(stdout: str) -> dict[str, Any]:
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
    record: dict[str, Any] = {"name": name, "command": shlex.join(cmd), "started_at": utc_now_iso()}
    stage_records.append(record)
    started = time.monotonic()
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    record.update(
        {
            "returncode": completed.returncode,
            "finished_at": utc_now_iso(),
            "duration_sec": round(time.monotonic() - started, 2),
            "stdout_tail": (completed.stdout or "")[-4000:],
            "stderr_tail": (completed.stderr or "")[-4000:],
        }
    )
    payload = extract_json_payload(completed.stdout or "")
    if payload:
        record["payload"] = {key: payload.get(key) for key in ("result", "status", "report", "content_manifest", "video", "wechat_docx", "bilibili_upload_manifest") if payload.get(key)}
    if completed.returncode != 0:
        record["status"] = "failed"
        raise RuntimeError(f"{name} failed: {(completed.stderr or completed.stdout or '').strip()[-1200:]}")
    record["status"] = "success"
    return payload


def copy_if_needed(src: Path, dest: Path) -> Path:
    ensure_dir(dest.parent)
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return dest


def move_if_needed(src: Path, dest: Path) -> Path:
    ensure_dir(dest.parent)
    if src.resolve() != dest.resolve():
        dest.unlink(missing_ok=True)
        shutil.move(str(src), str(dest))
    return dest


def clean_outputs(date: str) -> None:
    final_dir = tech_daily_final_dir(date)
    if final_dir.exists():
        for stale in (
            final_dir / "video.mp4",
            final_dir / "video.srt",
            final_dir / "wechat.docx",
            final_dir / "bilibili.txt",
            final_dir / "bilibili-upload.json",
            final_dir / "title-pack.json",
            final_dir / "summary.json",
            final_dir / "report.md",
            final_dir / "report.json",
            final_dir / "social-urls.txt",
            final_dir / "content-manifest.json",
            final_dir / "editorial-brief.json",
        ):
            stale.unlink(missing_ok=True)
        for stale_docx in final_dir.glob("*.docx"):
            stale_docx.unlink(missing_ok=True)
        for stale_video in final_dir.glob("*.mp4"):
            stale_video.unlink(missing_ok=True)
    for path in (tech_daily_video_build_dir(date), tech_daily_cover_lab_dir(date)):
        if path.exists():
            shutil.rmtree(path)
    for path in (tech_daily_source_pack_dir(date), tech_daily_reference_pack_dir(date), tech_daily_process_dir(date) / "content"):
        if path.exists():
            shutil.rmtree(path)
    for stale in (
        tech_daily_report_path(date),
        tech_daily_social_urls_path(date),
        tech_daily_report_json_path(date),
        tech_daily_content_manifest_path(date),
        tech_daily_editorial_brief_path(date),
        tech_daily_cover_copy_path(date),
        tech_daily_bgm_analysis_path(date),
    ):
        stale.unlink(missing_ok=True)


def maybe_prepare_discovery(date: str, mode: str, stage_records: list[dict[str, Any]]) -> None:
    discovery_dir = tech_daily_discovery_dir(date)
    merged_json = discovery_dir / "merged-candidates.json"
    if mode in {"auto", "always"} and merged_json.exists():
        return
    if mode == "always":
        raise RuntimeError(f"Discovery cache missing: {merged_json}")
    cmd = [sys.executable, str(DISCOVERY_SCRIPT), "--date", date, "--window-hours", "24"]
    if mode == "never":
        cmd.append("--refresh")
    run_stage(stage_records, "prepare_discovery", cmd)


def resolve_report_inputs(date: str, stage_records: list[dict[str, Any]]) -> tuple[Path, Path]:
    report = resolve_tech_daily_report_path(date)
    social_urls = resolve_tech_daily_social_urls_path(date)
    if report and social_urls:
        return report, social_urls

    discovery_json = tech_daily_discovery_dir(date) / "merged-candidates.json"
    if not discovery_json.exists():
        discovery_json = tech_daily_discovery_dir(date) / "rsshub-candidates.json"
    if not discovery_json.exists():
        raise RuntimeError(f"No report inputs and no discovery cache for {date}")

    report_out = tech_daily_report_path(date)
    social_out = tech_daily_social_urls_path(date)
    run_stage(
        stage_records,
        "build_report_from_collection",
        [
            sys.executable,
            str(REPORT_BUILDER_SCRIPT),
            "--date",
            date,
            "--discovery-json",
            str(discovery_json),
            "--report-out",
            str(report_out),
            "--social-urls-out",
            str(social_out),
        ],
    )
    return report_out, social_out


def existing_story_manifest(date: str, report: Path) -> Path | None:
    candidates = [
        report.with_name(f"{report.stem}.image-manifest.json"),
        tech_daily_source_pack_dir(date) / "story-assets.json",
        tech_daily_reference_pack_dir(date) / "story-assets.json",
    ]
    return next((path for path in candidates if path.exists()), None)


def require_cover(date: str) -> Path:
    cover = tech_daily_final_cover_path(date)
    if cover.exists():
        return cover
    raise RuntimeError(
        "Missing final/cover.png. Generate the cover with the imagegen skill prompt from "
        f"{tech_daily_cover_lab_dir(date) / 'imagegen-cover-brief.md'} and save it to {cover}, then rerun."
    )


def main() -> int:
    args = parse_args()
    date = args.date
    stage_records: list[dict[str, Any]] = []
    current_stage = "start"
    payload: dict[str, Any] = {"date": date, "started_at": utc_now_iso(), "stages": stage_records}
    qa_dir = ensure_dir(tech_daily_qa_dir(date))

    try:
        current_stage = "prepare_discovery"
        maybe_prepare_discovery(date, args.reuse_discovery, stage_records)

        if args.overwrite:
            clean_outputs(date)

        current_stage = "resolve_inputs"
        report_input, social_input = resolve_report_inputs(date, stage_records)

        report_md = copy_if_needed(report_input, tech_daily_report_path(date))
        social_urls = copy_if_needed(social_input, tech_daily_social_urls_path(date))
        source_pack_dir = tech_daily_source_pack_dir(date)
        reference_pack_dir = tech_daily_reference_pack_dir(date)
        content_manifest = tech_daily_content_manifest_path(date)

        current_stage = "text_compile"
        run_stage(
            stage_records,
            "text_compile",
            [
                sys.executable,
                str(TEXT_COMPILE_SCRIPT),
                "--report",
                str(report_md),
                "--date",
                date,
                "--report-json-out",
                str(tech_daily_report_json_path(date)),
                "--editorial-brief-out",
                str(tech_daily_editorial_brief_path(date)),
                "--content-manifest-out",
                str(content_manifest),
                "--reference-pack-out",
                str(reference_pack_dir),
                "--source-pack",
                str(source_pack_dir),
            ],
        )

        cover_copy = tech_daily_cover_copy_path(date)
        current_stage = "generate_cover_copy"
        run_stage(
            stage_records,
            "generate_cover_copy",
            [
                sys.executable,
                str(COVER_COPY_SCRIPT),
                "--report",
                str(report_md),
                "--content-manifest",
                str(content_manifest),
                "--out",
                str(cover_copy),
            ],
        )

        title_pack = tech_daily_title_pack_path(date)
        current_stage = "generate_title_pack"
        run_stage(
            stage_records,
            "generate_title_pack",
            [
                sys.executable,
                str(TITLE_PACK_SCRIPT),
                "--report",
                str(report_md),
                "--date",
                date,
                "--cover-copy",
                str(cover_copy),
                "--content-manifest",
                str(content_manifest),
                "--out",
                str(title_pack),
            ],
        )
        title_pack_payload = load_json(title_pack)
        final_video = tech_daily_final_video_path(date, title_pack_payload)
        final_wechat_docx = tech_daily_final_wechat_docx_path(date, title_pack_payload)

        story_manifest = existing_story_manifest(date, report_md)
        cover_lab = ensure_dir(tech_daily_cover_lab_dir(date))
        current_stage = "prepare_cover_brief"
        cover_brief_cmd = [
            sys.executable,
            str(IMAGEGEN_COVER_BRIEF_SCRIPT),
            "--date",
            date,
            "--report",
            str(report_md),
            "--cover-copy",
            str(cover_copy),
            "--title-pack",
            str(title_pack),
            "--final-cover",
            str(tech_daily_final_cover_path(date)),
            "--out-json",
            str(cover_lab / "imagegen-cover-brief.json"),
            "--out-md",
            str(cover_lab / "imagegen-cover-brief.md"),
        ]
        if story_manifest:
            cover_brief_cmd.extend(["--story-manifest", str(story_manifest)])
        run_stage(stage_records, "prepare_cover_brief", cover_brief_cmd)
        cover_image = require_cover(date)

        current_stage = "bgm_analysis"
        run_stage(
            stage_records,
            "bgm_analysis",
            [sys.executable, str(BGM_ANALYSIS_SCRIPT), "--bgm", str(DEFAULT_BGM_PATH), "--out", str(tech_daily_bgm_analysis_path(date))],
        )

        video_dir = tech_daily_video_build_dir(date)
        current_stage = "video_build"
        video_cmd = [
            sys.executable,
            str(VIDEO_BUILD_SCRIPT),
            "--report",
            str(report_md),
            "--out-dir",
            str(video_dir),
            "--title-pack",
            str(title_pack),
            "--content-manifest",
            str(content_manifest),
            "--bgm-analysis",
            str(tech_daily_bgm_analysis_path(date)),
            "--require-fish",
        ]
        if story_manifest:
            video_cmd.extend(["--manifest", str(story_manifest)])
        run_stage(stage_records, "video_build", video_cmd)
        final_dir = ensure_dir(tech_daily_final_dir(date))
        for stale_video in final_dir.glob("*.mp4"):
            stale_video.unlink(missing_ok=True)
        move_if_needed(video_dir / "video.mp4", final_video)
        copy_if_needed(video_dir / "video.srt", tech_daily_final_srt_path(date))
        build_summary = load_json(tech_daily_build_summary_path(date))
        if build_summary:
            build_summary["video"] = str(final_video)
            build_summary["final_video"] = str(final_video)
            write_json(tech_daily_build_summary_path(date), build_summary)

        current_stage = "render_wechat"
        wechat_payload = run_stage(
            stage_records,
            "render_wechat",
            [
                sys.executable,
                str(WECHAT_SCRIPT),
                "--report",
                str(report_md),
                "--out-dir",
                str(final_dir),
                "--cover-image",
                str(cover_image),
                "--title-pack",
                str(title_pack),
                "--content-manifest",
                str(content_manifest),
                "--summary-out",
                str(tech_daily_qa_dir(date) / "render-wechat-summary.json"),
            ],
        )
        current_stage = "render_bilibili"
        bilibili_payload = run_stage(
            stage_records,
            "render_bilibili",
            [
                sys.executable,
                str(BILIBILI_SCRIPT),
                "--report",
                str(report_md),
                "--out-dir",
                str(final_dir),
                "--video-file",
                str(final_video),
                "--video-summary",
                str(tech_daily_build_summary_path(date)),
                "--cover-image",
                str(cover_image),
                "--title-pack",
                str(title_pack),
                "--content-manifest",
                str(content_manifest),
                "--require-video",
                "--summary-out",
                str(tech_daily_qa_dir(date) / "render-bilibili-summary.json"),
            ],
        )

        required = [
            final_video,
            tech_daily_final_srt_path(date),
            tech_daily_final_cover_path(date),
            final_wechat_docx,
            final_dir / "bilibili.txt",
            final_dir / "bilibili-upload.json",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise RuntimeError(f"Missing required artifacts: {missing}")

        payload.update(
            {
                "result": "success",
                "process_dir": str(tech_daily_process_dir(date)),
                "final_dir": str(tech_daily_final_dir(date)),
                "report": str(report_md),
                "social_urls": str(social_urls),
                "content_manifest": str(content_manifest),
                "cover_brief": str(cover_lab / "imagegen-cover-brief.md"),
                "cover_image": str(cover_image),
                "cover_result": str(tech_daily_final_cover_result_path(date)),
                "video": str(final_video),
                "srt": str(tech_daily_final_srt_path(date)),
                "wechat_docx": str(final_wechat_docx),
                "bilibili_text": str(final_dir / "bilibili.txt"),
                "bilibili_upload_manifest": str(final_dir / "bilibili-upload.json"),
                "final_payload": {"wechat": wechat_payload, "bilibili": bilibili_payload},
            }
        )
        write_json(qa_dir / "pipeline-summary.json", payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001
        payload.update(
            {
                "result": "failed",
                "failed_stage": current_stage,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(limit=20),
            }
        )
        write_json(qa_dir / "pipeline-summary.json", payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
