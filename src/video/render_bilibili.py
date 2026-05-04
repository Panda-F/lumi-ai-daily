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

from cover_resolver import resolve_daily_cover
from llm_content import load_content_manifest
from tech_daily_parser import parse_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render Bilibili copy and upload manifest for a Lumi AI Daily video.")
    parser.add_argument("--report", required=True, help="Path to the tech daily Markdown report")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument("--video-file", help="Video file path")
    parser.add_argument("--video-summary", help="Optional build-summary.json from the video build")
    parser.add_argument("--cover-image", help="Optional resolved daily cover image path")
    parser.add_argument("--cover-result", help="Optional cover result JSON path")
    parser.add_argument("--title-pack", help="Optional title-pack.json")
    parser.add_argument("--content-manifest", help="Optional content-manifest.json path")
    parser.add_argument("--require-video", action="store_true", help="Fail unless a real video file is available")
    parser.add_argument("--summary-out", help="Optional process summary JSON path")
    return parser.parse_args()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_json(path: str | None) -> dict | None:
    if not path:
        return None
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        return None
    raw = json.loads(resolved.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else None


def resolve_existing_file(path: str | None, *, label: str, required: bool = False) -> str | None:
    if not path:
        if required:
            raise RuntimeError(f"Missing required {label}.")
        return None
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        if required:
            raise RuntimeError(f"Required {label} does not exist: {resolved}")
        return None
    return str(resolved)


def render_bilibili_text(bundle: dict, video_file: str | None, title_pack: dict | None = None) -> str:
    bilibili = bundle.get("bilibili") if isinstance(bundle.get("bilibili"), dict) else {}
    title = str((title_pack or {}).get("bilibili_title") or bilibili.get("title") or "").strip()
    description = str(bilibili.get("description") or "").strip()
    dynamic = str(bilibili.get("dynamic") or "").strip()
    tags = [str(tag).strip() for tag in bilibili.get("tags") or [] if str(tag).strip()]
    if not title or not description:
        raise RuntimeError("Content manifest missing bilibili.title or bilibili.description")

    parts = [title, description]
    if dynamic:
        parts.append(f"动态文案：{dynamic}")
    if tags:
        parts.append("推荐标签：" + "、".join(tags))
    parts.append(f"视频文件：{video_file}" if video_file else "视频文件：本次 bundle 未附带")
    return "\n\n".join(parts) + "\n"


def render_bilibili_upload_manifest(
    bundle: dict,
    video_file: str | None,
    cover_file: str | None,
    title_pack: dict | None = None,
) -> dict:
    bilibili = bundle.get("bilibili") if isinstance(bundle.get("bilibili"), dict) else {}
    return {
        "title": str((title_pack or {}).get("bilibili_title") or bilibili.get("title") or "").strip(),
        "description": str(bilibili.get("description") or "").strip(),
        "dynamic": str(bilibili.get("dynamic") or "").strip(),
        "tags": [str(tag).strip() for tag in bilibili.get("tags") or [] if str(tag).strip()],
        "video_file": video_file,
        "cover_file": cover_file,
    }


def main() -> int:
    args = parse_args()
    report = parse_report(args.report)
    content_manifest_path = args.content_manifest
    editorial_bundle = load_content_manifest(content_manifest_path, report_path=report.path, date=report.date)
    out_dir = ensure_dir(Path(args.out_dir).expanduser().resolve())
    title_pack = load_json(args.title_pack)
    video_summary = load_json(args.video_summary)

    video_file = args.video_file
    if not video_file and video_summary and video_summary.get("video"):
        video_file = str(Path(str(video_summary["video"])).expanduser().resolve())
    video_file = resolve_existing_file(video_file, label="video file", required=args.require_video)

    resolved_cover = resolve_daily_cover(
        date=report.date,
        explicit_cover_image=args.cover_image,
        explicit_cover_result=args.cover_result,
    )
    daily_cover_file = resolve_existing_file(str(resolved_cover.get("path") or ""), label="daily cover")

    bilibili_txt = out_dir / "bilibili.txt"
    bilibili_upload_json = out_dir / "bilibili-upload.json"
    bilibili_txt.write_text(render_bilibili_text(editorial_bundle, video_file, title_pack), encoding="utf-8")
    upload_manifest = render_bilibili_upload_manifest(editorial_bundle, video_file, daily_cover_file, title_pack)
    bilibili_upload_json.write_text(json.dumps(upload_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "result": "success",
        "title": upload_manifest.get("title"),
        "report": report.to_dict(),
        "video_file": video_file,
        "video_summary": str(Path(args.video_summary).expanduser().resolve()) if args.video_summary else None,
        "title_pack": str(Path(args.title_pack).expanduser().resolve()) if args.title_pack else None,
        "content_manifest": str(Path(content_manifest_path).expanduser().resolve()) if content_manifest_path else None,
        "daily_cover_image": daily_cover_file,
        "daily_cover_source": resolved_cover.get("source"),
        "daily_cover_result": resolved_cover.get("result_json"),
        "out_dir": str(out_dir),
        "files": {"bilibili": str(bilibili_txt), "bilibili_upload_manifest": str(bilibili_upload_json)},
        "bilibili_text": str(bilibili_txt),
        "bilibili_upload_manifest": str(bilibili_upload_json),
    }
    if args.summary_out:
        summary_out = Path(args.summary_out).expanduser().resolve()
        summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
