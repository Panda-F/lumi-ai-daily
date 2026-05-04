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
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ai_daily_paths import (
    tech_daily_discovery_dir,
    tech_daily_report_path,
    tech_daily_social_urls_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a deterministic AI Daily Markdown report from validated discovery/collection inputs."
    )
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--discovery-json", help="Optional merged-candidates.json path.")
    parser.add_argument("--report-out", help="Optional process/report.md path.")
    parser.add_argument("--social-urls-out", help="Optional process/social-urls.txt path.")
    parser.add_argument("--selection-review-out", help="Optional process/discovery/selection-review.json path.")
    parser.add_argument("--selection-model", default="gpt-5.4-mini", help="Codex model used only for news screening.")
    parser.add_argument("--selection-candidate-limit", type=int, default=48)
    parser.add_argument("--max-items", type=int, default=8)
    parser.add_argument("--min-items", type=int, default=6)
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def candidates_from(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("candidates")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def clean_text(value: Any, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(value or ""))).strip()
    return text[:limit].rstrip(" ，。；;")


def source_url(candidate: dict[str, Any]) -> str:
    return str(candidate.get("canonical_url") or candidate.get("url") or candidate.get("feed_url") or "").strip()


def source_label(url: str) -> str:
    match = re.match(r"https?://(?:www\.)?([^/]+)", url)
    return match.group(1) if match else "source"


def score_candidate(candidate: dict[str, Any]) -> tuple[float, int, str]:
    lane = str(candidate.get("signal_lane") or "")
    kind = str(candidate.get("source_kind") or "")
    official_bonus = 3 if kind in {"official", "research", "longform", "changelog"} else 0
    lane_bonus = 2 if lane in {"product_shadow", "research_velocity"} else 1
    signal = float(candidate.get("signal_score") or candidate.get("score") or 0)
    return (official_bonus + lane_bonus + signal, int(candidate.get("evidence_count") or 1), str(candidate.get("published_at") or ""))


def parse_iso_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def candidate_timestamp(candidate: dict[str, Any]) -> datetime | None:
    for key in ("published_at", "updated_at", "fetched_at", "created_at"):
        parsed = parse_iso_datetime(candidate.get(key))
        if parsed:
            return parsed
    return None


def selection_now() -> datetime:
    configured = os.environ.get("AI_DAILY_SELECTION_NOW", "").strip()
    parsed = parse_iso_datetime(configured)
    return parsed or datetime.now(timezone.utc)


def candidate_id(index: int) -> str:
    return f"c{index:03d}"


def codex_selection_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "notes", "selected", "rejected"],
        "properties": {
            "status": {"type": "string"},
            "notes": {"type": "string"},
            "selected": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["candidate_id", "rank", "reason", "impact"],
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "rank": {"type": "integer"},
                        "reason": {"type": "string"},
                        "impact": {"type": "string"},
                    },
                },
            },
            "rejected": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["candidate_id", "reason"],
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                },
            },
        },
    }


def compact_candidate(candidate: dict[str, Any], cid: str) -> dict[str, Any]:
    url = source_url(candidate)
    return {
        "candidate_id": cid,
        "title": clean_text(candidate.get("title"), 180),
        "url": url,
        "source_host": source_label(url),
        "source_kind": str(candidate.get("source_kind") or candidate.get("kind") or ""),
        "signal_lane": str(candidate.get("signal_lane") or ""),
        "published_at": str(candidate.get("published_at") or candidate.get("updated_at") or ""),
        "score": candidate.get("signal_score") or candidate.get("score"),
        "evidence_count": candidate.get("evidence_count"),
        "summary": clean_text(candidate.get("summary_for_editor") or candidate.get("summary") or candidate.get("snippet"), 520),
        "selection_fit": clean_text(candidate.get("selection_fit"), 260),
    }


