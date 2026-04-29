#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build structured style-corpus entries for the tech-daily writer layer.")
    parser.add_argument("--samples-json", required=True, help="JSON file containing newsletter samples.")
    parser.add_argument("--out", required=True, help="Output corpus JSON path.")
    parser.add_argument("--formal-source", choices=("gmail", "public"), default="public")
    parser.add_argument("--playbook-out", help="Optional writing playbook JSON path derived from this corpus.")
    return parser.parse_args()


def load_samples(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("samples"), list):
        return [item for item in payload["samples"] if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        return [item for item in payload["entries"] if isinstance(item, dict)]
    return []


def normalize_text(text: str) -> str:
    value = re.sub(r"\s+", " ", text or "").strip()
    return value


def split_paragraphs(text: str) -> list[str]:
    return [normalize_text(part) for part in re.split(r"\n\s*\n", text or "") if normalize_text(part)]


def truncate(text: str, limit: int) -> str:
    value = normalize_text(text)
    if len(value) <= limit:
        return value
    return value[: max(limit - 1, 1)].rstrip(" ,;:") + "…"


def detect_tone_tags(text: str, source: str) -> list[str]:
    value = f"{source} {text}".lower()
    tags: list[str] = []
    checks = [
        ("human-centered", ["human", "people", "society", "work", "adoption"]),
        ("operator-view", ["eval", "benchmark", "post-training", "cost", "deployment"]),
        ("essayistic", ["history", "theory", "culture", "psychology"]),
        ("judgment-first", ["i think", "my view", "the point is", "my take"]),
        ("boundary-aware", ["but", "however", "limit", "caveat", "boundary"]),
    ]
    for tag, markers in checks:
        if any(marker in value for marker in markers):
            tags.append(tag)
    return tags or ["general"]


def detect_visual_modes(text: str, explicit: list[str] | None) -> list[str]:
    values = [str(value) for value in explicit or [] if str(value).strip()]
    if values:
        return values
    lowered = text.lower()
    modes: list[str] = []
    if any(term in lowered for term in ["chart", "graph", "benchmark", "table", "index"]):
        modes.append("chart_or_screenshot")
    if any(term in lowered for term in ["diagram", "framework", "system", "workflow", "architecture"]):
        modes.append("diagram_or_framework")
    if any(term in lowered for term in ["history", "culture", "society", "psychology", "art"]):
        modes.append("art_or_cultural_image")
    return modes or ["diagram_or_framework"]


def build_entry(sample: dict[str, Any], *, formal_source: bool) -> dict[str, Any]:
    body = normalize_text(str(sample.get("body") or sample.get("content") or ""))
    raw_sections = sample.get("sections") if isinstance(sample.get("sections"), list) else []
    raw_tone_tags = sample.get("tone_tags") if isinstance(sample.get("tone_tags"), list) else []
    provided_lead = normalize_text(str(sample.get("lead") or ""))
    provided_closing = normalize_text(str(sample.get("closing") or ""))
    provided_sections = [
        normalize_text(str(value))
        for value in raw_sections
        if normalize_text(str(value))
    ]
    provided_tone_tags = [
        normalize_text(str(value))
        for value in raw_tone_tags
        if normalize_text(str(value))
    ]
    paragraphs = split_paragraphs(body)
    title = truncate(str(sample.get("title") or ""), 120)
    subhead = truncate(str(sample.get("subhead") or sample.get("subtitle") or ""), 220)
    lead = truncate(provided_lead or (paragraphs[0] if paragraphs else body), 220)
    evidence_block = ""
    for paragraph in paragraphs[1:]:
        if re.search(r"\d|%|\$|benchmark|eval|usage|study|index|survey", paragraph, re.I):
            evidence_block = truncate(paragraph, 260)
            break
    transition = ""
    for paragraph in paragraphs[1:]:
        if re.search(r"\bbut\b|\bhowever\b|\byet\b|\bmeanwhile\b|\bthough\b", paragraph, re.I):
            transition = truncate(paragraph, 220)
            break
    closing = truncate(provided_closing or (paragraphs[-1] if paragraphs else body), 220)
    derived_sections = [
        value
        for value in [
            f"subhead: {subhead}" if subhead else "",
            f"evidence_block: {evidence_block}" if evidence_block else "",
            f"transition: {transition}" if transition else "",
        ]
        if value
    ]
    sections = provided_sections or derived_sections
    analysis_text = normalize_text(
        " ".join([title, subhead, lead, " ".join(sections), closing, body])
    )
    return {
        "source": str(sample.get("source") or ""),
        "date": str(sample.get("date") or ""),
        "title": title,
        "lead": lead,
        "sections": sections,
        "closing": closing,
        "visual_mode": detect_visual_modes(
            analysis_text,
            sample.get("visual_mode") if isinstance(sample.get("visual_mode"), list) else None,
        ),
        "tone_tags": provided_tone_tags or detect_tone_tags(analysis_text, str(sample.get("source") or "")),
        "formal_source": formal_source,
    }


def build_playbook(entries: list[dict[str, Any]], *, formal_source: str) -> dict[str, Any]:
    opening_examples = [str(entry.get("lead") or "").strip() for entry in entries if str(entry.get("lead") or "").strip()][:3]
    closing_examples = [str(entry.get("closing") or "").strip() for entry in entries if str(entry.get("closing") or "").strip()][:3]
    tone_examples = [str(entry.get("title") or "").strip() for entry in entries if str(entry.get("title") or "").strip()][:3]
    rules = [
        {
            "key": "opening_judgment_first",
            "kind": "opening",
            "instruction": "开头先给总判断，再展开当天 6 条信号，不要直接平铺事实。",
            "confidence": 7.5,
            "examples": opening_examples,
        },
        {
            "key": "non_expert_bridge",
            "kind": "audience_bridge",
            "instruction": "先把技术变化翻译成人话，再补专业含义，默认读者不是专业从业者。",
            "confidence": 8.0,
            "examples": [],
        },
        {
            "key": "signal_triplet_structure",
            "kind": "structure",
            "instruction": "每条信号按“发生了什么 / 为什么是今天 / 为什么你该在意”组织，避免重复同一句 relevance 模板。",
            "confidence": 8.0,
            "examples": tone_examples,
        },
        {
            "key": "evidence_then_implication",
            "kind": "structure",
            "instruction": "每段先给可验证事实，再给影响判断，不要先下结论后找补证据。",
            "confidence": 7.0,
            "examples": [],
        },
        {
            "key": "closing_public_takeaway",
            "kind": "closing",
            "instruction": "结尾要回答普通人今天能带走什么，给出一条面向现实工作和生活的启发。",
            "confidence": 7.5,
            "examples": closing_examples,
        },
        {
            "key": "jargon_explain_on_first_use",
            "kind": "word_preference",
            "instruction": "公司、产品、术语第一次出现时顺手解释，不要假设读者已经懂。",
            "confidence": 8.5,
            "examples": [],
        },
    ]
    return {
        "version": 1,
        "formal_source": formal_source == "gmail",
        "source_type": formal_source,
        "entry_count": len(entries),
        "rules": rules,
    }


def main() -> int:
    args = parse_args()
    samples = load_samples(Path(args.samples_json).expanduser().resolve())
    entries = [build_entry(sample, formal_source=args.formal_source == "gmail") for sample in samples]
    payload = {
        "formal_source": args.formal_source == "gmail",
        "entry_count": len(entries),
        "entries": entries,
    }
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    playbook_path = None
    if args.playbook_out:
        playbook_path = Path(args.playbook_out).expanduser().resolve()
        playbook_path.parent.mkdir(parents=True, exist_ok=True)
        playbook_payload = build_playbook(entries, formal_source=args.formal_source)
        playbook_path.write_text(json.dumps(playbook_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "result": "success",
                "entry_count": len(entries),
                "out": str(out_path),
                "playbook_out": str(playbook_path) if playbook_path else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
