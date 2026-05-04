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
import shutil
from dataclasses import asdict, dataclass, field

from ai_daily_paths import title_pack_filename
from cover_resolver import resolve_daily_cover
from llm_content import load_content_manifest
from source_utils import canonicalize_url
from tech_daily_parser import TechDailyItem, parse_report
from wechat_docx import build_wechat_docx
from wechat_media import ResolvedWechatMedia, resolve_wechat_media


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render the WeChat DOCX for a Lumi AI Daily report.")
    parser.add_argument("--report", required=True, help="Path to the tech daily Markdown report")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument("--cover-image", help="Optional resolved daily cover image path")
    parser.add_argument("--cover-result", help="Optional cover result JSON path")
    parser.add_argument("--title-pack", help="Optional title-pack.json used for the final DOCX filename")
    parser.add_argument("--content-manifest", help="Optional content-manifest.json path")
    parser.add_argument("--summary-out", help="Optional process summary JSON path")
    parser.add_argument("--max-items", type=int, default=6, help="Max items to include")
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


def reset_generated_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


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
                title="",
                body=body,
                image_path=media.staged_path if media else "",
                image_caption=caption,
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
        outro_heading="",
        outro=str(wechat.get("outro") or "").strip(),
        sections=sections,
        references=references,
    )


def main() -> int:
    args = parse_args()
    report = parse_report(args.report)
    items = report.items[: args.max_items]
    content_manifest_path = args.content_manifest
    editorial_bundle = load_content_manifest(content_manifest_path, report_path=report.path, date=report.date)
    out_dir = ensure_dir(Path(args.out_dir).expanduser().resolve())
    title_pack = load_json(args.title_pack)
    resolved_cover = resolve_daily_cover(
        date=report.date,
        explicit_cover_image=args.cover_image,
        explicit_cover_result=args.cover_result,
    )
    daily_cover_file = resolve_existing_file(str(resolved_cover.get("path") or ""), label="daily cover")

    shutil.rmtree(out_dir / "assets", ignore_errors=True)
    wechat_asset_dir = reset_generated_dir(out_dir / "assets" / "wechat")
    for stale_path in (out_dir / "summary.json", out_dir / "wechat.docx"):
        remove_if_exists(stale_path)
    for stale_docx in out_dir.glob("*.docx"):
        remove_if_exists(stale_docx)

    wechat_docx = out_dir / title_pack_filename(title_pack, "wechat_filename", fallback="wechat.docx", suffix=".docx")
    resolved_wechat_media = resolve_wechat_media(report.path, items, wechat_asset_dir)
    resolved_media_indexes = {entry.item_index for entry in resolved_wechat_media}
    missing_wechat_media = [item.index for item in items if item.index not in resolved_media_indexes]
    if missing_wechat_media:
        raise RuntimeError(
            "WeChat DOCX image requirement failed: missing item images for "
            + ", ".join(str(index) for index in missing_wechat_media)
        )

    wechat_article = build_wechat_article(
        items,
        daily_cover_file,
        resolved_wechat_media,
        title_pack,
        editorial_bundle,
    )
    build_wechat_docx(wechat_article.to_dict(), wechat_docx)

    shutil.rmtree(out_dir / "assets", ignore_errors=True)
    summary = {
        "result": "success",
        "title": str((title_pack or {}).get("primary_hook") or ""),
        "report": report.to_dict(),
        "title_pack": str(Path(args.title_pack).expanduser().resolve()) if args.title_pack else None,
        "content_manifest": str(Path(content_manifest_path).expanduser().resolve()) if content_manifest_path else None,
        "daily_cover_image": daily_cover_file,
        "daily_cover_source": resolved_cover.get("source"),
        "daily_cover_result": resolved_cover.get("result_json"),
        "out_dir": str(out_dir),
        "files": {"wechat": str(wechat_docx)},
        "wechat_docx": str(wechat_docx),
        "wechat_image_count": len(resolved_wechat_media),
        "wechat_item_image_count": len(resolved_wechat_media),
        "wechat_missing_image_indexes": missing_wechat_media,
    }
    if args.summary_out:
        summary_out = Path(args.summary_out).expanduser().resolve()
        summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
