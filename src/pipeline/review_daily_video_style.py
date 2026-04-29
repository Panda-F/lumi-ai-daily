#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

EVENING_RE = re.compile(r"(晚上好|今晚|晚安|夜里|夜间|深夜|夜里收束)")
MORNING_RE = re.compile(r"(早|早安|早上|清早|今早|今天一早|上午|早间)")
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
TEMPLATE_CARD_HEADINGS = (
    "先看重点",
    "变化在哪",
    "值得盯住",
    "先看结论",
    "这次变了什么",
    "为什么值得盯",
    "为什么重要",
    "这条值得关注",
)
TTS_TAG_RE = re.compile(r"\[[A-Za-z][^\[\]\n]{0,80}\]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run high-signal QA checks against the generated daily video artifacts.")
    parser.add_argument("--report-json", required=True, help="Path to final/report.json")
    parser.add_argument("--video-script", required=True, help="Path to build/video/video-script.json")
    parser.add_argument("--srt", required=True, help="Path to final/video.srt")
    parser.add_argument("--title-pack", required=True, help="Path to publish/title-pack.json")
    parser.add_argument("--build-summary", help="Optional build-summary.json path")
    parser.add_argument("--out", required=True, help="Output JSON path")
    return parser.parse_args()


def load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    raw = json.loads(resolved.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return raw
    return {}


def parse_srt(path: Path) -> list[str]:
    cues: list[str] = []
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8"))
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        text = "\n".join(lines[2:])
        cues.append(text)
    return cues


def subtitle_failures(cues: list[str]) -> tuple[bool, list[str]]:
    findings: list[str] = []
    previous = ""
    for cue in cues:
        stripped = cue.strip()
        if not stripped:
            continue
        if re.fullmatch(r"[A-Za-z]", stripped):
            findings.append(f"subtitle_single_letter:{stripped}")
        if previous and re.search(r"[A-Za-z]$", previous) and re.search(r"^[A-Za-z]", stripped):
            findings.append(f"subtitle_broken_word:{previous} -> {stripped}")
        previous = stripped
    return not findings, findings


def clean_title_for_compare(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^[^A-Za-z0-9\u4e00-\u9fff]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def iter_title_surfaces(value: Any, key_path: str = "") -> list[str]:
    surfaces: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            next_path = f"{key_path}.{key}" if key_path else str(key)
            if isinstance(child, str) and re.search(r"(title|headline|heading|label|hook|lead_title|display_title|short_title)", str(key), re.I):
                surfaces.append(child)
            else:
                surfaces.extend(iter_title_surfaces(child, next_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            surfaces.extend(iter_title_surfaces(child, f"{key_path}[{index}]"))
    return surfaces


def no_title_ellipsis(*payloads: Any) -> tuple[bool, list[str]]:
    findings: list[str] = []
    for payload in payloads:
        for text in iter_title_surfaces(payload):
            if "..." in text or "…" in text:
                findings.append(f"title_contains_ellipsis:{text[:80]}")
    return not findings, findings


def review_screen_cards(item_segments: list[dict[str, Any]], manifest_item_scenes: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    findings: list[str] = []
    for source_name, segments in (("video_script", item_segments), ("manifest", manifest_item_scenes)):
        for index, segment in enumerate(segments, start=1):
            cards = segment.get("screen_cards")
            if not isinstance(cards, list) or len(cards) != 3:
                findings.append(f"{source_name}_item_{index}_screen_cards_missing_or_wrong_count")
                continue
            for card_offset, card in enumerate(cards, start=1):
                if not isinstance(card, dict):
                    findings.append(f"{source_name}_item_{index}_screen_card_{card_offset}_not_object")
                    continue
                heading = str(card.get("heading") or "").strip()
                body = str(card.get("body") or "").strip()
                if not heading or not body:
                    findings.append(f"{source_name}_item_{index}_screen_card_{card_offset}_empty")
                for phrase in TEMPLATE_CARD_HEADINGS:
                    if phrase in heading:
                        findings.append(f"{source_name}_item_{index}_screen_card_{card_offset}_template_heading:{phrase}")
    return not findings, findings


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().lower()


def review_sentence_pairs(source_name: str, segments: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    findings: list[str] = []
    for index, segment in enumerate(segments, start=1):
        kind = str(segment.get("kind") or "segment")
        path = f"{source_name}_{kind}_{index}"
        pairs = segment.get("sentence_pairs")
        if not isinstance(pairs, list) or not pairs:
            findings.append(f"{path}_missing_sentence_pairs")
            continue
        oral_parts: list[str] = []
        subtitle_parts: list[str] = []
        tts_parts: list[str] = []
        seen_ids: set[str] = set()
        for offset, pair in enumerate(pairs, start=1):
            if not isinstance(pair, dict):
                findings.append(f"{path}_sentence_pair_{offset}_not_object")
                continue
            sentence_id = str(pair.get("sentence_id") or "").strip()
            oral = str(pair.get("oral") or "").strip()
            subtitle = str(pair.get("subtitle") or "").strip()
            tags = pair.get("tts_tags") if isinstance(pair.get("tts_tags"), list) else []
            if not sentence_id:
                findings.append(f"{path}_sentence_pair_{offset}_missing_id")
            elif sentence_id in seen_ids:
                findings.append(f"{path}_sentence_pair_{offset}_duplicate_id:{sentence_id}")
            seen_ids.add(sentence_id)
            if not oral or not subtitle:
                findings.append(f"{path}_sentence_pair_{offset}_empty_text")
            if TTS_TAG_RE.search(oral) or TTS_TAG_RE.search(subtitle):
                findings.append(f"{path}_sentence_pair_{offset}_tag_leaked_to_text")
            oral_parts.append(oral)
            subtitle_parts.append(subtitle)
            tts_parts.append("".join(f"[{str(tag).strip().strip('[]')}]" for tag in tags if str(tag).strip()) + oral)
        if compact_text("".join(oral_parts)) != compact_text(segment.get("oral_script")):
            findings.append(f"{path}_sentence_pairs_oral_mismatch")
        if compact_text("".join(subtitle_parts)) != compact_text(segment.get("subtitle_script")):
            findings.append(f"{path}_sentence_pairs_subtitle_mismatch")
        if compact_text(TTS_TAG_RE.sub("", "".join(tts_parts))) != compact_text(TTS_TAG_RE.sub("", str(segment.get("tts_script") or ""))):
            findings.append(f"{path}_sentence_pairs_tts_mismatch")
    return not findings, findings


def morning_context_status(intro_scene: dict[str, Any], video_script: dict[str, Any]) -> tuple[bool, list[str]]:
    findings: list[str] = []
    all_video_text = json.dumps({"manifest_intro": intro_scene, "video_script": video_script}, ensure_ascii=False)
    opening = str(intro_scene.get("opening") or "")
    if EVENING_RE.search(all_video_text):
        findings.append("video_contains_evening_context")
    if not MORNING_RE.search(opening):
        findings.append("intro_opening_missing_morning_context")
    return not findings, findings


def fish_tts_status(build_summary: dict[str, Any], expected_segments: int) -> tuple[bool, list[str]]:
    findings: list[str] = []
    tts = build_summary.get("tts") if isinstance(build_summary.get("tts"), dict) else {}
    provider_counts = tts.get("provider_counts") if isinstance(tts.get("provider_counts"), dict) else {}
    fish_count = int(provider_counts.get("fish-speech") or 0)
    if int(provider_counts.get("macos-say") or 0) > 0:
        findings.append("tts_used_macos_say")
    if str(tts.get("effective_provider") or "") != "fish-speech":
        findings.append("tts_effective_provider_not_fish")
    if int(tts.get("remote_fallback_segments") or 0) > 0:
        findings.append("tts_remote_fallback_used")
    if fish_count < expected_segments:
        findings.append(f"tts_fish_segments_too_few:{fish_count}<{expected_segments}")
    return not findings, findings


def visual_coverage_reviews(summary_item_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for index, segment in enumerate(summary_item_segments, start=1):
        media_assets = [
            asset
            for asset in (segment.get("media_assets") or [])
            if isinstance(asset, dict) and str(asset.get("src") or "").strip()
        ]
        truthful_visual_count = int(
            segment.get("truthful_visual_count")
            or segment.get("approved_image_count")
            or 0
        )
        review = {
            "segment": segment.get("segment") or index,
            "item_index": segment.get("item_index") or index,
            "title": str(segment.get("display_title") or segment.get("title") or ""),
            "scene_visual_count": len(media_assets),
            "truthful_visual_count": truthful_visual_count,
            "coverage_status": (
                "pass" if len(media_assets) >= 2 and truthful_visual_count >= 1 else "fail"
            ),
        }
        reviews.append(review)
    return reviews


def main() -> int:
    args = parse_args()
    report_json = load_json(args.report_json)
    video_script = load_json(args.video_script)
    title_pack = load_json(args.title_pack)
    build_summary = load_json(args.build_summary) if args.build_summary else {}
    manifest_json_path = Path(str(build_summary.get("manifest_json") or "")).expanduser().resolve() if build_summary.get("manifest_json") else None
    remotion_manifest = load_json(manifest_json_path) if manifest_json_path and manifest_json_path.exists() else {}

    report_items = report_json.get("items") or []
    segments = video_script.get("segments") or []
    item_segments = [segment for segment in segments if isinstance(segment, dict) and segment.get("kind") == "item"]
    cues = parse_srt(Path(args.srt).expanduser().resolve())
    subtitle_pass, subtitle_findings = subtitle_failures(cues)

    manifest_meta = remotion_manifest.get("meta") if isinstance(remotion_manifest.get("meta"), dict) else {}
    summary_segments = build_summary.get("segments") or []
    summary_item_segments = [segment for segment in summary_segments if isinstance(segment, dict) and segment.get("kind") == "item"]
    intro_scene = next(
        (scene for scene in remotion_manifest.get("scenes") or [] if isinstance(scene, dict) and scene.get("kind") == "intro"),
        {},
    )
    manifest_item_scenes = [
        scene for scene in remotion_manifest.get("scenes") or [] if isinstance(scene, dict) and scene.get("kind") == "item"
    ]
    publication_contract = (
        report_json.get("machine_review", {}).get("publication_contract", {})
        if isinstance(report_json.get("machine_review"), dict)
        else {}
    )

    count_consistency_pass = (
        len(report_items) == len(item_segments)
        and (not summary_item_segments or len(summary_item_segments) == len(report_items))
        and title_pack.get("items_count") == len(report_items)
        and len(intro_scene.get("opening_items") or []) == len(report_items)
    )
    primary_hook = str(title_pack.get("primary_hook") or "").strip()
    top_story_title = clean_title_for_compare(title_pack.get("top_story_title"))
    cover_headline = str(title_pack.get("cover_headline") or "").strip()
    report_top_title = clean_title_for_compare(report_items[0].get("title")) if report_items else ""
    render_title = str(manifest_meta.get("title") or "").strip()
    title_consistency_pass = (
        bool(primary_hook)
        and title_pack.get("date") == report_json.get("date")
        and bool(title_pack.get("issue_label"))
        and bool(cover_headline)
        and bool(top_story_title)
        and top_story_title == report_top_title
        and (not render_title or render_title == primary_hook)
    )
    title_card_pass = bool(
        build_summary.get("subtitle_mode") == "cinematic_wrap" and build_summary.get("editorial_title_card")
    )
    duplicate_media_pass = build_summary.get("card_preview_media") is False
    intro_only_bgm_pass = (
        build_summary.get("bgm_scope") == "intro_only"
        and bool(build_summary.get("bgm_src"))
        and build_summary.get("bgm_end_frame") is not None
    )
    outro_bgm_pass = build_summary.get("outro_bgm_enabled") is not True
    top_story_confirmed_pass = bool(title_pack.get("top_story_confirmed"))
    confirmed_item_count_pass = int(publication_contract.get("confirmed_item_count") or 0) >= 6
    item_labels = build_summary.get("item_labels") or manifest_meta.get("item_labels") or []
    rail_label_pass = bool(item_labels) and all(
        isinstance(label, str)
        and label.strip()
        and len(label.strip()) <= 6
        and "..." not in label
        and "…" not in label
        and not re.search(r"[\U00010000-\U0010ffff\u2600-\u27BF]", label)
        for label in item_labels
    )
    gif_asset_pass = not (
        intro_scene.get("lumi_intro_src")
        and (
            str(intro_scene.get("lumi_intro_kind") or "").lower() != "video"
            or str(intro_scene.get("lumi_intro_src") or "").lower().endswith(".gif")
        )
    )
    emoji_icon_pass = True
    for report_item, manifest_item in zip(report_items, manifest_item_scenes):
        title = str(report_item.get("title") or "")
        if re.match(r"^[^A-Za-z0-9\u4e00-\u9fff]+", title) and not str(manifest_item.get("display_icon") or "").strip():
            emoji_icon_pass = False
            break
    visual_reviews = visual_coverage_reviews(summary_item_segments)
    truthful_visual_pass = all(review["truthful_visual_count"] >= 1 for review in visual_reviews)
    scene_visual_pass = all(review["scene_visual_count"] >= 2 for review in visual_reviews)
    live_search_fallback_pass = (
        not bool(build_summary.get("live_search_fallback_skipped"))
        or (truthful_visual_pass and scene_visual_pass)
    )
    title_ellipsis_pass, title_ellipsis_findings = no_title_ellipsis(title_pack, remotion_manifest)
    screen_cards_pass, screen_card_findings = review_screen_cards(item_segments, manifest_item_scenes)
    script_sentence_pairs_pass, script_sentence_pair_findings = review_sentence_pairs("video_script", segments)
    summary_sentence_pairs_pass, summary_sentence_pair_findings = review_sentence_pairs("timeline", summary_segments)
    morning_context_pass, morning_findings = morning_context_status(intro_scene, video_script)
    issue_quote_text = str(manifest_meta.get("issue_quote_text") or "")
    chinese_slogan_pass = bool(issue_quote_text.strip()) and bool(CHINESE_RE.search(issue_quote_text))
    fish_tts_pass, fish_tts_findings = fish_tts_status(build_summary, len(report_items) + 2)

    blocking_findings: list[str] = []
    if not subtitle_pass:
        blocking_findings.extend(subtitle_findings)
    if not count_consistency_pass:
        blocking_findings.append("item_count_mismatch_between_report_video_and_title_pack")
    if not top_story_confirmed_pass:
        blocking_findings.append("top_story_not_cross_confirmed")
    if not confirmed_item_count_pass:
        blocking_findings.append("less_than_6_confirmed_items")
    if not title_consistency_pass:
        blocking_findings.append("title_pack_inconsistent_with_report")
    if not title_card_pass:
        blocking_findings.append("editorial_title_card_contract_missing")
    if not duplicate_media_pass:
        blocking_findings.append("card_preview_media_contract_missing")
    if not intro_only_bgm_pass:
        blocking_findings.append("missing_intro_bgm_asset")
    if not outro_bgm_pass:
        blocking_findings.append("outro_bgm_not_disabled")
    if not rail_label_pass:
        blocking_findings.append("rail_label_overflow")
    if not gif_asset_pass:
        blocking_findings.append("gif_asset_not_rendered_as_video")
    if not emoji_icon_pass:
        blocking_findings.append("unmapped_emoji_found")
    if not truthful_visual_pass:
        blocking_findings.append("missing_truthful_visual_item")
    if not scene_visual_pass:
        blocking_findings.append("video_item_under_2_scene_visuals")
    if not live_search_fallback_pass:
        blocking_findings.append("live_search_fallback_skipped_unexpectedly")
    if not title_ellipsis_pass:
        blocking_findings.extend(title_ellipsis_findings)
    if not screen_cards_pass:
        blocking_findings.extend(screen_card_findings)
    if not script_sentence_pairs_pass:
        blocking_findings.extend(script_sentence_pair_findings)
    if not summary_sentence_pairs_pass:
        blocking_findings.extend(summary_sentence_pair_findings)
    if not morning_context_pass:
        blocking_findings.extend(morning_findings)
    if not chinese_slogan_pass:
        blocking_findings.append("issue_quote_text_not_chinese")
    if not fish_tts_pass:
        blocking_findings.extend(fish_tts_findings)

    payload = {
        "result": "success",
        "subtitle_pass": subtitle_pass,
        "title_card_pass": title_card_pass,
        "count_consistency_pass": count_consistency_pass,
        "title_consistency_pass": title_consistency_pass,
        "duplicate_media_pass": duplicate_media_pass,
        "intro_only_bgm_pass": intro_only_bgm_pass,
        "outro_bgm_pass": outro_bgm_pass,
        "top_story_confirmed_pass": top_story_confirmed_pass,
        "confirmed_item_count_pass": confirmed_item_count_pass,
        "rail_label_pass": rail_label_pass,
        "gif_asset_pass": gif_asset_pass,
        "emoji_icon_pass": emoji_icon_pass,
        "truthful_visual_pass": truthful_visual_pass,
        "scene_visual_pass": scene_visual_pass,
        "live_search_fallback_pass": live_search_fallback_pass,
        "title_ellipsis_pass": title_ellipsis_pass,
        "screen_cards_pass": screen_cards_pass,
        "script_sentence_pairs_pass": script_sentence_pairs_pass,
        "summary_sentence_pairs_pass": summary_sentence_pairs_pass,
        "morning_context_pass": morning_context_pass,
        "chinese_slogan_pass": chinese_slogan_pass,
        "fish_tts_pass": fish_tts_pass,
        "status": "pass" if not blocking_findings else "fail",
        "blocking_findings": blocking_findings,
        "report_items": len(report_items),
        "video_items": len(item_segments),
        "summary_items": len(summary_item_segments),
        "title_pack": str(Path(args.title_pack).expanduser().resolve()),
        "build_summary": str(Path(args.build_summary).expanduser().resolve()) if args.build_summary else None,
        "render_meta": manifest_meta,
        "screen_card_findings": screen_card_findings,
        "script_sentence_pair_findings": script_sentence_pair_findings,
        "summary_sentence_pair_findings": summary_sentence_pair_findings,
        "morning_findings": morning_findings,
        "fish_tts_findings": fish_tts_findings,
        "visual_reviews": visual_reviews,
    }
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
