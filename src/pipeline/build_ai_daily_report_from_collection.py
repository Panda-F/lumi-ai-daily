#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_daily_paths import (
    tech_daily_discovery_dir,
    tech_daily_final_report_path,
    tech_daily_final_social_urls_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a deterministic AI Daily Markdown report from validated discovery/collection inputs."
    )
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--discovery-json", help="Optional merged-candidates.json path.")
    parser.add_argument("--report-out", help="Optional final/report.md path.")
    parser.add_argument("--social-urls-out", help="Optional final/social-urls.txt path.")
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


def select_items(payload: dict[str, Any], max_items: int) -> list[dict[str, Any]]:
    candidates = dedupe(candidates_from(payload))
    candidates.sort(key=score_candidate, reverse=True)
    selected: list[dict[str, Any]] = []
    host_counts: dict[str, int] = {}
    for candidate in candidates:
        url = source_url(candidate)
        host = source_label(url)
        if host_counts.get(host, 0) >= 2:
            continue
        selected.append(candidate)
        host_counts[host] = host_counts.get(host, 0) + 1
        if len(selected) >= max_items:
            break
    return selected


def item_kind(candidate: dict[str, Any]) -> str:
    text = " ".join(str(candidate.get(key) or "") for key in ("source_kind", "signal_lane", "title", "snippet")).lower()
    if any(token in text for token in ("paper", "research", "arxiv", "huggingface", "benchmark", "dataset")):
        return "research"
    return "tech"


def build_report(date: str, items: list[dict[str, Any]]) -> str:
    trend_url = source_url(items[0]) if items else ""
    lines = [
        f"# 📰 AI速递 - {date}",
        "",
        "## 硅谷风向词",
        "",
        f"- Agent Runtime：企业关注点从模型演示转向权限、执行和留痕\n  X出处：{trend_url}",
        f"- MCP Connector：工具连接器正在把 AI 带回原有软件现场\n  X出处：{trend_url}",
        f"- Evaluation Harness：团队更关心可复测、可回滚、可验收的 Agent 运行环境\n  X出处：{trend_url}",
        "",
        "## 硅谷科技热点",
        "",
    ]
    tech_items = [item for item in items if item_kind(item) == "tech"]
    research_items = [item for item in items if item_kind(item) == "research"]
    if not tech_items:
        tech_items, research_items = items[: min(5, len(items))], items[min(5, len(items)) :]

    emojis = ["🚀", "🎨", "💼", "🧰", "🌐"]
    for offset, candidate in enumerate(tech_items[:5]):
        title = clean_text(candidate.get("title"), 48)
        snippet = clean_text(candidate.get("snippet") or candidate.get("summary"), 115)
        url = source_url(candidate)
        label = source_label(url)
        lines.extend(
            [
                f"{emojis[offset % len(emojis)]} {title}",
                f"内容：{snippet or f'{label} 发布了新的 AI 相关更新，已进入今日候选池。'}",
                "解读：值得关注的是它改变了团队试用、采购、集成或验证 AI 的具体路径。",
                f"原文链接：{url}",
                f"【引用】{clean_text(candidate.get('title'), 28)}",
                "状态：[单源]",
                "",
            ]
        )
    lines.extend(["## 硅谷学术热点", ""])
    research_source = research_items[:3] or items[len(tech_items[:5]) : len(tech_items[:5]) + 3]
    research_emojis = ["🧪", "🔬", "🧠"]
    for offset, candidate in enumerate(research_source):
        title = clean_text(candidate.get("title"), 48)
        snippet = clean_text(candidate.get("snippet") or candidate.get("summary"), 115)
        url = source_url(candidate)
        lines.extend(
            [
                f"{research_emojis[offset % len(research_emojis)]} {title}",
                f"内容：{snippet or '该研究信号进入今日候选池，需在后续 text_compile 阶段补充方法与证据。'}",
                "解读：先把它作为研究方向信号，正式发布前必须由 reference pack 进一步核验边界。",
                f"原文链接：{url}",
                f"【引用】{clean_text(candidate.get('title'), 28)}",
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
    items = select_items(payload, max(args.max_items, 1))
    if len(items) < args.min_items:
        raise RuntimeError(f"Not enough candidates to build report: {len(items)} < {args.min_items}")

    report_out = Path(args.report_out).expanduser().resolve() if args.report_out else tech_daily_final_report_path(args.date)
    social_out = (
        Path(args.social_urls_out).expanduser().resolve()
        if args.social_urls_out
        else tech_daily_final_social_urls_path(args.date)
    )
    report_out.parent.mkdir(parents=True, exist_ok=True)
    social_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(build_report(args.date, items), encoding="utf-8")

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
        "item_count": len(items),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
