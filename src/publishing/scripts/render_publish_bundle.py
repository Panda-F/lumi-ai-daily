#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parents[3]
SHARED_SCRIPTS_DIR = WORKSPACE_DIR / "scripts"
if str(SHARED_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS_DIR))

from tech_daily_candidate_review import canonicalize_url
from tech_daily_cover_resolver import resolve_daily_cover
from tech_daily_media_resolver import ResolvedWechatMedia, resolve_wechat_media
from tech_daily_parser import TechDailyItem, parse_report
from tech_daily_publication_contract import sanitize_display_title
from ai_daily_llm_content import load_content_manifest
from wechat_docx_builder import build_wechat_docx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render cross-platform publish drafts from a tech daily report.")
    parser.add_argument("--report", required=True, help="Path to the tech daily Markdown report")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument("--video-file", help="Optional video file path")
    parser.add_argument("--video-summary", help="Optional build-summary.json from the video skill")
    parser.add_argument("--cover-image", help="Optional resolved daily cover image path")
    parser.add_argument("--cover-result", help="Optional plus-media cover result JSON path")
    parser.add_argument("--title-pack", help="Optional title-pack.json used as the single source of truth for outward-facing titles")
    parser.add_argument("--content-manifest", help="Optional content-manifest.json path")
    parser.add_argument("--editorial-bundle", help="Deprecated alias for --content-manifest")
    parser.add_argument("--max-items", type=int, default=6, help="Max items to include")
    parser.add_argument("--require-video", action="store_true", help="Fail unless a real video file is available.")
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


@dataclass
class WechatReference:
    index: int
    label: str
    url: str


@dataclass
class WechatSection:
    index: int
    title: str
    body: str = ""
    facts: str = ""
    analysis: str = ""
    image_path: str = ""
    image_caption: str = ""
    quote: str = ""
    source_label: str = ""
    source_url: str = ""
    highlight_terms: list[str] = field(default_factory=list)


@dataclass
class WechatArticle:
    title: str
    cover_image: str = ""
    intro: str = ""
    sections: list[WechatSection] = field(default_factory=list)
    outro_heading: str = ""
    outro: str = ""
    references: list[WechatReference] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def publish_strategy(video_file: str | None) -> dict:
    return {
        "updated_at": "2026-04-17",
        "platforms": {
            "telegram": {
                "mode": "bot_api_video_bundle",
                "login_required": False,
                "credential_type": "Telegram bot token or OpenClaw telegram channel config",
                "needs_user_setup": [
                    "Configure the Telegram bot token or OpenClaw telegram channel",
                    "Know the target chat id",
                ],
                "notes": "Send the resolved daily cover first, then upload the formal MP4 with Telegram sendVideo, then send the Telegram summary text last.",
            },
            "wechat_official_account": {
                "mode": "docx_import",
                "login_required": True,
                "credential_type": "WeChat Official Account web console login",
                "needs_user_setup": [
                    "Log into the WeChat Official Account backend",
                    "Use the article import flow that accepts docx files",
                    "Review layout and references before publishing",
                ],
                "notes": "This workspace generates wechat.docx for manual import. API draft publishing is not part of the default WeChat path.",
            },
            "bilibili": {
                "mode": "api_if_open_platform_else_browser",
                "login_required": True,
                "credential_type": "Bilibili Open Platform OAuth if qualified, else creator-web login",
                "needs_user_setup": [
                    "Open Platform onboarding",
                    "Create app",
                    "Authorize target account",
                ],
                "notes": "API-first only if the account can complete official Open Platform onboarding; otherwise browser posting is the fallback.",
            },
        },
        "video_file": video_file,
    }


def strip_emoji(text: str) -> str:
    cleaned = sanitize_display_title(text)
    cleaned = "".join(char for char in cleaned if unicodedata.category(char) != "Mn")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.strip("-|｜ ")


def ensure_full_stop(text: str) -> str:
    value = text.strip()
    if not value:
        return ""
    if value.endswith(("。", "！", "？", "；")):
        return value
    return f"{value}。"


