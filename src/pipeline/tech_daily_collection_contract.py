#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_daily_paths import (
    tech_daily_collection_summary_path,
    tech_daily_content_manifest_path,
    tech_daily_day_dir,
    tech_daily_discovery_dir,
    tech_daily_final_report_json_path,
    tech_daily_final_report_path,
    tech_daily_final_social_urls_path,
    tech_daily_reference_pack_dir,
    tech_daily_source_pack_dir,
    tech_daily_story_assets_dir,
)
from tech_daily_candidate_review import canonicalize_url, load_source_pack

CORE_HASH_KEYS = ("report", "report_json", "content_manifest", "social_urls")
STALE_FALLBACK_MARKERS = (
    "mock",
    "histor",
    "stale",
    "previous",
    "old",
    "reused_local",
    "used_mock",
)


def read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collection_summary_path(date: str) -> Path:
    return tech_daily_collection_summary_path(date)


def default_collection_paths(date: str) -> dict[str, Path]:
    discovery_dir = tech_daily_discovery_dir(date)
    story_dir = tech_daily_story_assets_dir(date)
    return {
        "day_dir": tech_daily_day_dir(date),
        "report": tech_daily_final_report_path(date),
        "report_json": tech_daily_final_report_json_path(date),
        "content_manifest": tech_daily_content_manifest_path(date),
        "social_urls": tech_daily_final_social_urls_path(date),
        "source_pack": tech_daily_source_pack_dir(date),
        "reference_pack": tech_daily_reference_pack_dir(date),
        "story_assets": story_dir,
        "story_manifest": story_dir / "manifest.json",
        "discovery_json": discovery_dir / "rsshub-candidates.json",
        "search_terms": discovery_dir / "search-terms.json",
        "candidate_review": discovery_dir / "candidate-review.json",
        "feed_healthcheck": discovery_dir / "feed-healthcheck.json",
    }


def resolve_collection_paths(date: str, payload: dict[str, Any] | None = None) -> dict[str, Path]:
    resolved = default_collection_paths(date)
    raw_paths = (payload or {}).get("paths")
    if not isinstance(raw_paths, dict):
        return resolved
    for key, value in raw_paths.items():
        if isinstance(value, str) and value.strip():
            normalized_key = "content_manifest" if str(key) == "editorial_bundle" else str(key)
            resolved[normalized_key] = Path(value).expanduser().resolve()
    return resolved


def build_hashes(paths: dict[str, Path], keys: tuple[str, ...] = CORE_HASH_KEYS) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for key in keys:
        path = paths.get(key)
        if key == "content_manifest" and not path:
            path = paths.get("editorial_bundle")
        if path and path.exists() and path.is_file():
            hashes[key] = file_sha256(path)
    return hashes


def story_asset_count(manifest_path: Path) -> int:
    if not manifest_path.exists():
        return 0
    payload = read_json(manifest_path)
    assets = payload.get("assets")
    return len(assets) if isinstance(assets, list) else 0


def report_publication_contract(report_json_path: Path) -> dict[str, Any]:
    if not report_json_path.exists():
        return {}
    payload = read_json(report_json_path)
    machine_review = payload.get("machine_review")
    if not isinstance(machine_review, dict):
        return {}
    contract = machine_review.get("publication_contract")
    return contract if isinstance(contract, dict) else {}


def parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def candidate_entries_by_url(candidate_review_path: Path) -> dict[str, dict[str, Any]]:
    if not candidate_review_path.exists():
        return {}
    payload = read_json(candidate_review_path)
    entries = []
    for key in ("selected_candidates", "ranked_candidates", "all_candidates"):
        raw = payload.get(key)
        if isinstance(raw, list):
            entries.extend(item for item in raw if isinstance(item, dict))
    by_url: dict[str, dict[str, Any]] = {}
    for entry in entries:
        url = canonicalize_url(str(entry.get("canonical_url") or entry.get("url") or ""))
        if url and url not in by_url:
            by_url[url] = entry
    return by_url


def reference_time_for_freshness(payload: dict[str, Any], candidate_review_path: Path) -> tuple[datetime, int]:
    reference = parse_iso_datetime(payload.get("started_at")) or datetime.now(timezone.utc)
    window_hours = 24
    if candidate_review_path.exists():
        try:
            candidate_review = read_json(candidate_review_path)
        except Exception:  # noqa: BLE001
            candidate_review = {}
        reference = parse_iso_datetime(candidate_review.get("generated_at")) or reference
        window_hours = int(candidate_review.get("hot_window_hours") or window_hours)
    return reference, max(window_hours, 1)


