#!/usr/bin/env python3

from __future__ import annotations

import argparse
import difflib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Learn daily-writer playbook rules from draft vs final markdown.")
    parser.add_argument("--draft", required=True, help="Generated markdown path.")
    parser.add_argument("--final", required=True, help="Edited markdown path.")
    parser.add_argument("--playbook-out", required=True, help="Playbook JSON output path.")
    return parser.parse_args()


def read_text(path: str | Path) -> str:
    return Path(path).expanduser().resolve().read_text(encoding="utf-8")


def normalize_text(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"\r\n?", "\n", text)
    return text.strip()


def paragraphs(text: str) -> list[str]:
    body = re.sub(r"^#.*$", "", text, flags=re.M)
    return [re.sub(r"\s+", " ", part).strip() for part in re.split(r"\n\s*\n", body) if re.sub(r"\s+", " ", part).strip()]


def title(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def first_paragraph(text: str) -> str:
    parts = paragraphs(text)
    return parts[0] if parts else ""


def average_paragraph_length(text: str) -> float:
    parts = paragraphs(text)
    if not parts:
        return 0.0
    return sum(len(part) for part in parts) / len(parts)


def word_preferences(draft: str, final: str) -> list[dict[str, Any]]:
    draft_tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9_-]{2,}", draft)
    final_tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9_-]{2,}", final)
    draft_counter = Counter(draft_tokens)
    final_counter = Counter(final_tokens)
    rules: list[dict[str, Any]] = []
    for token, count in draft_counter.most_common(12):
        if count >= 2 and final_counter[token] == 0:
            rules.append(
                {
                    "key": f"avoid_{token}",
                    "kind": "banned_word",
                    "instruction": f"不要使用“{token}”",
                    "confidence": 3.0,
                }
            )
    return rules[:4]


def summarize_rules(draft_text: str, final_text: str) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    draft_title = title(draft_text)
    final_title = title(final_text)
    if draft_title and final_title and draft_title != final_title:
        rules.append(
            {
                "key": "title_rewrite_pattern",
                "kind": "title",
                "instruction": f"标题优先向“{final_title}”这类更直接、判断先行的写法靠拢",
                "confidence": 4.0,
                "examples": [final_title],
            }
        )

    draft_opening = first_paragraph(draft_text)
    final_opening = first_paragraph(final_text)
    if draft_opening and final_opening and draft_opening != final_opening:
        rules.append(
            {
                "key": "opening_syntax_preference",
                "kind": "opening",
                "instruction": "开头前 120 字先回答‘这和普通读者/产品人有什么关系’，避免直接平铺新闻事实",
                "confidence": 4.0,
                "examples": [final_opening[:120]],
            }
        )

    draft_avg = average_paragraph_length(draft_text)
    final_avg = average_paragraph_length(final_text)
    if draft_avg and final_avg:
        if final_avg + 12 < draft_avg:
            rules.append(
                {
                    "key": "shorter_paragraphs",
                    "kind": "paragraph_length",
                    "instruction": "段落保持更短，每段尽量只完成一个判断或一个转折",
                    "confidence": 3.5,
                }
            )
        elif final_avg > draft_avg + 12:
            rules.append(
                {
                    "key": "longer_paragraphs",
                    "kind": "paragraph_length",
                    "instruction": "段落允许稍长，但必须先给判断再补证据，不要碎成过多信息块",
                    "confidence": 3.5,
                }
            )

    rules.extend(word_preferences(draft_text, final_text))
    return rules


def merge_playbook(existing: dict[str, Any], fresh_rules: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {}
    for raw in existing.get("rules") or []:
        if isinstance(raw, dict) and raw.get("key"):
            merged[str(raw["key"])] = dict(raw)
    for rule in fresh_rules:
        key = str(rule.get("key") or "")
        if not key:
            continue
        current = merged.get(key, {})
        occurrences = int(current.get("occurrences") or 0) + 1
        confidence = max(float(current.get("confidence") or 0.0), float(rule.get("confidence") or 0.0))
        confidence = round(min(confidence + 0.5 * (occurrences - 1), 8.0), 2)
        merged[key] = {
            "key": key,
            "kind": str(rule.get("kind") or current.get("kind") or ""),
            "instruction": str(rule.get("instruction") or current.get("instruction") or ""),
            "confidence": confidence,
            "occurrences": occurrences,
            "examples": list(dict.fromkeys([*(current.get("examples") or []), *(rule.get("examples") or [])]))[:4],
        }
    payload = {
        "version": int(existing.get("version") or 1),
        "rules": sorted(merged.values(), key=lambda rule: (-float(rule.get("confidence") or 0.0), str(rule.get("key") or ""))),
    }
    return payload


def main() -> int:
    args = parse_args()
    draft_text = normalize_text(read_text(args.draft))
    final_text = normalize_text(read_text(args.final))
    fresh_rules = summarize_rules(draft_text, final_text)
    out_path = Path(args.playbook_out).expanduser().resolve()
    existing = {}
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    payload = merge_playbook(existing if isinstance(existing, dict) else {}, fresh_rules)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "result": "success",
        "rule_count": len(payload["rules"]),
        "playbook": str(out_path),
        "added_keys": [rule["key"] for rule in fresh_rules],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
