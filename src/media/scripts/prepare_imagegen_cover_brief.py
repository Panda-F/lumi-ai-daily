#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a Lumi AI Daily cover brief for the imagegen skill.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD run date.")
    parser.add_argument("--report", required=True, help="Final report markdown path.")
    parser.add_argument("--cover-copy", required=True, help="Cover copy JSON path.")
    parser.add_argument("--title-pack", required=True, help="Title pack JSON path.")
    parser.add_argument("--story-manifest", required=True, help="Story asset manifest JSON path.")
    parser.add_argument("--lumi-reference", default="/Users/dystopia/.openclaw/workspace/assets/lumi-cover-ref.png")
    parser.add_argument("--final-cover", required=True, help="Expected final cover output path.")
    parser.add_argument("--out-json", required=True, help="Output machine-readable brief JSON path.")
    parser.add_argument("--out-md", required=True, help="Output human/imagegen prompt markdown path.")
    return parser.parse_args()


def load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    raw = json.loads(resolved.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def clean_text(value: Any, *, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if limit is not None and len(text) > limit:
        return text[:limit].rstrip()
    return text


def iter_manifest_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = manifest.get("items") or manifest.get("assets") or []
    return [item for item in raw_items if isinstance(item, dict)]


def candidate_path(raw: dict[str, Any]) -> str:
    for key in (
        "selected_image",
        "local_path",
        "path",
        "file",
        "image",
        "resolved_path",
        "thumbnail",
    ):
        value = str(raw.get(key) or "").strip()
        if value:
            return value
    assets = raw.get("assets")
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            value = candidate_path(asset)
            if value:
                return value
    return ""


def select_visual_roles(manifest: dict[str, Any], *, max_assets: int = 4) -> list[dict[str, str]]:
    roles: list[dict[str, str]] = []
    for item in iter_manifest_items(manifest):
        image_path = candidate_path(item)
        if not image_path:
            continue
        title = clean_text(item.get("title") or item.get("source_title") or item.get("headline"), limit=80)
        source = clean_text(item.get("source_url") or item.get("url") or item.get("domain"), limit=140)
        role = "dominant background" if not roles else "supporting evidence card"
        roles.append(
            {
                "role": role,
                "title": title,
                "source": source,
                "path": image_path,
            }
        )
        if len(roles) >= max_assets:
            break
    return roles


def build_prompt(
    *,
    date: str,
    title_pack: dict[str, Any],
    cover_copy: dict[str, Any],
    visual_roles: list[dict[str, str]],
    lumi_reference: str,
) -> str:
    main_hook = clean_text(cover_copy.get("headline") or title_pack.get("cover_headline"), limit=24)
    subhead = clean_text(cover_copy.get("subhead") or title_pack.get("cover_subhead"), limit=24)
    traffic_title = clean_text(title_pack.get("bilibili_title") or title_pack.get("primary_hook"), limit=96)
    entity = clean_text(title_pack.get("headline_subject") or ", ".join(title_pack.get("primary_entities") or []), limit=48)
    stakes = clean_text(title_pack.get("headline_stakes"), limit=96)
    role_lines = []
    for visual in visual_roles:
        role_lines.append(
            f"- {visual['role']}: {visual['path']} | {visual.get('title') or 'untitled'} | {visual.get('source') or ''}"
        )
    if not role_lines:
        role_lines.append("- no strong source visual found; use a truthful abstract editorial scene based on the report")

    return f"""Use case: ads-marketing
Asset type: 16:9 AI daily news thumbnail cover
Primary request: Create one high-click but truthful Lumi AI Daily cover for {date}.

Traffic title: {traffic_title}
Main entity: {entity}
Reader stake: {stakes}

Text (verbatim):
Main hook: "{main_hook}"
Subhead: "{subhead}"

Input images:
- Lumi reference: {lumi_reference}
{chr(10).join(role_lines)}

Composition:
- one dominant real-news visual or source-grounded editorial scene
- massive main hook text, 6-18 Chinese visual characters, thick outline or strong shadow
- short subhead directly under or near the main hook
- Lumi appears as a small AI host in a lower corner, no more than 15 percent of the frame
- Lumi character design target: restore the look and temperament of 藤原千花 / Chika Fujiwara from Kaguya-sama: Love Is War as closely as the image model can: pale pink hair, large black bow, round cheerful face, light blush, playful student-council-secretary energy, white school-uniform blouse, black shoulder straps/ribbon details, and a small readable "Lumi" chest badge
- leave clean negative space around text; thumbnail must read on mobile

Style:
- Bilibili/YouTube knowledge thumbnail energy, but credible and not tacky
- high contrast, clear focal point, one visual conflict
- use source visuals as truth anchors, not as raw screenshots

Constraints:
- preserve the Fujiwara Chika-like Lumi identity: pink hair, black bow, friendly student-secretary anime host, visible Lumi chest badge
- the image prompt may explicitly name 藤原千花 / Chika Fujiwara because the intended Lumi image is a close character restoration with a Lumi badge
- avoid hoodie, cyberpunk outfit, VTuber streamer styling, mature influencer styling, or generic mascot look
- keep the exact Chinese cover text legible
- do not invent fake claims, numbers, charts, awards, rankings, timestamps, or platform UI
- avoid logo walls, QR codes, login pages, dense tables, unreadable small text, random robot/circuit filler, watermarks
"""


def main() -> int:
    args = parse_args()
    title_pack = load_json(args.title_pack)
    cover_copy = load_json(args.cover_copy)
    manifest = load_json(args.story_manifest)
    visual_roles = select_visual_roles(manifest)
    prompt = build_prompt(
        date=args.date,
        title_pack=title_pack,
        cover_copy=cover_copy,
        visual_roles=visual_roles,
        lumi_reference=str(Path(args.lumi_reference).expanduser()),
    )

    payload = {
        "status": "prompt_ready",
        "provider": "imagegen_skill",
        "mode": "built_in_image_gen",
        "date": args.date,
        "report": str(Path(args.report).expanduser().resolve()),
        "title_pack": str(Path(args.title_pack).expanduser().resolve()),
        "cover_copy": str(Path(args.cover_copy).expanduser().resolve()),
        "story_manifest": str(Path(args.story_manifest).expanduser().resolve()),
        "lumi_reference": str(Path(args.lumi_reference).expanduser()),
        "final_cover": str(Path(args.final_cover).expanduser().resolve()),
        "visual_roles": visual_roles,
        "prompt": prompt,
        "handoff": (
            "Use the imagegen skill with this prompt, then save the selected image to final_cover. "
            "After saving, rerun cover review and downstream publish stages."
        ),
    }

    out_json = Path(args.out_json).expanduser().resolve()
    out_md = Path(args.out_md).expanduser().resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(
        "# Imagegen Cover Brief\n\n"
        f"Expected final cover: `{payload['final_cover']}`\n\n"
        "Use the imagegen skill in built-in tool mode. Save the selected image to the expected final cover path.\n\n"
        "```text\n"
        f"{prompt.strip()}\n"
        "```\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
