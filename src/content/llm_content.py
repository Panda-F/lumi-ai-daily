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
import concurrent.futures
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from ai_daily_paths import (
    ai_daily_root,
    extract_tech_daily_date,
    tech_daily_content_dir,
    tech_daily_content_manifest_path,
    tech_daily_discovery_dir,
    tech_daily_editorial_brief_path,
    tech_daily_reference_pack_dir,
    tech_daily_source_pack_dir,
    tech_daily_writing_playbook_path,
    tech_daily_writing_profile_path,
)
from source_utils import canonicalize_url, load_source_pack
from tech_daily_parser import TechDailyItem, TechDailyReport, parse_report, report_json_path_for_markdown


DEFAULT_MODEL = "gpt-5.4"
DEFAULT_CODEX_MODEL = "gpt-5.4"
DEFAULT_POLISH_MODEL = DEFAULT_CODEX_MODEL
DEFAULT_PROVIDER = "codex_cli"
DEFAULT_REASONING_EFFORT = "high"
DEFAULT_MAX_RETRIES = 2
DEFAULT_INTERNET_WRITING_METHODOLOGY_PATH = (
    Path(__file__).resolve().parents[1]
    / "intelligence"
    / "writing_methodology.md"
)
DEFAULT_TITLE_COVER_PLAYBOOK_PATH = (
    Path(__file__).resolve().parents[1]
    / "intelligence"
    / "title_cover_playbook.md"
)
DEFAULT_VIDEO_STYLE_POLICY_PATH = _SRC_DIR.parent / "config" / "ai_daily_video_style_policy.json"
DEFAULT_CONTENT_PARALLELISM = 2
DEFAULT_CONTENT_TASK_RETRIES = 1
OFFICIAL_ISSUE_START_DATE = os.environ.get("AI_DAILY_OFFICIAL_START_DATE", "2026-04-13").strip()
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
MAX_NAMED_ARTIFACT_STEM_CHARS = 96

URL_RE = re.compile(r"https?://[^\s<>\")\]]+")
TTS_TAG_RE = re.compile(r"\[[A-Za-z][^\[\]\n]{0,80}\]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate AI daily Markdown content sources.")
    parser.add_argument("--report", required=True, help="Path to the factual tech-daily Markdown report.")
    parser.add_argument("--report-json", help="Optional report JSON sidecar.")
    parser.add_argument("--candidate-review", help="Optional candidate-review JSON path.")
    parser.add_argument("--source-pack", action="append", default=[], help="Optional source-pack/reference-pack directory. Can be repeated.")
    parser.add_argument("--image-manifest", help="Optional image manifest JSON path.")
    parser.add_argument("--writing-profile", help="Optional synthesized writing profile path.")
    parser.add_argument("--writing-playbook", help="Optional synthesized writing playbook path.")
    parser.add_argument("--editorial-brief-out", help="Optional editorial-brief.json output path.")
    parser.add_argument("--out", help="Output content-manifest JSON path.")
    parser.add_argument("--rewrite-report", action="store_true", help="Overwrite --report with the generated report Markdown.")
    return parser.parse_args()


def read_text_file(path: str | Path | None, *, max_chars: int = 12000) -> str:
    if not path:
        return ""
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        return ""
    text = resolved.read_text(encoding="utf-8", errors="replace").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[truncated]"


def load_json_file(path: str | Path | None) -> Any:
    if not path:
        return None
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        return None
    return json.loads(resolved.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def stable_json(payload: Any, *, max_chars: int = 60000) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[truncated]"


def env_bool(name: str, *, default: bool = False) -> bool:
    configured = os.environ.get(name, "").strip().lower()
    if not configured:
        return default
    return configured in {"1", "true", "yes", "on"}


def load_local_env_file() -> None:
    default_env = Path(__file__).resolve().parents[2] / ".env"
    env_path = Path(os.environ.get("AI_DAILY_ENV_FILE", default_env)).expanduser()
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value


def env_text(name: str, default: str = "") -> str:
    load_local_env_file()
    return os.environ.get(name, "").strip() or default


def visual_text_len(text: str) -> int:
    return len(re.sub(r"[\s，。！？；：,.!?;:、]", "", text or ""))


SCREEN_CARD_BAD_PHRASES = (
    "观看理由",
    "今天看它",
    "判断框架",
    "先看事实",
    "为什么你该在意",
    "事实锚点",
    "人的影响",
    "继续观察",
)
UNCLEAR_REFERENCE_PHRASES = (
    "那条帖子",
    "这条帖子",
    "这条 Reddit",
    "Reddit 那条",
    "这个事情",
    "这件事情",
    "这件事",
    "这件",
    "前面提到",
    "上面说",
    "上述内容",
    "材料里",
    "这条新闻",
    "这条更新",
    "这条信号",
    "这条研究",
    "这条消息",
    "这条",
    "这篇报道",
    "这篇文章",
    "这篇论文",
    "这篇",
    "前两条",
)
UNCLEAR_REFERENCE_PATTERNS = (
    re.compile(r"[A-Za-z][A-Za-z0-9 .&'’:_-]{1,48}\s*这条"),
    re.compile(r"[A-Za-z][A-Za-z0-9 .&'’:_-]{1,48}\s*这篇"),
)


def unclear_reference_findings(text: str) -> list[str]:
    value = str(text or "")
    findings = [phrase for phrase in UNCLEAR_REFERENCE_PHRASES if phrase in value]
    for pattern in UNCLEAR_REFERENCE_PATTERNS:
        findings.extend(match.group(0).strip() for match in pattern.finditer(value))
    return sorted(set(findings))


def max_stripped_line_len(value: Any) -> int:
    lines = str(value or "").splitlines() or [""]
    return max(len(line.strip()) for line in lines)


def contains_chinese_text(value: Any) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in str(value or ""))


def require_chinese_cover_text(value: str, label: str) -> str:
    cleaned = clean_display_text(value)
    if not contains_chinese_text(cleaned):
        raise ValueError(f"title-copy.md {label} must contain Chinese text")
    ascii_words = re.findall(r"[A-Za-z][A-Za-z0-9._-]*", cleaned)
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", cleaned)
    if ascii_words and len(chinese_chars) < 4:
        raise ValueError(f"title-copy.md {label} must be Chinese-led; English is only allowed for necessary entity names")
    return cleaned


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)


def collect_urls(*payloads: Any) -> set[str]:
    urls: set[str] = set()
    for payload in payloads:
        for text in iter_strings(payload):
            for raw_url in URL_RE.findall(text):
                canonical = canonicalize_url(raw_url.rstrip("。；，、."))
                if canonical:
                    urls.add(canonical)
    return urls


def load_video_style_policy() -> dict[str, Any]:
    configured = os.environ.get("AI_DAILY_VIDEO_STYLE_POLICY", "").strip()
    path = Path(configured).expanduser().resolve() if configured else DEFAULT_VIDEO_STYLE_POLICY_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def policy_string_list(policy: dict[str, Any], key: str) -> list[str]:
    value = policy.get(key)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def policy_int_mapping(policy: dict[str, Any], key: str) -> dict[str, int]:
    value = policy.get(key)
    if not isinstance(value, dict):
        return {}
    parsed: dict[str, int] = {}
    for name, raw in value.items():
        try:
            parsed[str(name)] = int(raw)
        except (TypeError, ValueError):
            continue
    return parsed


def policy_nested_int(policy: dict[str, Any], key: str, name: str, child_key: str, default: int = 0) -> int:
    value = policy.get(key)
    if not isinstance(value, dict):
        return default
    child = value.get(name)
    if not isinstance(child, dict):
        return default
    try:
        return int(child.get(child_key) or default)
    except (TypeError, ValueError):
        return default


def title_policy_prompt() -> str:
    policy = load_video_style_policy()
    rules = policy_string_list(policy, "title_generation_rules")
    parts: list[str] = []
    if rules:
        parts.append("标题生成规则：" + "；".join(rules) + "。")
    parts.append(
        "本轮标题允许更强冲突感，但必须以事实里的公司、模型、产品或项目为主语，"
        "用真实反差、压力点或后果吸引点击，不能虚构危机。"
        "传播心理优先顺序是：读者自我相关、具体损失或收益、反常识信息差、可验证证据。"
        "标题必须让人知道新闻变化落到谁的工作、生活、成本、信任或选择上，而不是只说 AI 又变强了。"
        "标题和封面共享同一条传播主线，但不要互相照抄：标题负责说清完整承诺，"
        "封面只负责在一秒内打出一个短、粗、准的视觉钩子。"
    )
    return "".join(parts)


def title_cover_playbook_prompt() -> str:
    configured = os.environ.get("AI_DAILY_TITLE_COVER_PLAYBOOK", "").strip()
    path = Path(configured).expanduser().resolve() if configured else DEFAULT_TITLE_COVER_PLAYBOOK_PATH
    text = read_text_file(path, max_chars=8000)
    if not text:
        return (
            "标题和封面方法论：先判断今天的流量来源，再写标题。"
            "标题使用具体实体 + 真实动作 + 读者后果；封面使用 4-12 个视觉字的强钩子，"
            "只保留一个主视觉冲突，Lumi 作为小型栏目识别点。"
        )
    return "标题与封面方法论，只作为编辑动作参考，输出必须忠于输入事实：" + text


def internet_writing_methodology_prompt() -> str:
    configured = os.environ.get("AI_DAILY_INTERNET_WRITING_METHODOLOGY", "").strip()
    path = Path(configured).expanduser().resolve() if configured else DEFAULT_INTERNET_WRITING_METHODOLOGY_PATH
    text = read_text_file(path, max_chars=8000)
    if not text:
        return (
            "互联网文章写作原则：标题必须有具体主语和信息量；开头从当天真实变化切入；"
            "每段要同时有事实锚点和编辑判断；少口号，多场景；结尾给读者一个能复述的判断。"
        )
    return "互联网文章写作方法论，只作为编辑动作参考，成稿使用 Lumi 自己的表达：" + text


def video_style_policy_prompt() -> str:
    policy = load_video_style_policy()
    parts: list[str] = []
    tone = str(policy.get("tone") or "").strip()
    if tone:
        parts.append(f"视频口播风格：{tone}")
    for key, label in (
        ("human_narration_rules", "人味口播规则"),
        ("reference_voice_capabilities", "参考内容能力，不模仿名人"),
        ("dynamic_intro_outro_rules", "动态开头结尾规则"),
        ("avoid_categories", "避免的表达类型"),
    ):
        values = policy_string_list(policy, key)
        if values:
            parts.append(label + "：" + "；".join(values) + "。")
    return "".join(parts) or "新闻播报可以轻快，但要避开过度网感、江湖感或动作片式隐喻。"


def source_domain_label(url: str) -> str:
    try:
        hostname = urlparse(url).hostname or ""
    except ValueError:
        return ""
    parts = [part for part in hostname.lower().split(".") if part and part not in {"www", "blog", "docs"}]
    if not parts:
        return ""
    label = parts[0]
    if label == "huggingface":
        return "Hugging Face"
    return label.replace("-", " ").title() if label.islower() else label


