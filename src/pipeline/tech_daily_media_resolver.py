#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

from ai_daily_paths import extract_tech_daily_date, tech_daily_day_dir
from tech_daily_candidate_review import canonicalize_url
from tech_daily_parser import TechDailyItem


STABLE_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
PACK_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
FALLBACK_CARD_SIZE = (1280, 720)
FALLBACK_BG = "#0b1020"
FALLBACK_PANEL = "#111a30"
FALLBACK_ACCENT = "#ffd12f"
FALLBACK_SUBTLE = "#7aa2ff"
FALLBACK_TEXT = "#f5f7ff"
FALLBACK_MUTED = "#b8c0db"
FALLBACK_FONTS = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


@dataclass
class ResolvedWechatMedia:
    item_index: int
    item_title: str
    source: str
    matched_url: str
    original_path: str
    staged_path: str
    caption: str = ""
    selector: str = ""
    truthfulness_tier: str = "truthful"
    coverage_status: str = "pass"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _item_urls(item: TechDailyItem) -> set[str]:
    urls = {canonicalize_url(item.source_url)} if item.source_url else set()
    urls.update(canonicalize_url(ref) for ref in item.source_refs if ref)
    return {url for url in urls if url}


def _normalize_caption(raw: str, item_title: str) -> str:
    value = re.sub(r"\s+", " ", str(raw or "")).strip(" -|")
    if not value:
        return ""
    if value.casefold() == item_title.casefold():
        return ""
    if not re.search(r"[\u4e00-\u9fff]", value):
        return ""
    if re.fullmatch(r"[\w./:-]+", value):
        return ""
    return value[:96]


def _report_manifest_match(entry: dict[str, Any], item: TechDailyItem, item_urls: set[str]) -> bool:
    if str(entry.get("index") or "").isdigit() and int(entry["index"]) == item.index:
        return True
    candidate_urls = {
        canonicalize_url(str(entry.get("source_url") or "")),
        canonicalize_url(str(entry.get("matched_url") or "")),
    }
    candidate_urls = {url for url in candidate_urls if url}
    if candidate_urls and candidate_urls.intersection(item_urls):
        return True
    return str(entry.get("title") or "").strip() == item.title


def _load_report_image_candidate(manifest_path: Path, item: TechDailyItem) -> dict[str, Any] | None:
    if not manifest_path.exists():
        return None
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    item_urls = _item_urls(item)
    for entry in payload.get("items", []):
        if not isinstance(entry, dict):
            continue
        if not _report_manifest_match(entry, item, item_urls):
            continue
        if entry.get("skip_image"):
            return {"skip": True, "selector": "report-manifest-skip"}
        selected_image_raw = str(entry.get("selected_image") or "").strip()
        if not selected_image_raw:
            continue
        selected_image = Path(selected_image_raw).expanduser()
        if not selected_image.exists() or selected_image.is_dir():
            continue
        return {
            "path": selected_image.resolve(),
            "matched_url": canonicalize_url(str(entry.get("matched_url") or entry.get("source_url") or item.source_url)),
            "caption": _normalize_caption(str(entry.get("source_title") or entry.get("title") or ""), item.title),
            "selector": str(entry.get("image_source") or "report-manifest"),
        }
    return None


def _pack_candidate_paths(source: dict[str, Any], pack_root: Path) -> list[Path]:
    ordered: list[str] = []
    for raw in [source.get("hero_image_file"), *(source.get("image_files") or [])]:
        value = str(raw or "").strip()
        if value and value not in ordered:
            ordered.append(value)
    if not ordered:
        for raw in source.get("asset_files") or []:
            value = str(raw or "").strip()
            if value and Path(value).suffix.lower() in PACK_IMAGE_SUFFIXES and value not in ordered:
                ordered.append(value)
    source_dir = str(source.get("dir") or "").strip()
    candidates: list[Path] = []
    seen: set[Path] = set()
    for rel_path in ordered:
        path = (pack_root / source_dir / rel_path).resolve()
        if path.exists() and path.is_file() and path not in seen:
            candidates.append(path)
            seen.add(path)
    image_dir = (pack_root / source_dir / "images").resolve()
    if image_dir.exists() and image_dir.is_dir():
        for path in sorted(image_dir.iterdir()):
            resolved = path.resolve()
            if (
                path.is_file()
                and path.suffix.lower() in PACK_IMAGE_SUFFIXES
                and resolved not in seen
            ):
                candidates.append(resolved)
                seen.add(resolved)
    return candidates