def source_pack_entries_by_url(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for key in ("source_pack", "reference_pack"):
        path = paths.get(key)
        if path and path.exists():
            merged.update(load_source_pack(path))
    return merged


def item_source_urls(item: dict[str, Any]) -> list[str]:
    raw_refs = item.get("source_refs")
    refs = [str(ref).strip() for ref in raw_refs if str(ref).strip()] if isinstance(raw_refs, list) else []
    refs.append(str(item.get("source_url") or "").strip())
    canonical_refs = [canonicalize_url(ref) for ref in refs if ref]
    return list(dict.fromkeys(ref for ref in canonical_refs if ref))


def source_timestamp_for_urls(
    urls: list[str],
    *,
    candidates_by_url: dict[str, dict[str, Any]],
    sources_by_url: dict[str, dict[str, Any]],
) -> tuple[datetime | None, str]:
    for url in urls:
        candidate = candidates_by_url.get(url) or {}
        source = sources_by_url.get(url) or {}
        for field in ("published_at", "updated_at", "created_at"):
            parsed = parse_iso_datetime(candidate.get(field))
            if parsed:
                return parsed, f"candidate:{field}:{url}"
        for field in ("published_at", "updated_at", "created_at"):
            parsed = parse_iso_datetime(source.get(field))
            if parsed:
                return parsed, f"source_pack:{field}:{url}"
    return None, ""


def report_freshness_findings(payload: dict[str, Any], paths: dict[str, Path]) -> list[str]:
    report_json_path = paths.get("report_json")
    candidate_review_path = paths.get("candidate_review")
    if not report_json_path or not report_json_path.exists():
        return []
    if not candidate_review_path or not candidate_review_path.exists():
        return ["missing_candidate_review_for_freshness"]
    report_json = read_json(report_json_path)
    items = report_json.get("items")
    if not isinstance(items, list) or not items:
        return ["missing_report_items_for_freshness"]
    reference_time, window_hours = reference_time_for_freshness(payload, candidate_review_path)
    candidates_by_url = candidate_entries_by_url(candidate_review_path)
    sources_by_url = source_pack_entries_by_url(paths)
    findings: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        index = str(item.get("index") or "?")
        urls = item_source_urls(item)
        timestamp, source_label = source_timestamp_for_urls(
            urls,
            candidates_by_url=candidates_by_url,
            sources_by_url=sources_by_url,
        )
        if not timestamp:
            findings.append(f"item_{index}_missing_fresh_source_timestamp")
            continue
        age_hours = (reference_time - timestamp).total_seconds() / 3600.0
        if age_hours < -1.0:
            findings.append(f"item_{index}_future_source_timestamp")
        elif age_hours > window_hours:
            findings.append(f"item_{index}_stale_source_timestamp")
        if source_label.startswith("source_pack:") and not any(url in candidates_by_url for url in urls):
            findings.append(f"item_{index}_not_in_candidate_review")
    return findings


def validate_collection_summary(
    date: str,
    payload: dict[str, Any],
    *,
    min_confirmed: int = 6,
    require_hashes: bool = True,
) -> list[str]:
    findings: list[str] = []
    paths = resolve_collection_paths(date, payload)

    if payload.get("date") != date:
        findings.append("date_mismatch")
    if payload.get("result") not in {None, "success"}:
        findings.append("collection_result_not_success")
    if payload.get("targets_met") is not True:
        findings.append("targets_not_met")
    if int(payload.get("confirmed_count") or 0) < min_confirmed:
        findings.append("less_than_6_confirmed_items")
    if payload.get("top_story_confirmed") is not True:
        findings.append("top_story_not_cross_confirmed")

    fallback_actions = payload.get("fallback_actions")
    if isinstance(fallback_actions, list):
        for action in fallback_actions:
            normalized = str(action or "").lower()
            if any(marker in normalized for marker in STALE_FALLBACK_MARKERS):
                findings.append("stale_or_mock_collection_fallback_used")
                break

    required_files = ("report", "report_json", "content_manifest", "social_urls", "story_manifest")
    for key in required_files:
        path = paths.get(key)
        if not path or not path.exists() or not path.is_file():
            findings.append(f"missing_{key}")

    for key in ("source_pack", "reference_pack"):
        path = paths.get(key)
        if not path or not path.exists() or not path.is_dir():
            findings.append(f"missing_{key}")
        elif not (path / "index.json").exists():
            findings.append(f"missing_{key}_index")

    if int(payload.get("visual_seed_count") or 0) <= 0:
        findings.append("missing_visual_seed")

    contract = report_publication_contract(paths["report_json"])
    if contract:
        contract_confirmed = int(contract.get("confirmed_item_count") or 0)
        if contract_confirmed < min_confirmed:
            findings.append("report_json_less_than_6_confirmed_items")
        top_story = contract.get("top_story") if isinstance(contract.get("top_story"), dict) else {}
        if top_story.get("top_story_confirmed") is not True:
            findings.append("report_json_top_story_not_cross_confirmed")
        if contract.get("status") != "pass":
            findings.append("report_json_publication_contract_failed")

    findings.extend(report_freshness_findings(payload, paths))

    expected_hashes = payload.get("hashes")
    if require_hashes and not isinstance(expected_hashes, dict):
        findings.append("missing_hashes")
        expected_hashes = {}
    if isinstance(expected_hashes, dict):
        for key in CORE_HASH_KEYS:
            path = paths.get(key)
            expected = str(expected_hashes.get(key) or "").strip()
            if key == "content_manifest":
                path = path or paths.get("editorial_bundle")
                expected = expected or str(expected_hashes.get("editorial_bundle") or "").strip()
            if require_hashes and not expected:
                findings.append(f"missing_{key}_hash")
                continue
            if expected and path and path.exists() and path.is_file():
                actual = file_sha256(path)
                if actual != expected:
                    findings.append(f"{key}_hash_mismatch")

    return sorted(set(findings))


def load_collection_summary(date: str) -> dict[str, Any]:
    path = collection_summary_path(date)
    if not path.exists():
        raise FileNotFoundError(f"Missing collection summary: {path}")
    return read_json(path)
