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

import html
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ai_daily_paths import extract_tech_daily_date, tech_daily_report_json_path

ITEM_HEADING_RE = re.compile(r"^(#{2,3})\s*(\d+)[\)\.]\s*(.+?)\s*$", re.M)
SECTION_HEADING_RE = re.compile(r"^#{2,3}\s*(硅谷科技热点|硅谷学术热点)\s*$", re.M)
TREND_HEADING_RE = re.compile(r"^#{2,3}\s*硅谷风向词\s*$", re.M)
URL_RE = re.compile(r"https?://[^\s<>\"]+")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
FIELD_LABEL_RE = re.compile(r"^(?:\*\*)?(内容|解读|原文链接|短引文|状态)(?:\*\*)?[：:]\s*(.*)$")
QUOTE_LABEL_RE = re.compile(r"^【(?:引用|短引文)】\s*(.*)$")
NOTE_LABEL_RE = re.compile(r"^(附注|备注|注)[：:]\s*(.*)$")
LEADING_DECORATION_RE = re.compile(r"^[^A-Za-z0-9\u4e00-\u9fff]+")


@dataclass
class TechDailyItem:
    index: int
    title: str
    content: str
    interpretation: str
    source_url: str
    quote: str
    status: str | None = None
    decision_impact: str = ""
    source_refs: list[str] = field(default_factory=list)
    item_kind: str = ""
    duplicate_key: str = ""

    @property
    def source_domain(self) -> str:
        return source_domain(self.source_url)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TechDailyReport:
    path: str
    title: str
    date: str
    trend_words: list[str]
    trend_lines: list[str]
    items: list[TechDailyItem]
    hot_window_hours: int = 24
    machine_review: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["items"] = [item.to_dict() for item in self.items]
        return payload


