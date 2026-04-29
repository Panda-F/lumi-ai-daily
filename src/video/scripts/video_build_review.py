#!/usr/bin/env python3

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from tech_daily_parser import TechDailyItem, TechDailyReport

NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
NUMBER_UNIT_RE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*([BMK]|亿|万)\b", flags=re.I)
ALIAS_SEPARATOR_RE = re.compile(r"\s*(?:=>|->|→|：|:)\s*")


def estimate_script_duration_seconds(text: str) -> float:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return 0.0
    pause_bonus = sum(compact.count(token) for token in "，。！？；：,.!?;:") * 0.22
    return round(len(compact) / 5.1 + pause_bonus + 0.8, 2)


def _segment_spoken_text(segment: dict[str, Any]) -> str:
    return str(segment.get("oral_script") or segment.get("script") or "")


def _normalize_numbers(text: str) -> set[str]:
    return {match.group(0).replace(",", "") for match in NUMBER_RE.finditer(text or "")}


def _format_numeric(value: float) -> str:
    if abs(value - round(value)) < 1e-8:
        return str(int(round(value)))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _derived_supported_numbers(text: str) -> set[str]:
    supported: set[str] = set()
    for match in NUMBER_UNIT_RE.finditer(text or ""):
        raw_value = match.group(1).replace(",", "")
        unit = match.group(2).lower()
        try:
            value = float(raw_value)
        except ValueError:
            continue
        if unit == "b":
            # Chinese narration often converts USD billions into 亿美元:
            # 5B -> 50 亿, 20B -> 200 亿, 100B -> 1000 亿.
            supported.add(_format_numeric(value * 10))
        elif unit == "m":
            supported.add(_format_numeric(value / 100))
        elif unit == "k":
            supported.add(_format_numeric(value / 100000))
        elif unit in {"亿", "万"}:
            supported.add(_format_numeric(value))
    return supported


def _alias_supported_spoken_numbers(segment: dict[str, Any], base_text: str) -> set[str]:
    supported: set[str] = set()
    subtitle_script = str(segment.get("subtitle_script") or "")
    searchable = f"{base_text}\n{subtitle_script}"
    for raw_alias in segment.get("spoken_aliases") or []:
        parts = ALIAS_SEPARATOR_RE.split(str(raw_alias or "").strip(), maxsplit=1)
        if len(parts) != 2:
            continue
        display, spoken = (part.strip() for part in parts)
        if not display or not spoken:
            continue
        if display in searchable or re.sub(r"\s+", "", display) in re.sub(r"\s+", "", searchable):
            supported.update(_normalize_numbers(spoken))
    return supported


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "").strip()


def _review_intro_segment(report: TechDailyReport, segment: dict[str, Any]) -> tuple[list[str], list[str]]:
    blocking: list[str] = []
    warnings: list[str] = []
    opening = str(segment.get("opening") or "").strip()
    agenda = str(segment.get("agenda") or "").strip()
    transition = str(segment.get("transition") or "").strip()
    oral_script = _segment_spoken_text(segment)

    if not opening:
        blocking.append("视频 intro 缺少栏目开场。")
    if not agenda:
        blocking.append("视频 intro 缺少主线预告。")
    if not transition:
        warnings.append("视频 intro 缺少单独 transition 字段，将以口播正文承接。")
    if not oral_script:
        blocking.append("视频 intro 缺少口播稿。")
    if not report.trend_words and not report.trend_lines:
        warnings.append("日报没有风向词，视频 intro 只能依赖默认主线文案。")
    return blocking, warnings