def _load_pack_candidate(index_path: Path, item: TechDailyItem, source_name: str) -> dict[str, Any] | None:
    if not index_path.exists():
        return None
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    sources = payload.get("sources", []) if isinstance(payload, dict) else []
    item_urls = _item_urls(item)
    pack_root = index_path.parent
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_urls = {
            canonicalize_url(str(source.get("url") or "")),
            canonicalize_url(str(source.get("final_url") or "")),
        }
        source_urls = {url for url in source_urls if url}
        if not source_urls.intersection(item_urls):
            continue
        candidates = _pack_candidate_paths(source, pack_root)
        if not candidates:
            continue
        return {
            "path": candidates[0],
            "matched_url": sorted(source_urls)[0],
            "caption": _normalize_caption(str(source.get("title") or source.get("source_title") or ""), item.title),
            "selector": source_name,
        }
    return None


def _matching_pack_source(index_path: Path, item: TechDailyItem) -> tuple[dict[str, Any], Path] | None:
    if not index_path.exists():
        return None
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    sources = payload.get("sources", []) if isinstance(payload, dict) else []
    item_urls = _item_urls(item)
    pack_root = index_path.parent
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_urls = {
            canonicalize_url(str(source.get("url") or "")),
            canonicalize_url(str(source.get("final_url") or "")),
        }
        source_urls = {url for url in source_urls if url}
        if source_urls.intersection(item_urls):
            return source, pack_root
    return None


def _load_source_shot_candidate(day_dir: Path, item: TechDailyItem) -> dict[str, Any] | None:
    source_shot_dir = day_dir / "publish" / "assets" / "wechat-source-shots"
    if not source_shot_dir.exists():
        return None
    candidates = sorted(source_shot_dir.glob(f"item-{item.index:02d}*"))
    for image_path in candidates:
        if image_path.suffix.lower() not in PACK_IMAGE_SUFFIXES or not image_path.is_file():
            continue
        return {
            "path": image_path.resolve(),
            "matched_url": canonicalize_url(item.source_url),
            "caption": f"图源：{_item_domain(item)} / 来源页截图",
            "selector": "source-shot",
        }
    return None


def _plain_source_excerpt(text: str, *, max_chars: int = 420) -> str:
    value = re.sub(r"```.*?```", " ", str(text or ""), flags=re.S)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"^[#>*\-\s]+", "", value, flags=re.M)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:max_chars].rstrip(" ，。；：、") if len(value) > max_chars else value


def _source_body_text(content: str) -> str:
    value = str(content or "")
    if "## Text" in value:
        value = value.split("## Text", 1)[1]
    if "## Assets" in value:
        value = value.split("## Assets", 1)[0]
    lines: list[str] = []
    for raw in value.splitlines():
        line = raw.strip()
        if not line:
            lines.append("")
            continue
        if line.startswith("- ") and re.match(r"-\s*(URL|Final URL|Method|Status|Text Chars|Usable For Scoring|Discovery Only|Extraction Confidence|Asset Count|Asset Types|Duplicate Key|Platform ID|Content Hash|Content SimHash):", line):
            continue
        if line.lower().startswith(("subscribe", "sponsored by:", "posted ", "recent articles")):
            continue
        lines.append(raw)
    return "\n".join(lines).strip()


def _source_excerpt_material(index_path: Path, item: TechDailyItem) -> tuple[str, str, str] | None:
    match = _matching_pack_source(index_path, item)
    if not match:
        return None
    source, pack_root = match
    source_dir = pack_root / str(source.get("dir") or "")
    title = str(source.get("title") or source.get("source_title") or item.title).strip()
    url = str(source.get("final_url") or source.get("url") or item.source_url).strip()
    content = ""
    content_path = source_dir / "content.md"
    if content_path.exists():
        content = content_path.read_text(encoding="utf-8", errors="replace")
    if not content:
        content = " ".join(
            str(source.get(key) or "").strip()
            for key in ("excerpt", "summary", "text_excerpt", "note")
            if str(source.get(key) or "").strip()
        )
    excerpt = _plain_source_excerpt(f"{item.content} {item.interpretation}")
    metadata_markers = ("Final URL", "Method:", "Status:", "Text Chars", "Usable For Scoring", "Duplicate Key")
    if not excerpt or any(marker in excerpt for marker in metadata_markers):
        excerpt = _plain_source_excerpt(_source_body_text(content))
    return title, url, excerpt