def extract_json_object(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value)
        value = re.sub(r"\s*```$", "", value).strip()
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(value[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Codex selection output must be a JSON object")
    return payload


def codex_select_candidates(
    *,
    date: str,
    candidates: list[dict[str, Any]],
    min_items: int,
    max_items: int,
    model: str,
) -> dict[str, Any]:
    if model != "gpt-5.4-mini":
        raise RuntimeError(f"News screening must use gpt-5.4-mini, got {model}")
    codex = shutil.which("codex")
    if not codex:
        raise FileNotFoundError("codex CLI not found; cannot run gpt-5.4-mini news screening.")
    packets = [compact_candidate(candidate, candidate_id(index)) for index, candidate in enumerate(candidates, start=1)]
    prompt = (
        "你是 Lumi AI Daily 的新闻筛选主编。只做候选筛选，不写正文。\n"
        f"日期：{date}。目标：从候选里选出 {min_items}-{max_items} 条最值得进入今天 AI 日报的新闻。\n\n"
        "筛选标准：优先最近 24 小时内的新进展；优先官方、论文、产品发布、工程博客、可信媒体；"
        "入选理由要说清它为什么现在值得看，以及会影响谁的工作、判断、成本、信任或安全。"
        "弱来源、重复搬运、无上下文社区帖、只有模型名但没有具体变化的候选直接淘汰。"
        "保持议题多样性，避免同一公司或同一角度占满整期。\n\n"
        "输出严格 JSON，字段遵守 schema；selected 只写 candidate_id，不要发明 URL 或标题。"
        "`reason` 写入选或淘汰原因，`impact` 写受影响的人或处境。\n\n"
        "候选：\n"
        + json.dumps(packets, ensure_ascii=False, indent=2)
    )
    timeout = int(os.environ.get("AI_DAILY_SELECTION_CODEX_TIMEOUT", "900") or 900)
    with tempfile.TemporaryDirectory(prefix="lumi-selection-") as tmp:
        tmp_dir = Path(tmp)
        schema_path = tmp_dir / "schema.json"
        output_path = tmp_dir / "selection.json"
        schema_path.write_text(json.dumps(codex_selection_schema(), ensure_ascii=False), encoding="utf-8")
        completed = subprocess.run(
            [
                codex,
                "exec",
                "--model",
                model,
                "--sandbox",
                "read-only",
                "--ephemeral",
                "--skip-git-repo-check",
                "-C",
                str(_SRC_DIR.parent),
                "--output-schema",
                str(schema_path),
                "-o",
                str(output_path),
                "-",
            ],
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"gpt-5.4-mini news screening failed: {detail[:2000]}")
        raw_output = output_path.read_text(encoding="utf-8") if output_path.exists() else completed.stdout
    payload = extract_json_object(raw_output)
    selected = payload.get("selected")
    if not isinstance(selected, list):
        raise RuntimeError("gpt-5.4-mini selection output missing selected[]")
    if not (min_items <= len(selected) <= max_items):
        raise RuntimeError(f"gpt-5.4-mini selected {len(selected)} items, expected {min_items}-{max_items}")
    return payload


def dedupe(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        url = source_url(candidate)
        title = clean_text(candidate.get("title"), 120)
        title_key = re.sub(r"\W+", "", title.lower())[:64]
        if not url or not title:
            continue
        if url in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(title_key)
        result.append(candidate)
    return result


def prefilter_candidates(payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    candidates = dedupe(candidates_from(payload))
    window_hours = int(payload.get("window_hours") or payload.get("hot_window_hours") or 24)
    cutoff = selection_now() - timedelta(hours=window_hours)
    candidates = [
        candidate
        for candidate in candidates
        if (timestamp := candidate_timestamp(candidate)) is not None and timestamp >= cutoff
    ]
    candidates.sort(key=score_candidate, reverse=True)
    prefiltered: list[dict[str, Any]] = []
    host_counts: dict[str, int] = {}
    for candidate in candidates:
        url = source_url(candidate)
        host = source_label(url)
        if host_counts.get(host, 0) >= 4:
            continue
        prefiltered.append(candidate)
        host_counts[host] = host_counts.get(host, 0) + 1
        if len(prefiltered) >= limit:
            break
    return prefiltered


def select_items_with_review(
    *,
    payload: dict[str, Any],
    date: str,
    min_items: int,
    max_items: int,
    candidate_limit: int,
    model: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates = prefilter_candidates(payload, max(candidate_limit, max_items))
    if len(candidates) < min_items:
        raise RuntimeError(f"Not enough candidates after prefilter: {len(candidates)} < {min_items}")
    by_id = {candidate_id(index): candidate for index, candidate in enumerate(candidates, start=1)}
    selection = codex_select_candidates(
        date=date,
        candidates=candidates,
        min_items=min_items,
        max_items=max_items,
        model=model,
    )
    selected_ids: list[str] = []
    selected_candidates: list[dict[str, Any]] = []
    for raw in sorted(selection.get("selected") or [], key=lambda item: int(item.get("rank") or 999)):
        cid = str(raw.get("candidate_id") or "").strip()
        candidate = by_id.get(cid)
        if not candidate:
            raise RuntimeError(f"gpt-5.4-mini selected unknown candidate_id: {cid}")
        if cid in selected_ids:
            raise RuntimeError(f"gpt-5.4-mini selected duplicate candidate_id: {cid}")
        selected_ids.append(cid)
        reason = clean_text(raw.get("reason") or raw.get("inclusion_reason"), 300)
        impact = clean_text(raw.get("impact") or raw.get("human_impact"), 300)
        enriched = dict(candidate)
        enriched.update(
            {
                "candidate_id": cid,
                "selection_rank": int(raw.get("rank") or len(selected_ids)),
                "inclusion_reason": reason,
                "human_impact": impact,
                "decision_impact": impact,
                "selection_fit": reason,
            }
        )
        selected_candidates.append(enriched)
    rejected = []
    for raw in selection.get("rejected") or []:
        cid = str(raw.get("candidate_id") or "").strip()
        candidate = by_id.get(cid, {})
        rejected.append(
            {
                "candidate_id": cid,
                "title": clean_text(candidate.get("title"), 180),
                "canonical_url": source_url(candidate),
                "rejection_reason": clean_text(raw.get("reason") or raw.get("rejection_reason"), 260),
            }
        )
    selected_review = [
        {
            "candidate_id": str(item.get("candidate_id") or ""),
            "rank": item.get("selection_rank"),
            "title": clean_text(item.get("title"), 180),
            "url": source_url(item),
            "reason": clean_text(item.get("inclusion_reason"), 300),
            "impact": clean_text(item.get("human_impact"), 300),
        }
        for item in selected_candidates
    ]
    review = {
        "status": "selected",
        "date": date,
        "hot_window_hours": payload.get("window_hours") or payload.get("hot_window_hours") or 24,
        "selection_now_utc": selection_now().isoformat(),
        "selector": "codex",
        "selection_model": model,
        "candidate_limit": len(candidates),
        "selected_count": len(selected_candidates),
        "rejected_count": len(rejected),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "notes": clean_text(selection.get("notes") or selection.get("overall_notes"), 600),
        "selected": selected_review,
        "rejected": rejected,
        "selected_candidates": selected_candidates,
        "rejected_candidates": rejected,
        "reviewed_candidate_count": len(candidates),
        "reviewed_candidates": [compact_candidate(candidate, cid) for cid, candidate in by_id.items()],
        "all_candidates": [*selected_candidates, *rejected],
    }
    return selected_candidates, review


def item_kind(candidate: dict[str, Any]) -> str:
    url = source_url(candidate).lower()
    source_kind = str(candidate.get("source_kind") or "").lower()
    text = " ".join(str(candidate.get(key) or "") for key in ("signal_lane", "title", "snippet", "summary")).lower()
    if source_kind in {"arxiv", "research", "huggingface_paper"}:
        return "research"
    if any(token in url for token in ("arxiv.org", "pub.sakana.ai", "research.google", "openreview.net")):
        return "research"
    if any(token in text for token in ("paper", "preprint", "benchmark", "dataset", "taxonomy-driven evaluation")):
        return "research"
    return "tech"


def build_report(date: str, items: list[dict[str, Any]], selection_review: dict[str, Any]) -> str:
    trend_url = source_url(items[0]) if items else ""
    lines = [
        f"# 📰 AI速递 - {date}",
        "",
        "## 硅谷风向词",
        "",
        f"- 真实配图：今天只使用官方和来源页面里的可核验图片\n  X出处：{trend_url}",
        f"- 人的影响：筛选先看谁的等待、劳动、信任或成本被改变\n  X出处：{trend_url}",
        f"- 可复核来源：每条入选都必须能追到原始发布或可信报道\n  X出处：{trend_url}",
        "",
        "## 硅谷科技热点",
        "",
    ]
    tech_items = [item for item in items if item_kind(item) == "tech"]
    research_items = [item for item in items if item_kind(item) == "research"]
    emojis = ["🚀", "🎨", "💼", "🧰", "🌐"]
    for offset, candidate in enumerate(tech_items):
        title = clean_text(candidate.get("title"), 120)
        snippet = clean_text(candidate.get("snippet") or candidate.get("summary") or candidate.get("inclusion_reason"), 240)
        human_impact = clean_text(candidate.get("human_impact") or candidate.get("decision_impact"), 200)
        inclusion_reason = clean_text(candidate.get("inclusion_reason") or candidate.get("selection_fit"), 180)
        url = source_url(candidate)
        label = source_label(url)
        lines.extend(
            [
                f"{emojis[offset % len(emojis)]} {title}",
                f"内容：{snippet or f'{label} 发布了新的 AI 相关更新，已进入今日候选池。'}",
                f"解读：{human_impact or inclusion_reason or '它值得关注的不是技术名词本身，而是会改变团队试用、采购、集成或验证 AI 的具体路径。'}",
                f"原文链接：{url}",
                f"【引用】{clean_text(candidate.get('title'), 80)}",
                "状态：[单源]",
                "",
            ]
        )
    if not research_items:
        return "\n".join(lines).strip() + "\n"
    lines.extend(["## 硅谷学术热点", ""])
    research_source = research_items
    research_emojis = ["🧪", "🔬", "🧠"]
    for offset, candidate in enumerate(research_source):
        title = clean_text(candidate.get("title"), 120)
        snippet = clean_text(candidate.get("snippet") or candidate.get("summary") or candidate.get("inclusion_reason"), 240)
        human_impact = clean_text(candidate.get("human_impact") or candidate.get("decision_impact"), 200)
        url = source_url(candidate)
        lines.extend(
            [
                f"{research_emojis[offset % len(research_emojis)]} {title}",
                f"内容：{snippet or '该研究信号进入今日候选池，需在后续 text_compile 阶段补充方法与证据。'}",
                f"解读：{human_impact or '先把它作为研究方向信号，正式发布前必须由 reference pack 进一步核验边界。'}",
                f"原文链接：{url}",
                f"【引用】{clean_text(candidate.get('title'), 80)}",
                "状态：[单源]",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    args = parse_args()
    discovery_path = (
        Path(args.discovery_json).expanduser().resolve()
        if args.discovery_json
        else tech_daily_discovery_dir(args.date) / "merged-candidates.json"
    )
    if not discovery_path.exists():
        raise FileNotFoundError(f"Missing discovery JSON: {discovery_path}")
    payload = read_json(discovery_path)
    items, selection_review = select_items_with_review(
        payload=payload,
        date=args.date,
        min_items=args.min_items,
        max_items=max(args.max_items, 1),
        candidate_limit=args.selection_candidate_limit,
        model=args.selection_model,
    )
    if len(items) < args.min_items:
        raise RuntimeError(f"Not enough selected candidates to build report: {len(items)} < {args.min_items}")

    report_out = Path(args.report_out).expanduser().resolve() if args.report_out else tech_daily_report_path(args.date)
    social_out = (
        Path(args.social_urls_out).expanduser().resolve()
        if args.social_urls_out
        else tech_daily_social_urls_path(args.date)
    )
    report_out.parent.mkdir(parents=True, exist_ok=True)
    social_out.parent.mkdir(parents=True, exist_ok=True)
    selection_out = (
        Path(args.selection_review_out).expanduser().resolve()
        if args.selection_review_out
        else tech_daily_discovery_dir(args.date) / "selection-review.json"
    )
    selection_out.parent.mkdir(parents=True, exist_ok=True)
    selection_out.write_text(json.dumps(selection_review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_out.write_text(build_report(args.date, items, selection_review), encoding="utf-8")

    social_urls = [
        source_url(candidate)
        for candidate in items
        if str(candidate.get("source_kind") or "").lower() in {"x", "social", "chinese_roundup", "community"}
    ]
    if not social_urls:
        social_urls = [source_url(candidate) for candidate in items[:3]]
    social_out.write_text("\n".join(url for url in social_urls if url) + "\n", encoding="utf-8")

    result = {
        "result": "success",
        "date": args.date,
        "report": str(report_out),
        "social_urls": str(social_out),
        "source": str(discovery_path),
        "selection_review": str(selection_out),
        "selection_model": args.selection_model,
        "item_count": len(items),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