def clean_markdown_text(text: str, keep_urls: bool = False) -> str:
    value = text.strip()
    value = MARKDOWN_LINK_RE.sub(lambda match: match.group(1), value)
    value = value.replace("**", "").replace("__", "").replace("`", "")
    value = value.replace("<", "").replace(">", "")
    value = html.unescape(value)
    if not keep_urls:
        value = URL_RE.sub("", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t\r\n-")


def clean_title_text(text: str) -> str:
    value = clean_markdown_text(text, keep_urls=True)
    return LEADING_DECORATION_RE.sub("", value).strip()


def split_inline_status(text: str) -> tuple[str, str | None]:
    value = text.strip()
    if not value:
        return "", None
    match = re.search(r"\s*状态：\s*([^\n]+)\s*$", value)
    if not match:
        return value, None
    status = clean_markdown_text(match.group(1), keep_urls=True) or None
    content = value[: match.start()].rstrip()
    return content, status


def source_domain(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def report_json_path_for_markdown(report_path: str | Path) -> Path:
    path = Path(report_path).expanduser().resolve()
    report_date = extract_tech_daily_date(path)
    if report_date:
        return tech_daily_report_json_path(report_date)
    return path.with_suffix(".report.json")


def load_report_json_sidecar(report_path: str | Path) -> dict[str, Any]:
    json_path = report_json_path_for_markdown(report_path)
    if not json_path.exists():
        return {}
    try:
        raw = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def write_report_json(report: TechDailyReport, out_path: str | Path | None = None) -> Path:
    json_path = Path(out_path).expanduser().resolve() if out_path else report_json_path_for_markdown(report.path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return json_path


def guess_report_date(path: Path, title: str, text: str) -> str:
    candidates = [path.name, title, text[:500]]
    for candidate in candidates:
        match = re.search(r"(20\d{2}-\d{2}-\d{2})", candidate)
        if match:
            return match.group(1)
    return ""


def shorten_text(text: str, limit: int) -> str:
    value = clean_markdown_text(text)
    if len(value) <= limit:
        return value
    sentences = re.split(r"(?<=[。！？；!?])", value)
    kept: list[str] = []
    total = 0
    for sentence in sentences:
        chunk = sentence.strip()
        if not chunk:
            continue
        if total and total + len(chunk) > limit:
            break
        kept.append(chunk)
        total += len(chunk)
        if total >= limit:
            break
    merged = "".join(kept).strip()
    if merged:
        return merged
    return value[: max(limit - 1, 1)].rstrip() + "…"


def _extract_title(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return clean_markdown_text(line[2:], keep_urls=True)
    return "AI 科技日报"


def _extract_trends(text: str) -> tuple[list[str], list[str]]:
    heading = TREND_HEADING_RE.search(text)
    if not heading:
        return [], []

    start = heading.end()
    remainder = text[start:]
    next_item = ITEM_HEADING_RE.search(remainder)
    block = remainder[: next_item.start()] if next_item else remainder

    trend_lines: list[str] = []
    trend_words: list[str] = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line.startswith("-"):
            continue
        cleaned = clean_markdown_text(line.lstrip("-").strip(), keep_urls=True)
        if not cleaned:
            continue
        trend_lines.append(cleaned)
        bold_match = re.search(r"\*\*(.+?)\*\*", raw_line)
        if bold_match:
            trend_words.append(clean_markdown_text(bold_match.group(1), keep_urls=True))
            continue
        prefix = cleaned.split("：", 1)[0].strip()
        if prefix:
            trend_words.append(prefix)
    return trend_words[:3], trend_lines[:3]


def _extract_fields(block: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in block.splitlines():
        line = raw_line.strip()
        match = FIELD_LABEL_RE.match(line)
        if match:
            label, value = match.groups()
            fields[label] = value.strip()
            continue
        quote_match = QUOTE_LABEL_RE.match(line)
        if quote_match:
            fields["短引文"] = quote_match.group(1).strip()
    return fields


def _section_kind(label: str) -> str:
    if "科技热点" in label:
        return "tech"
    if "学术热点" in label:
        return "research"
    return ""


def _item_kind_for_offset(text: str, offset: int) -> str:
    matches = list(SECTION_HEADING_RE.finditer(text))
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        if start <= offset < end:
            return _section_kind(match.group(1))
    return ""


def _extract_source_url(block: str, fields: dict[str, str]) -> str:
    if "原文链接" in fields:
        candidates = URL_RE.findall(fields["原文链接"])
        if candidates:
            return candidates[0]
    candidates = URL_RE.findall(block)
    return candidates[0] if candidates else ""


def _extract_source_refs(block: str, source_url: str) -> list[str]:
    refs: list[str] = []
    for raw in [source_url, *URL_RE.findall(block)]:
        value = str(raw or "").strip()
        if value and value not in refs:
            refs.append(value)
    return refs


def _extract_quote_and_status(fields: dict[str, str], block: str) -> tuple[str, str | None]:
    status = clean_markdown_text(fields.get("状态", ""), keep_urls=True) or None
    raw_quote = fields.get("短引文", "")
    if "状态：" in raw_quote:
        raw_quote, _, raw_status = raw_quote.partition("状态：")
        raw_status_clean = clean_markdown_text(raw_status, keep_urls=True)
        if raw_status_clean:
            status = raw_status_clean
    quote = clean_markdown_text(raw_quote, keep_urls=True).strip("\"'“”")
    if not status:
        inline_status = re.search(r"状态：\s*([^\n]+)", block)
        if inline_status:
            status = clean_markdown_text(inline_status.group(1), keep_urls=True)
    return quote, status


def _looks_like_section_item_title(line: str) -> bool:
    value = line.strip()
    if not value or value.startswith("#") or value.startswith("-"):
        return False
    if FIELD_LABEL_RE.match(value) or QUOTE_LABEL_RE.match(value) or NOTE_LABEL_RE.match(value):
        return False
    if value.startswith("X出处：") or value.startswith("X出处:"):
        return False
    if URL_RE.fullmatch(value):
        return False
    return True


def _item_from_section_block(index: int, title: str, block: str, item_kind: str) -> TechDailyItem | None:
    fields = _extract_fields(block)
    if not any(fields.get(key) for key in ("内容", "解读", "原文链接", "短引文", "状态")):
        return None
    quote, status = _extract_quote_and_status(fields, block)
    interpretation_text, interpretation_status = split_inline_status(fields.get("解读", ""))
    if interpretation_status and not status:
        status = interpretation_status
    source_url = _extract_source_url(block, fields)
    source_refs = _extract_source_refs(block, source_url)
    return TechDailyItem(
        index=index,
        title=clean_title_text(title),
        content=clean_markdown_text(fields.get("内容", ""), keep_urls=True),
        interpretation=clean_markdown_text(interpretation_text, keep_urls=True),
        source_url=source_url,
        quote=quote,
        status=status,
        source_refs=source_refs,
        item_kind=item_kind,
    )


def _parse_section_style_items(text: str) -> list[TechDailyItem]:
    items: list[TechDailyItem] = []
    index = 1
    section_matches = list(SECTION_HEADING_RE.finditer(text))
    for section_idx, section_match in enumerate(section_matches):
        block_start = section_match.end()
        block_end = section_matches[section_idx + 1].start() if section_idx + 1 < len(section_matches) else len(text)
        block = text[block_start:block_end]
        item_kind = _section_kind(section_match.group(1))
        current_title: str | None = None
        current_lines: list[str] = []

        def flush_current() -> None:
            nonlocal current_title, current_lines, index
            if not current_title:
                return
            item = _item_from_section_block(index, current_title, "\n".join(current_lines).strip(), item_kind)
            current_title = None
            current_lines = []
            if not item:
                return
            items.append(item)
            index += 1

        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                if current_title and current_lines:
                    current_lines.append("")
                continue
            if _looks_like_section_item_title(line):
                flush_current()
                current_title = line
                current_lines = []
                continue
            if current_title:
                current_lines.append(line)
        flush_current()
    return items


def _merge_item_sidecar(item: TechDailyItem, item_sidecar: dict[str, Any]) -> TechDailyItem:
    merged = item.to_dict()
    merged["decision_impact"] = str(item.decision_impact or item_sidecar.get("decision_impact") or "")
    merged["duplicate_key"] = str(item_sidecar.get("duplicate_key") or item.duplicate_key or "")
    merged["item_kind"] = str(item.item_kind or item_sidecar.get("item_kind") or "")
    refs = item_sidecar.get("source_refs")
    if isinstance(refs, list):
        merged["source_refs"] = [str(ref).strip() for ref in refs if str(ref).strip()]
    elif item.source_refs:
        merged["source_refs"] = list(item.source_refs)
    elif item.source_url:
        merged["source_refs"] = [item.source_url]
    else:
        merged["source_refs"] = []
    return TechDailyItem(**merged)


def _sidecar_matches_item(item: TechDailyItem, item_sidecar: dict[str, Any]) -> bool:
    if not item_sidecar:
        return False
    sidecar_url = str(item_sidecar.get("source_url", "")).strip()
    if sidecar_url and item.source_url and sidecar_url.rstrip("/") != item.source_url.rstrip("/"):
        return False
    sidecar_title = clean_markdown_text(str(item_sidecar.get("title", "")), keep_urls=True)
    if sidecar_title and item.title and sidecar_title != item.title:
        return False
    return bool(sidecar_url or sidecar_title)


def _merge_report_sidecar(report: TechDailyReport, sidecar: dict[str, Any]) -> TechDailyReport:
    if not sidecar:
        return report

    item_sidecars = sidecar.get("items", [])
    sidecar_by_index = {
        int(item.get("index")): item
        for item in item_sidecars
        if isinstance(item, dict) and str(item.get("index", "")).isdigit()
    }
    sidecar_by_url = {
        source_url: item
        for item in item_sidecars
        if isinstance(item, dict)
        for source_url in [str(item.get("source_url", "")).strip()]
        if source_url
    }

    merged_items: list[TechDailyItem] = []
    for item in report.items:
        item_sidecar = sidecar_by_url.get(item.source_url) if item.source_url else None
        if not item_sidecar:
            candidate = sidecar_by_index.get(item.index)
            if _sidecar_matches_item(item, candidate or {}):
                item_sidecar = candidate
        merged_items.append(_merge_item_sidecar(item, item_sidecar or {}))

    return TechDailyReport(
        path=report.path,
        title=report.title,
        date=report.date,
        trend_words=[str(word) for word in report.trend_words if str(word).strip()],
        trend_lines=[str(line) for line in report.trend_lines if str(line).strip()],
        items=merged_items,
        hot_window_hours=int(sidecar.get("hot_window_hours") or report.hot_window_hours or 24),
        machine_review=sidecar.get("machine_review") if isinstance(sidecar.get("machine_review"), dict) else dict(report.machine_review),
    )


def parse_report(report_path: str | Path) -> TechDailyReport:
    path = Path(report_path).expanduser().resolve()
    text = path.read_text(encoding="utf-8")
    title = _extract_title(text)
    trend_words, trend_lines = _extract_trends(text)

    items: list[TechDailyItem] = []
    matches = list(ITEM_HEADING_RE.finditer(text))
    for idx, match in enumerate(matches):
        block_start = match.end()
        block_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[block_start:block_end].strip()
        fields = _extract_fields(block)
        quote, status = _extract_quote_and_status(fields, block)
        interpretation_text, interpretation_status = split_inline_status(fields.get("解读", ""))
        if interpretation_status and not status:
            status = interpretation_status
        source_url = _extract_source_url(block, fields)
        source_refs = _extract_source_refs(block, source_url)
        items.append(
            TechDailyItem(
                index=int(match.group(2)),
                title=clean_title_text(match.group(3)),
                content=clean_markdown_text(fields.get("内容", ""), keep_urls=True),
                interpretation=clean_markdown_text(interpretation_text, keep_urls=True),
                source_url=source_url,
                quote=quote,
                status=status,
                source_refs=source_refs,
                item_kind=_item_kind_for_offset(text, match.start()),
            )
        )

    if not items:
        items = _parse_section_style_items(text)
    if not items:
        raise ValueError(f"No report items found in {path}")

    report = TechDailyReport(
        path=str(path),
        title=title,
        date=guess_report_date(path, title, text),
        trend_words=[word for word in trend_words if word],
        trend_lines=[line for line in trend_lines if line],
        items=items,
    )
    return _merge_report_sidecar(report, load_report_json_sidecar(path))