def _render_source_excerpt_image(item: TechDailyItem, materials: tuple[str, str, str], stage_root: Path) -> Path:
    title, url, excerpt = materials
    stage_root.mkdir(parents=True, exist_ok=True)
    output = (stage_root / f"source-excerpt-{item.index:02d}.png").resolve()
    width, height = FALLBACK_CARD_SIZE
    canvas = Image.new("RGB", FALLBACK_CARD_SIZE, "#f8fafc")
    draw = ImageDraw.Draw(canvas)

    draw.rounded_rectangle((42, 42, width - 42, height - 42), radius=24, fill="#ffffff", outline="#d7dce5", width=2)
    domain = _item_domain(item)
    draw.text((82, 78), domain, font=_fallback_font(28), fill="#2563eb")
    draw.text((82, 120), "来源页摘录", font=_fallback_font(22), fill="#64748b")
    draw.line((82, 168, width - 82, 168), fill="#e2e8f0", width=2)

    title_font, title_lines = _fit_title_block(
        draw,
        title or item.title,
        max_width=width - 164,
        max_lines=2,
        start_size=48,
        min_size=34,
    )
    y = 202
    for line in title_lines:
        draw.text((82, y), line, font=title_font, fill="#0f172a")
        y += title_font.size + 12

    excerpt_font = _fallback_font(30)
    excerpt_lines = _wrap_text(draw, excerpt, excerpt_font, width - 164)[:6]
    y += 24
    for line in excerpt_lines:
        draw.text((82, y), line, font=excerpt_font, fill="#334155")
        y += excerpt_font.size + 14

    footer = url.replace("https://", "").replace("http://", "")
    footer_font = _fallback_font(22)
    footer_lines = _wrap_text(draw, footer, footer_font, width - 164)[:2]
    y = height - 130
    for line in footer_lines:
        draw.text((82, y), line, font=footer_font, fill="#64748b")
        y += footer_font.size + 8
    canvas.save(output)
    return output


def _load_source_excerpt_candidate(index_paths: list[Path], item: TechDailyItem, stage_root: Path) -> dict[str, Any] | None:
    for index_path in index_paths:
        materials = _source_excerpt_material(index_path, item)
        if not materials:
            continue
        image_path = _render_source_excerpt_image(item, materials, stage_root / "_source-excerpts")
        return {
            "path": image_path,
            "matched_url": canonicalize_url(item.source_url),
            "caption": f"图源：{_item_domain(item)} / 来源页摘录",
            "selector": "source-excerpt",
        }
    return None


def _truthfulness_tier(selector: str) -> str:
    value = str(selector or "").lower()
    if "slides" in value or "derived" in value:
        return "derived_truthful"
    return "truthful"


def _save_static_image(source_path: Path, target_path: Path) -> None:
    with Image.open(source_path) as image:
        frame = ImageOps.exif_transpose(image)
        if getattr(frame, "is_animated", False):
            frame.seek(0)
            frame = frame.copy()
        has_alpha = "A" in frame.getbands()
        converted = frame.convert("RGBA" if has_alpha else "RGB")
        converted.save(target_path)


def _fallback_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    del bold
    for candidate in FALLBACK_FONTS:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        probe = f"{current}{char}"
        if current and draw.textbbox((0, 0), probe, font=font)[2] > max_width:
            lines.append(current.rstrip())
            current = char.lstrip()
        else:
            current = probe
    if current.strip():
        lines.append(current.rstrip())
    return lines or [text]