def _review_item_segment(
    item: TechDailyItem,
    segment: dict[str, Any],
    seen_duplicate_keys: set[str],
    seen_sources: set[str],
) -> tuple[list[str], list[str]]:
    blocking: list[str] = []
    warnings: list[str] = []

    if not item.decision_impact.strip():
        blocking.append(f"第 {item.index} 条缺少 decision_impact。")
    if not item.source_url and not item.source_refs:
        blocking.append(f"第 {item.index} 条缺少 source_url/source_refs。")
    elif not item.source_url:
        warnings.append(f"第 {item.index} 条没有主 source_url，只能依赖 source_refs。")
    if not item.quote.strip():
        warnings.append(f"第 {item.index} 条缺少短引文。")

    duplicate_key = item.duplicate_key.strip()
    if duplicate_key:
        if duplicate_key in seen_duplicate_keys:
            blocking.append(f"第 {item.index} 条与其他视频条目重复占用 duplicate_key={duplicate_key}。")
        seen_duplicate_keys.add(duplicate_key)

    if item.source_url:
        if item.source_url in seen_sources:
            blocking.append(f"第 {item.index} 条与其他视频条目重复占用 source_url。")
        seen_sources.add(item.source_url)

    hook = str(segment.get("hook") or "").strip()
    takeaway = str(segment.get("takeaway") or "").strip()
    fact_points = [str(point).strip() for point in segment.get("fact_points", []) or [] if str(point).strip()]
    oral_script = _segment_spoken_text(segment)
    subtitle_script = str(segment.get("subtitle_script") or "").strip()
    media_assets = [asset for asset in segment.get("media_assets", []) or [] if isinstance(asset, dict) and asset.get("src")]

    if not hook:
        blocking.append(f"第 {item.index} 条缺少 hook。")
    if not takeaway:
        blocking.append(f"第 {item.index} 条缺少 takeaway。")
    if len(fact_points) < 2:
        blocking.append(f"第 {item.index} 条事实点少于 2 条。")
    if not oral_script:
        blocking.append(f"第 {item.index} 条缺少 oral_script。")
    if not subtitle_script:
        blocking.append(f"第 {item.index} 条缺少 subtitle_script。")
    if "media_assets" in segment and len(media_assets) < 2:
        blocking.append(f"第 {item.index} 条配图少于 2 张。")

    base_text = " ".join(
        [
            item.title,
            item.content,
            item.interpretation,
            item.quote,
            item.decision_impact,
            item.source_url,
            " ".join(item.source_refs),
        ]
    )
    supported_spoken_numbers = _alias_supported_spoken_numbers(segment, base_text)
    supported_numbers = _normalize_numbers(base_text) | _derived_supported_numbers(base_text) | supported_spoken_numbers
    unsupported_numbers = sorted(_normalize_numbers(oral_script) - supported_numbers)
    unsupported_numbers = [token for token in unsupported_numbers if token not in {str(item.index)}]
    if unsupported_numbers:
        blocking.append(f"第 {item.index} 条视频稿引入了原文里没有的数字：{', '.join(unsupported_numbers[:4])}。")

    compact_oral = _compact(oral_script)
    compact_raw = _compact(" ".join([item.title, item.content, item.interpretation, item.quote]))
    if compact_oral and compact_oral == compact_raw:
        blocking.append(f"第 {item.index} 条 oral_script 仍然等于原日报原文拼接，尚未转成口播稿。")

    return blocking, warnings


def review_video_script(
    report: TechDailyReport,
    items: list[TechDailyItem],
    video_script: dict[str, Any],
    *,
    max_duration_seconds: int = 480,
) -> dict[str, Any]:
    segments = list(video_script.get("segments", []))
    intro_segments = [segment for segment in segments if segment.get("kind") == "intro"]
    item_segments = [segment for segment in segments if segment.get("kind") == "item"]
    blocking_findings: list[str] = []
    warnings: list[str] = []

    if len(intro_segments) != 1:
        blocking_findings.append("视频稿 intro 段数量异常。")
    elif intro_segments:
        intro_blocking, intro_warnings = _review_intro_segment(report, intro_segments[0])
        blocking_findings.extend(intro_blocking)
        warnings.extend(intro_warnings)

    item_map = {item.index: item for item in items}
    seen_duplicate_keys: set[str] = set()
    seen_sources: set[str] = set()

    if len(item_segments) != len(items):
        blocking_findings.append("视频稿 item 段数量和日报条目数量不一致。")

    for segment in item_segments:
        item_index = int(segment.get("item_index", 0) or 0)
        item = item_map.get(item_index)
        if not item:
            blocking_findings.append(f"视频稿存在无法映射回 report item 的段落：item_index={item_index}。")
            continue
        item_blocking, item_warnings = _review_item_segment(item, segment, seen_duplicate_keys, seen_sources)
        blocking_findings.extend(item_blocking)
        warnings.extend(item_warnings)

    estimated_duration = round(sum(estimate_script_duration_seconds(_segment_spoken_text(segment)) for segment in segments), 2)
    min_duration_seconds = max(55, len(item_segments) * 14 + 10)
    if estimated_duration < min_duration_seconds:
        blocking_findings.append(
            f"视频稿预计时长 {estimated_duration:.1f}s，低于当前条目数要求的最小时长 {min_duration_seconds}s。"
        )
    if estimated_duration > max_duration_seconds:
        blocking_findings.append(
            f"视频稿预计时长 {estimated_duration:.1f}s，超过上限 {max_duration_seconds}s。"
        )

    status = "pass" if not blocking_findings else "fail"
    return {
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "estimated_duration_sec": estimated_duration,
        "duration_bounds_sec": {"min": min_duration_seconds, "max": max_duration_seconds},
        "blocking_findings": blocking_findings,
        "warnings": warnings,
        "reviewed_items": len(item_segments),
    }
