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

import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from PIL import Image, ImageOps, UnidentifiedImageError

from ai_daily_paths import extract_tech_daily_date, tech_daily_process_dir
from source_utils import canonicalize_url
from tech_daily_parser import TechDailyItem


STABLE_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
PACK_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}


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


def _item_domain(item: TechDailyItem) -> str:
    url = canonicalize_url(item.source_url)
    if not url:
        return "来源待补"
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "来源待补"


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
    process_dir = tech_daily_process_dir(date) if date else report.parent

    report_manifest = report.with_name(f"{report.stem}.image-manifest.json")
    reference_index = process_dir / "reference-pack" / "index.json"
    source_index = process_dir / "source-pack" / "index.json"

    resolved: list[ResolvedWechatMedia] = []
    for item in items:
        report_candidate = _load_report_image_candidate(report_manifest, item)
        if report_candidate and report_candidate.get("skip"):
            continue
        candidate = (
            report_candidate
            or _load_pack_candidate(reference_index, item, "reference-pack")
            or _load_pack_candidate(source_index, item, "source-pack")
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