def clean_entity(value: str) -> str:
    cleaned = re.sub(r"^[\s:：,，、/|-]+|[\s:：,，、/|-]+$", "", value or "")
    cleaned = re.sub(r"^[^\w\u4e00-\u9fff]+|[^\w\u4e00-\u9fff.）)]+$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def title_entity_anchor(title: str) -> str:
    value = str(title or "").strip()
    if not value:
        return ""
    parts = [clean_entity(part) for part in re.split(r"[\s/／、,，;；|:：()（）]+", value) if part.strip()]
    for part in parts:
        if any(char.isalnum() for char in part):
            return part[:28].strip()
    return clean_entity(value)[:28].strip()


def extract_entities_from_texts(*texts: Any, source_url: str = "") -> list[str]:
    seen: set[str] = set()
    entities: list[str] = []
    for text in texts:
        for raw in re.split(r"[\s/／、,，;；|:：()（）「」『』【】]+", str(text or "")):
            entity = clean_entity(raw)
            if not entity or entity in seen:
                continue
            if visual_text_len(entity) < 2 or visual_text_len(entity) > 32:
                continue
            if not any(char.isalnum() for char in entity):
                continue
            seen.add(entity)
            entities.append(entity)
            if len(entities) >= 8:
                break
        if len(entities) >= 8:
            break
    domain_label = clean_entity(source_domain_label(source_url))
    if domain_label and domain_label not in seen:
        entities.append(domain_label)
    return entities[:8]


def brief_action_from_title(title: str, entity_anchor: str) -> str:
    value = str(title or "").strip()
    if entity_anchor and value.startswith(entity_anchor):
        action = value[len(entity_anchor) :].strip(" ，,：:")
        if action:
            return action
    return value


def candidate_metadata_by_url(candidate_review: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(candidate_review, dict):
        return {}
    raw_entries = candidate_review.get("selected_candidates") or candidate_review.get("all_candidates") or []
    by_url: dict[str, dict[str, Any]] = {}
    for raw in raw_entries:
        if not isinstance(raw, dict):
            continue
        url = canonicalize_url(str(raw.get("canonical_url") or raw.get("url") or raw.get("source_url") or ""))
        if url and url not in by_url:
            by_url[url] = raw
    return by_url


def summarize_candidate_review(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    entries = payload.get("selected_candidates") or payload.get("all_candidates") or []
    candidates: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        candidates.append(
            {
                "title": str(entry.get("title") or "")[:240],
                "url": str(entry.get("canonical_url") or entry.get("url") or entry.get("source_url") or ""),
                "source": str(entry.get("source") or entry.get("feed") or ""),
                "decision_impact": str(entry.get("decision_impact") or entry.get("human_impact") or ""),
                "published_at": str(entry.get("published_at") or entry.get("updated_at") or ""),
                "duplicate_key": str(entry.get("duplicate_key") or ""),
                "inclusion_reason": str(entry.get("inclusion_reason") or ""),
                "source_credibility": str(entry.get("source_credibility") or ""),
            }
        )
        if len(candidates) >= 40:
            break
    return {
        "status": payload.get("status"),
        "hot_window_hours": payload.get("hot_window_hours"),
        "blocking_findings": payload.get("blocking_findings") or [],
        "candidates": candidates,
    }


def summarize_pack_dir(path: Path) -> dict[str, Any]:
    index_path = path / "index.json"
    if not index_path.exists():
        return {"path": str(path), "exists": path.exists(), "sources": []}
    raw = load_json_file(index_path)
    sources: list[dict[str, Any]] = []
    for source in (raw or {}).get("sources", []) if isinstance(raw, dict) else []:
        if not isinstance(source, dict):
            continue
        sources.append(
            {
                "kind": str(source.get("kind") or ""),
                "title": str(source.get("title") or source.get("source_title") or "")[:240],
                "url": str(source.get("url") or ""),
                "final_url": str(source.get("final_url") or ""),
                "domain": str(source.get("domain") or ""),
                "source_author": str(source.get("source_author") or source.get("feed_name") or ""),
                "published_at": str(source.get("published_at") or ""),
                "status": str(source.get("status") or ""),
                "hero_image_file": str(source.get("hero_image_file") or ""),
                "hero_image_url": str(source.get("hero_image_url") or ""),
                "image_files": [str(value) for value in (source.get("image_files") or [])[:6]],
                "image_urls": [str(value) for value in (source.get("image_urls") or [])[:6]],
                "image_count": int(source.get("image_count") or 0),
                "asset_type_counts": source.get("asset_type_counts") or {},
                "summary": str(source.get("summary") or source.get("text_excerpt") or "")[:900],
            }
        )
        if len(sources) >= 40:
            break
    return {"path": str(path), "exists": True, "sources": sources}


def pack_sources_by_url(pack_summaries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for pack in pack_summaries:
        for source in pack.get("sources") or []:
            if not isinstance(source, dict):
                continue
            enriched = dict(source)
            enriched["pack_path"] = str(pack.get("path") or "")
            for raw_url in (source.get("url"), source.get("final_url")):
                canonical = canonicalize_url(str(raw_url or ""))
                if canonical and canonical not in indexed:
                    indexed[canonical] = enriched
    return indexed


def brief_fact_particles(*texts: Any, limit: int = 8) -> list[str]:
    chunks: list[str] = []
    for text in texts:
        value = html.unescape(str(text or ""))
        value = re.sub(r"<[^>]+>", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        if not value:
            continue
        chunks.extend(part.strip() for part in re.split(r"(?<=[。！？；;])\s+|[。\n]+", value) if part.strip())
    result: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        fact = chunk.strip("。；; ")
        if not fact or fact in seen:
            continue
        seen.add(fact)
        result.append(fact)
        if len(result) >= limit:
            break
    return result


def source_image_evidence(source: dict[str, Any], *, limit: int = 4) -> list[dict[str, Any]]:
    files = [str(source.get("hero_image_file") or ""), *[str(value) for value in (source.get("image_files") or [])]]
    urls = [str(source.get("hero_image_url") or ""), *[str(value) for value in (source.get("image_urls") or [])]]
    evidence: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for file_path, url in zip_longest(files, urls, fillvalue=""):
        file_path = file_path.strip()
        url = url.strip()
        key = (file_path, url)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        evidence.append(
            {
                "file": file_path,
                "url": url,
                "source": "source-pack",
            }
        )
        if len(evidence) >= limit:
            break
    return evidence


def style_guidance(profile_path: Path, playbook_path: Path) -> dict[str, Any]:
    return {
        "writing_profile": read_text_file(profile_path, max_chars=12000),
        "writing_playbook": read_text_file(playbook_path, max_chars=12000),
        "notes": [
            "Style inputs are guidance only.",
            "Do not quote private samples or reference-person names.",
        ],
    }


def build_editorial_brief(
    report: TechDailyReport,
    *,
    report_json: Any,
    candidate_review: Any,
    pack_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate_by_url = candidate_metadata_by_url(candidate_review)
    pack_by_url = pack_sources_by_url(pack_summaries)
    sidecar_items = report_json.get("items") if isinstance(report_json, dict) else []
    sidecar_by_index = {
        int(item.get("index")): item
        for item in sidecar_items
        if isinstance(item, dict) and str(item.get("index") or "").isdigit()
    }
    ranked_items: list[dict[str, Any]] = []
    primary_entities: list[str] = []
    for rank, item in enumerate(report.items, start=1):
        sidecar = sidecar_by_index.get(item.index, {})
        source_url = canonicalize_url(item.source_url)
        candidate = candidate_by_url.get(source_url, {})
        source_meta = pack_by_url.get(source_url, {})
        entity_anchor = title_entity_anchor(item.title)
        entities = extract_entities_from_texts(
            item.title,
            item.content,
            item.interpretation,
            *(item.source_refs or []),
            source_url=item.source_url,
        )
        if entity_anchor and entity_anchor not in entities:
            entities.insert(0, entity_anchor)
        for entity in entities[:3]:
            if entity and entity not in primary_entities:
                primary_entities.append(entity)
        ranked_items.append(
            {
                "rank": rank,
                "index": item.index,
                "source_url": item.source_url,
                "source_refs": list(dict.fromkeys([*(item.source_refs or []), item.source_url])),
                "published_at": str(candidate.get("published_at") or source_meta.get("published_at") or sidecar.get("published_at") or ""),
                "source_type": " / ".join(
                    part
                    for part in [
                        str(source_meta.get("kind") or candidate.get("source_kind") or ""),
                        str(source_meta.get("domain") or candidate.get("source_host") or ""),
                    ]
                    if part
                ),
                "source_title": str(source_meta.get("title") or candidate.get("title") or "")[:240],
                "source_summary": str(source_meta.get("summary") or candidate.get("summary_for_editor") or "")[:900],
                "entity_anchor": entity_anchor,
                "entities": entities[:6],
                "action": brief_action_from_title(item.title, entity_anchor),
                "fact_particles": brief_fact_particles(
                    item.content,
                    item.interpretation,
                    item.decision_impact,
                    source_meta.get("summary"),
                    candidate.get("summary_for_editor"),
                ),
                "image_evidence": source_image_evidence(source_meta),
                "facts": {
                    "title": item.title,
                    "content": item.content,
                    "interpretation": item.interpretation,
                    "status": item.status,
                    "item_kind": item.item_kind,
                },
                "stakes": str(item.interpretation or sidecar.get("interpretation") or "").strip(),
                "reader_pull": str(
                    item.decision_impact
                    or sidecar.get("decision_impact")
                    or candidate.get("decision_impact")
                    or ""
                ).strip(),
                "selection_fit": str(candidate.get("selection_fit") or ""),
            }
        )
    return {
        "version": 2,
        "date": report.date,
        "hot_window_hours": (
            int(report_json.get("hot_window_hours") or 0)
            if isinstance(report_json, dict) and str(report_json.get("hot_window_hours") or "").isdigit()
            else report.hot_window_hours or 24
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "headline_contract": {
            "primary_entities": primary_entities[:6],
            "rule": "Public titles must start from concrete entities plus a real conflict, pressure point, or consequence.",
        },
        "writing_contract": {
            "wechat": "Markdown-first. Generate a day editor map, draft segments sequentially with prior context, then run a whole-article editorial pass.",
            "voice": "Lumi: professional AI editor, clear and warm, with concrete facts before judgment.",
        },
        "internet_writing_methodology": read_text_file(DEFAULT_INTERNET_WRITING_METHODOLOGY_PATH, max_chars=6000),
        "ranked_items": ranked_items,
        "source_reference_pack_count": len(pack_summaries),
    }


def default_report_json_path(report_path: Path, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return report_json_path_for_markdown(report_path)


def default_candidate_review_path(report: TechDailyReport, explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit).expanduser().resolve()
    date = report.date or extract_tech_daily_date(report.path)
    if not date:
        return None
    selection_review = tech_daily_discovery_dir(date) / "selection-review.json"
    if selection_review.exists():
        return selection_review
    return tech_daily_discovery_dir(date) / "candidate-review.json"


def default_image_manifest_path(report_path: Path, explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit).expanduser().resolve()
    candidate = report_path.with_name(f"{report_path.stem}.image-manifest.json")
    return candidate if candidate.exists() else None


def default_pack_dirs(report: TechDailyReport, explicit_dirs: list[str]) -> list[Path]:
    dirs = [Path(value).expanduser().resolve() for value in explicit_dirs]
    date = report.date or extract_tech_daily_date(report.path)
    if date:
        for candidate in (tech_daily_source_pack_dir(date), tech_daily_reference_pack_dir(date)):
            if candidate.exists() and candidate not in dirs:
                dirs.append(candidate)
    return dirs


def default_content_dir(report: TechDailyReport) -> Path:
    date = report.date or extract_tech_daily_date(report.path) or "latest"
    return tech_daily_content_dir(date)


def default_output_path(report_path: Path, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    date = extract_tech_daily_date(report_path)
    if date:
        return tech_daily_content_manifest_path(date)
    return report_path.with_name("content-manifest.json")


def codex_binary() -> str:
    configured = os.environ.get("AI_DAILY_CONTENT_CODEX_BIN", "").strip()
    if configured:
        return configured
    discovered = shutil.which("codex")
    if discovered:
        return discovered
    app_binary = Path("/Applications/Codex.app/Contents/Resources/codex")
    if app_binary.exists():
        return str(app_binary)
    raise FileNotFoundError("codex CLI not found; content generation must run through Codex CLI or Codex automation.")


def content_codex_model() -> str:
    return os.environ.get("AI_DAILY_CONTENT_CODEX_MODEL", DEFAULT_CODEX_MODEL).strip() or DEFAULT_CODEX_MODEL


def content_codex_timeout() -> int:
    return int(os.environ.get("AI_DAILY_CONTENT_CODEX_TIMEOUT", "900") or 900)


def read_mock_markdown(slug: str) -> str | None:
    mock_dir = os.environ.get("AI_DAILY_CONTENT_MOCK_MARKDOWN_DIR", "").strip()
    if not mock_dir:
        return None
    if os.environ.get("AI_DAILY_ALLOW_CONTENT_MOCKS", "").strip() != "1":
        raise RuntimeError(
            "AI_DAILY_CONTENT_MOCK_MARKDOWN_DIR is disabled for production AI Daily runs; "
            "using mock Markdown can leak historical news into today's report."
        )
    path = Path(mock_dir).expanduser().resolve() / f"{slug}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def call_codex_markdown(context: dict[str, Any], *, slug: str, prompt: str, output_path: Path) -> str:
    mock = read_mock_markdown(slug)
    if mock is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(mock.strip() + "\n", encoding="utf-8")
        return mock.strip()

    timeout = content_codex_timeout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)
    final_prompt = (
        "这是 AI 日报流水线里的单个内容写作子任务。完整事实、风格、结构和输出要求已经全部写在本条消息里。\n"
        "请只使用本条消息内的材料完成当前写作，并把成品写入指定 Markdown 文件；本任务不涉及发布、打包或上传。\n\n"
        f"{prompt}\n\n"
        "执行方式要求：\n"
        f"1. 只把最终 Markdown 正文写入这个文件：{output_path}\n"
        "2. 最终文件使用普通 Markdown 正文，不使用代码块包裹。\n"
        "3. 不修改其他文件，不运行发布动作，不调用外部旧代理。\n"
        "4. 文件写完后最终回复只写 DONE。\n"
    )
    stdout_path = output_path.with_suffix(output_path.suffix + ".codex-last-message.txt")
    cmd = [
        codex_binary(),
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "danger-full-access",
        "--cd",
        str(Path(__file__).resolve().parents[2]),
        "--add-dir",
        str(ai_daily_root()),
        "-m",
        content_codex_model(),
        "-c",
        f"model_reasoning_effort={json.dumps(os.environ.get('AI_DAILY_CONTENT_REASONING_EFFORT', DEFAULT_REASONING_EFFORT).strip() or DEFAULT_REASONING_EFFORT)}",
        "-o",
        str(stdout_path),
        final_prompt,
    ]
    completed = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0 and not output_path.exists():
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"Content runner failed with exit code {completed.returncode}: {detail[:2000]}")
    text = read_text_file(output_path, max_chars=200000)
    if not text:
        raise RuntimeError(f"Content runner did not write Markdown file: {output_path}")
    return text


def preflight_polish_backend() -> None:
    codex_binary()


def prompt_execution_principles() -> str:
    return (
        "先确认当前任务只服务哪一个产物，再写作；"
        "长事实材料只作为证据来源，成稿要围绕读者阅读体验重组；"
        "事实、日期、数字、URL 和实体名以输入材料为准；"
        "推断必须能从事实材料自然推出。"
    )


def lumi_current_style_contract() -> str:
    return (
        "Lumi 的文字先服从事实，再追求表达。写作从一个具体变化进入：谁做了什么、发生在哪个产品或场景、"
        "读者为什么现在需要知道。技术解释先搭理解台阶，再给术语和机制，最后落到人的等待、劳动、信任、成本、"
        "安全或选择上。语气像真人主编，清楚、有判断、有温度；少用万能结论和公告腔。标题、正文、视频和封面共享同一条主线，"
        "但按各自场景压缩表达。开头负责让人愿意读下去，结尾负责把全天新闻收束成一个可带走的判断。"
    )


def language_policy_prompt() -> str:
    return (
        "中文优先原则：除公司名、产品名、模型名、论文题名、协议名、仓库名等没有稳定中文译名的专有名词外，"
        "其余表达尽量使用中文。英文实体出现时，紧跟中文场景或后果，不能让英文短语独自承担理解成本。"
        "常见概念要翻成中文，例如 credentials 写作凭证或密钥，regression harness 写作回归测试框架，"
        "talent pipeline 写作人才培养链；只有翻译会造成误解时才保留英文。"
    )


def lumi_article_role() -> str:
    return (
        "你是 Lumi 的 AI 科技公众号主编。读者关注 AI 产品、工程实践、创业和投资语境，"
        "但不默认理解每个论文术语、架构名、芯片名、benchmark 或缩写。"
        "他们不需要公告改写，也不需要术语堆叠，而需要你从当天事实里挑出真正有用的变化、技术含义和产业位置。"
        "文章声音要像真人编辑：专业、清楚、轻快、有判断，也有一点温度；"
        "技术解释要先给理解台阶，再给术语和机制，最后落到产品、成本、工作流或产业位置。"
    )


def lumi_title_role() -> str:
    return (
        "你是 Lumi 的标题编辑。你的任务是把当天新闻里最能让真实读者点开的矛盾压成短句："
        "有具体实体，有真实动作，有读者会在意的后果。标题要有传播力，但不能牺牲事实。"
        "你写给普通读者，不写给已经知道所有代号的圈内人；技术名可以出现，但必须立刻翻译成可感知的使用场景、成本变化或风险变化。"
    )


def lumi_video_role() -> str:
    return (
        "你是 Lumi 的视频主编和口播编辑。画面文案负责让观众一眼抓住信息，"
        "口播负责把复杂变化讲得自然、可信、能听下去。视频语言要更口语，但判断不能变薄。"
    )


def lumi_platform_role() -> str:
    return (
        "你是 Lumi 的 B站发布编辑。你要把当天主线压成观众愿意点开的标题、简介和动态，"
        "用具体实体、真实变化和人的处境解释这期为什么值得看。"
    )


def factual_boundary_prompt() -> str:
    return (
        "事实边界：只使用输入事实包中的事实、URL、日期、数字、版本号、人物身份、公司关系和发布日期。"
        "参考链接按 URL 文本呈现。写作的判断来自具体事实、具体场景和产业变化。"
        "通俗表达的目标是把复杂问题讲清楚，而不是把判断写空；"
        "解释术语时只能解释输入事实自然涉及的机制，不补不存在的背景设定。"
    )


def compact_style_guidance(context: dict[str, Any]) -> dict[str, str]:
    style = context.get("style_guidance") if isinstance(context.get("style_guidance"), dict) else {}
    return {
        "writing_profile": str(style.get("writing_profile") or "")[:3500],
        "writing_playbook": str(style.get("writing_playbook") or "")[:3500],
    }


def style_guidance_prompt(context: dict[str, Any], *, include_methodology: bool = True) -> str:
    _ = (context, include_methodology)
    return (
        "编辑方法：先写事实稿，再做结构化。事实稿要像一位主编直接写给读者的完整文字，"
        "不要先套字段、不要按样例拼装。结构化阶段只负责把已经写好的文字整理成标题、段落、卡片和口播标签。"
        "每个段落都要有具体实体或具体动作；每个判断都要能回到输入事实包中的事实。"
        "复杂技术内容按“现实问题 -> 技术名称 -> 机制一句话 -> 对人的影响”展开。"
    )


def compact_prompt_item(item: dict[str, Any]) -> dict[str, Any]:
    facts = item.get("facts") if isinstance(item.get("facts"), dict) else {}
    return {
        "rank": item.get("rank"),
        "index": item.get("index"),
        "source_url": item.get("source_url"),
        "source_refs": item.get("source_refs") or [],
        "published_at": item.get("published_at"),
        "source_type": item.get("source_type"),
        "source_title": item.get("source_title"),
        "source_summary": item.get("source_summary"),
        "entity_anchor": item.get("entity_anchor"),
        "entities": item.get("entities") or [],
        "action": item.get("action"),
        "fact_particles": item.get("fact_particles") or [],
        "image_evidence": item.get("image_evidence") or [],
        "reader_pull": item.get("reader_pull"),
        "selection_fit": item.get("selection_fit"),
        "facts": {
            "title": facts.get("title"),
            "content": facts.get("content"),
            "interpretation": facts.get("interpretation"),
            "status": facts.get("status"),
            "item_kind": facts.get("item_kind"),
        },
        "stakes": item.get("stakes"),
    }


def prompt_input_context(
    context: dict[str, Any],
    *,
    current_item: dict[str, Any] | None = None,
    scope: str = "all",
    max_chars: int = 36000,
) -> str:
    brief = context.get("editorial_brief") if isinstance(context.get("editorial_brief"), dict) else {}
    ranked = [compact_prompt_item(item) for item in (brief.get("ranked_items") or []) if isinstance(item, dict)]
    selected_urls = {str(item.get("source_url") or "").strip() for item in ranked if str(item.get("source_url") or "").strip()}
    candidate_review = context.get("candidate_review") if isinstance(context.get("candidate_review"), dict) else {}
    candidates = [
        candidate
        for candidate in (candidate_review.get("candidates") or [])
        if isinstance(candidate, dict) and str(candidate.get("url") or "").strip() in selected_urls
    ][:10]
    candidate_digest = {
        "status": candidate_review.get("status"),
        "hot_window_hours": candidate_review.get("hot_window_hours"),
        "blocking_findings": candidate_review.get("blocking_findings") or [],
        "selected_candidates": candidates,
    }
    if scope == "item" and current_item:
        current_index = int(current_item.get("index") or 0)
        current = compact_prompt_item(current_item)
        image_manifest = context.get("image_manifest") if isinstance(context.get("image_manifest"), dict) else {}
        image_manifest_item = {}
        for raw_image_item in image_manifest.get("items") or []:
            if not isinstance(raw_image_item, dict):
                continue
            if int(raw_image_item.get("index") or 0) == current_index:
                image_manifest_item = raw_image_item
                break
        dayline = [
            {
                "index": item.get("index"),
                "entity_anchor": item.get("entity_anchor"),
                "action": item.get("action"),
                "reader_pull": item.get("reader_pull"),
                "source_url": item.get("source_url"),
            }
            for item in ranked
            if int(item.get("index") or 0) != current_index
        ]
        payload: dict[str, Any] = {
            "date": context.get("date"),
            "hot_window_hours": brief.get("hot_window_hours"),
            "current_news": current,
            "current_image_manifest": image_manifest_item,
            "dayline_context": dayline,
            "allowed_source_urls": context.get("constraints", {}).get("allowed_source_urls", []),
            "style_guidance": compact_style_guidance(context),
        }
    else:
        payload = {
            "date": context.get("date"),
            "hot_window_hours": brief.get("hot_window_hours"),
            "headline_contract": brief.get("headline_contract"),
            "writing_contract": brief.get("writing_contract"),
            "ranked_items": ranked,
            "candidate_review": candidate_digest,
            "image_manifest": context.get("image_manifest"),
            "allowed_source_urls": context.get("constraints", {}).get("allowed_source_urls", []),
            "style_guidance": compact_style_guidance(context),
        }
    return stable_json(payload, max_chars=max_chars)


def input_materials_prompt(
    context: dict[str, Any],
    *,
    current_item: dict[str, Any] | None = None,
    scope: str = "all",
    max_context_chars: int = 36000,
) -> str:
    return (
        "<input_materials>\n"
        f"{prompt_input_context(context, current_item=current_item, scope=scope, max_chars=max_context_chars)}\n"
        "</input_materials>"
    )


def wechat_prompt_preamble(
    context: dict[str, Any],
    *,
    current_item: dict[str, Any] | None = None,
    scope: str = "all",
    max_context_chars: int = 36000,
) -> str:
    return (
        "# 角色\n"
        f"{lumi_article_role()}\n\n"
        "# 执行原则\n"
        f"{prompt_execution_principles()}\n\n"
        "# 统一文本风格\n"
        f"{lumi_current_style_contract()}\n\n"
        "# 语言选择\n"
        f"{language_policy_prompt()}\n\n"
        "# 事实边界\n"
        f"{factual_boundary_prompt()}\n\n"
        "# 写作方法\n"
        f"{style_guidance_prompt(context)}\n\n"
        "# 输入材料\n"
        f"{input_materials_prompt(context, current_item=current_item, scope=scope, max_context_chars=max_context_chars)}"
    )


def title_prompt_preamble(context: dict[str, Any], *, max_context_chars: int = 32000) -> str:
    return (
        "# 角色\n"
        f"{lumi_title_role()}\n\n"
        "# 执行原则\n"
        f"{prompt_execution_principles()}\n\n"
        "# 统一文本风格\n"
        f"{lumi_current_style_contract()}\n\n"
        "# 语言选择\n"
        f"{language_policy_prompt()}\n\n"
        "# 事实边界\n"
        f"{factual_boundary_prompt()}\n\n"
        "# 标题方法\n"
        f"{style_guidance_prompt(context)}\n"
        f"{title_policy_prompt()}\n\n"
        f"{title_cover_playbook_prompt()}\n\n"
        "# 输入材料\n"
        f"{input_materials_prompt(context, max_context_chars=max_context_chars)}"
    )


def video_prompt_preamble(context: dict[str, Any], *, max_context_chars: int = 32000) -> str:
    return (
        "# 角色\n"
        f"{lumi_video_role()}\n\n"
        "# 执行原则\n"
        f"{prompt_execution_principles()}\n\n"
        "# 统一文本风格\n"
        f"{lumi_current_style_contract()}\n\n"
        "# 语言选择\n"
        f"{language_policy_prompt()}\n\n"
        "# 事实边界\n"
        f"{factual_boundary_prompt()}\n\n"
        "# 写作方法\n"
        f"{style_guidance_prompt(context, include_methodology=True)}\n\n"
        "# 视频与口播风格\n"
        f"{video_style_policy_prompt()}\n\n"
        "# 输入材料\n"
        f"{input_materials_prompt(context, max_context_chars=max_context_chars)}"
    )


def platform_prompt_preamble(context: dict[str, Any], *, max_context_chars: int = 30000) -> str:
    return (
        "# 角色\n"
        f"{lumi_platform_role()}\n\n"
        "# 执行原则\n"
        f"{prompt_execution_principles()}\n\n"
        "# 统一文本风格\n"
        f"{lumi_current_style_contract()}\n\n"
        "# 语言选择\n"
        f"{language_policy_prompt()}\n\n"
        "# 事实边界\n"
        f"{factual_boundary_prompt()}\n\n"
        "# 写作方法\n"
        f"{style_guidance_prompt(context, include_methodology=True)}\n\n"
        "# 输入材料\n"
        f"{input_materials_prompt(context, max_context_chars=max_context_chars)}"
    )


def editor_map_prompt(context: dict[str, Any]) -> str:
    return (
        f"{wechat_prompt_preamble(context, max_context_chars=36000)}\n\n"
        "# 当前任务\n"
        "先做今天的主编地图，不写正文。请读完整天事实，判断这一期真正的主线、读者对象、标题方向、"
        "每条新闻在文章里的功能、需要铺垫的技术概念，以及它和前后新闻的关系。\n\n"
        "# 输出格式\n"
        "输出 Markdown：\n"
        "# 今日编辑地图\n"
        "## 全篇主线\n"
        "写 1 段主线判断。\n"
        "## 读者为什么要读\n"
        "写 2-4 条具体理由。\n"
        "## 新闻角色\n"
        "每条新闻用一个三级标题，说明：具体主体承担的文章角色、最有质感的原文细节、需要先铺垫的普通问题、"
        "首次出现的技术术语、解释台阶、产业判断角度、和前后文的承接关系。\n"
        "## 技术术语过桥\n"
        "列出今天最可能卡住普通读者的术语或观点；每个术语写：普通问题 -> 术语名称 -> 机制一句话 -> 对读者的影响。\n"
        "## 开头和结尾设计\n"
        "为开头选一个能让读者停下来的具体细节、场景、反差或悬念缺口；"
        "为结尾选一个能总结或升华通篇内容的收束角度。开头负责吸引人读下去，结尾负责让人带走判断，二者不能复用同一套句式。\n"
        "## 句式避让\n"
        "列出今天成稿里需要错开的开头方式、判断句式和收束方式。不要使用任何“这条…”“这篇…”“材料里”等偷懒指代，直接写具体媒体、公司、论文或产品。"
    )


def wechat_draft_segment_prompt(
    context: dict[str, Any],
    item: dict[str, Any] | None,
    paragraph_kind: str,
    *,
    editor_map: str,
    previous_text: str = "",
) -> str:
    item_text = stable_json(item, max_chars=18000) if item else ""
    if paragraph_kind == "intro":
        task = (
            "写微信公众号开头。请把它当作专栏第一屏，而不是日报导语：从今天事实包中的一个具体细节、使用瞬间、反常识观察或未完成问题入手，"
            "让读者先看见一个真实动作和它背后的张力，再自然带出这一期要追的主线。长度 1-2 段，不提前罗列新闻清单，"
            "不要写“今天为什么值得看”这几个字。"
        )
    elif paragraph_kind == "outro":
        task = (
            "写微信公众号结尾。请像主编落笔：总结今天几条新闻共同露出的变化，"
            "再把它升华到人的判断、工作、信任或选择上。长度 1-2 段；不要复述新闻列表，不要写“读完之后把注意力放在哪里”这几个字。"
        )
    else:
        task = (
            "直接写这一条新闻的完整文字稿。先不要套结构，也不要为了字段而写字段；"
            "把当前新闻当作一段可以直接给读者看的正文来写。请讲清完整上下文：主体是谁，哪一天发生了什么，"
            "来源页面或报道说了什么关键事实；再讲它会影响谁，改变哪些等待、成本、信任、安全或工作方式。"
            "如果需要英文专有名词，保留实体名；普通概念尽量翻成中文，并在同一句里交代现实场景。"
            "不要使用离开上下文就看不懂的指代，例如“那条帖子”“这个事情”“这条新闻”“这篇报道”“这篇当天稿”“材料里”“输入材料里”。"
            "媒体名后面要补足报道对象，论文站点后面要补足论文题名。"
        )
    return (
        f"{wechat_prompt_preamble(context, current_item=item, scope='item' if item else 'all', max_context_chars=28000)}\n\n"
        "# 今日主编地图\n"
        f"{editor_map.strip()}\n\n"
        "# 已完成前文\n"
        f"{previous_text[-5000:].strip() or '(暂无)'}\n\n"
        "# 当前任务\n"
        f"{task}\n\n"
        "# 输出格式\n"
        "只输出读者会看到的自然文字。新闻正文阶段可以不写标题，不写字段，不写清单。"
        "不要使用任何“这条…”“这篇…”“材料里”等偷懒指代；需要指代时直接写具体媒体、公司、论文、产品或事件。\n\n"
        "# 当前新闻事实\n"
        f"{item_text}"
    )


def title_prompt(context: dict[str, Any], editor_map: str = "") -> str:
    return (
        f"{title_prompt_preamble(context, max_context_chars=32000)}\n\n"
        "# 今日主编地图\n"
        f"{editor_map.strip() or '(未生成主编地图)'}\n\n"
        "# 当前任务\n"
        "请重写今天整套外显标题：统一对外标题、封面文案和文件名。"
        "主传播标题、微信标题、视频标题和 B站标题必须使用同一句话，不再按平台拆成多个版本。"
        "这句统一标题要同时适合公众号、视频和 B站：有人话、有具体实体、有点击理由，但不浮夸。"
        "先读完事实底稿，再判断今天真正能让读者点开的矛盾：谁在做什么、它改变了什么成本或入口、读者为什么现在要看。"
        "标题里的传播心理必须是人能感受到的：少写“抢工作流”“能力提升”这类抽象话，"
        "多写“少等一次审批”“修图师少做一遍苦活”“家长多一道求助线”“小公司被落下”等具体人和后果。"
        "标题要像专业 AI 科技公众号编辑写给真实读者看的标题：有信息密度、有悬念、有明确主语，但不浮夸。"
        "主标题使用具体公司、模型、产品或项目名作为主语；同时要把技术动作翻译成普通人能想象的场景变化。"
        "不要让陌生代号独占标题的理解成本；如果使用产品名、模型名或协议名，标题里必须同时出现它影响的真实对象、场景或代价。"
        "AI / 模型 / 系统 / 工作流只作为判断背景。"
        "如果今天有多条强新闻，可以用两个实体形成张力；如果只有一条最强，就让一个实体和一个具体后果站在标题中心。"
        "标题、封面和文件名都不得出现任何“这条…”“这篇…”“这件…”“那条…”等偷懒指代；要直接写清具体主体和具体变化。"
        "封面文案要比标题更短、更狠、更视觉化；只有没有稳定中文译名的公司名、产品名、模型名、论文名、协议名或仓库名可以保留英文。"
        "其他概念尽量写中文，例如 credentials 写凭证或密钥，regression harness 写回归测试框架。英文实体不能独自承担理解成本。"
        "封面主标题不承担完整解释，只承担一秒内让人停下来的任务；"
        "封面副标题再补一个具体后果或场景。封面必须让第一次刷到的人不用背景知识也知道："
        "当前事实和什么使用场景、成本、入口或风险有关。\n\n"
        "# 输出格式\n"
        "输出 Markdown，每行一项，严格使用这些中文标签，方便脚本读取；正文之外省略解释和 JSON 格式。\n"
        "主传播标题：今天唯一对外标题，具体实体 + 真实冲突/反差 + 后果，建议 18-34 字。\n"
        "正文标题：18-30 字，适合作为公众号 DOCX 正文大标题，具体、顺口、有主语。\n"
        "微信标题：必须和主传播标题完全一致。\n"
        "视频标题：必须和主传播标题完全一致。\n"
        "B站标题：必须和主传播标题完全一致。\n"
        "封面主标题：6-18 个中文视觉字，像 B站/YouTube 缩略图钩子；优先短词、强动词、问号或对比，不写完整长句。\n"
        "封面副标题：6-18 个中文视觉字，解释主标题的后果或读者关心点，不写半句话，不重复主标题。\n"
        "文件名短标题：保留关键实体，20 字以内。\n"
        "标题主语：具体公司/模型/产品名。\n"
        "标题动作：真实动作。\n"
        "标题后果：读者为什么会点开。\n"
        "封面左侧：两条，每条 6-12 字，用分号隔开；写可感知的场景、数字或变化。\n"
        "封面右侧：两条，每条 6-12 字，用分号隔开；写可感知的场景、数字或变化。"
    )


def title_repair_prompt(context: dict[str, Any], current_title_copy: str, findings: list[str], editor_map: str = "") -> str:
    return (
        f"{title_prompt_preamble(context, max_context_chars=28000)}\n\n"
        "# 今日主编地图\n"
        f"{editor_map.strip() or '(未生成主编地图)'}\n\n"
        "# 当前任务\n"
        "下面这版标题文案没有通过硬校验。请只重写标题和封面文案，仍然输出同样的 Markdown 标签。\n"
        "只保留标签行；正文之外省略解释和 JSON 格式。\n"
        "没有被未通过项点名的问题，尽量保持原统一标题和文件名短标题的传播方向，不要借一次封面修复改掉整天的主标题。\n"
        "除了长度问题，也要检查读者理解成本：陌生技术名不能独占标题，必须同时写出它改变的真实使用场景、成本、入口或风险。\n"
        "硬限制：主传播标题、微信标题、视频标题和 B站标题必须完全相同；正文标题 18-30 字；"
        "封面主标题 6-18 个视觉字，必须短、粗、准，适合放大到缩略图；封面主标题和副标题中文主导，只有没有稳定中文译名的实体名可以保留英文；"
        "封面副标题 6-18 字；文件名短标题 20 字以内。\n"
        "标题必须保留事实包中的具体实体或产品名，优先使用 editorial_brief 中的 entity_anchor、entities 和 headline_subject。"
        "如果标题里有英文实体，中文部分要更短，保留一个清楚的传播钩子。"
        "标题、封面和文件名都不得出现任何“这条…”“这篇…”“这件…”“那条…”等偷懒指代；要直接写清具体主体和具体变化。"
        "写完后逐行自检长度，任何一行超限就立刻改短；标题文本由模型自己写短，脚本只做校验。"
        "标题只围绕本次输入里的日期和新闻实体。\n\n"
        f"未通过项：{'; '.join(findings)}\n\n"
        f"当前标题文案：\n{current_title_copy}"
    )


def video_screen_prompt(context: dict[str, Any], editor_map: str = "", narration_text: str = "") -> str:
    narration_section = (
        "# 已生成口播稿\n"
        f"{narration_text.strip()}\n\n"
        if narration_text.strip()
        else "# 已生成口播稿\n(尚未提供；请依据事实材料写画面文案。)\n\n"
    )
    return (
        f"{video_prompt_preamble(context, max_context_chars=32000)}\n\n"
        "# 今日主编地图\n"
        f"{editor_map.strip() or '(未生成主编地图)'}\n\n"
        f"{narration_section}"
        "# 当前任务\n"
        "请写视频页面文案，只用于画面截图，不生成视频。画面文案不是摘要，要像编辑在每页上放的判断卡片。"
        "必须严格沿用输入报告里的新闻顺序：`新闻 N` 对应报告里的第 N 条新闻，禁止为了叙事顺手重排。"
        "本任务必须以已经生成的口播稿为上游：信息卡片和图片页说明从口播稿里提取事实、影响和判断，"
        "不要另起一套叙事，也不要新增口播里没有支撑的事实。"
        "这版视频截图即使没有 TTS，也要让观众靠画面读懂主要内容；所以需要讲清楚的内容优先放进信息卡片，"
        "再由图片展示页标题下方的一段说明承接完整语境。"
        "顶部进度条保留，每条新闻起一个 4-10 字的引流小标题；part 名要像可点击目录，"
        "既能看出主语或场景，也能看出为什么要继续看，例如 修图也上班、政务进门、账单失控。"
        "part 名优先使用“实体/人群 + 具体变化”的结构，避免只写抽象概念；如果 8 字装不下，保留最有记忆点的名词和动词。"
        "屏幕卡片参考 shadcn/Magic UI 常见信息卡片思路：一个主卡负责视觉重心，两张副卡负责补充；"
        "每张卡只讲一个层级，靠标题、分点、强调词和图标建立扫读路径。"
        "内容结构采用“关键事实 + 影响的人 + 后续观察”，不写三张平均用力的摘要卡。"
        "信息卡片要承担讲解功能：第一张把事件、来源、时间和动作讲清楚；第二张把人或组织承受的变化讲清楚；"
        "第三张把后续该盯的信号讲清楚。不要把这些内容藏在口播里。"
        "如果卡片涉及技术词，标题先写具体变化，正文用一句话把技术词翻成影响，不堆概念。"
        "信息卡片用 `；` 分成短分点，让画面更直观；不同卡片使用不同 icon，"
        "优先选能对应场景的 emoji，例如 🎨 🏛️ 📚 ⚙️ 💸 🧭 🔐 🧰 ⏱️。"
        "每条新闻的画面主标题要有具体主语：公司、模型、产品、论文、项目或平台名放在标题前半句，"
        "不能只写“长上下文的压力”“真正变化”“系统能力”这类抽象主语。"
        "每条新闻写 3 行卡片，一行一个卡片。卡片标题要像人写的编辑判断，具体、带主语或场景，避免使用“事实锚点”“人的影响”“继续观察”这类模板标题。"
        "卡片标题必须短，建议 6-14 个中文字符，最长不得超过 18 个视觉字符；英文实体名放进正文分点，不放进卡片标题。"
        "第一张主卡写 2-3 个事实点，尽量含实体、数字、时间、动作或来源中的至少两个；标题写事件真正的转折。"
        "第二张写谁会受影响，以及等待、返工、成本、信任或安全怎样变化；标题写人的处境，不要写抽象分类名。"
        "第三张写接下来该看哪个具体信号，不写空泛建议；标题写一个可被记住的判断句。"
        "不要写“观看理由”“今天看它”“判断框架”“先看事实”，也不要把编辑提纲直接露出来。"
        "卡片正文是短而完整的人话句子，不能出现省略号，也不能出现任何“这条…”“这篇…”结构；需要承接时直接写 The Atlantic、MorphCast、公司、员工、HR 或具体事件。\n\n"
        "# 输出格式\n"
        "输出 Markdown，格式如下；正文之外省略解释和 JSON 格式：\n"
        "## 顶部进度条\n"
        "- 封面\n- 开场\n- 每条新闻 4-10 字的引流小标题\n- 结尾\n\n"
        "然后每条新闻一个 `## 新闻 N：标题`，下面写三行卡片：`卡片：人话标题｜分点1；分点2；分点3｜icon｜强调词`。\n"
        "三行卡片标题必须各不相同，像视频编辑写给观众看的判断，不使用固定模板词；标题最长 18 个视觉字符，写完必须自检改短。\n"
        "每行只写一个卡片，四段之间用全角竖线分隔；强调词写 2-8 个中文字，用来做卡片里的视觉标签。\n"
        "part 名要能看出是谁或什么场景，不只写概念；正文里保留公司名和产品名，表达要自然。\n"
        "第一张主卡写 2-3 个事实分点，第二、三张各写 2 个分点；每个分点都要是可以直接放到画面上的完整短句，"
        "不要写成机械清单。"
    )


def video_screen_repair_prompt(
    context: dict[str, Any],
    current_video_copy: str,
    error: str,
    editor_map: str = "",
    narration_text: str = "",
) -> str:
    narration_section = (
        "# 已生成口播稿\n"
        f"{narration_text.strip()}\n\n"
        if narration_text.strip()
        else ""
    )
    return (
        f"{video_prompt_preamble(context, max_context_chars=28000)}\n\n"
        "# 今日主编地图\n"
        f"{editor_map.strip() or '(未生成主编地图)'}\n\n"
        f"{narration_section}"
        "# 当前任务\n"
        "下面这版视频页面文案没有通过解析。请只重写视频页面文案，仍然输出 Markdown；正文之外省略解释和 JSON 格式。\n"
        "必须以口播稿为上游，从口播里提取信息卡片内容，不新增另一套叙事。\n"
        "必须严格沿用输入报告里的新闻顺序：`新闻 N` 对应报告里的第 N 条新闻，禁止重排。\n"
        "硬规则：顶部进度条包含封面、开场、所有新闻 part 名、结尾；每条新闻必须正好 3 行卡片。"
        "每一行卡片必须严格使用：卡片：标题｜分点1；分点2；分点3｜icon｜强调词。"
        "每条新闻保持 3 张卡，标题必须具体、有人味、有主语或场景，且最长 18 个视觉字符；禁止使用“事实锚点”“人的影响”“继续观察”。"
        "顶部 part 名 4-10 个 Unicode 字符，要像可点击小标题；正文一句话，可用 `；` 分成 2 个短分点。"
        "不要写“观看理由”“今天看它”“判断框架”“先看事实”，不要出现省略号，也不要出现任何“这条…”“这篇…”结构。\n\n"
        f"未通过原因：{error}\n\n"
        f"当前文案：\n{current_video_copy}"
    )


def video_narration_prompt(context: dict[str, Any], editor_map: str = "") -> str:
    issue_label = str(context.get("issue_label") or "第 N 期").strip()
    return (
        f"{video_prompt_preamble(context, max_context_chars=34000)}\n\n"
        "# 今日主编地图\n"
        f"{editor_map.strip() or '(未生成主编地图)'}\n\n"
        "# 当前任务\n"
        "请写 Lumi 口播稿。它不是把文章读出来，也不是 AI 摘要，而是 Lumi 在给熟悉科技的人讲今天的判断。"
        "必须严格沿用输入报告里的新闻顺序：`新闻 N` 对应报告里的第 N 条新闻，禁止为了叙事顺手重排；"
        "如果需要承接关系，用转场句解决，不移动新闻顺序。"
        f"本期编号是 {issue_label}。开场不假定早上、晚上或任何具体时段；"
        f"第一句直接自然问好，第二句必须介绍“这里是 Lumi 的 AI 日报{issue_label}”，再进入当天真实场景、产品动作或反常识冲突。"
        "不要先宣布“今天这组 AI 消息”或“我最先记住的是”。"
        "口播要有更强的人文感：先讲人的麻烦、等待、重复劳动、信任成本或判断压力，再讲技术名词；"
        "像一个有经验的人提醒朋友，而不是一段公司白皮书。"
        "少用“系统能力、正式工作流、能力边界、入口、基线”这类抽象词；必须使用时，先用人话解释它落到谁身上。"
        "口播要轻快、有判断、有一点温度，但不是段子手，也不是报告朗读。"
        "每条新闻至少包含一个事实锚点、一句人能听懂的解释、一句编辑判断；"
        "硬术语先用真实场景铺垫，再说术语本身，最后落到产品或工程后果。"
        "每条新闻的显示标题必须有具体主语，把公司、模型、产品、论文或项目名放在标题前半句。"
        "口播里不要用任何“这条…”“这篇…”“材料里”这类偷懒指代；需要指代时直接说具体公司、媒体、论文或产品。"
        "结尾要回到开场的具体问题，用一个可执行判断标准收住，而不是复述今天看了哪些新闻。"
        "口播要和字幕逐句对应，字幕不写别名解释，数字和版本号保持事实准确。"
        "同时要和画面文案互相补位：最重要的事实、影响和判断必须能在信息卡片与图片页说明中看见，"
        "口播负责把这些画面信息串成顺滑的听觉路径。"
        "片尾的中文金句必须是名人名言的中文版本，不允许写 Lumi 自己临时编的一句话；"
        "中文金句后必须给出金句作者，优先选择和劳动、工具、判断、效率、技术有关的真实名人。"
        "Fish TTS 方括号 tag 留给渲染链路，口播稿只写自然语言；情绪由语义和停顿自然体现。\n\n"
        "# 输出格式\n"
        "输出 Markdown，使用这些中文标签方便脚本读取；正文之外省略解释和 JSON 格式：\n"
        "## 开场\n显示标题：...\n口播标题：...\n情绪：warm / curious / measured / brighter / thoughtful 中选一个\n口播：...\n\n"
        "每条新闻写 `## 新闻 N：标题`，下面写：\n"
        "显示标题：...\n口播标题：...\n情绪：warm / curious / measured / brighter / thoughtful 中选一个\n钩子：...\n判断：...\n口播：...\n\n"
        "最后写：\n## 结尾\n显示标题：...\n口播标题：...\n情绪：warm / curious / measured / brighter / thoughtful 中选一个\n片尾一：...\n片尾二：...\n中文金句：...\n金句作者：...\n口播：...\n"
        "只写这些标签和读者会听到/看到的文字。"
    )


def video_narration_repair_prompt(
    context: dict[str, Any],
    *,
    current_narration: str,
    findings: list[str],
    editor_map: str = "",
) -> str:
    issue_label = str(context.get("issue_label") or "第 N 期").strip()
    return (
        f"{video_prompt_preamble(context, max_context_chars=28000)}\n\n"
        "# 今日主编地图\n"
        f"{editor_map.strip() or '(未生成主编地图)'}\n\n"
        "# 当前任务\n"
        "下面这版口播稿没有通过主线 QA。请重写完整 `video-narration.md`，保留新闻顺序、事实、实体、标题层级和输出标签，"
        "只修复 QA 指出的表达问题，同时消除同类隐患。"
        f"开场仍然不假定早上、晚上或具体时间；第一句自然问好，第二句必须介绍“这里是 Lumi 的 AI 日报{issue_label}”。"
        "口播和字幕里不得出现任何“这条…”“这篇…”“这件…”“那条…”“材料里”“前面提到”等离开上下文就不清楚的指代；"
        "需要承接时直接说具体媒体、公司、论文、产品、机构或事件。"
        "片尾金句必须是真实名人名言的中文版本，并给出作者。\n\n"
        "# 未通过原因\n"
        + "\n".join(f"- {finding}" for finding in findings)
        + "\n\n# 输出格式\n"
        "沿用原格式：`## 开场`、每条 `## 新闻 N：标题`、`## 结尾`，并使用显示标题、口播标题、情绪、钩子、判断、片尾一、片尾二、中文金句、金句作者、口播等标签。"
        "只输出 Markdown 正文。\n\n"
        "# 待修复口播稿\n"
        f"{current_narration.strip()}"
    )


def platform_prompt(context: dict[str, Any], editor_map: str = "") -> str:
    return (
        f"{platform_prompt_preamble(context, max_context_chars=30000)}\n\n"
        "# 今日主编地图\n"
        f"{editor_map.strip() or '(未生成主编地图)'}\n\n"
        "# 当前任务\n"
        "请写 B站发布文案。文案要从今天主线出发，让人知道这期为什么值得点开。"
        "短文案也要继承最新风格：用具体实体和真实变化开场，不写空泛总结；"
        "遇到技术词时，用一句人话解释它为什么影响读者的工作、成本或选择。\n\n"
        "# 输出格式\n"
        "输出 Markdown；正文之外省略解释和 JSON 格式：\n"
        "## Bilibili\n标题：...\n简介：...\n动态：...\n标签：AI,科技,..."
    )


def content_parallelism() -> int:
    configured = os.environ.get("AI_DAILY_CONTENT_PARALLELISM", "").strip()
    try:
        value = int(configured or DEFAULT_CONTENT_PARALLELISM)
    except ValueError:
        value = DEFAULT_CONTENT_PARALLELISM
    return max(1, min(value, 6))


def content_task_retries() -> int:
    configured = os.environ.get("AI_DAILY_CONTENT_TASK_RETRIES", "").strip()
    try:
        value = int(configured or DEFAULT_CONTENT_TASK_RETRIES)
    except ValueError:
        value = DEFAULT_CONTENT_TASK_RETRIES
    return max(0, min(value, 3))


def call_markdown_task(context: dict[str, Any], task: dict[str, Any]) -> None:
    last_error: Exception | None = None
    attempts = content_task_retries() + 1
    for attempt in range(1, attempts + 1):
        try:
            call_codex_markdown(
                context,
                slug=str(task["slug"]) if attempt == 1 else f"{task['slug']}-retry-{attempt - 1}",
                prompt=str(task["prompt"]),
                output_path=Path(task["output_path"]),
            )
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= attempts:
                break
    raise RuntimeError(f"Markdown generation task failed: {task['slug']}: {last_error}") from last_error


def call_markdown_tasks(context: dict[str, Any], tasks: list[dict[str, Any]]) -> None:
    workers = min(content_parallelism(), len(tasks))
    if workers <= 1:
        for task in tasks:
            call_markdown_task(context, task)
        return
    failed: list[tuple[dict[str, Any], Exception]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                call_codex_markdown,
                context,
                slug=str(task["slug"]),
                prompt=str(task["prompt"]),
                output_path=Path(task["output_path"]),
            ): task
            for task in tasks
        }
        for future in concurrent.futures.as_completed(futures):
            task = futures[future]
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001
                failed.append((task, exc))
    for task, _exc in failed:
        call_markdown_task(context, task)


def write_markdown(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def report_source_trace_path(report: TechDailyReport) -> Path:
    report_path = Path(report.path)
    return report_path.with_name(f"{report_path.stem}.source-trace.md")


def source_trace_excerpt(report: TechDailyReport, index: int | None = None, *, max_chars: int = 12000) -> str:
    source_trace = read_text_file(report_source_trace_path(report), max_chars=160000)
    if not source_trace or index is None:
        return source_trace[:max_chars].rstrip()
    pattern = re.compile(rf"(^##\s+{re.escape(str(index))}\.\s.*?)(?=^##\s+\d+\.\s|\Z)", re.M | re.S)
    match = pattern.search(source_trace)
    if not match:
        return ""
    return match.group(1).strip()[:max_chars].rstrip()


def source_pack_index(source_pack_dirs: list[Path]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for source_pack_dir in source_pack_dirs:
        for url, meta in load_source_pack(source_pack_dir).items():
            enriched = dict(meta)
            source_dir = source_pack_dir / str(meta.get("dir") or "")
            if source_dir.exists():
                enriched["_content_md"] = read_text_file(source_dir / "content.md", max_chars=9000)
                enriched["_raw_json"] = read_text_file(source_dir / "raw.json", max_chars=3000)
            indexed[url] = enriched
    return indexed


def item_source_material(item: TechDailyItem, source_by_url: dict[str, dict[str, Any]]) -> str:
    refs = [*(item.source_refs or []), item.source_url]
    chunks: list[str] = []
    seen: set[str] = set()
    for raw_ref in refs:
        url = canonicalize_url(str(raw_ref or ""))
        if not url or url in seen:
            continue
        seen.add(url)
        meta = source_by_url.get(url, {})
        parts = [
            f"URL: {url}",
            f"标题: {meta.get('title') or meta.get('source_title') or ''}",
            f"发布时间: {meta.get('published_at') or ''}",
            f"作者/来源: {meta.get('source_author') or meta.get('feed_name') or meta.get('domain') or ''}",
            f"摘录: {meta.get('excerpt') or meta.get('summary') or meta.get('text_excerpt') or ''}",
                str(meta.get("_content_md") or "")[:5000],
        ]
        chunks.append("\n".join(part for part in parts if str(part).strip()))
    if not chunks:
        chunks.append(
            "\n".join(
                [
                    f"URL: {item.source_url}",
                    f"标题: {item.title}",
                    f"事实: {item.content}",
                    f"解释: {item.interpretation}",
                ]
            )
        )
    return "\n\n---\n\n".join(chunks)[:7000]


def compact_report_for_polish(report_json: Any, index: int | None = None) -> dict[str, Any]:
    if not isinstance(report_json, dict):
        return {}
    items = report_json.get("items") if isinstance(report_json.get("items"), list) else []
    compact_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if index is not None and int(item.get("index") or 0) != index:
            continue
        compact_items.append(
            {
                "index": item.get("index"),
                "title": item.get("title"),
                "content": item.get("content"),
                "interpretation": item.get("interpretation"),
                "source_url": item.get("source_url"),
                "source_refs": item.get("source_refs"),
                "status": item.get("status"),
                "decision_impact": item.get("decision_impact"),
            }
        )
    return {
        "title": report_json.get("title"),
        "date": report_json.get("date"),
        "hot_window_hours": report_json.get("hot_window_hours"),
        "trend_words": report_json.get("trend_words"),
        "items": compact_items,
    }


def article_spine(report: TechDailyReport, title_copy: str) -> str:
    lines = [
        f"日期：{report.date}",
        f"原始标题：{report.title}",
        "标题草案：",
        title_copy.strip(),
        "",
        "今日新闻线索：",
    ]
    for item in report.items:
        lines.append(f"{item.index}. {item.title} -> {item.content} / {item.interpretation}")
    return "\n".join(lines).strip()


def wechat_polish_preamble(context: dict[str, Any]) -> str:
    _ = context
    return "\n\n".join(
        [
            "# 角色",
            lumi_article_role(),
            "# 统一文本风格",
            lumi_current_style_contract(),
            "# 改稿原则",
            (
                "只做主编级轻改稿：保留事实、URL、数字和实体名；让表达更顺、更具体、更像真人编辑。"
                "一段只承担一个任务：场景、概念铺垫、机制、后果或判断。用具体名词带出判断，减少空泛总结。"
                "每个技术观点要有理解过渡：先让普通读者知道它在解决什么问题，再写术语或机制，最后写现实影响。"
                "开头像短视频第一秒的文字钩子，第一句话就进入事实包中的动作、细节、反差或悬念；结尾像主编落笔，"
                "总结全天共同变化并留下一个更高一层的判断。过渡要靠具体事实承接，不靠导语式脚手架。"
                "不要使用“那条帖子”“这个事情”“这件事”“这条新闻”“这条更新”“这条信号”“这条研究”“这篇当天稿”“前面提到”“前两条”“材料里”“输入材料里”这类离开上下文就看不懂的指代。"
                "不要写“VentureBeat 这条”“Axios 这篇”“arXiv 这篇”这类懒省略；媒体名后面必须接完整事件、报道或论文标题。"
            ),
        ]
    )


def wechat_structure_prompt(
    context: dict[str, Any],
    *,
    draft_article: str,
    editor_map: str,
    source_trace: str,
    report: TechDailyReport,
) -> str:
    item_lines = "\n".join(f"{item.index}. {item.title}｜{item.source_url}" for item in report.items)
    return "\n\n".join(
        [
            "# 角色",
            lumi_article_role(),
            "# 语言选择",
            language_policy_prompt(),
            "# 任务",
            (
                "下面的草稿已经由模型按事实写成自然文字。现在只做结构化整理："
                "补全每条新闻的小标题，整理段落顺序，去掉重复和指代不明，但不要把文章改成字段表、模板清单或样例套写。"
                "每条新闻保留两段正文：第一段讲完整上下文、主体、日期、事件和关键事实；第二段讲影响、判断和人的处境。"
                "开头负责吸引读者继续看，结尾负责总结或升华，不复用同一套句式。"
                "正文中保留必要专有名词；普通英文概念尽量翻译为中文。"
            ),
            "# 今日新闻顺序",
            item_lines,
            "# 今日主编地图",
            (editor_map.strip() or "(未生成主编地图)")[:8000],
            "# 事实回溯",
            source_trace[:8000].strip(),
            "# 待结构化草稿",
            draft_article.strip(),
            "# 输出格式",
            (
                "输出完整 Markdown 成稿：开头自然正文；随后每条新闻一个 `## 小标题`，每个小标题下且仅有两段正文；"
                "最后一个 `## 收束标题` 和自然结尾；末尾保留 `## 参考链接`，按新闻顺序列 URL。"
                "不要输出 JSON，不要解释你的改动，不要出现任何“这条…”“这篇…”“前面提到”“材料里”“输入材料里”等不明指代。"
            ),
        ]
    )


def wechat_polish_prompt(
    context: dict[str, Any],
    *,
    segment: str,
    article_line: str,
    factual_draft: str,
    editor_map: str = "",
    previous_text: str = "",
    source_text: str = "",
    source_trace: str = "",
    draft_text: str = "",
) -> str:
    material = [
        wechat_polish_preamble(context),
        "# 当前润色任务",
        segment,
        "# 今日主编地图",
        (editor_map.strip() or "(未生成主编地图)")[:3000],
        "# 全篇主线",
        article_line[:1500],
        "# 已完成前文",
        previous_text[-1000:].strip() or "(暂无)",
        "# 事实底稿",
        factual_draft[:2500],
    ]
    if source_trace.strip():
        material.extend(["# 事实回溯底稿", source_trace.strip()[:2500]])
    if source_text.strip():
        material.extend(["# 原始相关新闻原稿", source_text.strip()[:3000]])
    if draft_text.strip():
        material.extend(["# 待润色草稿", draft_text.strip()[:3500]])
    material.extend(
        [
            "# 输出要求",
            (
                "直接输出 Markdown 成稿片段。标题任务输出一个 # 标题；开头输出自然正文；"
                "单条新闻输出一个 ## 小标题和且仅有 2 个自然段；结尾输出自然收束。"
                "请把待润色草稿当作素材，不保留它的段落骨架；优先改善节奏、具体性、技术解释、理解台阶和句式变化。"
                "首次出现的技术术语要配一个普通问题或工作场景，让读者先懂为什么需要这个概念。"
                "单条新闻第一段讲清楚完整上下文、主体、事件和关键事实；第二段讲清楚影响、判断和人的处境。"
            ),
        ]
    )
    return "\n\n".join(material)


def wechat_final_edit_prompt(context: dict[str, Any], *, article: str, editor_map: str, source_trace: str) -> str:
    return "\n\n".join(
        [
            wechat_polish_preamble(context),
            "# 当前任务",
            (
                "对下面整篇微信公众号稿做最后一轮主编改稿。目标是统一语气、消除重复句式、增强具体细节和自然过渡。"
                "同时检查技术理解台阶：遇到术语、缩写、架构名、芯片名、benchmark 或论文方法，"
                "正文要先铺普通问题，再解释机制，再给现实影响；相邻段落不能连续堆术语。"
                "请特别处理开头和结尾：开头第一句直接落到事实包中的具体动作、产品细节、反差或悬念，"
                "让读者有继续读下去的理由；结尾总结或升华通篇内容，落到人的判断、工作、信任或选择。"
                "把导语式过渡改成具体承接，例如用上一节留下的问题、某个实体的动作、一个成本或边界变化来推进。"
                "每条新闻小节必须只有 2 个自然段，不许写成 3 段以上；不得出现没有上下文的“那条帖子”“这个事情”“这件事”“这条新闻”“这条更新”“这条信号”“这条研究”“这篇当天稿”“前面提到”“前两条”“材料里”“输入材料里”等指代。"
                "媒体名、平台名、论文站点名后面不能直接接“这条/这篇”，必须补足报道对象或论文标题。"
                "保留标题层级、新闻顺序、参考链接、URL、日期、数字、实体名和事实关系。"
                "输出完整 Markdown 成稿。"
            ),
            "# 今日主编地图",
            (editor_map.strip() or "(未生成主编地图)")[:9000],
            "# 事实回溯底稿",
            source_trace[:8000].strip(),
            "# 待改稿全文",
            article.strip(),
        ]
    )


def wechat_article_repair_prompt(
    context: dict[str, Any],
    *,
    article: str,
    error: str,
    editor_map: str,
    source_trace: str,
) -> str:
    return "\n\n".join(
        [
            wechat_polish_preamble(context),
            "# 当前任务",
            (
                "下面这篇微信公众号成稿没有通过主线 QA。请重写完整 Markdown 成稿，保留事实、URL、标题层级、新闻顺序和两段正文结构，"
                "只修复 QA 指出的表达问题，同时顺手消除相同类型的隐患。"
                "不得出现任何“这条…”“这篇…”“这件…”“那条…”“材料里”“前面提到”等离开上下文就不清楚的指代；"
                "需要承接时直接写具体媒体、公司、论文、产品、人物、机构或事件。"
                "每条新闻仍然只有 2 个自然段；开头负责吸引读者继续读，结尾负责总结或升华。"
                "输出完整 Markdown 成稿，不输出解释。"
            ),
            "# 未通过原因",
            error,
            "# 今日主编地图",
            (editor_map.strip() or "(未生成主编地图)")[:9000],
            "# 事实回溯底稿",
            source_trace[:8000].strip(),
            "# 待修复成稿",
            article.strip(),
        ]
    )


def segment_complete(text: str, *, label: str, min_chars: int, heading_prefix: str | None = None) -> list[str]:
    findings: list[str] = []
    value = text.strip()
    if len(value) < min_chars:
        findings.append(f"{label}_too_short")
    if heading_prefix and not value.startswith(heading_prefix):
        findings.append(f"{label}_missing_heading")
    if heading_prefix == "# ":
        return findings
    if value and value[-1] not in "。！？.!?）)」』”’":
        findings.append(f"{label}_appears_truncated")
    return findings


def call_polish_task(context: dict[str, Any], task: dict[str, Any]) -> None:
    call_codex_markdown(
        context,
        slug=str(task["slug"]),
        prompt=str(task["prompt"]),
        output_path=Path(task["output_path"]),
    )


def call_polish_task_checked(context: dict[str, Any], task: dict[str, Any]) -> None:
    call_polish_task(context, task)
    output_path = Path(task["output_path"])
    findings = segment_complete(
        read_text_file(output_path, max_chars=80000),
        label=str(task["slug"]),
        min_chars=int(task.get("min_chars") or 80),
        heading_prefix=str(task.get("heading_prefix") or "") or None,
    )
    if findings:
        retry_incomplete_polish_segments(context, [task])


def call_polish_tasks(context: dict[str, Any], tasks: list[dict[str, Any]]) -> None:
    workers = min(content_parallelism(), len(tasks))
    if workers <= 1:
        for task in tasks:
            call_polish_task(context, task)
        return
    failed: list[tuple[dict[str, Any], Exception]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(call_polish_task, context, task): task for task in tasks}
        for future in concurrent.futures.as_completed(futures):
            task = futures[future]
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001
                failed.append((task, exc))
    for task, _exc in failed:
        call_polish_task(context, task)


def retry_incomplete_polish_segments(context: dict[str, Any], tasks: list[dict[str, Any]]) -> None:
    for task in tasks:
        output_path = Path(task["output_path"])
        text = read_text_file(output_path, max_chars=80000)
        findings = segment_complete(
            text,
            label=str(task["slug"]),
            min_chars=int(task.get("min_chars") or 80),
            heading_prefix=str(task.get("heading_prefix") or "") or None,
        )
        if not findings:
            continue
        retry_task = {
            **task,
            "slug": f"{task['slug']}-completion-retry",
            "prompt": str(task["prompt"])
            + "\n\n# 本次修正\n上一版没有形成完整成稿片段。请重新输出完整、自然、可发表的 Markdown 成稿片段。",
        }
        call_polish_task(context, retry_task)
        retry_text = read_text_file(output_path, max_chars=80000)
        retry_findings = segment_complete(
            retry_text,
            label=str(task["slug"]),
            min_chars=int(task.get("min_chars") or 80),
            heading_prefix=str(task.get("heading_prefix") or "") or None,
        )
        if retry_findings:
            raise RuntimeError(f"Codex polish segment incomplete: {', '.join(retry_findings)}")


def assemble_polished_wechat_article(
    *,
    title: str,
    intro: str,
    items: list[str],
    outro: str,
    report: TechDailyReport,
) -> str:
    article_title = re.sub(r"^#+\s*", "", title.strip()).strip()
    article_parts: list[str] = [normalize_wechat_intro_segment(intro)]
    for report_item, item_text in zip(report.items, items):
        normalized = normalize_wechat_item_segment(item_text, fallback_title=report_item.title, article_title=article_title)
        if normalized:
            article_parts.append(normalized)
    article_parts.append(normalize_wechat_outro_segment(outro))
    article_parts.append("## 参考链接")
    for offset, item in enumerate(report.items, start=1):
        article_parts.append(f"{offset}. [{item.source_url}]({item.source_url})")
    return "\n\n".join(part for part in article_parts if part.strip()).strip() + "\n"


def heading_text(line: str) -> str:
    return re.sub(r"^#{1,6}\s*", "", line.strip()).strip()


def normalize_wechat_intro_segment(markdown: str) -> str:
    lines: list[str] = []
    for raw in str(markdown or "").splitlines():
        line = raw.rstrip()
        if line.strip().startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def normalize_wechat_item_segment(markdown: str, *, fallback_title: str, article_title: str) -> str:
    title = ""
    body_lines: list[str] = []
    for raw in str(markdown or "").splitlines():
        line = raw.rstrip()
        if line.strip().startswith("#"):
            text = heading_text(line)
            if not text:
                continue
            if not title and text != article_title:
                title = text
                continue
            body_lines.extend(["", f"**{text}**", ""])
            continue
        body_lines.append(line)
    resolved_title = title or re.sub(r"^[^A-Za-z0-9\u4e00-\u9fff]+", "", str(fallback_title or "新闻")).strip()
    body = "\n".join(body_lines).strip()
    return f"## {resolved_title}\n\n{body}".strip()


def normalize_wechat_outro_segment(markdown: str) -> str:
    title = ""
    body_lines: list[str] = []
    for raw in str(markdown or "").splitlines():
        line = raw.rstrip()
        if line.strip().startswith("#"):
            text = heading_text(line)
            if not text:
                continue
            if not title:
                title = text
                continue
            body_lines.extend(["", f"**{text}**", ""])
            continue
        body_lines.append(line)
    resolved_title = title or "收束"
    body = "\n".join(body_lines).strip()
    return f"## {resolved_title}\n\n{body}".strip()


def wechat_article_title_from_title_copy(title_copy: str, report: TechDailyReport) -> str:
    labels: dict[str, str] = {}
    for raw in title_copy.splitlines():
        line = raw.strip().lstrip("-").strip()
        if not line or "：" not in line:
            continue
        label, value = line.split("：", 1)
        labels[label.strip()] = value.strip()
    title = labels.get("正文标题") or labels.get("主传播标题") or labels.get("微信标题") or report.title
    return "# " + re.sub(r"\s+", " ", str(title or "AI日报")).strip()


def run_codex_wechat_polish(
    *,
    report: TechDailyReport,
    report_json: Any,
    context: dict[str, Any],
    content_dir: Path,
    source_pack_dirs: list[Path],
    title_copy_path: Path,
    editor_map_path: Path,
) -> dict[str, Any]:
    wechat_dir = content_dir / "wechat"
    items_dir = wechat_dir / "items"
    if wechat_dir.exists():
        shutil.rmtree(wechat_dir)
    items_dir.mkdir(parents=True, exist_ok=True)

    title_copy = read_text_file(title_copy_path, max_chars=6000)
    draft_dir = content_dir / "wechat-paragraphs"
    title_path = write_markdown(wechat_dir / "title.md", wechat_article_title_from_title_copy(title_copy, report))

    intro_path = write_markdown(wechat_dir / "intro.md", read_text_file(draft_dir / "00-intro.md", max_chars=12000))
    item_outputs: list[str] = []
    item_paths: dict[str, str] = {}
    for item in report.items:
        text = read_text_file(draft_dir / f"{item.index:02d}-news.md", max_chars=20000)
        item_path = write_markdown(items_dir / f"{item.index:02d}.md", text)
        item_paths[f"wechat-item-{item.index:02d}"] = str(item_path)
        item_outputs.append(text)
    outro_path = write_markdown(wechat_dir / "outro.md", read_text_file(draft_dir / "99-outro.md", max_chars=12000))

    polished_article = assemble_polished_wechat_article(
        title="",
        intro=read_text_file(intro_path, max_chars=12000),
        items=item_outputs,
        outro=read_text_file(outro_path, max_chars=12000),
        report=report,
    )
    source_trace = source_trace_excerpt(report, max_chars=14000)
    structure_path = wechat_dir / "wechat-structured.md"
    call_codex_markdown(
        context,
        slug="wechat-structure",
        prompt=wechat_structure_prompt(
            context,
            draft_article=polished_article,
            editor_map=read_text_file(editor_map_path, max_chars=26000),
            source_trace=source_trace,
            report=report,
        ),
        output_path=structure_path,
    )
    structured_article = read_text_file(structure_path, max_chars=160000)
    final_wechat = write_markdown(wechat_dir / "wechat-polished.md", structured_article)
    compatibility = write_markdown(content_dir / "wechat-polished.md", structured_article)
    manifest = {
        "result": "success",
        "provider": "draft_then_structure",
        "model": "codex-generated-structure",
        "reasoning_effort": env_text("AI_DAILY_CONTENT_REASONING_EFFORT", DEFAULT_REASONING_EFFORT) or DEFAULT_REASONING_EFFORT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "wechat_dir": str(wechat_dir),
        "wechat_polished": str(final_wechat),
        "wechat_structured": str(structure_path),
        "compatibility_wechat_polished": str(compatibility),
        "item_count": len(item_outputs),
        "segments": {
            "wechat-title": str(title_path),
            "wechat-intro": str(intro_path),
            **item_paths,
            "wechat-outro": str(outro_path),
        },
    }
    write_markdown(wechat_dir / "codex-polish-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def write_prompt_contract_snapshot(content_dir: Path, context: dict[str, Any]) -> Path:
    path = content_dir / "prompt-contract.md"
    body = "\n\n".join(
        [
            "# Lumi AI Daily Prompt 合约",
            "## 目标",
            "把当天经过筛选的 AI 新闻写成公众号正文、标题封面文案、视频口播和视频画面文案。所有产物先服务读者理解，再服务格式。",
            "## 共同角色",
            "Lumi 是专业、清楚、轻快、有判断、有温度的 AI 科技主编。读者关注产品、工程、创业和投资，但不默认理解每个术语。",
            "## 事实边界",
            factual_boundary_prompt(),
            "## 语言选择",
            language_policy_prompt(),
            "## 统一写法",
            lumi_current_style_contract(),
            "## 生产链路",
            (
                "1. 新闻筛选：使用 gpt-5.4-mini 从候选中选出当天最值得写的新闻，只输出简单结构。\n"
                "2. 事实写稿：模型直接基于事实为每条新闻写自然文字，不先套字段模板。\n"
                "3. 结构化：另一次模型调用把自然稿整理成公众号结构，保证每条新闻两段正文。\n"
                "4. 标题封面：从同一条主线生成统一标题和短封面文案。\n"
                "5. 视频文案：先生成完整口播稿，再从口播稿提取进度条标题、信息卡片和图片页说明。"
            ),
            "## 输出结构",
            (
                "- `selection-review.json`：`status`、`notes`、`selected[]`、`rejected[]`。\n"
                "- `wechat-paragraphs/*.md`：未经结构化的自然文字稿。\n"
                "- `wechat/wechat-structured.md`：结构化后的公众号稿。\n"
                "- `title-copy.md`：统一标题、封面主标题、副标题和文件名短标题。\n"
                "- `video-narration.md`：开场、每条新闻口播和结尾。\n"
                "- `video-screen-copy.md`：从口播提取出的顶部进度条和每条新闻三张信息卡。"
            ),
            "## 结构化原则",
            (
                "结构化只整理，不把文章改成模板。开头吸引读者进入当天主线；每条新闻两段；结尾总结或升华。"
                "视频截图优先让画面自己讲清楚：信息卡片采用主卡加副卡，主卡放关键事实，副卡放人的影响和下一步观察；"
                "图片页标题下面的一段说明从口播中提取，用较短字数解释图片对应的事实、主体和影响，让版式自然落在两行左右。"
            ),
            "## 当前日期",
            str(context.get("date") or ""),
        ]
    )
    path.write_text(body.strip() + "\n", encoding="utf-8")
    return path


def source_context(
    report_path: Path,
    report_json_path: Path,
    candidate_review_path: Path | None,
    source_pack_dirs: list[Path],
    image_manifest_path: Path | None,
    writing_profile_path: Path,
    writing_playbook_path: Path,
) -> tuple[TechDailyReport, dict[str, Any], set[str]]:
    report = parse_report(report_path)
    report_json = load_json_file(report_json_path) if report_json_path.exists() else report.to_dict()
    candidate_review = load_json_file(candidate_review_path) if candidate_review_path and candidate_review_path.exists() else {}
    pack_summaries = [summarize_pack_dir(path) for path in source_pack_dirs]
    image_manifest = load_json_file(image_manifest_path) if image_manifest_path and image_manifest_path.exists() else {}
    brief = build_editorial_brief(report, report_json=report_json, candidate_review=candidate_review, pack_summaries=pack_summaries)
    issue_no = count_issue_number(report.date)
    context = {
        "date": report.date,
        "issue_no": issue_no,
        "issue_label": f"第 {issue_no} 期",
        "editorial_brief": brief,
        "original_report_markdown": read_text_file(report_path, max_chars=50000),
        "report_json": report_json,
        "candidate_review": summarize_candidate_review(candidate_review),
        "source_reference_packs": pack_summaries,
        "image_manifest": image_manifest,
        "style_guidance": style_guidance(writing_profile_path, writing_playbook_path),
        "constraints": {
            "allowed_source_urls": [item.source_url for item in report.items if item.source_url],
            "wechat_docx": [
                "Reference link text is rendered from source URLs.",
            ],
        },
    }
    allowed_urls = collect_urls(report.to_dict(), report_json, candidate_review, pack_summaries, image_manifest)
    allowed_urls.update(canonicalize_url(item.source_url) for item in report.items if item.source_url)
    return report, context, {url for url in allowed_urls if url}


def generate_markdown_sources(
    report: TechDailyReport,
    context: dict[str, Any],
    content_dir: Path,
    *,
    report_json_path: Path,
    source_pack_dirs: list[Path],
) -> dict[str, Path]:
    preflight_polish_backend()
    reuse_existing = env_bool("AI_DAILY_CONTENT_REUSE_EXISTING", default=False)
    if reuse_existing:
        paragraphs_dir = content_dir / "wechat-paragraphs"
        paths: dict[str, Path] = {
            "content_dir": content_dir,
            "wechat_paragraphs": paragraphs_dir,
            "prompt_contract": content_dir / "prompt-contract.md",
            "day_editor_map": content_dir / "day-editor-map.md",
            "wechat_draft": content_dir / "wechat-draft.md",
            "title_copy": content_dir / "title-copy.md",
            "wechat_polished": content_dir / "wechat-polished.md",
            "wechat_dir": content_dir / "wechat",
            "video_screen_copy": content_dir / "video-screen-copy.md",
            "video_narration": content_dir / "video-narration.md",
            "platform_copy": content_dir / "platform-copy.md",
        }
        required = [
            paths["day_editor_map"],
            paths["wechat_draft"],
            paths["title_copy"],
            paths["wechat_polished"],
            paths["video_screen_copy"],
            paths["video_narration"],
            paths["platform_copy"],
            *[paragraphs_dir / f"{item.index:02d}-news.md" for item in report.items],
            paragraphs_dir / "00-intro.md",
            paragraphs_dir / "99-outro.md",
        ]
        if all(path.exists() and path.stat().st_size > 0 for path in required):
            return paths
    if content_dir.exists():
        shutil.rmtree(content_dir)
    paragraphs_dir = content_dir / "wechat-paragraphs"
    paragraphs_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {"content_dir": content_dir, "wechat_paragraphs": paragraphs_dir}
    paths["prompt_contract"] = write_prompt_contract_snapshot(content_dir, context)
    paths["day_editor_map"] = content_dir / "day-editor-map.md"
    call_markdown_task(context, {"slug": "day-editor-map", "prompt": editor_map_prompt(context), "output_path": paths["day_editor_map"]})
    editor_map = read_text_file(paths["day_editor_map"], max_chars=26000)

    ranked_by_index = {
        int(item.get("index")): item
        for item in (context.get("editorial_brief", {}).get("ranked_items") or [])
        if isinstance(item, dict) and str(item.get("index") or "").isdigit()
    }
    previous_draft = ""
    intro_task = {
        "slug": "wechat-intro",
        "prompt": wechat_draft_segment_prompt(context, None, "intro", editor_map=editor_map, previous_text=previous_draft),
        "output_path": paragraphs_dir / "00-intro.md",
    }
    call_markdown_task(context, intro_task)
    previous_draft = read_text_file(paragraphs_dir / "00-intro.md", max_chars=10000)
    for item in report.items:
        brief_item = ranked_by_index.get(item.index, {})
        task = {
            "slug": f"wechat-{item.index:02d}-news",
            "prompt": wechat_draft_segment_prompt(
                context,
                brief_item,
                "news",
                editor_map=editor_map,
                previous_text=previous_draft,
            ),
            "output_path": paragraphs_dir / f"{item.index:02d}-news.md",
        }
        call_markdown_task(context, task)
        previous_draft = previous_draft + "\n\n" + read_text_file(paragraphs_dir / f"{item.index:02d}-news.md", max_chars=12000)
    outro_task = {
        "slug": "wechat-outro",
        "prompt": wechat_draft_segment_prompt(context, None, "outro", editor_map=editor_map, previous_text=previous_draft),
        "output_path": paragraphs_dir / "99-outro.md",
    }
    call_markdown_task(context, outro_task)

    draft = assemble_wechat_draft(report, paragraphs_dir)
    draft_path = content_dir / "wechat-draft.md"
    draft_path.write_text(draft, encoding="utf-8")
    paths["wechat_draft"] = draft_path

    paths["title_copy"] = content_dir / "title-copy.md"
    call_markdown_task(context, {"slug": "title-copy", "prompt": title_prompt(context, editor_map), "output_path": paths["title_copy"]})

    paths["wechat_polished"] = content_dir / "wechat-polished.md"
    polish_manifest = run_codex_wechat_polish(
        report=report,
        report_json=load_json_file(report_json_path) if report_json_path.exists() else report.to_dict(),
        context=context,
        content_dir=content_dir,
        source_pack_dirs=source_pack_dirs,
        title_copy_path=paths["title_copy"],
        editor_map_path=paths["day_editor_map"],
    )
    paths["wechat_dir"] = Path(str(polish_manifest.get("wechat_dir") or content_dir / "wechat"))

    paths["video_screen_copy"] = content_dir / "video-screen-copy.md"
    paths["video_narration"] = content_dir / "video-narration.md"
    paths["platform_copy"] = content_dir / "platform-copy.md"
    call_markdown_task(
        context,
        {"slug": "video-narration", "prompt": video_narration_prompt(context, editor_map), "output_path": paths["video_narration"]},
    )
    narration_text = read_text_file(paths["video_narration"], max_chars=30000)
    call_markdown_tasks(
        context,
        [
            {"slug": "video-screen-copy", "prompt": video_screen_prompt(context, editor_map, narration_text), "output_path": paths["video_screen_copy"]},
            {"slug": "platform-copy", "prompt": platform_prompt(context, editor_map), "output_path": paths["platform_copy"]},
        ],
    )
    return paths


def assemble_wechat_draft(report: TechDailyReport, paragraphs_dir: Path) -> str:
    lines: list[str] = []
    intro = read_text_file(paragraphs_dir / "00-intro.md", max_chars=5000)
    if intro:
        lines.append(intro)
        lines.append("")
    for item in report.items:
        lines.append(f"## {item.title}")
        text = read_text_file(paragraphs_dir / f"{item.index:02d}-news.md", max_chars=9000)
        if text:
            lines.append(text)
            lines.append("")
    outro = read_text_file(paragraphs_dir / "99-outro.md", max_chars=5000)
    if outro:
        lines.append(outro)
        lines.append("")
    lines.append("## 参考链接")
    for offset, item in enumerate(report.items, start=1):
        lines.append(f"{offset}. {item.source_url}")
    return "\n".join(lines).strip() + "\n"


def extract_labeled_lines(markdown: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in markdown.splitlines():
        line = raw.strip().lstrip("-").strip()
        if not line or "：" not in line:
            continue
        label, value = line.split("：", 1)
        label = label.strip()
        value = value.strip()
        if label and value:
            result[label] = value
    return result


def clean_display_text(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip("。！？；，、 ")
    return text


def clean_filename_stem(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", value)
    cleaned = re.sub(r"\s+", "", cleaned).strip(" .")
    return cleaned[:48].strip(" .") or "AI日报"


def count_issue_number(report_date: str) -> int:
    root = ai_daily_root()
    dates: list[str] = []
    for day_dir in sorted(root.glob("20??-??-??")):
        date = day_dir.name
        if OFFICIAL_ISSUE_START_DATE and date < OFFICIAL_ISSUE_START_DATE:
            continue
        if (day_dir / "process" / "report.md").exists():
            dates.append(date)
    if report_date and report_date not in dates and (not OFFICIAL_ISSUE_START_DATE or report_date >= OFFICIAL_ISSUE_START_DATE):
        dates.append(report_date)
    dates = sorted(set(dates))
    try:
        return dates.index(report_date) + 1
    except ValueError:
        return max(len(dates), 1)


def sanitize_artifact_title(text: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub(" ", str(text or ""))
    return re.sub(r"\s+", " ", cleaned).strip(" .")


def named_artifact_filename(title: str, trailer: str, suffix: str) -> str:
    clean_title = sanitize_artifact_title(title)
    clean_trailer = sanitize_artifact_title(trailer)
    if not clean_title:
        clean_title = "AI日报"
    max_title_chars = max(12, MAX_NAMED_ARTIFACT_STEM_CHARS - len(clean_trailer))
    if len(clean_title) > max_title_chars:
        clean_title = clean_title[:max_title_chars].rstrip(" .")
    return f"{clean_title}{clean_trailer}{suffix}"


def require_labeled_text(labels: dict[str, str], label: str, *, source: str = "title-copy.md") -> str:
    value = clean_display_text(labels.get(label) or "")
    if not value:
        raise ValueError(f"{source} missing required label: {label}")
    return value


def require_labeled_paragraph(labels: dict[str, str], label: str, *, source: str) -> str:
    value = re.sub(r"\s+", " ", str(labels.get(label) or "")).strip()
    if not value:
        raise ValueError(f"{source} missing required label: {label}")
    return value


def split_entity_label(value: str) -> list[str]:
    entities: list[str] = []
    for raw in re.split(r"[／/、,，;；|]+", str(value or "")):
        entity = clean_entity(raw)
        if not entity:
            continue
        if entity not in entities:
            entities.append(entity)
    return entities


def parse_title_copy(markdown: str, report: TechDailyReport) -> tuple[dict[str, Any], dict[str, Any]]:
    labels = extract_labeled_lines(markdown)
    issue_no = count_issue_number(report.date)
    issue_label = f"第 {issue_no} 期"
    primary_entities: list[str] = []
    for entity in split_entity_label(labels.get("标题主语", "")):
        if entity and entity not in primary_entities:
            primary_entities.append(entity)
    for item in report.items:
        anchor = title_entity_anchor(item.title)
        if anchor and anchor not in primary_entities:
            primary_entities.append(anchor)
    primary_entities = primary_entities[:8]
    primary_hook = require_labeled_text(labels, "主传播标题")
    require_labeled_text(labels, "微信标题")
    require_labeled_text(labels, "视频标题")
    require_labeled_text(labels, "B站标题")
    public_title = primary_hook
    wechat_title = public_title
    video_title = public_title
    bilibili_title = public_title
    cover_headline = require_chinese_cover_text(require_labeled_text(labels, "封面主标题"), "封面主标题")
    cover_subhead = require_chinese_cover_text(require_labeled_text(labels, "封面副标题"), "封面副标题")
    file_stem = clean_filename_stem(require_labeled_text(labels, "文件名短标题"))
    title_pack = {
        "issue_no": issue_no,
        "issue_label": issue_label,
        "primary_entities": primary_entities,
        "headline_subject": require_labeled_text(labels, "标题主语"),
        "headline_action": require_labeled_text(labels, "标题动作"),
        "headline_stakes": require_labeled_text(labels, "标题后果"),
        "primary_hook": primary_hook,
        "video_title": video_title,
        "bilibili_title": bilibili_title,
        "wechat_title": wechat_title,
        "cover_headline": cover_headline,
        "cover_subhead": cover_subhead,
        "video_filename": named_artifact_filename(video_title or file_stem, f"｜Lumi的AI速递｜{report.date}", ".mp4")
        if report.date
        else named_artifact_filename(video_title or file_stem, "｜Lumi的AI速递", ".mp4"),
        "wechat_filename": named_artifact_filename(wechat_title or file_stem, f"｜Lumi的AI速递｜{report.date}", ".docx")
        if report.date
        else named_artifact_filename(wechat_title or file_stem, "｜Lumi的AI速递", ".docx"),
    }
    left_lines = [line.strip() for line in re.split(r"[；;、,，]", labels.get("封面左侧", "")) if line.strip()]
    right_lines = [line.strip() for line in re.split(r"[；;、,，]", labels.get("封面右侧", "")) if line.strip()]
    if not left_lines:
        raise ValueError("title-copy.md missing required label: 封面左侧")
    if not right_lines:
        raise ValueError("title-copy.md missing required label: 封面右侧")
    cover_copy = {
        "headline": cover_headline,
        "subhead": cover_subhead,
        "left_lines": [require_chinese_cover_text(line, "封面左侧") for line in left_lines[:3]],
        "right_lines": [require_chinese_cover_text(line, "封面右侧") for line in right_lines[:3]],
        "entity_anchors": primary_entities,
    }
    return title_pack, cover_copy


def split_markdown_sections(markdown: str) -> tuple[str, list[tuple[str, str]], str]:
    title = ""
    sections: list[tuple[str, str]] = []
    current_title = ""
    current_lines: list[str] = []
    intro_lines: list[str] = []
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            if current_title:
                sections.append((current_title, "\n".join(current_lines).strip()))
            elif current_lines:
                intro_lines.extend(current_lines)
            current_title = line[3:].strip()
            current_lines = []
            continue
        if current_title:
            current_lines.append(line)
        else:
            intro_lines.append(line)
    if current_title:
        sections.append((current_title, "\n".join(current_lines).strip()))
    intro = "\n".join(intro_lines).strip()
    return title, sections, intro


def section_paragraphs(body: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\n\s*\n", body or "") if part.strip()]
    return [re.sub(r"\s*\n\s*", " ", part).strip() for part in parts]


def parse_wechat_article(markdown: str, report: TechDailyReport, title_pack: dict[str, Any]) -> dict[str, Any]:
    title, sections_raw, intro = split_markdown_sections(markdown)
    intro_unresolved = unclear_reference_findings(intro)
    if intro_unresolved:
        raise ValueError(f"wechat-polished.md intro has unclear references {intro_unresolved}")
    item_sections: list[dict[str, Any]] = []
    outro_heading = ""
    outro_parts: list[str] = []
    references: list[dict[str, Any]] = []
    item_offset = 0
    for heading, body in sections_raw:
        normalized = heading.strip()
        if "参考" in normalized:
            continue
        if item_offset >= len(report.items):
            outro_heading = normalized or outro_heading
            outro_parts.extend(section_paragraphs(body))
            continue
        item = report.items[item_offset]
        paragraphs = section_paragraphs(body)
        if not paragraphs:
            raise ValueError(f"wechat-polished.md section has no paragraphs: {normalized}")
        if len(paragraphs) != 2:
            raise ValueError(f"wechat-polished.md section must contain exactly 2 paragraphs: {normalized}")
        unresolved = unclear_reference_findings("\n".join(paragraphs))
        if unresolved:
            raise ValueError(f"wechat-polished.md section has unclear references {unresolved}: {normalized}")
        section_body = "\n\n".join(paragraphs).strip()
        item_sections.append(
            {
                "index": item.index,
                "title": normalized or item.title,
                "body": section_body,
                "facts": section_body,
                "analysis": "",
                "image_caption": "",
                "source_url": item.source_url,
                "highlight_terms": extract_entities_from_texts(item.title, item.content, item.interpretation, source_url=item.source_url)[:4],
            }
        )
        item_offset += 1
    for item in report.items:
        references.append({"index": item.index, "title": item.title, "url": item.source_url})
    outro = "\n\n".join(outro_parts).strip()
    outro_unresolved = unclear_reference_findings(outro)
    if outro_unresolved:
        raise ValueError(f"wechat-polished.md outro has unclear references {outro_unresolved}: {outro_heading}")
    return {
        "title": title or title_pack.get("wechat_title") or report.title,
        "intro": intro,
        "sections": item_sections,
        "outro_heading": outro_heading,
        "outro": outro,
        "references": references,
    }


def parse_platform_copy(markdown: str, report: TechDailyReport, title_pack: dict[str, Any]) -> dict[str, Any]:
    sections = dict(split_markdown_sections(markdown)[1])
    bilibili_body = section_text_by_heading(sections, "Bilibili")
    labels = extract_labeled_lines(bilibili_body)
    if not bilibili_body.strip():
        raise ValueError("platform-copy.md missing Bilibili section text")
    blocks = extract_label_blocks(bilibili_body)
    merged_labels = {**labels, **blocks}
    tags = [tag.strip() for tag in re.split(r"[,，、]", merged_labels.get("标签", "")) if tag.strip()]
    if not tags:
        raise ValueError("platform-copy.md missing Bilibili 标签")
    return {
        "title": require_labeled_text(merged_labels, "标题", source="platform-copy.md"),
        "description": require_labeled_paragraph(merged_labels, "简介", source="platform-copy.md"),
        "dynamic": merged_labels.get("动态", "").strip(),
        "tags": tags[:8],
    }


def section_text_by_heading(sections: dict[str, str], needle: str) -> str:
    for heading, body in sections.items():
        if needle.lower() in heading.lower():
            return body
    return ""


LABEL_LINE_RE = re.compile(r"^([^\n：:]{1,18})[：:]\s*(.*)$")


def extract_label_blocks(body: str) -> dict[str, str]:
    blocks: dict[str, list[str]] = {}
    current_label = ""
    for raw in str(body or "").splitlines():
        line = raw.rstrip()
        match = LABEL_LINE_RE.match(line.strip())
        if match:
            current_label = match.group(1).strip()
            blocks[current_label] = [match.group(2).strip()] if match.group(2).strip() else []
            continue
        if current_label:
            blocks[current_label].append(line.strip())
    return {label: "\n".join(part for part in parts if part).strip() for label, parts in blocks.items()}


def require_block(blocks: dict[str, str], label: str, context: str) -> str:
    value = re.sub(r"\s*\n\s*", " ", str(blocks.get(label) or "")).strip()
    if not value:
        raise ValueError(f"video-narration.md missing {context}.{label}")
    return value


def parse_video_narration(markdown: str, report: TechDailyReport) -> dict[str, Any]:
    sections = split_markdown_sections(markdown)[1]
    intro: dict[str, Any] = {}
    outro: dict[str, Any] = {}
    items: dict[int, dict[str, Any]] = {}
    for heading, body in sections:
        blocks = extract_label_blocks(body)
        if "开场" in heading:
            intro = {
                "display_title": require_block(blocks, "显示标题", "intro"),
                "spoken_title": require_block(blocks, "口播标题", "intro"),
                "emotion_hint": blocks.get("情绪", "").strip(),
                "oral": require_block(blocks, "口播", "intro"),
            }
            continue
        if "结尾" in heading:
            oral = require_block(blocks, "口播", "outro")
            outro = {
                "display_title": require_block(blocks, "显示标题", "outro"),
                "spoken_title": require_block(blocks, "口播标题", "outro"),
                "emotion_hint": blocks.get("情绪", "").strip(),
                "line_one": blocks.get("片尾一", "").strip(),
                "line_two": blocks.get("片尾二", "").strip(),
                "quote_translation": blocks.get("中文金句", "").strip() or oral,
                "quote_author": blocks.get("金句作者", "").strip(),
                "oral": oral,
            }
            continue
        match = re.search(r"新闻\s*(\d+)", heading)
        if not match:
            continue
        item_index = int(match.group(1))
        items[item_index] = {
            "display_title": require_block(blocks, "显示标题", f"items[{item_index}]"),
            "spoken_title": require_block(blocks, "口播标题", f"items[{item_index}]"),
            "emotion_hint": blocks.get("情绪", "").strip(),
            "hook": blocks.get("钩子", "").strip(),
            "takeaway": blocks.get("判断", "").strip(),
            "oral": require_block(blocks, "口播", f"items[{item_index}]"),
        }
    if not intro:
        raise ValueError("video-narration.md missing ## 开场")
    if not outro:
        raise ValueError("video-narration.md missing ## 结尾")
    missing = [item.index for item in report.items if item.index not in items]
    if missing:
        raise ValueError("video-narration.md missing news narration for item indexes: " + ", ".join(str(index) for index in missing))
    return {"intro": intro, "items": items, "outro": outro}


def parse_video_screen_copy(markdown: str, report: TechDailyReport) -> dict[str, Any]:
    lines = markdown.splitlines()
    nav_labels: list[str] = []
    item_cards: dict[int, list[dict[str, Any]]] = {}
    current_index: int | None = None
    in_nav = False
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            heading = line[3:].strip()
            in_nav = "顶部" in heading or "进度" in heading
            current_index = None
            match = re.search(r"新闻\s*(\d+)", heading)
            if match:
                current_index = int(match.group(1))
                item_cards.setdefault(current_index, [])
            continue
        if in_nav and line.startswith("-"):
            label = line.lstrip("-").strip()
            if label:
                nav_labels.append(clean_display_text(label))
            continue
        if current_index and line.startswith("卡片"):
            _, value = line.split("：", 1) if "：" in line else ("卡片", line.removeprefix("卡片").strip(":： "))
            parts = [part.strip() for part in re.split(r"[|｜]", value) if part.strip()]
            if len(parts) >= 2:
                point_text = parts[1].strip()
                points = [clean_display_text(part) for part in re.split(r"[；;]", point_text) if clean_display_text(part)]
                item_cards.setdefault(current_index, []).append(
                    {
                        "heading": clean_display_text(parts[0]),
                        "body": point_text,
                        "points": points[:3],
                        "icon_hint": parts[2].strip() if len(parts) >= 3 else "",
                        "emphasis": clean_display_text(parts[3]) if len(parts) >= 4 else "",
                    }
                )
    item_nav = [label for label in nav_labels if label not in {"封面", "开场", "结尾"}]
    if len(item_nav) < len(report.items):
        raise ValueError("video-screen-copy.md missing enough item part names in 顶部进度条")
    by_index: dict[int, dict[str, Any]] = {}
    for offset, item in enumerate(report.items, start=1):
        cards = item_cards.get(offset) or []
        if len(cards) != 3:
            raise ValueError(f"video-screen-copy.md news {offset} must contain exactly 3 cards")
        for card_offset, card in enumerate(cards, start=1):
            if not card.get("heading") or not card.get("body") or not card.get("icon_hint"):
                raise ValueError(f"video-screen-copy.md news {offset} card {card_offset} requires title, body and icon")
            heading = clean_display_text(card.get("heading", ""))
            if visual_text_len(heading) < 3:
                raise ValueError(f"video-screen-copy.md news {offset} card {card_offset} heading too short")
            body = str(card.get("body") or "")
            points = card.get("points") if isinstance(card.get("points"), list) else []
            if "…" in body or "..." in body:
                raise ValueError(f"video-screen-copy.md news {offset} card {card_offset} must not use ellipses")
            unresolved = unclear_reference_findings(f"{heading}\n{body}")
            if unresolved:
                raise ValueError(f"video-screen-copy.md news {offset} card {card_offset} has unclear references {unresolved}")
            if any(phrase in body or phrase in heading for phrase in SCREEN_CARD_BAD_PHRASES):
                raise ValueError(f"video-screen-copy.md news {offset} card {card_offset} uses meta viewing language")
            if card_offset == 1 and len(points) < 2:
                raise ValueError(f"video-screen-copy.md news {offset} lead card must contain at least 2 points")
            if visual_text_len(body) > 220:
                raise ValueError(f"video-screen-copy.md news {offset} card {card_offset} body too long")
        by_index[item.index] = {
            "nav_label": clean_display_text(item_nav[offset - 1]),
            "screen_cards": cards[:3],
        }
    return {"nav_parts": nav_labels, "items": by_index}


def sentence_emotion_hint(text: str, fallback: str) -> str:
    value = str(text or "")
    if fallback:
        return fallback
    if "？" in value or "?" in value:
        return "curious"
    if any(token in value for token in ("但是", "但", "关键", "真正", "问题")):
        return "measured"
    if any(token in value for token in ("开始", "正在", "机会", "打开")):
        return "brighter"
    if any(token in value for token in ("代价", "风险", "压力", "约束")):
        return "thoughtful"
    return "warm"


def sentence_pairs_from_text(text: str, prefix: str, *, emotion_hint: str = "") -> list[dict[str, Any]]:
    raw_parts = [part.strip() for part in re.split(r"(?<=[。！？!?；;])", text or "") if part.strip()]
    if not raw_parts:
        raw_parts = [text.strip()] if text.strip() else []
    pairs: list[dict[str, Any]] = []
    for offset, part in enumerate(raw_parts, start=1):
        pairs.append(
            {
                "sentence_id": f"{prefix}-{offset}",
                "oral": spokenize_version_token(part),
                "subtitle": part,
                "tts_tags": [],
                "emotion_hint": sentence_emotion_hint(part, emotion_hint),
            }
        )
    return pairs


def spokenize_version_token(text: str) -> str:
    return str(text or "")


def apply_sentence_pairs(block: dict[str, Any], pairs: list[dict[str, Any]]) -> None:
    block["sentence_pairs"] = pairs
    block["oral_script"] = "".join(pair["oral"] for pair in pairs)
    block["subtitle_script"] = "".join(pair["subtitle"] for pair in pairs)
    block["tts_script"] = "".join(pair["oral"] for pair in pairs)


def ensure_intro_identity(text: str, issue_label: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return cleaned
    issue = str(issue_label or "第 N 期").strip()
    identity = f"Lumi 的 AI 日报{issue}"
    has_greeting = bool(re.match(r"^(大家好|你好|各位好|朋友们好|嗨)[，。!！]", cleaned))
    if identity in cleaned or ("Lumi" in cleaned and issue in cleaned and "日报" in cleaned):
        return cleaned if has_greeting else f"大家好。{cleaned}"
    if not has_greeting:
        return f"大家好。这里是 {identity}。{cleaned}"
    match = re.match(r"^(.+?[。！？!])(.+)$", cleaned)
    if match:
        return f"{match.group(1)}这里是 {identity}。{match.group(2).strip()}"
    return f"{cleaned}这里是 {identity}。"


def build_video_script(
    report: TechDailyReport,
    wechat: dict[str, Any],
    video_copy: dict[str, Any],
    title_pack: dict[str, Any],
    narration: dict[str, Any],
) -> dict[str, Any]:
    intro_source = narration.get("intro") if isinstance(narration.get("intro"), dict) else {}
    intro_text = str(intro_source.get("oral") or "").strip()
    if not intro_text:
        raise ValueError("video-narration.md intro oral text is empty")
    intro_text = ensure_intro_identity(intro_text, str(title_pack.get("issue_label") or "第 N 期"))
    intro = {
        "opening": intro_text.split("。")[0] + "。" if "。" in intro_text else intro_text,
        "agenda": str(title_pack.get("primary_hook") or ""),
        "transition": "",
        "display_title": str(intro_source.get("display_title") or title_pack.get("primary_hook") or "").strip(),
        "spoken_title": str(intro_source.get("spoken_title") or title_pack.get("primary_hook") or "").strip(),
        "spoken_aliases": [],
        "style_variant": "intro_light",
        "tts_style_tags": "",
    }
    apply_sentence_pairs(intro, sentence_pairs_from_text(intro_text, "intro", emotion_hint=str(intro_source.get("emotion_hint") or "")))
    sections_by_index = {
        int(section.get("index")): section
        for section in wechat.get("sections") or []
        if isinstance(section, dict) and str(section.get("index") or "").isdigit()
    }
    items: list[dict[str, Any]] = []
    video_items = video_copy.get("items") if isinstance(video_copy.get("items"), dict) else {}
    narration_items = narration.get("items") if isinstance(narration.get("items"), dict) else {}
    for item in report.items:
        section = sections_by_index.get(item.index, {})
        screen = video_items.get(item.index, {}) if isinstance(video_items, dict) else {}
        narration_item = narration_items.get(item.index, {}) if isinstance(narration_items, dict) else {}
        paragraph = str(narration_item.get("oral") or "").strip()
        if not paragraph:
            raise ValueError(f"video-narration.md missing oral text for item {item.index}")
        cards = screen.get("screen_cards")
        if not isinstance(cards, list) or len(cards) != 3:
            raise ValueError(f"video-screen-copy.md missing screen_cards for item {item.index}")
        nav_label = str(screen.get("nav_label") or "").strip()
        if not nav_label:
            raise ValueError(f"video-screen-copy.md missing nav_label for item {item.index}")
        raw = {
            "index": item.index,
            "hook": str(narration_item.get("hook") or section.get("title") or item.title),
            "takeaway": str(narration_item.get("takeaway") or section.get("body") or section.get("analysis") or "").strip(),
            "fact_points": [item.content, item.interpretation],
            "source_note": f"来源：{item.source_url}",
            "outro": str(narration_item.get("takeaway") or section.get("body") or section.get("analysis") or "").strip(),
            "decision_impact": str(
                narration_item.get("decision_impact")
                or item.decision_impact
                or narration_item.get("takeaway")
                or section.get("body")
                or section.get("analysis")
                or item.interpretation
                or ""
            ).strip(),
            "display_title": str(narration_item.get("display_title") or section.get("title") or item.title),
            "spoken_title": str(narration_item.get("spoken_title") or section.get("title") or item.title),
            "spoken_aliases": [],
            "screen_cards": cards,
            "media_summary": paragraph,
            "nav_label": nav_label,
            "style_variant": "",
            "tts_style_tags": "",
        }
        apply_sentence_pairs(
            raw,
            sentence_pairs_from_text(paragraph, f"item{item.index}", emotion_hint=str(narration_item.get("emotion_hint") or "")),
        )
        items.append(raw)
    outro_source = narration.get("outro") if isinstance(narration.get("outro"), dict) else {}
    outro_text = str(outro_source.get("oral") or "").strip()
    if not outro_text:
        raise ValueError("video-narration.md outro oral text is empty")
    outro = {
        "display_title": str(outro_source.get("display_title") or "").strip(),
        "spoken_title": str(outro_source.get("spoken_title") or "").strip(),
        "spoken_aliases": [],
        "style_variant": "outro_light",
        "tts_style_tags": "",
        "line_one": str(outro_source.get("line_one") or "").strip(),
        "line_two": str(outro_source.get("line_two") or "").strip(),
        "quote_id": f"{report.date or 'latest'}-outro",
        "quote_text": "",
        "quote_translation": str(outro_source.get("quote_translation") or "").strip(),
        "quote_author": str(outro_source.get("quote_author") or "").strip() or "Lumi",
    }
    apply_sentence_pairs(outro, sentence_pairs_from_text(outro_text, "outro", emotion_hint=str(outro_source.get("emotion_hint") or "")))
    return {"intro": intro, "items": items, "outro": outro}


def build_report_markdown(report: TechDailyReport, items: list[dict[str, Any]]) -> str:
    lines = [f"# {report.title or f'AI速递 - {report.date}'}", "", "## 硅谷风向词", ""]
    for index, word in enumerate(report.trend_words):
        line = report.trend_lines[index] if index < len(report.trend_lines) else ""
        if line and line.startswith(f"{word}："):
            lines.append(f"- {line}")
        else:
            lines.append(f"- {word}：{line}" if line else f"- {word}")
    lines.append("")
    tech_written = False
    research_written = False
    for raw in items:
        item_kind = str(raw.get("item_kind") or "tech")
        if item_kind == "research":
            if not research_written:
                lines.extend(["", "## 硅谷学术热点", ""])
                research_written = True
        else:
            if not tech_written:
                lines.extend(["", "## 硅谷科技热点", ""])
                tech_written = True
        lines.append(str(raw.get("title") or ""))
        lines.append(f"内容：{raw.get('content') or ''}")
        lines.append(f"解读：{raw.get('interpretation') or ''}")
        lines.append(f"原文链接：{raw.get('source_url') or ''}")
        if raw.get("status"):
            lines.append(f"状态：{raw.get('status')}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_manifest(
    report: TechDailyReport,
    context: dict[str, Any],
    paths: dict[str, Path],
    out_path: Path,
) -> dict[str, Any]:
    title_markdown = read_text_file(paths["title_copy"], max_chars=20000)
    title_pack, cover_copy = parse_title_copy(title_markdown, report)
    wechat_markdown = read_text_file(paths["wechat_polished"], max_chars=120000)
    wechat = parse_wechat_article(wechat_markdown, report, title_pack)
    platform_markdown = read_text_file(paths["platform_copy"], max_chars=40000)
    bilibili = parse_platform_copy(platform_markdown, report, title_pack)
    video_markdown = read_text_file(paths["video_screen_copy"], max_chars=50000)
    video_copy = parse_video_screen_copy(video_markdown, report)
    narration_markdown = read_text_file(paths["video_narration"], max_chars=80000)
    narration = parse_video_narration(narration_markdown, report)
    video_script = build_video_script(report, wechat, video_copy, title_pack, narration)
    items = [
        {
            "index": item.index,
            "title": item.title,
            "content": item.content,
            "interpretation": item.interpretation,
            "source_url": item.source_url,
            "source_refs": list(dict.fromkeys([*(item.source_refs or []), item.source_url])),
            "highlight_terms": extract_entities_from_texts(item.title, item.content, item.interpretation, source_url=item.source_url)[:4],
            "item_kind": item.item_kind,
            "status": item.status,
            "decision_impact": item.decision_impact or item.interpretation,
        }
        for item in report.items
    ]
    manifest = {
        "version": 2,
        "content_generation": "markdown_first",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date": report.date,
        "content_sources": {key: str(path) for key, path in paths.items()},
        "editorial_brief": context.get("editorial_brief"),
        "report_markdown": build_report_markdown(report, items),
        "items": items,
        "wechat": wechat,
        "bilibili": bilibili,
        "cover_copy": cover_copy,
        "title_pack": title_pack,
        "video_screen_copy": video_copy,
        "video_narration": narration,
        "video_script": video_script,
    }
    write_json(out_path, manifest)
    return manifest


def validate_content_manifest(manifest: dict[str, Any], expected_report: TechDailyReport, allowed_urls: set[str]) -> list[str]:
    findings: list[str] = []
    if manifest.get("content_generation") != "markdown_first":
        findings.append("content_generation_not_markdown_first")
    output_payload = {
        "report_markdown": manifest.get("report_markdown"),
        "items": manifest.get("items"),
        "wechat": manifest.get("wechat"),
        "bilibili": manifest.get("bilibili"),
        "cover_copy": manifest.get("cover_copy"),
        "title_pack": manifest.get("title_pack"),
        "video_screen_copy": manifest.get("video_screen_copy"),
        "video_narration": manifest.get("video_narration"),
        "video_script": manifest.get("video_script"),
    }
    for raw_url in collect_urls(output_payload):
        if raw_url not in allowed_urls:
            findings.append(f"unknown_output_url:{raw_url}")
    cover_copy = manifest.get("cover_copy") if isinstance(manifest.get("cover_copy"), dict) else {}
    cover_headline_len = max_stripped_line_len(cover_copy.get("headline"))
    cover_subhead_len = max_stripped_line_len(cover_copy.get("subhead"))
    if cover_headline_len < 6:
        findings.append("cover_headline_too_short")
    if cover_headline_len > 20:
        findings.append("cover_headline_too_long")
    if not contains_chinese_text(cover_copy.get("headline")):
        findings.append("cover_headline_not_chinese")
    if cover_subhead_len < 6:
        findings.append("cover_subhead_too_short")
    if cover_subhead_len > 20:
        findings.append("cover_subhead_too_long")
    if not contains_chinese_text(cover_copy.get("subhead")):
        findings.append("cover_subhead_not_chinese")
    title_pack = manifest.get("title_pack") if isinstance(manifest.get("title_pack"), dict) else {}
    for key in ("primary_hook", "video_title", "bilibili_title", "wechat_title", "video_filename", "wechat_filename"):
        value = str(title_pack.get(key) or "")
        for phrase in unclear_reference_findings(value):
            findings.append(f"title_pack_{key}_unclear_reference:{phrase}")
    wechat_title = str((manifest.get("wechat") or {}).get("title") if isinstance(manifest.get("wechat"), dict) else "")
    for phrase in unclear_reference_findings(wechat_title):
        findings.append(f"title_pack_wechat_manifest_title_unclear_reference:{phrase}")
    wechat = manifest.get("wechat") if isinstance(manifest.get("wechat"), dict) else {}
    for label in ("intro", "outro"):
        body = str(wechat.get(label) or "")
        for phrase in unclear_reference_findings(body):
            findings.append(f"wechat_{label}_unclear_reference:{phrase}")
    sections = wechat.get("sections") if isinstance(wechat.get("sections"), list) else []
    if len(sections) != len(expected_report.items):
        findings.append(f"wechat_sections_count_mismatch:{len(sections)}!={len(expected_report.items)}")
    for raw_section in sections:
        if not isinstance(raw_section, dict):
            continue
        body = str(raw_section.get("body") or "")
        paragraphs = section_paragraphs(body)
        if len(paragraphs) != 2:
            findings.append(f"wechat_section_{raw_section.get('index')}_paragraph_count:{len(paragraphs)}")
        for phrase in unclear_reference_findings(body):
            findings.append(f"wechat_section_{raw_section.get('index')}_unclear_reference:{phrase}")
    video = manifest.get("video_script") if isinstance(manifest.get("video_script"), dict) else {}
    if isinstance(video.get("intro"), dict):
        validate_video_script_text(video["intro"], "video_script.intro", findings)
    for raw_item in video.get("items") or []:
        if isinstance(raw_item, dict):
            validate_video_script_text(raw_item, f"video_script.items[{raw_item.get('index')}]", findings)
            validate_video_screen_cards(raw_item, f"video_script.items[{raw_item.get('index')}]", findings)
            nav_label = str(raw_item.get("nav_label") or "").strip()
            if not nav_label:
                findings.append(f"video_script.items[{raw_item.get('index')}]_missing_nav_label")
    if isinstance(video.get("outro"), dict):
        validate_video_script_text(video["outro"], "video_script.outro", findings)
        validate_outro_quote_translation(video["outro"], "video_script.outro", findings)
    return findings


def load_content_manifest(path: str | Path | None = None, *, report_path: str | Path | None = None, date: str | None = None) -> dict[str, Any]:
    if path:
        manifest_path = Path(path).expanduser().resolve()
    else:
        resolved_date = date
        if not resolved_date and report_path:
            resolved_date = extract_tech_daily_date(report_path)
        if not resolved_date:
            raise FileNotFoundError("Could not resolve content-manifest path without date or report path.")
        manifest_path = tech_daily_content_manifest_path(resolved_date)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Content manifest not found: {manifest_path}")
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Content manifest must be an object: {manifest_path}")
    return raw


def load_editorial_bundle(path: str | Path | None = None, *, report_path: str | Path | None = None, date: str | None = None) -> dict[str, Any]:
    # Deprecated compatibility shim. The returned object is a deterministic
    # manifest assembled from Markdown source files.
    return load_content_manifest(path, report_path=report_path, date=date)


def generate_editorial_bundle(
    *,
    report_path: str | Path,
    report_json_path: str | Path | None = None,
    candidate_review_path: str | Path | None = None,
    source_pack_dirs: list[str | Path] | None = None,
    image_manifest_path: str | Path | None = None,
    writing_profile_path: str | Path | None = None,
    writing_playbook_path: str | Path | None = None,
    editorial_brief_out_path: str | Path | None = None,
    out_path: str | Path | None = None,
    rewrite_report: bool = False,
) -> dict[str, Any]:
    report_file = Path(report_path).expanduser().resolve()
    report = parse_report(report_file)
    report_json_file = default_report_json_path(report_file, str(report_json_path) if report_json_path else None)
    candidate_review_file = default_candidate_review_path(report, str(candidate_review_path) if candidate_review_path else None)
    source_dirs = default_pack_dirs(report, [str(path) for path in (source_pack_dirs or [])])
    image_manifest_file = default_image_manifest_path(report_file, str(image_manifest_path) if image_manifest_path else None)
    profile_file = Path(writing_profile_path).expanduser().resolve() if writing_profile_path else tech_daily_writing_profile_path()
    playbook_file = Path(writing_playbook_path).expanduser().resolve() if writing_playbook_path else tech_daily_writing_playbook_path()
    output_file = default_output_path(report_file, str(out_path) if out_path else None)
    content_dir = default_content_dir(report)
    brief_out = Path(editorial_brief_out_path).expanduser().resolve() if editorial_brief_out_path else tech_daily_editorial_brief_path(report.date or extract_tech_daily_date(report_file) or "latest")

    report, context, allowed_urls = source_context(
        report_file,
        report_json_file,
        candidate_review_file,
        source_dirs,
        image_manifest_file,
        profile_file,
        playbook_file,
    )
    write_json(brief_out, context["editorial_brief"])
    paths = generate_markdown_sources(
        report,
        context,
        content_dir,
        report_json_path=report_json_file,
        source_pack_dirs=source_dirs,
    )
    max_retries = max(0, int(os.environ.get("AI_DAILY_CONTENT_MAX_RETRIES", DEFAULT_MAX_RETRIES) or DEFAULT_MAX_RETRIES))
    manifest: dict[str, Any] | None = None
    for repair_index in range(0, max_retries + 1):
        try:
            manifest = build_manifest(report, context, paths, output_file)
            break
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            if repair_index >= max_retries:
                raise
            if "video-screen-copy.md" in error:
                current_video_copy = read_text_file(paths["video_screen_copy"], max_chars=20000)
                call_codex_markdown(
                    context,
                    slug=f"video-screen-copy-retry-{repair_index + 1}",
                    prompt=video_screen_repair_prompt(
                        context,
                        current_video_copy,
                        error,
                        read_text_file(paths.get("day_editor_map"), max_chars=26000),
                        read_text_file(paths.get("video_narration"), max_chars=30000),
                    ),
                    output_path=paths["video_screen_copy"],
                )
                continue
            if "wechat-polished.md" in error:
                repaired = call_codex_markdown(
                    context,
                    slug=f"wechat-polished-retry-{repair_index + 1}",
                    prompt=wechat_article_repair_prompt(
                        context,
                        article=read_text_file(paths["wechat_polished"], max_chars=120000),
                        error=error,
                        editor_map=read_text_file(paths.get("day_editor_map"), max_chars=26000),
                        source_trace=source_trace_excerpt(report, max_chars=14000),
                    ),
                    output_path=paths["wechat_polished"],
                )
                wechat_dir = paths.get("wechat_dir")
                if wechat_dir:
                    write_markdown(Path(wechat_dir) / "wechat-polished.md", repaired)
                continue
            raise
    if manifest is None:
        raise RuntimeError("Could not build Markdown content manifest.")
    findings = validate_content_manifest(manifest, report, allowed_urls)
    title_retry_prefixes = (
        "title_pack_",
        "cover_copy_",
        "cover_headline_too_short",
        "cover_headline_too_long",
        "cover_headline_not_chinese",
        "cover_subhead_too_short",
        "cover_subhead_too_long",
        "cover_subhead_not_chinese",
    )
    retry_index = 0
    while findings and retry_index < max_retries and all(
        finding.startswith(title_retry_prefixes) for finding in findings
    ):
        retry_index += 1
        current_title_copy = read_text_file(paths["title_copy"], max_chars=20000)
        call_codex_markdown(
            context,
            slug=f"title-copy-retry-{retry_index}",
            prompt=title_repair_prompt(
                context,
                current_title_copy,
                findings,
                read_text_file(paths.get("day_editor_map"), max_chars=26000),
            ),
            output_path=paths["title_copy"],
        )
        manifest = build_manifest(report, context, paths, output_file)
        findings = validate_content_manifest(manifest, report, allowed_urls)
    narration_retry_index = 0
    while (
        findings
        and narration_retry_index < max_retries
        and all(finding.startswith("video_script.") and "_unclear_reference:" in finding for finding in findings)
    ):
        narration_retry_index += 1
        call_codex_markdown(
            context,
            slug=f"video-narration-retry-{narration_retry_index}",
            prompt=video_narration_repair_prompt(
                context,
                current_narration=read_text_file(paths["video_narration"], max_chars=80000),
                findings=findings,
                editor_map=read_text_file(paths.get("day_editor_map"), max_chars=26000),
            ),
            output_path=paths["video_narration"],
        )
        manifest = build_manifest(report, context, paths, output_file)
        findings = validate_content_manifest(manifest, report, allowed_urls)
    if findings:
        raise RuntimeError("Markdown content manifest validation failed: " + "; ".join(findings[:20]))
    if rewrite_report:
        report_file.write_text(str(manifest.get("report_markdown") or ""), encoding="utf-8")
    return {
        "result": "success",
        "content_manifest": str(output_file),
        "editorial_bundle": str(output_file),
        "editorial_brief": str(brief_out),
        "content_dir": str(content_dir),
        "report": str(report_file),
        "report_rewritten": rewrite_report,
        "provider": DEFAULT_PROVIDER,
        "model": content_codex_model(),
        "reasoning_effort": os.environ.get("AI_DAILY_CONTENT_REASONING_EFFORT", DEFAULT_REASONING_EFFORT).strip() or DEFAULT_REASONING_EFFORT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items_count": len(report.items),
        "markdown_sources": {key: str(path) for key, path in paths.items()},
    }


def clean_sentence_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalized_sentence_pairs(raw: dict[str, Any]) -> list[dict[str, Any]]:
    pairs = raw.get("sentence_pairs")
    if not isinstance(pairs, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, pair_raw in enumerate(pairs, start=1):
        if not isinstance(pair_raw, dict):
            continue
        sentence_id = str(pair_raw.get("sentence_id") or f"s{index:02d}").strip()
        oral = clean_sentence_text(pair_raw.get("oral"))
        subtitle = clean_sentence_text(pair_raw.get("subtitle"))
        tags_raw = pair_raw.get("tts_tags")
        tags = [str(tag).strip().strip("[]") for tag in tags_raw if str(tag).strip()] if isinstance(tags_raw, list) else []
        emotion_hint = str(pair_raw.get("emotion_hint") or "").strip()
        if oral and subtitle:
            normalized.append(
                {
                    "sentence_id": sentence_id,
                    "oral": oral,
                    "subtitle": subtitle,
                    "tts_tags": tags,
                    "emotion_hint": emotion_hint,
                }
            )
    return normalized


def strip_tts_tags(text: str) -> str:
    return TTS_TAG_RE.sub("", text or "")


def tts_tag_names(text: str) -> list[str]:
    return [match.group(0).strip("[]").strip().lower() for match in TTS_TAG_RE.finditer(text or "")]


def compact_for_alias_match(text: str) -> str:
    return re.sub(r"\s+", "", text or "").strip().lower()


def validate_sentence_pairs(raw: dict[str, Any], path: str, findings: list[str]) -> None:
    pairs = normalized_sentence_pairs(raw)
    if not pairs:
        findings.append(f"{path}_missing_sentence_pairs")
        return
    seen_ids: set[str] = set()
    for offset, pair in enumerate(pairs, start=1):
        pair_path = f"{path}.sentence_pairs[{offset}]"
        sentence_id = str(pair.get("sentence_id") or "")
        if not sentence_id:
            findings.append(f"{pair_path}_missing_sentence_id")
        elif sentence_id in seen_ids:
            findings.append(f"{pair_path}_duplicate_sentence_id:{sentence_id}")
        seen_ids.add(sentence_id)
        if TTS_TAG_RE.search(pair.get("oral") or ""):
            findings.append(f"{pair_path}_oral_contains_tts_tag")
        if TTS_TAG_RE.search(pair.get("subtitle") or ""):
            findings.append(f"{pair_path}_subtitle_contains_tts_tag")
    composed_oral = "".join(pair["oral"] for pair in pairs)
    composed_subtitle = "".join(pair["subtitle"] for pair in pairs)
    if compact_for_alias_match(composed_oral) != compact_for_alias_match(str(raw.get("oral_script") or "")):
        findings.append(f"{path}_sentence_pairs_oral_mismatch")
    if compact_for_alias_match(composed_subtitle) != compact_for_alias_match(str(raw.get("subtitle_script") or "")):
        findings.append(f"{path}_sentence_pairs_subtitle_mismatch")


def validate_video_screen_cards(raw: dict[str, Any], path: str, findings: list[str]) -> None:
    cards = raw.get("screen_cards")
    if not isinstance(cards, list):
        findings.append(f"{path}_missing_screen_cards")
        return
    if len(cards) != 3:
        findings.append(f"{path}_screen_cards_count:{len(cards)}")
    for offset, card_raw in enumerate(cards[:3]):
        card_path = f"{path}.screen_cards[{offset}]"
        if not isinstance(card_raw, dict):
            findings.append(f"{card_path}_not_object")
            continue
        heading = str(card_raw.get("heading") or "").strip()
        body = str(card_raw.get("body") or "").strip()
        points = [str(point).strip() for point in card_raw.get("points") or [] if str(point).strip()] if isinstance(card_raw.get("points"), list) else []
        icon_hint = str(card_raw.get("icon_hint") or "").strip()
        emphasis = str(card_raw.get("emphasis") or "").strip()
        if not heading:
            findings.append(f"{card_path}_missing_heading")
        if not body:
            findings.append(f"{card_path}_missing_body")
        if not points:
            findings.append(f"{card_path}_missing_points")
        if offset == 0 and len(points) < 2:
            findings.append(f"{card_path}_lead_requires_two_points")
        if not icon_hint:
            findings.append(f"{card_path}_missing_icon_hint")
        if not emphasis:
            findings.append(f"{card_path}_missing_emphasis")
        if visual_text_len(heading) < 3:
            findings.append(f"{card_path}_heading_too_short:{visual_text_len(heading)}")
        if "…" in body or "..." in body:
            findings.append(f"{card_path}_body_has_ellipsis")
        for phrase in unclear_reference_findings(f"{heading}\n{body}"):
            findings.append(f"{card_path}_unclear_reference:{phrase}")
        if any(phrase in f"{heading} {body}" for phrase in SCREEN_CARD_BAD_PHRASES):
            findings.append(f"{card_path}_has_meta_viewing_language")
        if visual_text_len(heading) > 18:
            findings.append(f"{card_path}_heading_too_long:{visual_text_len(heading)}")
        if visual_text_len(body) > 150:
            findings.append(f"{card_path}_body_too_long:{visual_text_len(body)}")


def validate_outro_quote_translation(raw: dict[str, Any], path: str, findings: list[str]) -> None:
    quote_translation = str(raw.get("quote_translation") or "").strip()
    if not quote_translation:
        findings.append(f"{path}_missing_quote_translation")
    elif not contains_chinese_text(quote_translation):
        findings.append(f"{path}_quote_translation_not_chinese")


def video_segment_kind(raw: dict[str, Any], path: str) -> str:
    raw_kind = str(raw.get("kind") or "").strip().lower()
    if raw_kind in {"intro", "item", "outro"}:
        return raw_kind
    if "intro" in path:
        return "intro"
    if "outro" in path:
        return "outro"
    return "item"


def minimum_oral_visual_chars(kind: str) -> int:
    return policy_int_mapping(load_video_style_policy(), "minimum_oral_visual_chars").get(kind, 0)


def tts_tag_requirement(kind: str, key: str) -> int:
    return policy_nested_int(load_video_style_policy(), "tts_tag_requirements", kind, key)


def strict_video_style_validation() -> bool:
    return env_bool("AI_DAILY_STRICT_VIDEO_STYLE_VALIDATION", default=False)


def sentence_visual_lengths(text: str) -> list[int]:
    parts = re.split(r"(?<=[。！？!?；;])", text or "")
    lengths = [visual_text_len(part) for part in parts if part and part.strip()]
    return [length for length in lengths if length > 0]


def parse_alias_pair(value: Any) -> tuple[str, str] | None:
    if isinstance(value, dict):
        display = str(value.get("display") or value.get("written") or value.get("from") or "").strip()
        spoken = str(value.get("spoken") or value.get("oral") or value.get("to") or "").strip()
        if display and spoken and compact_for_alias_match(display) != compact_for_alias_match(spoken):
            return display, spoken
        return None
    raw = str(value or "").strip()
    if not raw:
        return None
    for separator in ("=>", "->", "→", "：", ":"):
        if separator not in raw:
            continue
        display, spoken = (part.strip() for part in raw.split(separator, 1))
        if display and spoken and compact_for_alias_match(display) != compact_for_alias_match(spoken):
            return display, spoken
    return None


def contains_alias_form(text: str, alias: str) -> bool:
    alias = str(alias or "").strip()
    if not alias:
        return False
    return alias in text or compact_for_alias_match(alias) in compact_for_alias_match(text)


def video_alias_pairs(raw: dict[str, Any]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for alias in raw.get("spoken_aliases") or []:
        pair = parse_alias_pair(alias)
        if pair and pair not in pairs:
            pairs.append(pair)
    title_pair = parse_alias_pair({"display": raw.get("display_title"), "spoken": raw.get("spoken_title")})
    if title_pair and title_pair not in pairs:
        pairs.append(title_pair)
    return pairs


def alias_requires_written_spoken_split(display: str, spoken: str) -> bool:
    return bool(display and spoken and compact_for_alias_match(display) != compact_for_alias_match(spoken))


def validate_video_script_text(raw: dict[str, Any], path: str, findings: list[str]) -> None:
    validate_sentence_pairs(raw, path, findings)
    kind = video_segment_kind(raw, path)
    oral = str(raw.get("oral_script") or "").strip()
    subtitle = str(raw.get("subtitle_script") or "").strip()
    tts_script = str(raw.get("tts_script") or "").strip()
    if not oral:
        findings.append(f"{path}_missing_oral")
        return
    if not subtitle:
        findings.append(f"{path}_missing_subtitle")
        return
    if not tts_script:
        findings.append(f"{path}_missing_tts_script")
        return
    if TTS_TAG_RE.search(oral):
        findings.append(f"{path}_oral_contains_tts_tag")
    if TTS_TAG_RE.search(subtitle):
        findings.append(f"{path}_subtitle_contains_tts_tag")
    for phrase in unclear_reference_findings("\n".join([oral, subtitle, str(raw.get("display_title") or ""), str(raw.get("spoken_title") or "")])):
        findings.append(f"{path}_unclear_reference:{phrase}")
    clean_tts_script = strip_tts_tags(tts_script)
    if compact_for_alias_match(clean_tts_script) != compact_for_alias_match(oral):
        findings.append(f"{path}_tts_script_text_mismatch")

    strict_style = strict_video_style_validation()
    tag_matches = list(TTS_TAG_RE.finditer(tts_script))
    tag_names = tts_tag_names(tts_script)
    if strict_style:
        min_visual = minimum_oral_visual_chars(kind)
        oral_visual = visual_text_len(oral)
        if min_visual and oral_visual < min_visual:
            findings.append(f"{path}_oral_too_short:{oral_visual}<{min_visual}")
        min_tags = tts_tag_requirement(kind, "min_tags")
        min_unique_tags = tts_tag_requirement(kind, "min_unique_tags")
        if min_tags and len(tag_names) < min_tags:
            findings.append(f"{path}_too_few_tts_tags:{len(tag_names)}<{min_tags}")
        if min_unique_tags and len(set(tag_names)) < min_unique_tags:
            findings.append(f"{path}_too_few_tts_tag_types:{len(set(tag_names))}<{min_unique_tags}")
    if strict_style and tag_matches:
        first_text = TTS_TAG_RE.sub("", tts_script[: tag_matches[-1].end()]).strip()
        trailing_text = tts_script[tag_matches[-1].end() :].strip()
        if not first_text and trailing_text:
            findings.append(f"{path}_tts_tags_only_at_prefix")
    alias_pairs = video_alias_pairs(raw)
    alias_used = False
    for display, spoken in alias_pairs:
        if not alias_requires_written_spoken_split(display, spoken):
            continue
        if contains_alias_form(oral, spoken) or contains_alias_form(subtitle, display):
            alias_used = True
        if contains_alias_form(subtitle, spoken):
            findings.append(f"{path}_subtitle_contains_spoken_alias:{spoken[:40]}")
        if contains_alias_form(oral, display):
            findings.append(f"{path}_oral_contains_display_alias:{display[:40]}")
    if oral == subtitle and alias_used:
        findings.append(f"{path}_oral_subtitle_not_separated")
    if strict_style:
        too_long = [length for length in sentence_visual_lengths(oral) if length > 42]
        if too_long:
            findings.append(f"{path}_oral_sentence_too_long:{max(too_long)}")


def main() -> int:
    args = parse_args()
    summary = generate_editorial_bundle(
        report_path=args.report,
        report_json_path=args.report_json,
        candidate_review_path=args.candidate_review,
        source_pack_dirs=args.source_pack,
        image_manifest_path=args.image_manifest,
        writing_profile_path=args.writing_profile,
        writing_playbook_path=args.writing_playbook,
        editorial_brief_out_path=args.editorial_brief_out,
        out_path=args.out,
        rewrite_report=args.rewrite_report,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
