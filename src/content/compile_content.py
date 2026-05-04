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
import html
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ai_daily_paths import (
    tech_daily_day_dir,
    tech_daily_content_manifest_path,
    tech_daily_discovery_dir,
    tech_daily_editorial_brief_path,
    tech_daily_latest_report,
    tech_daily_reference_pack_dir,
    tech_daily_report_json_path,
    tech_daily_report_path,
    resolve_tech_daily_sources_dirs,
    tech_daily_source_pack_dir,
    tech_daily_style_corpus_dir,
    tech_daily_writing_playbook_path,
    tech_daily_writing_profile_path,
)
from llm_content import generate_editorial_bundle
from source_utils import canonicalize_url, load_source_pack, build_publication_summary
from tech_daily_parser import TechDailyItem, TechDailyReport, parse_report, write_report_json

SRC_DIR = Path(__file__).resolve().parents[1]
DISCOVERY_DIR = SRC_DIR / "discovery"
SEARCH_TERMS_SCRIPT = DISCOVERY_DIR / "search_terms.py"
REFERENCE_ARCHIVE_SCRIPT = DISCOVERY_DIR / "archive_reference_sources.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile the formal tech-daily SSOT report JSON from Markdown, discovery, and source-pack data.")
    parser.add_argument("--report", help="Path to the tech daily Markdown report.")
    parser.add_argument("--date", help="Optional YYYY-MM-DD date used to resolve default paths.")
    parser.add_argument("--discovery-json", help="Optional discovery cache JSON path.")
    parser.add_argument("--search-terms-out", help="Optional output path for generated search terms.")
    parser.add_argument("--report-json-out", help="Optional explicit output path for the report JSON.")
    parser.add_argument("--source-pack", action="append", default=[], help="Optional source-pack directory. Can be repeated.")
    parser.add_argument("--reference-pack-out", help="Optional explicit output path for the archived non-social reference pack.")
    parser.add_argument("--image-manifest-out", help="Optional explicit output path for the collected story image manifest.")
    parser.add_argument("--editorial-brief-out", help="Optional explicit output path for editorial-brief.json.")
    parser.add_argument("--content-manifest-out", help="Optional explicit output path for content-manifest.json.")
    parser.add_argument("--writing-profile", help="Optional writing profile YAML path.")
    parser.add_argument("--style-corpus-dir", help="Optional style corpus directory.")
    parser.add_argument("--writing-playbook", help="Optional writing playbook JSON path.")
    parser.add_argument("--skip-search-terms", action="store_true", help="Skip daily search-term generation.")
    parser.add_argument("--skip-reference-pack", action="store_true", help="Skip reference-pack generation for official/blog/paper sources.")
    return parser.parse_args()


def resolve_report_path(args: argparse.Namespace) -> Path:
    if args.report:
        path = Path(args.report).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Report not found: {path}")
        return path
    if args.date:
        path = tech_daily_report_path(args.date)
        if not path.exists():
            raise FileNotFoundError(f"Report not found: {path}")
        return path
    latest = tech_daily_latest_report()
    if not latest:
        raise FileNotFoundError("No tech-daily report found.")
    return latest


def resolve_date(report_path: Path, requested_date: str | None) -> str:
    if requested_date:
        return requested_date
    name = report_path.stem.removeprefix("tech-daily-")
    return name if name and name != report_path.stem else datetime.now(timezone.utc).strftime("%Y-%m-%d")


def run_json(cmd: list[str]) -> dict[str, Any]:
    completed = subprocess.run(cmd, text=True, capture_output=True)
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(cmd)}\n{stderr or stdout}")
    if not stdout:
        return {}
    return json.loads(stdout)


