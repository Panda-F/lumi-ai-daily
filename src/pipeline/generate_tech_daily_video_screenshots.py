#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE_DIR = Path(__file__).resolve().parents[1]
VIDEO_BUILD_SCRIPT = WORKSPACE_DIR / "scripts" / "tech-daily-video-build"


FORBIDDEN_OLD_LABELS = {"ChatGP", "Anthro", "K2626", "ParseB", "Huggin"}
FORBIDDEN_TEXT_MARKERS = ("…", "...")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render and self-review the tech-daily video screenshot package.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--report", required=True, help="Path to final/report.md")
    parser.add_argument("--content-manifest", required=True, help="Path to final/content-manifest.json")
    parser.add_argument("--title-pack", required=True, help="Path to publish/title-pack.json")
    parser.add_argument("--build-dir", required=True, help="Build directory that owns remotion-manifest.json and slides/")
    parser.add_argument("--out-dir", required=True, help="Final publish/video-screenshots directory")
    parser.add_argument("--story-manifest", help="Optional story image manifest for still-only rendering")
    parser.add_argument("--old-slides-dir", help="Optional previous slides directory used for stale hash detection")
    parser.add_argument("--review-out", help="Optional review JSON output path")
    parser.add_argument("--render-stills", action="store_true", help="Run the still-only Remotion render before packaging")
    parser.add_argument("--max-items", type=int, default=6)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)


def content_nav_labels(content_manifest: dict[str, Any]) -> list[str]:
    video_script = content_manifest.get("video_script") if isinstance(content_manifest.get("video_script"), dict) else {}
    items = video_script.get("items") if isinstance(video_script.get("items"), list) else []
    return [str(item.get("nav_label") or "").strip() for item in items if isinstance(item, dict)]


def content_screen_cards(content_manifest: dict[str, Any]) -> dict[int, list[dict[str, str]]]:
    video_script = content_manifest.get("video_script") if isinstance(content_manifest.get("video_script"), dict) else {}
    items = video_script.get("items") if isinstance(video_script.get("items"), list) else []
    by_index: dict[int, list[dict[str, str]]] = {}
    for item in items:
        if not isinstance(item, dict) or not str(item.get("index") or "").isdigit():
            continue
        cards = item.get("screen_cards") if isinstance(item.get("screen_cards"), list) else []
        by_index[int(item["index"])] = [
            {
                "heading": str(card.get("heading") or "").strip(),
                "body": str(card.get("body") or "").strip(),
                "icon_hint": str(card.get("icon_hint") or "").strip(),
            }
            for card in cards
            if isinstance(card, dict)
        ]
    return by_index


def expected_screenshot_names(item_count: int, include_outro: bool = True) -> list[str]:
    names = ["cover.png", "00-intro.png"]
    names.extend(f"{index:02d}-item.png" for index in range(1, item_count + 1))
    if include_outro:
        names.append("99-outro.png")
    return names


def run_stills_render(args: argparse.Namespace) -> None:
    cmd = [
        sys.executable,
        str(VIDEO_BUILD_SCRIPT),
        "--report",
        str(Path(args.report).expanduser().resolve()),
        "--out-dir",
        str(Path(args.build_dir).expanduser().resolve()),
        "--title-pack",
        str(Path(args.title_pack).expanduser().resolve()),
        "--content-manifest",
        str(Path(args.content_manifest).expanduser().resolve()),
        "--max-items",
        str(args.max_items),
        "--stills-only",
        "--min-reviewed-images",
        "0",
        "--no-bgm",
        "--no-transition-sfx",
        "--disable-outro-bgm",
        "--no-whisper",
    ]
    if args.story_manifest:
        story_manifest = Path(args.story_manifest).expanduser().resolve()
        if story_manifest.exists():
            cmd.extend(["--manifest", str(story_manifest)])
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "stills-only render failed\n"
            + (completed.stderr or completed.stdout or "").strip()[-4000:]
        )