def reset_generated_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def format_timestamp(seconds: float) -> str:
    rounded = int(seconds)
    minutes, secs = divmod(rounded, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def load_video_summary(path: str | None) -> dict | None:
    return load_json(path)


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


def resolved_video_cover(video_summary: dict | None) -> str | None:
    if not video_summary:
        return None
    return str(video_summary.get("video_cover_image") or video_summary.get("cover_image") or "") or None


def chapter_offsets(items: list[TechDailyItem], video_summary: dict | None) -> list[str]:
    if not video_summary:
        return ["00:00"] * len(items)

    offsets: list[str] = []
    cursor = 0.0
    segments = video_summary.get("segments", [])
    for segment in segments:
        if segment.get("kind") == "intro":
            cursor += float(segment.get("duration", 0.0))
            continue
        offsets.append(format_timestamp(cursor))
        cursor += float(segment.get("duration", 0.0))
    if len(offsets) < len(items):
        offsets.extend(["00:00"] * (len(items) - len(offsets)))
    return offsets[: len(items)]


def render_telegram(bundle: dict) -> str:
    telegram = bundle.get("telegram") if isinstance(bundle.get("telegram"), dict) else {}
    text = str(telegram.get("text") or "").strip()
    if not text:
        raise RuntimeError("Content manifest missing telegram.text")
    return text + "\n"


def render_telegram_send_manifest(
    items: list[TechDailyItem],
    video_file: str | None,
    daily_cover_file: str | None,
    video_cover_file: str | None,
    captions_file: str | None,
    video_summary_path: str | None,
    telegram_text_file: Path,
) -> dict:
    hottest_link = next((item.source_url for item in items if item.source_url), None)
    return {
        "delivery_order": ["cover_image", "video", "text"],
        "cover_image_file": daily_cover_file,
        "video_file": video_file,
        "text_file": str(telegram_text_file),
        "captions_file": captions_file,
        "video_cover_image_file": video_cover_file,
        "cover_method": "sendPhoto",
        "video_method": "sendVideo",
        "text_method": "sendMessage",
        "video_delivery_mode": "video",
        "summary_file": str(Path(video_summary_path).expanduser().resolve()) if video_summary_path else None,
        "hot_link": hottest_link,
        "notes": [
            "Send the cover image as a media message first when available.",
            "Send the daily video from the formal video-build output next with Telegram sendVideo.",
            "Send the Telegram text last so the thread keeps the hottest link preview.",
        ],
    }


def build_wechat_article(
    items: list[TechDailyItem],
    cover_file: str | None,
    resolved_media: list[ResolvedWechatMedia],
    title_pack: dict | None,
    bundle: dict,
) -> WechatArticle:
    wechat = bundle.get("wechat") if isinstance(bundle.get("wechat"), dict) else {}
    bundle_sections = wechat.get("sections") if isinstance(wechat.get("sections"), list) else []
    bundle_refs = wechat.get("references") if isinstance(wechat.get("references"), list) else []
    if not bundle_sections:
        raise RuntimeError("Content manifest missing wechat.sections")
    media_by_index = {entry.item_index: entry for entry in resolved_media}
    source_by_index = {item.index: item.source_url for item in items}
    sections: list[WechatSection] = []
    for raw_section in bundle_sections:
        if not isinstance(raw_section, dict):
            continue
        index = int(raw_section.get("index") or 0)
        if index not in source_by_index:
            continue
        media = media_by_index.get(index)
        caption = str(raw_section.get("image_caption") or (media.caption if media else "") or "").strip()
        body = str(raw_section.get("body") or "").strip()
        if not body:
            body = "\n\n".join(
                part
                for part in [
                    str(raw_section.get("facts") or "").strip(),
                    str(raw_section.get("analysis") or "").strip(),
                ]
                if part
            )
        sections.append(
            WechatSection(
                index=index,
                title=str(raw_section.get("title") or "").strip(),
                body=body,
                facts="",
                analysis="",
                image_path=media.staged_path if media else "",
                image_caption=caption,
                source_label="",
                source_url=str(raw_section.get("source_url") or source_by_index[index]),
                highlight_terms=[str(term) for term in raw_section.get("highlight_terms") or []],
            )
        )
    references: list[WechatReference] = []
    seen_references: set[str] = set()
    for raw_ref in bundle_refs:
        if not isinstance(raw_ref, dict):
            continue
        url = str(raw_ref.get("url") or "").strip()
        canonical = canonicalize_url(url)
        if not url or canonical in seen_references:
            continue
        seen_references.add(canonical)
        references.append(
            WechatReference(
                index=int(raw_ref.get("index") or 0),
                label=str(raw_ref.get("title") or url),
                url=url,
            )
        )
    return WechatArticle(
        title=str(wechat.get("title") or (title_pack or {}).get("wechat_title") or "").strip(),
        cover_image=cover_file or "",
        intro=str(wechat.get("intro") or "").strip(),
        outro_heading=str(wechat.get("outro_heading") or "").strip(),
        outro=str(wechat.get("outro") or "").strip(),
        sections=sections,
        references=references,
    )


def render_bilibili(
    bundle: dict,
    video_file: str | None,
    title_pack: dict | None = None,
) -> str:
    bilibili = bundle.get("bilibili") if isinstance(bundle.get("bilibili"), dict) else {}
    title = str((title_pack or {}).get("bilibili_title") or bilibili.get("title") or "").strip()
    description = str(bilibili.get("description") or "").strip()
    dynamic = str(bilibili.get("dynamic") or "").strip()
    tags = [str(tag).strip() for tag in bilibili.get("tags") or [] if str(tag).strip()]
    if not title or not description:
        raise RuntimeError("Content manifest missing bilibili.title or bilibili.description")
    tags_text = "推荐标签：" + "、".join(tags) if tags else ""
    asset = f"视频文件：{video_file}" if video_file else "视频文件：本次 bundle 未附带"
    parts = [title, description]
    if dynamic:
        parts.append(f"动态文案：{dynamic}")
    if tags_text:
        parts.append(tags_text)
    parts.append(asset)
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
    items = report.items[: args.max_items]
    content_manifest_path = args.content_manifest or args.editorial_bundle
    editorial_bundle = load_content_manifest(content_manifest_path, report_path=report.path, date=report.date)
    out_dir = ensure_dir(Path(args.out_dir).expanduser().resolve())
    video_summary = load_video_summary(args.video_summary)
    title_pack = load_json(args.title_pack)
    video_file = args.video_file
    if not video_file and video_summary and video_summary.get("video"):
        video_file = str(Path(video_summary["video"]).expanduser().resolve())
    video_file = resolve_existing_file(video_file, label="video file", required=args.require_video)
    video_cover_file = resolved_video_cover(video_summary)
    captions_file = str(video_summary.get("srt")) if video_summary and video_summary.get("srt") else None
    resolved_cover = resolve_daily_cover(
        date=report.date,
        explicit_cover_image=args.cover_image,
        explicit_cover_result=args.cover_result,
        fallback_video_cover=video_cover_file,
    )
    daily_cover_file = resolve_existing_file(str(resolved_cover.get("path") or ""), label="daily cover")
    shutil.rmtree(out_dir / "assets", ignore_errors=True)
    wechat_asset_dir = reset_generated_dir(out_dir / "assets" / "wechat")
    for stale_path in (
        out_dir / "wechat.md",
        out_dir / "wechat-article.html",
        out_dir / "wechat-article.json",
        out_dir / "xiaohongshu.md",
        out_dir / "zhihu.md",
        out_dir / "x-thread.txt",
        out_dir / "x-post.json",
        out_dir / "youtube.txt",
        out_dir / "youtube-upload.json",
        out_dir / "youtube-description.txt",
        out_dir / "publish-strategy.json",
        out_dir / "summary.json",
        out_dir / "wechat.docx",
    ):
        remove_if_exists(stale_path)
    for stale_docx in out_dir.glob("*.docx"):
        remove_if_exists(stale_docx)
    for stale_video in out_dir.glob("*.mp4"):
        remove_if_exists(stale_video)

    files = {
        "telegram": out_dir / "telegram.txt",
        "wechat": out_dir / "wechat.docx",
        "bilibili": out_dir / "bilibili.txt",
    }

    files["telegram"].write_text(
        render_telegram(editorial_bundle),
        encoding="utf-8",
    )
    resolved_wechat_media = resolve_wechat_media(report.path, items, wechat_asset_dir)
    resolved_media_indexes = {entry.item_index for entry in resolved_wechat_media}
    missing_wechat_media = [item.index for item in items if item.index not in resolved_media_indexes]
    if missing_wechat_media:
        raise RuntimeError(
            "WeChat docx image requirement failed: missing item images for "
            + ", ".join(str(index) for index in missing_wechat_media)
        )
    wechat_article = build_wechat_article(
        items,
        daily_cover_file,
        resolved_wechat_media,
        title_pack,
        editorial_bundle,
    )
    build_wechat_docx(wechat_article.to_dict(), files["wechat"])
    titled_wechat_docx: Path | None = None
    if title_pack:
        raw_wechat_filename = str(title_pack.get("wechat_filename") or "").strip()
        if raw_wechat_filename:
            titled_wechat_docx = out_dir / Path(raw_wechat_filename).name
            if titled_wechat_docx != files["wechat"]:
                shutil.copy2(files["wechat"], titled_wechat_docx)
    files["bilibili"].write_text(
        render_bilibili(editorial_bundle, video_file, title_pack),
        encoding="utf-8",
    )
    bilibili_upload_manifest = render_bilibili_upload_manifest(
        editorial_bundle,
        video_file,
        daily_cover_file,
        title_pack,
    )
    bilibili_upload_path = out_dir / "bilibili-upload.json"
    bilibili_upload_path.write_text(
        json.dumps(bilibili_upload_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    telegram_send_manifest = render_telegram_send_manifest(
        items,
        video_file,
        daily_cover_file,
        video_cover_file,
        captions_file,
        args.video_summary,
        files["telegram"],
    )
    telegram_send_path = out_dir / "telegram-send.json"
    telegram_send_path.write_text(
        json.dumps(telegram_send_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    strategy = publish_strategy(video_file)
    wechat_image_count = len(resolved_wechat_media)
    shutil.rmtree(out_dir / "assets", ignore_errors=True)

    summary = {
        "result": "success",
        "title": str((title_pack or {}).get("primary_hook") or ""),
        "report": report.to_dict(),
        "video_file": video_file,
        "video_summary": str(Path(args.video_summary).expanduser().resolve()) if args.video_summary else None,
        "title_pack": str(Path(args.title_pack).expanduser().resolve()) if args.title_pack else None,
        "content_manifest": str(Path(content_manifest_path).expanduser().resolve()) if content_manifest_path else None,
        "daily_cover_image": daily_cover_file,
        "daily_cover_source": resolved_cover.get("source"),
        "daily_cover_result": resolved_cover.get("result_json"),
        "video_cover_image": str(Path(video_cover_file).expanduser().resolve()) if video_cover_file else None,
        "out_dir": str(out_dir),
        "files": {name: str(path) for name, path in files.items()},
        "wechat_docx": str(files["wechat"]),
        "wechat_docx_titled": str(titled_wechat_docx) if titled_wechat_docx else None,
        "wechat_image_count": wechat_image_count,
        "wechat_item_image_count": len(resolved_wechat_media),
        "wechat_missing_image_indexes": missing_wechat_media,
        "bilibili_upload_manifest": str(bilibili_upload_path),
        "telegram_send_manifest": str(telegram_send_path),
        "publish_strategy": strategy,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
