#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tech_daily_candidate_review import canonicalize_url
from tech_daily_parser import clean_markdown_text, parse_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render an illustrated markdown variant of the tech-daily report.")
    parser.add_argument("--report", required=True, help="Path to the formal markdown report.")
    parser.add_argument("--out", help="Optional illustrated markdown output path.")
    parser.add_argument("--manifest-out", help="Optional image manifest output path.")
    parser.add_argument("--reference-pack", help="Optional reference-pack directory.")
    parser.add_argument("--source-pack", help="Optional source-pack directory.")
    parser.add_argument("--legacy-manifest", help="Optional preexisting image manifest used as fallback.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    ordered: list[Path] = []
    for path in paths:
        resolved = str(path.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(path.resolve())
    return ordered


def resolve_existing_paths(base_dir: Path, source_dir: str, rel_paths: list[str]) -> list[Path]:
    resolved: list[Path] = []
    for rel_path in rel_paths:
        if not rel_path:
            continue
        candidate = (base_dir / source_dir / rel_path).resolve()
        if candidate.exists() and candidate.is_file():
            resolved.append(candidate)
    return unique_paths(resolved)


def load_source_images_json(pack_dir: Path, source_dir: str) -> list[dict[str, Any]]:
    path = pack_dir / source_dir / "images.json"
    if not path.exists():
        return []
    try:
        payload = load_json(path)
    except json.JSONDecodeError:
        return []
    images = payload.get("images")
    return [entry for entry in images if isinstance(entry, dict)] if isinstance(images, list) else []


def image_evidence_entries(pack_dir: Path, source_dir: str, source: dict[str, Any], image_paths: list[Path]) -> list[dict[str, Any]]:
    by_file = {path.name: str(path) for path in image_paths}
    entries: list[dict[str, Any]] = []
    for raw in load_source_images_json(pack_dir, source_dir):
        rel_file = str(raw.get("file") or "").strip()
        resolved = (pack_dir / source_dir / rel_file).resolve() if rel_file else None
        file_path = str(resolved) if resolved and resolved.exists() else by_file.get(Path(rel_file).name, "")
        entries.append(
            {
                "url": str(raw.get("url") or "").strip(),
                "file": file_path,
                "source": str(raw.get("source") or raw.get("label") or raw.get("class_name") or "source-image").strip(),
                "alt": str(raw.get("alt") or "").strip(),
                "width": raw.get("width") or "",
                "height": raw.get("height") or "",
            }
        )
    if entries:
        return entries
    image_urls = [str(value).strip() for value in (source.get("image_urls") or []) if str(value).strip()]
    for index, path in enumerate(image_paths):
        entries.append(
            {
                "url": image_urls[index] if index < len(image_urls) else "",
                "file": str(path),
                "source": "source-pack",
                "alt": "",
                "width": "",
                "height": "",
            }
        )
    return entries


def load_pack_images(pack_dir: Path | None, label: str) -> dict[str, dict[str, Any]]:
    if not pack_dir:
        return {}
    index_path = pack_dir / "index.json"
    if not index_path.exists():
        return {}
    payload = load_json(index_path)
    entries: dict[str, dict[str, Any]] = {}
    for source in payload.get("sources", []):
        if not isinstance(source, dict):
            continue
        source_dir = str(source.get("dir") or "").strip()
        if not source_dir:
            continue
        raw_paths = [
            str(source.get("hero_image_file") or "").strip(),
            *[str(path).strip() for path in source.get("image_files", []) if str(path).strip()],
        ]
        image_paths = resolve_existing_paths(pack_dir, source_dir, raw_paths)
        if not image_paths:
            continue
        evidence = image_evidence_entries(pack_dir, source_dir, source, image_paths)
        canonical_urls = []
        for raw_url in [source.get("url"), source.get("final_url")]:
            if not raw_url:
                continue
            canonical = canonicalize_url(str(raw_url))
            if canonical and canonical not in canonical_urls:
                canonical_urls.append(canonical)
        if not canonical_urls:
            continue
        entry = {
            "image_path": str(image_paths[0]),
            "image_candidates": [str(path) for path in image_paths],
            "image_source": label,
            "pack_dir": str(pack_dir.resolve()),
            "source_dir": source_dir,
            "source_kind": str(source.get("kind") or ""),
            "source_title": str(source.get("title") or ""),
            "image_evidence": evidence,
            "matched_urls": canonical_urls,
        }
        for canonical_url in canonical_urls:
            entries.setdefault(canonical_url, entry)
    return entries


def load_fallback_manifest(manifest_path: Path | None) -> dict[str, list[str]]:
    if not manifest_path or not manifest_path.exists():
        return {}
    payload = load_json(manifest_path)
    items = payload.get("items", [])
    if not isinstance(items, list):
        return {}
    by_title: dict[str, list[str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        title = clean_markdown_text(str(item.get("title") or ""), keep_urls=True)
        if not title:
            continue
        raw_images: list[str] = []
        selected_image = str(item.get("selected_image") or "").strip()
        if selected_image:
            raw_images.append(selected_image)
        raw_images.extend(str(path).strip() for path in item.get("images", []) if str(path).strip())
        existing = []
        for raw_path in raw_images:
            candidate = Path(raw_path).expanduser().resolve()
            if candidate.exists() and candidate.is_file():
                existing.append(str(candidate))
        if existing:
            by_title[title] = list(dict.fromkeys(existing))
    return by_title


def choose_item_image(
    item: Any,
    reference_images: dict[str, dict[str, Any]],
    source_images: dict[str, dict[str, Any]],
    fallback_images: dict[str, list[str]],
) -> dict[str, Any]:
    candidate_urls: list[str] = []
    for raw_url in [item.source_url, *item.source_refs]:
        if not raw_url:
            continue
        canonical = canonicalize_url(str(raw_url))
        if canonical and canonical not in candidate_urls:
            candidate_urls.append(canonical)

    for image_map in (reference_images, source_images):
        for canonical_url in candidate_urls:
            entry = image_map.get(canonical_url)
            if entry:
                return {
                    "selected_image": entry["image_path"],
                    "image_source": entry["image_source"],
                    "matched_url": canonical_url,
                    "image_candidates": list(entry["image_candidates"]),
                    "pack_dir": entry["pack_dir"],
                    "source_dir": entry["source_dir"],
                    "source_kind": entry["source_kind"],
                    "source_title": entry["source_title"],
                    "image_evidence": list(entry.get("image_evidence") or []),
                }

    fallback = fallback_images.get(item.title, [])
    if fallback:
        return {
            "selected_image": fallback[0],
            "image_source": "legacy-manifest",
            "matched_url": "",
            "image_candidates": fallback,
            "pack_dir": "",
            "source_dir": "",
            "source_kind": "",
            "source_title": "",
            "image_evidence": [],
        }

    return {
        "selected_image": "",
        "image_source": "none",
        "matched_url": "",
        "image_candidates": [],
        "pack_dir": "",
        "source_dir": "",
        "source_kind": "",
        "source_title": "",
        "image_evidence": [],
    }


def build_note(total_items: int, illustrated_items: int) -> str:
    return (
        "这版是基于 OpenClaw 正式 SSOT 自动派生的带配图文字版。"
        f"{total_items} 条里命中了 {illustrated_items} 条可信图源，"
        "优先使用 `reference-pack` / `source-pack`，缺图时再回退到已归档配图；"
        "没命中的条目保持纯文字，避免错配。"
    )


def render_markdown(report_path: Path, note: str, item_images: dict[str, dict[str, Any]]) -> str:
    lines = report_path.read_text(encoding="utf-8").splitlines()
    rendered: list[str] = []
    note_inserted = False
    current_title = ""
    inserted_titles: set[str] = set()
    normalized_titles = {title: title for title in item_images}

    for line in lines:
        rendered.append(line)
        stripped = line.strip()
        cleaned = clean_markdown_text(stripped, keep_urls=True)
        if not note_inserted and line.startswith("# "):
            rendered.append("")
            rendered.append(note)
            rendered.append("")
            note_inserted = True
            continue
        if cleaned in normalized_titles:
            current_title = normalized_titles[cleaned]
            continue
        if stripped.startswith("状态：") and current_title and current_title not in inserted_titles:
            selected_image = str(item_images[current_title].get("selected_image") or "")
            if selected_image:
                rendered.append("")
                rendered.append(f"![{current_title} 配图](<{selected_image}>)")
                rendered.append("")
                inserted_titles.add(current_title)
    return "\n".join(rendered).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    report_path = Path(args.report).expanduser().resolve()
    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")

    illustrated_out = Path(args.out).expanduser().resolve() if args.out else report_path.with_name(f"{report_path.stem}.illustrated.md")
    manifest_out = Path(args.manifest_out).expanduser().resolve() if args.manifest_out else report_path.with_name(f"{report_path.stem}.image-manifest.json")
    reference_pack = Path(args.reference_pack).expanduser().resolve() if args.reference_pack else report_path.parent / "reference-pack"
    source_pack = Path(args.source_pack).expanduser().resolve() if args.source_pack else report_path.parent / "source-pack"
    legacy_manifest = Path(args.legacy_manifest).expanduser().resolve() if args.legacy_manifest else manifest_out

    report = parse_report(report_path)
    reference_images = load_pack_images(reference_pack if reference_pack.exists() else None, "reference-pack")
    source_images = load_pack_images(source_pack if source_pack.exists() else None, "source-pack")
    fallback_images = load_fallback_manifest(legacy_manifest)

    manifest_items: list[dict[str, Any]] = []
    illustrated_count = 0
    for item in report.items:
        selection = choose_item_image(item, reference_images, source_images, fallback_images)
        if selection["selected_image"]:
            illustrated_count += 1
        manifest_items.append(
            {
                "index": item.index,
                "title": item.title,
                "source_url": item.source_url,
                "item_kind": item.item_kind,
                "selected_image": selection["selected_image"],
                "image_source": selection["image_source"],
                "matched_url": selection["matched_url"],
                "image_candidates": selection["image_candidates"],
                "pack_dir": selection["pack_dir"],
                "source_dir": selection["source_dir"],
                "source_kind": selection["source_kind"],
                "source_title": selection["source_title"],
                "image_evidence": selection["image_evidence"],
            }
        )

    note = build_note(len(report.items), illustrated_count)
    item_images = {item["title"]: item for item in manifest_items}
    illustrated_text = render_markdown(report_path, note, item_images)

    illustrated_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    illustrated_out.write_text(illustrated_text, encoding="utf-8")
    manifest_payload = {
        "date": report.date,
        "report": str(report_path),
        "illustrated_report": str(illustrated_out),
        "selection_priority": ["reference-pack", "source-pack", "legacy-manifest"],
        "inserted_image_count": illustrated_count,
        "item_count": len(report.items),
        "items": manifest_items,
    }
    manifest_out.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "result": "success",
                "report": str(report_path),
                "illustrated_report": str(illustrated_out),
                "manifest": str(manifest_out),
                "item_count": len(report.items),
                "inserted_image_count": illustrated_count,
                "reference_pack_used": reference_pack.exists(),
                "source_pack_used": source_pack.exists(),
                "legacy_manifest_used": legacy_manifest.exists(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