def build_contact_sheet(image_paths: list[Path], output: Path) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Pillow unavailable for contact sheet: {exc}") from exc

    thumbs: list[tuple[str, Image.Image]] = []
    for path in image_paths:
        with Image.open(path) as image:
            thumb = image.convert("RGB")
            thumb.thumbnail((480, 270), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (480, 306), "#fff8f5")
            canvas.paste(thumb, ((480 - thumb.width) // 2, 0))
            draw = ImageDraw.Draw(canvas)
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 18)
            except Exception:  # noqa: BLE001
                font = ImageFont.load_default()
            draw.text((12, 278), path.name, fill="#4b4548", font=font)
            thumbs.append((path.name, canvas))
    cols = 2
    rows = max(1, (len(thumbs) + cols - 1) // cols)
    sheet = Image.new("RGB", (cols * 500 + 20, rows * 326 + 20), "#fff8f5")
    for index, (_, thumb) in enumerate(thumbs):
        col = index % cols
        row = index // cols
        sheet.paste(thumb, (20 + col * 500, 20 + row * 326))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def self_review(
    *,
    content_manifest_path: Path,
    title_pack_path: Path,
    remotion_manifest_path: Path,
    slides_dir: Path,
    old_slides_dir: Path | None,
) -> tuple[dict[str, Any], list[str]]:
    findings: list[str] = []
    warnings: list[str] = []
    content_manifest = read_json(content_manifest_path)
    title_pack = read_json(title_pack_path)
    remotion_manifest = read_json(remotion_manifest_path)
    item_count = int(remotion_manifest.get("meta", {}).get("item_count") or len(content_manifest.get("items") or []))
    expected_names = expected_screenshot_names(item_count)

    content_mtime = content_manifest_path.stat().st_mtime
    files: dict[str, dict[str, Any]] = {}
    for name in expected_names:
        path = slides_dir / name
        if not path.exists():
            findings.append(f"missing_screenshot:{name}")
            continue
        if path.stat().st_mtime + 1 < content_mtime:
            findings.append(f"screenshot_older_than_content_manifest:{name}")
        files[name] = {
            "source": str(path),
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
            "mtime": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        }

    if old_slides_dir and old_slides_dir.exists() and old_slides_dir.resolve() != slides_dir.resolve():
        for name, file_info in files.items():
            old_path = old_slides_dir / name
            if old_path.exists() and sha256_file(old_path) == file_info["sha256"]:
                findings.append(f"stale_hash_matches_old_slide:{name}")

    meta = remotion_manifest.get("meta") if isinstance(remotion_manifest.get("meta"), dict) else {}
    expected_title = str(title_pack.get("primary_hook") or content_manifest.get("title_pack", {}).get("primary_hook") or "").strip()
    actual_title = str(meta.get("title") or "").strip()
    if expected_title and actual_title != expected_title:
        findings.append(f"manifest_title_mismatch: expected={expected_title} actual={actual_title}")

    expected_labels = content_nav_labels(content_manifest)[:item_count]
    actual_labels = [str(label).strip() for label in meta.get("item_labels") or []]
    if expected_labels and actual_labels != expected_labels:
        findings.append(f"nav_labels_mismatch: expected={expected_labels} actual={actual_labels}")
    for label in actual_labels:
        if label in FORBIDDEN_OLD_LABELS:
            findings.append(f"old_truncated_nav_label:{label}")
        if not (2 <= len(label) <= 6):
            findings.append(f"nav_label_length_out_of_range:{label}")

    expected_cards = content_screen_cards(content_manifest)
    scenes = remotion_manifest.get("scenes") if isinstance(remotion_manifest.get("scenes"), list) else []
    for scene in scenes:
        if not isinstance(scene, dict) or scene.get("kind") != "item":
            continue
        index = int(scene.get("index") or 0)
        scene_cards = [
            {
                "heading": str(card.get("heading") or "").strip(),
                "body": str(card.get("body") or "").strip(),
                "icon_hint": str(card.get("icon_hint") or "").strip(),
            }
            for card in scene.get("screen_cards") or []
            if isinstance(card, dict)
        ]
        if expected_cards.get(index) and scene_cards != expected_cards[index]:
            findings.append(f"screen_cards_mismatch:item-{index}")

    for text in iter_strings(
        {
            "title": actual_title,
            "labels": actual_labels,
            "scenes": [
                {
                    "display_title": scene.get("display_title"),
                    "screen_cards": scene.get("screen_cards"),
                }
                for scene in scenes
                if isinstance(scene, dict) and scene.get("kind") == "item"
            ],
        }
    ):
        if any(marker in text for marker in FORBIDDEN_TEXT_MARKERS):
            findings.append(f"forbidden_ellipsis_text:{text[:80]}")

    review = {
        "status": "fail" if findings else "pass",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "content_manifest": str(content_manifest_path),
        "content_manifest_sha256": sha256_file(content_manifest_path),
        "title_pack": str(title_pack_path),
        "remotion_manifest": str(remotion_manifest_path),
        "remotion_manifest_sha256": sha256_file(remotion_manifest_path),
        "slides_dir": str(slides_dir),
        "item_count": item_count,
        "title": actual_title,
        "item_labels": actual_labels,
        "files": files,
        "blocking_findings": findings,
        "warnings": warnings,
    }
    return review, findings


def main() -> int:
    args = parse_args()
    build_dir = Path(args.build_dir).expanduser().resolve()
    slides_dir = build_dir / "slides"
    out_dir = Path(args.out_dir).expanduser().resolve()
    content_manifest_path = Path(args.content_manifest).expanduser().resolve()
    title_pack_path = Path(args.title_pack).expanduser().resolve()
    old_slides_dir = Path(args.old_slides_dir).expanduser().resolve() if args.old_slides_dir else None

    if args.render_stills:
        run_stills_render(args)

    remotion_manifest_path = build_dir / "remotion-manifest.json"
    if not remotion_manifest_path.exists():
        raise FileNotFoundError(f"Missing remotion manifest: {remotion_manifest_path}")
    review, findings = self_review(
        content_manifest_path=content_manifest_path,
        title_pack_path=title_pack_path,
        remotion_manifest_path=remotion_manifest_path,
        slides_dir=slides_dir,
        old_slides_dir=old_slides_dir,
    )
    if findings:
        if args.review_out:
            write_json(Path(args.review_out).expanduser().resolve(), review)
        print(json.dumps(review, ensure_ascii=False, indent=2))
        return 1

    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    copied_paths: list[Path] = []
    for name in review["files"]:
        source = Path(review["files"][name]["source"])
        destination = out_dir / name
        shutil.copy2(source, destination)
        copied_paths.append(destination)
        review["files"][name]["published"] = str(destination)
        review["files"][name]["published_sha256"] = sha256_file(destination)
    contact_sheet = out_dir / "contact-sheet.png"
    build_contact_sheet(copied_paths, contact_sheet)
    review["files"]["contact-sheet.png"] = {
        "published": str(contact_sheet),
        "published_sha256": sha256_file(contact_sheet),
        "size": contact_sheet.stat().st_size,
    }
    review["out_dir"] = str(out_dir)
    review["result"] = "success"
    review["package_manifest"] = str(out_dir / "manifest.json")
    write_json(out_dir / "manifest.json", review)
    if args.review_out:
        write_json(Path(args.review_out).expanduser().resolve(), review)
    print(json.dumps(review, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