def _fit_title_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    max_width: int,
    max_lines: int,
    start_size: int,
    min_size: int,
) -> tuple[ImageFont.ImageFont, list[str]]:
    for size in range(start_size, min_size - 1, -4):
        font = _fallback_font(size)
        lines = _wrap_text(draw, text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines
    font = _fallback_font(min_size)
    lines = _wrap_text(draw, text, font, max_width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        tail = lines[-1].rstrip()
        if len(tail) > 1:
            tail = tail[:-1].rstrip(" ，。；：、")
        lines[-1] = tail
    return font, lines


def _item_kind_label(item: TechDailyItem) -> str:
    if item.item_kind == "research":
        return "学术热点"
    return "科技热点"


def _item_domain(item: TechDailyItem) -> str:
    url = canonicalize_url(item.source_url)
    if not url:
        return "来源待补"
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "来源待补"


def _item_snippet(item: TechDailyItem) -> str:
    raw = re.sub(r"\s+", " ", f"{item.content} {item.interpretation}").strip()
    if len(raw) <= 54:
        return raw
    return raw[:54].rstrip(" ，。；：、")


def _render_fallback_card(item: TechDailyItem, stage_root: Path) -> Path:
    stage_root.mkdir(parents=True, exist_ok=True)
    output = (stage_root / f"item-{item.index:02d}.png").resolve()

    canvas = Image.new("RGB", FALLBACK_CARD_SIZE, FALLBACK_BG)
    draw = ImageDraw.Draw(canvas)
    width, height = FALLBACK_CARD_SIZE
    draw.rounded_rectangle((28, 28, width - 28, height - 28), radius=32, outline="#223054", width=3)
    draw.rounded_rectangle((58, 66, 250, 126), radius=18, fill=FALLBACK_PANEL, outline=FALLBACK_SUBTLE, width=2)
    draw.text((82, 82), _item_kind_label(item), font=_fallback_font(28), fill=FALLBACK_ACCENT)
    draw.text((64, 158), f"第 {item.index} 条", font=_fallback_font(24), fill=FALLBACK_SUBTLE)
    draw.text((64, 194), _item_domain(item), font=_fallback_font(22), fill=FALLBACK_MUTED)

    title_font, title_lines = _fit_title_block(
        draw,
        re.sub(r"^[^\w\u4e00-\u9fff]+", "", item.title).strip(),
        max_width=width - 128,
        max_lines=3,
        start_size=74,
        min_size=44,
    )
    y = 276
    for line in title_lines:
        draw.text((64, y), line, font=title_font, fill=FALLBACK_TEXT)
        y += title_font.size + 14

    snippet = _item_snippet(item)
    if snippet:
        snippet_font = _fallback_font(28)
        snippet_lines = _wrap_text(draw, snippet, snippet_font, width - 140)[:2]
        y += 18
        for line in snippet_lines:
            draw.text((64, y), line, font=snippet_font, fill=FALLBACK_MUTED)
            y += snippet_font.size + 10

    draw.rounded_rectangle((64, height - 118, width - 64, height - 66), radius=20, fill="#0f1730")
    draw.text((88, height - 103), "自动补图卡片", font=_fallback_font(24), fill=FALLBACK_SUBTLE)
    draw.text((width - 320, height - 103), "WeChat image fallback", font=_fallback_font(24), fill=FALLBACK_MUTED)
    canvas.save(output)
    return output


def stage_wechat_image(source_path: str | Path, stage_dir: str | Path, stem: str) -> Path:
    source = Path(source_path).expanduser().resolve()
    target_root = Path(stage_dir).expanduser().resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    if source.suffix.lower() in STABLE_IMAGE_SUFFIXES:
        target = target_root / f"{stem}{source.suffix.lower()}"
        shutil.copy2(source, target)
        return target

    target = target_root / f"{stem}.png"
    try:
        _save_static_image(source, target)
    except UnidentifiedImageError:
        shutil.copy2(source, target_root / f"{stem}{source.suffix.lower()}")
        return target_root / f"{stem}{source.suffix.lower()}"
    return target


def resolve_wechat_media(
    report_path: str | Path,
    items: Iterable[TechDailyItem],
    stage_dir: str | Path,
) -> list[ResolvedWechatMedia]:
    report = Path(report_path).expanduser().resolve()
    stage_root = Path(stage_dir).expanduser().resolve()
    date = extract_tech_daily_date(report)
    day_dir = tech_daily_day_dir(date) if date else report.parent

    report_manifest = report.with_name(f"{report.stem}.image-manifest.json")
    reference_index = day_dir / "reference-pack" / "index.json"
    sources_index = day_dir / "sources" / "index.json"
    source_index = day_dir / "source-pack" / "index.json"

    resolved: list[ResolvedWechatMedia] = []
    for item in items:
        report_candidate = _load_report_image_candidate(report_manifest, item)
        if report_candidate and report_candidate.get("skip"):
            continue
        candidate = (
            report_candidate
            or _load_pack_candidate(reference_index, item, "reference-pack")
            or _load_pack_candidate(sources_index, item, "sources")
            or _load_pack_candidate(source_index, item, "source-pack")
            or _load_source_shot_candidate(day_dir, item)
            or _load_source_excerpt_candidate([reference_index, sources_index, source_index], item, stage_root)
        )
        if not candidate:
            continue
        raw_path = str(candidate.get("path") or "").strip()
        source_path = Path(raw_path).expanduser().resolve() if raw_path else None
        if not source_path or not source_path.exists() or source_path.is_dir():
            continue
        staged_path = stage_wechat_image(source_path, stage_root, f"item-{item.index:02d}")
        selector = str(candidate.get("selector") or "")
        resolved.append(
            ResolvedWechatMedia(
                item_index=item.index,
                item_title=item.title,
                source=selector,
                matched_url=str(candidate.get("matched_url") or ""),
                original_path=str(source_path),
                staged_path=str(staged_path),
                caption=str(candidate.get("caption") or ""),
                selector=selector,
                truthfulness_tier=_truthfulness_tier(selector),
                coverage_status="pass",
            )
        )
    return resolved