def load_json(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def clean_inline_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def source_host(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").removeprefix("www.")
    except ValueError:
        return ""


def source_kind_for_editor(source_meta: dict[str, Any], candidate: dict[str, Any]) -> str:
    parts = [
        clean_inline_text(source_meta.get("kind") or candidate.get("source_kind") or candidate.get("kind")),
        source_host(str(source_meta.get("final_url") or source_meta.get("url") or candidate.get("canonical_url") or candidate.get("url") or "")),
    ]
    return " / ".join(part for part in parts if part)


def split_fact_sentences(*texts: Any, limit: int = 8) -> list[str]:
    chunks: list[str] = []
    for text in texts:
        value = clean_inline_text(text)
        if not value:
            continue
        chunks.extend(part.strip() for part in re.split(r"(?<=[。！？；;])\s+|[。\n]+", value) if part.strip())
    facts: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        normalized = clean_inline_text(chunk).strip("。；;")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        facts.append(normalized)
        if len(facts) >= limit:
            break
    return facts


def source_dir_from_meta(source_meta: dict[str, Any]) -> Path | None:
    source_dir_raw = clean_inline_text(source_meta.get("_source_pack_dir"))
    item_dir_raw = clean_inline_text(source_meta.get("dir"))
    if not source_dir_raw or not item_dir_raw:
        return None
    source_dir = Path(source_dir_raw) / item_dir_raw
    return source_dir if source_dir.exists() else None


def load_sidecar_json(source_meta: dict[str, Any], filename: str) -> dict[str, Any]:
    source_dir = source_dir_from_meta(source_meta)
    if not source_dir:
        return {}
    path = source_dir / filename
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def resolve_asset_file(source_meta: dict[str, Any], raw_file: Any) -> str:
    value = clean_inline_text(raw_file)
    if not value:
        return ""
    source_dir = source_dir_from_meta(source_meta)
    if not source_dir:
        return value
    candidate = (source_dir / value).resolve()
    return str(candidate) if candidate.exists() else value


def source_asset_cards(source_meta: dict[str, Any], *, max_items: int = 5) -> list[dict[str, str]]:
    images_payload = load_sidecar_json(source_meta, "images.json")
    assets_payload = load_sidecar_json(source_meta, "assets.json")
    raw_entries = []
    if isinstance(images_payload.get("images"), list):
        raw_entries.extend(entry for entry in images_payload["images"] if isinstance(entry, dict))
    if isinstance(assets_payload.get("assets"), list):
        raw_entries.extend(
            entry
            for entry in assets_payload["assets"]
            if isinstance(entry, dict) and clean_inline_text(entry.get("asset_kind")) == "image"
        )
    if not raw_entries:
        raw_urls = [
            clean_inline_text(source_meta.get("hero_image_url")),
            *[clean_inline_text(url) for url in (source_meta.get("image_urls") or [])],
        ]
        raw_files = [
            clean_inline_text(source_meta.get("hero_image_file")),
            *[clean_inline_text(path) for path in (source_meta.get("image_files") or [])],
        ]
        for url, file_path in zip_longest(raw_urls, raw_files, fillvalue=""):
            if url or file_path:
                raw_entries.append({"url": url, "file": file_path, "source": "source-pack"})

    cards: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in raw_entries:
        url = clean_inline_text(entry.get("url"))
        file_path = resolve_asset_file(source_meta, entry.get("file"))
        key = (url, file_path)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        source = clean_inline_text(entry.get("source") or entry.get("label") or entry.get("class_name") or "source-image")
        width = clean_inline_text(entry.get("width"))
        height = clean_inline_text(entry.get("height"))
        dimensions = "x".join(part for part in (width, height) if part)
        cards.append(
            {
                "url": url,
                "file": file_path,
                "source": source,
                "alt": clean_inline_text(entry.get("alt")),
                "dimensions": dimensions,
            }
        )
        if len(cards) >= max_items:
            break
    return cards


def image_manifest_map(image_manifest_path: Path | None) -> dict[str, dict[str, Any]]:
    if not image_manifest_path or not image_manifest_path.exists():
        return {}
    payload = load_json(image_manifest_path)
    result: dict[str, dict[str, Any]] = {}
    for item in payload.get("items", []) if isinstance(payload.get("items"), list) else []:
        if not isinstance(item, dict):
            continue
        keys = [
            f"index:{item.get('index')}",
            canonicalize_url(str(item.get("source_url") or "")),
            clean_inline_text(item.get("title")),
        ]
        for key in keys:
            if key:
                result.setdefault(key, item)
    return result


def item_candidate_map(payload: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    all_candidates = payload.get("selected_candidates") or payload.get("all_candidates", [])
    by_url: dict[str, dict[str, Any]] = {}
    by_duplicate_key: dict[str, dict[str, Any]] = {}
    for candidate in all_candidates:
        if not isinstance(candidate, dict):
            continue
        canonical_url = canonicalize_url(str(candidate.get("canonical_url") or candidate.get("url") or ""))
        if canonical_url:
            by_url[canonical_url] = candidate
        duplicate_key = str(candidate.get("duplicate_key", "")).strip()
        if duplicate_key:
            by_duplicate_key[duplicate_key] = candidate
    return by_url, by_duplicate_key


def source_pack_map(source_pack_dirs: list[Path]) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for source_pack_dir in source_pack_dirs:
        merged.update(load_source_pack(source_pack_dir))
    return merged


def merge_item(
    item: TechDailyItem,
    *,
    candidate_by_url: dict[str, dict[str, Any]],
    candidate_by_duplicate_key: dict[str, dict[str, Any]],
    source_pack_by_url: dict[str, dict[str, Any]],
) -> TechDailyItem:
    source_url = canonicalize_url(item.source_url)
    source_meta = source_pack_by_url.get(source_url, {})
    duplicate_key = str(source_meta.get("duplicate_key") or item.duplicate_key or "").strip()
    candidate = candidate_by_url.get(source_url) if source_url else {}
    if not candidate and duplicate_key:
        candidate = candidate_by_duplicate_key.get(duplicate_key, {})
    candidate = candidate or {}

    decision_impact = str(
        candidate.get("decision_impact")
        or item.decision_impact
        or item.interpretation
    ).strip()
    source_refs = [
        ref
        for ref in [
            *(item.source_refs or []),
            item.source_url,
            str(candidate.get("canonical_url", "")).strip(),
        ]
        if ref
    ]
    source_refs = list(dict.fromkeys(source_refs))

    return TechDailyItem(
        index=item.index,
        title=item.title,
        content=item.content,
        interpretation=item.interpretation,
        source_url=item.source_url,
        quote=item.quote,
        status=item.status,
        decision_impact=decision_impact,
        source_refs=source_refs,
        item_kind=item.item_kind,
        duplicate_key=duplicate_key or str(candidate.get("duplicate_key", "")).strip(),
    )


def build_report_json(
    report: TechDailyReport,
    *,
    candidate_review: dict[str, Any],
    source_pack_dirs: list[Path],
) -> TechDailyReport:
    candidate_by_url, candidate_by_duplicate_key = item_candidate_map(candidate_review)
    source_pack_by_url = source_pack_map(source_pack_dirs)
    items = [
        merge_item(
            item,
            candidate_by_url=candidate_by_url,
            candidate_by_duplicate_key=candidate_by_duplicate_key,
            source_pack_by_url=source_pack_by_url,
        )
        for item in report.items
    ]
    return TechDailyReport(
        path=report.path,
        title=report.title,
        date=report.date,
        trend_words=report.trend_words,
        trend_lines=report.trend_lines,
        items=items,
        hot_window_hours=int(candidate_review.get("hot_window_hours") or report.hot_window_hours or 24),
        machine_review=dict(report.machine_review),
    )


def resolve_candidate_review_path(discovery_dir: Path) -> Path:
    selection_review = discovery_dir / "selection-review.json"
    if selection_review.exists():
        return selection_review
    return discovery_dir / "candidate-review.json"


def enrich_report_with_publication_refs(
    compiled_report: TechDailyReport,
    publication_summary: dict[str, Any],
) -> TechDailyReport:
    confirmation_by_index = {
        int(entry.get("index")): entry
        for entry in publication_summary.get("items") or []
        if str(entry.get("index", "")).isdigit()
    }
    enriched_items: list[TechDailyItem] = []
    for item in compiled_report.items:
        confirmation = confirmation_by_index.get(item.index, {})
        refs = [
            str(source.get("url") or "").strip()
            for source in confirmation.get("confirmation_sources") or []
            if str(source.get("url") or "").strip()
        ]
        if not refs and item.source_refs:
            refs = list(item.source_refs)
        enriched_items.append(
            TechDailyItem(
                index=item.index,
                title=item.title,
                content=item.content,
                interpretation=item.interpretation,
                source_url=item.source_url,
                quote=item.quote,
                status=item.status,
                decision_impact=item.decision_impact,
                source_refs=refs,
                item_kind=item.item_kind,
                duplicate_key=item.duplicate_key,
            )
        )
    compiled_report.items = enriched_items
    return compiled_report


def read_source_manuscript(source_meta: dict[str, Any], *, max_chars: int = 6000) -> str:
    source_dir_raw = str(source_meta.get("_source_pack_dir") or "").strip()
    item_dir_raw = str(source_meta.get("dir") or "").strip()
    content = ""
    if source_dir_raw and item_dir_raw:
        content_path = Path(source_dir_raw) / item_dir_raw / "content.md"
        if content_path.exists():
            content = content_path.read_text(encoding="utf-8", errors="replace")
    if not content:
        content = "\n".join(
            str(source_meta.get(key) or "").strip()
            for key in ("title", "excerpt", "summary", "text_excerpt", "note")
            if str(source_meta.get(key) or "").strip()
        )
    content = content.strip()
    if len(content) > max_chars:
        return content[:max_chars].rstrip() + "\n...[truncated]"
    return content


def build_traceable_fact_draft(
    compiled_report: TechDailyReport,
    *,
    candidate_review: dict[str, Any],
    source_pack_dirs: list[Path],
    image_manifest_path: Path | None = None,
) -> str:
    candidate_by_url, candidate_by_duplicate_key = item_candidate_map(candidate_review)
    source_pack_by_url = source_pack_map(source_pack_dirs)
    image_by_key = image_manifest_map(image_manifest_path)
    lines: list[str] = [
        f"# AI 日报事实底稿 - {compiled_report.date or 'unknown'}",
        "",
        "这份底稿只做事实回溯：保留来源、发布时间、原始标题、可核验事实、图片证据和原始原稿。后续写作角度由模型根据材料单独判断。",
        "",
    ]
    for item in compiled_report.items:
        canonical = canonicalize_url(item.source_url)
        source_meta = source_pack_by_url.get(canonical, {})
        candidate = candidate_by_url.get(canonical) or candidate_by_duplicate_key.get(item.duplicate_key, {}) or {}
        source_title = clean_inline_text(candidate.get("title") or source_meta.get("title") or source_meta.get("source_title") or item.title)
        published = clean_inline_text(candidate.get("published_at") or source_meta.get("published_at"))
        source_summary = clean_inline_text(
            candidate.get("summary_for_editor")
            or candidate.get("summary")
            or candidate.get("excerpt")
            or source_meta.get("summary")
            or source_meta.get("text_excerpt")
        )
        raw_manuscript = read_source_manuscript(source_meta)
        fact_particles = split_fact_sentences(
            item.content,
            source_summary,
            raw_manuscript[:2400],
            limit=10,
        )
        selected_image = (
            image_by_key.get(f"index:{item.index}")
            or image_by_key.get(canonical)
            or image_by_key.get(clean_inline_text(item.title))
            or {}
        )
        image_cards = source_asset_cards(source_meta)
        lines.extend(
            [
                f"## {item.index}. {item.title}",
                "",
                "### 来源卡",
                "",
                f"- 分类：{item.item_kind or candidate.get('source_kind') or source_meta.get('kind') or ''}",
                f"- 来源类型：{source_kind_for_editor(source_meta, candidate)}",
                f"- 来源 URL：{item.source_url}",
                f"- 发布时间：{published}",
                f"- 来源标题：{source_title}",
                f"- 状态：{item.status or ''}",
                f"- 可信度线索：{candidate.get('selection_fit') or source_meta.get('status') or ''}",
                "",
                "### 日报当前摘要（供回溯，不直接当正文）",
                "",
                f"- 事实摘要：{item.content}",
                f"- 既有解读：{item.interpretation}",
                f"- 影响备注：{item.decision_impact or ''}",
                "",
                "### 原文可核验事实颗粒",
                "",
                *[f"- {fact}" for fact in fact_particles],
                "",
                "### 原文摘要与可观察细节",
                "",
                source_summary or "(source summary unavailable)",
                "",
                "### 图片素材卡",
                "",
            ]
        )
        if selected_image:
            lines.extend(
                [
                    f"- 已选配图：{selected_image.get('selected_image') or ''}",
                    f"- 配图来源：{selected_image.get('image_source') or ''}",
                    f"- 匹配链接：{selected_image.get('matched_url') or ''}",
                ]
            )
        if image_cards:
            for index, card in enumerate(image_cards, start=1):
                bits = [
                    f"类型：{card.get('source') or 'source-image'}",
                    f"尺寸：{card.get('dimensions')}" if card.get("dimensions") else "",
                    f"文件：{card.get('file')}" if card.get("file") else "",
                    f"URL：{card.get('url')}" if card.get("url") else "",
                    f"说明：{card.get('alt')}" if card.get("alt") else "",
                ]
                lines.append(f"- {index}. " + "；".join(bit for bit in bits if bit))
        else:
            lines.append("- 当前 source pack 没有可用图片；这条新闻应回到信息采集阶段补图。")
        lines.extend(
            [
                "",
                "### 原始相关新闻原稿",
                "",
                raw_manuscript or "(source manuscript unavailable)",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def run_reference_pack_archive(report_path: Path, report_json_out: Path, reference_pack_out: Path) -> tuple[dict[str, Any], str]:
    try:
        payload = run_json(
            [
                sys.executable,
                str(REFERENCE_ARCHIVE_SCRIPT),
                "--report",
                str(report_path),
                "--report-json",
                str(report_json_out),
                "--out-dir",
                str(reference_pack_out),
            ]
        )
        return payload, ""
    except Exception as exc:  # noqa: BLE001
        return {}, str(exc)


def main() -> int:
    args = parse_args()
    report_path = resolve_report_path(args)
    run_date = resolve_date(report_path, args.date)
    discovery_dir = tech_daily_discovery_dir(run_date)
    discovery_json = (
        Path(args.discovery_json).expanduser().resolve()
        if args.discovery_json
        else discovery_dir / "merged-candidates.json"
    )
    if not discovery_json.exists() and not args.discovery_json:
        discovery_json = discovery_dir / "rsshub-candidates.json"
    search_terms_out = Path(args.search_terms_out).expanduser().resolve() if args.search_terms_out else discovery_dir / "search-terms.json"
    candidate_review_out = resolve_candidate_review_path(discovery_dir)
    report_json_out = Path(args.report_json_out).expanduser().resolve() if args.report_json_out else tech_daily_report_json_path(run_date)
    reference_pack_out = Path(args.reference_pack_out).expanduser().resolve() if args.reference_pack_out else tech_daily_reference_pack_dir(run_date)
    image_manifest_out = Path(args.image_manifest_out).expanduser().resolve() if args.image_manifest_out else report_path.with_name(f"{report_path.stem}.image-manifest.json")
    editorial_brief_out = Path(args.editorial_brief_out).expanduser().resolve() if args.editorial_brief_out else tech_daily_editorial_brief_path(run_date)
    content_manifest_out = Path(args.content_manifest_out).expanduser().resolve() if args.content_manifest_out else tech_daily_content_manifest_path(run_date)
    writing_profile_path = Path(args.writing_profile).expanduser().resolve() if args.writing_profile else tech_daily_writing_profile_path()
    style_corpus_dir = Path(args.style_corpus_dir).expanduser().resolve() if args.style_corpus_dir else tech_daily_style_corpus_dir()
    writing_playbook_path = Path(args.writing_playbook).expanduser().resolve() if args.writing_playbook else tech_daily_writing_playbook_path()

    source_pack_args = [Path(raw).expanduser().resolve() for raw in args.source_pack]
    resolved_source_dirs = resolve_tech_daily_sources_dirs(run_date)
    default_source_pack = tech_daily_source_pack_dir(run_date)
    if not source_pack_args:
        source_pack_args.extend(resolved_source_dirs)
    else:
        if default_source_pack.exists() and default_source_pack not in source_pack_args:
            source_pack_args.append(default_source_pack)
    default_reference_pack = tech_daily_reference_pack_dir(run_date)
    if default_reference_pack.exists() and default_reference_pack not in source_pack_args:
        source_pack_args.append(default_reference_pack)

    search_terms_payload: dict[str, Any] = {}
    candidate_review_payload: dict[str, Any] = {}

    if discovery_json.exists():
        discovery_dir.mkdir(parents=True, exist_ok=True)
        if not args.skip_search_terms:
            search_terms_payload = run_json(
                [
                    sys.executable,
                    str(SEARCH_TERMS_SCRIPT),
                    "--discovery-json",
                    str(discovery_json),
                    "--out",
                    str(search_terms_out),
                ]
            )
        else:
            search_terms_payload = load_json(search_terms_out)
        candidate_review_payload = load_json(candidate_review_out)
    else:
        search_terms_payload = load_json(search_terms_out)
        candidate_review_payload = load_json(candidate_review_out)

    report = parse_report(report_path)
    compiled_report = build_report_json(report, candidate_review=candidate_review_payload, source_pack_dirs=source_pack_args)
    publication_summary = build_publication_summary(compiled_report, source_pack_dirs=source_pack_args)
    compiled_report = enrich_report_with_publication_refs(compiled_report, publication_summary)
    compiled_report.machine_review["publication_summary"] = publication_summary
    write_report_json(compiled_report, report_json_out)

    reference_pack_payload: dict[str, Any] = {}
    reference_pack_error = ""
    if not args.skip_reference_pack:
        reference_pack_payload, reference_pack_error = run_reference_pack_archive(report_path, report_json_out, reference_pack_out)
        if reference_pack_out.exists() and reference_pack_out not in source_pack_args:
            source_pack_args.append(reference_pack_out)
        compiled_report = build_report_json(report, candidate_review=candidate_review_payload, source_pack_dirs=source_pack_args)
        publication_summary = build_publication_summary(compiled_report, source_pack_dirs=source_pack_args)
        compiled_report = enrich_report_with_publication_refs(compiled_report, publication_summary)
        compiled_report.machine_review["publication_summary"] = publication_summary
        write_report_json(compiled_report, report_json_out)

    fact_draft_out = report_path.with_name(f"{report_path.stem}.source-trace.md")
    fact_draft_out.write_text(
        build_traceable_fact_draft(
            compiled_report,
            candidate_review=candidate_review_payload,
            source_pack_dirs=source_pack_args,
            image_manifest_path=image_manifest_out if image_manifest_out.exists() else None,
        ),
        encoding="utf-8",
    )

    content_manifest_payload: dict[str, Any] = {}
    content_manifest_payload = generate_editorial_bundle(
        report_path=report_path,
        report_json_path=report_json_out,
        candidate_review_path=candidate_review_out,
        source_pack_dirs=source_pack_args,
        image_manifest_path=image_manifest_out if image_manifest_out.exists() else None,
        writing_profile_path=writing_profile_path,
        writing_playbook_path=writing_playbook_path,
        editorial_brief_out_path=editorial_brief_out,
        out_path=content_manifest_out,
        rewrite_report=True,
    )
    content_manifest_generated = True
    report = parse_report(report_path)
    compiled_report = build_report_json(report, candidate_review=candidate_review_payload, source_pack_dirs=source_pack_args)
    publication_summary = build_publication_summary(compiled_report, source_pack_dirs=source_pack_args)
    compiled_report = enrich_report_with_publication_refs(compiled_report, publication_summary)
    fact_draft_out.write_text(
        build_traceable_fact_draft(
            compiled_report,
            candidate_review=candidate_review_payload,
            source_pack_dirs=source_pack_args,
            image_manifest_path=image_manifest_out if image_manifest_out.exists() else None,
        ),
        encoding="utf-8",
    )

    compiled_report.machine_review = dict(compiled_report.machine_review)
    compiled_report.machine_review.pop("editorial_bundle", None)
    compiled_report.machine_review["content_manifest"] = {
        "enabled": content_manifest_generated,
        "path": str(content_manifest_out) if content_manifest_out.exists() else None,
        "editorial_brief": str(editorial_brief_out) if editorial_brief_out.exists() else None,
        "fact_draft": str(fact_draft_out),
        "model": content_manifest_payload.get("model"),
        "reasoning_effort": content_manifest_payload.get("reasoning_effort"),
        "style_corpus_dir": str(style_corpus_dir),
        "writing_profile": str(writing_profile_path),
        "writing_playbook": str(writing_playbook_path),
    }
    compiled_report.machine_review["publication_summary"] = publication_summary
    write_report_json(compiled_report, report_json_out)

    payload = {
        "result": "success",
        "date": run_date,
        "report": str(report_path),
        "report_json": str(report_json_out),
        "discovery_json": str(discovery_json) if discovery_json.exists() else None,
        "candidate_review": str(candidate_review_out) if candidate_review_out.exists() else None,
        "search_terms": str(search_terms_out) if search_terms_out.exists() else None,
        "source_packs": [str(path) for path in source_pack_args],
        "editorial_brief": str(editorial_brief_out) if editorial_brief_out.exists() else None,
        "content_manifest": str(content_manifest_out) if content_manifest_out.exists() else None,
        "content_manifest_generated": content_manifest_generated,
        "content_manifest_payload": content_manifest_payload or None,
        "fact_draft": str(fact_draft_out),
        "content_generation": {
            "provider": content_manifest_payload.get("provider") or "unknown",
            "model": content_manifest_payload.get("model"),
            "source_format": "markdown_files",
            "reasoning_effort": content_manifest_payload.get("reasoning_effort"),
        },
        "reference_pack": str(reference_pack_out) if reference_pack_out.exists() else None,
        "image_manifest": str(image_manifest_out) if image_manifest_out.exists() else None,
        "hot_window_hours": compiled_report.hot_window_hours,
        "item_count": len(compiled_report.items),
        "confirmed_item_count": int(publication_summary.get("confirmed_item_count") or 0),
        "publication_status": publication_summary.get("status"),
        "decision_impact_count": sum(1 for item in compiled_report.items if item.decision_impact),
        "search_terms_generated": bool(search_terms_payload),
        "reference_pack_generated": bool(reference_pack_payload),
        "reference_pack_error": reference_pack_error or None,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
