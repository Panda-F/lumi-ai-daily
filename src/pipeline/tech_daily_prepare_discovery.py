#!/usr/bin/env python3

from __future__ import annotations

import argparse
import email.utils
import html
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_daily_paths import tech_daily_discovery_dir

WORKSPACE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = WORKSPACE_DIR / "skills" / "ai-daily-intel" / "references" / "rsshub-discovery.toml"
DEFAULT_EARLY_CONFIG = WORKSPACE_DIR / "skills" / "ai-daily-intel" / "references" / "early-signal-discovery.toml"
DISCOVERY_SCRIPT = WORKSPACE_DIR / "scripts" / "tech_daily_rsshub_discovery.py"
EARLY_SIGNAL_SCRIPT = WORKSPACE_DIR / "scripts" / "tech_daily_early_signal_discovery.py"
SEARCH_TERMS_SCRIPT = WORKSPACE_DIR / "scripts" / "tech_daily_search_terms.py"
HEALTHCHECK_SCRIPT = WORKSPACE_DIR / "scripts" / "tech_daily_feed_healthcheck.py"

DIRECT_PUBLIC_FEEDS: tuple[tuple[str, str, str, str], ...] = (
    ("openai-news", "official", "product_shadow", "https://openai.com/news/rss.xml"),
    ("google-ai", "official", "product_shadow", "https://blog.google/technology/ai/rss/"),
    ("google-deepmind", "official", "research_velocity", "https://deepmind.google/blog/rss.xml"),
    ("hugging-face-blog", "longform", "research_velocity", "https://huggingface.co/blog/feed.xml"),
    ("github-changelog", "changelog", "product_shadow", "https://github.blog/changelog/feed/"),
    ("hacker-news", "community", "people_voice", "https://news.ycombinator.com/rss"),
    ("local-llama", "community", "people_voice", "https://old.reddit.com/r/LocalLLaMA/top/.rss?t=day"),
    ("machine-learning", "community", "research_velocity", "https://old.reddit.com/r/MachineLearning/top/.rss?t=day"),
    ("juya-ai-daily", "chinese_roundup", "people_voice", "https://imjuya.github.io/juya-ai-daily/rss.xml"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare same-day tech-daily discovery artifacts with optional cache reuse."
    )
    parser.add_argument("--date", help="YYYY-MM-DD. Defaults to local today.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to rsshub-discovery TOML config.")
    parser.add_argument("--early-config", default=str(DEFAULT_EARLY_CONFIG), help="Path to early-signal discovery TOML config.")
    parser.add_argument("--discovery-json", help="Optional explicit rsshub-candidates.json path.")
    parser.add_argument("--early-signal-json", help="Optional explicit early-signal-candidates.json path.")
    parser.add_argument("--merged-discovery-json", help="Optional explicit merged-candidates.json path.")
    parser.add_argument("--search-terms-json", help="Optional explicit search-terms.json path.")
    parser.add_argument("--summary-out", help="Optional explicit preflight summary JSON path.")
    parser.add_argument("--window-hours", type=int, default=24, help="Discovery lookback window in hours.")
    parser.add_argument(
        "--reuse-min-candidates",
        type=int,
        default=20,
        help="Reuse an existing same-day discovery cache when it already has at least this many candidates.",
    )
    parser.add_argument(
        "--reuse-max-age-minutes",
        type=int,
        default=120,
        help="Only reuse an existing discovery cache when it was generated within this many minutes.",
    )
    parser.add_argument(
        "--min-candidates",
        type=int,
        default=0,
        help="Mark the run as incomplete when the candidate pool is below this threshold.",
    )
    parser.add_argument(
        "--min-search-terms",
        type=int,
        default=0,
        help="Mark the run as incomplete when generated search terms are below this threshold.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=1,
        help="Maximum number of fresh discovery attempts before returning the best available result.",
    )
    parser.add_argument("--refresh", action="store_true", help="Force a fresh RSSHub discovery run.")
    parser.add_argument("--skip-early-signal", action="store_true", help="Skip the early-signal discovery lane.")
    parser.add_argument("--skip-healthcheck", action="store_true", help="Skip the best-effort feed healthcheck.")
    parser.add_argument("--healthcheck-out", help="Optional explicit feed-healthcheck.json path.")
    parser.add_argument(
        "--check-x-browser",
        action="store_true",
        help="Also probe x-reader browser health during the best-effort healthcheck.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when the configured candidate/search-term targets are not met.",
    )
    parser.add_argument(
        "--discovery-timeout-seconds",
        type=int,
        default=int(os.environ.get("AI_DAILY_DISCOVERY_TIMEOUT_SECONDS", "900")),
        help="Maximum seconds allowed for one RSSHub discovery attempt.",
    )
    parser.add_argument(
        "--early-timeout-seconds",
        type=int,
        default=int(os.environ.get("AI_DAILY_EARLY_SIGNAL_TIMEOUT_SECONDS", "720")),
        help="Maximum seconds allowed for the early-signal discovery layer.",
    )
    parser.add_argument(
        "--research-window-hours",
        type=int,
        default=72,
        help="Lookback window for research velocity signals.",
    )
    return parser.parse_args()


def local_today() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def candidate_count(payload: dict[str, Any]) -> int:
    raw_count = payload.get("candidate_count")
    if isinstance(raw_count, int):
        return raw_count
    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        return len(candidates)
    return 0


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


def discovery_cache_is_recent(payload: dict[str, Any], *, max_age_minutes: int) -> bool:
    if payload.get("stale_or_seed_only") is True or payload.get("recovery_source"):
        return False
    generated_at = parse_iso_datetime(payload.get("generated_at") or payload.get("created_at"))
    if not generated_at:
        return False
    age_minutes = (datetime.now(timezone.utc) - generated_at).total_seconds() / 60.0
    return 0 <= age_minutes <= max(float(max_age_minutes), 1.0)


def term_count(payload: dict[str, Any]) -> int:
    total = 0
    for value in payload.values():
        if isinstance(value, list):
            total += len(value)
    return total


def candidate_date_is_same_day(candidate: dict[str, Any], run_date: str) -> bool:
    published = parse_iso_datetime(candidate.get("published_at"))
    if not published:
        return False
    return published.astimezone(timezone.utc).strftime("%Y-%m-%d") == run_date


def same_day_candidate_count(payload: dict[str, Any], run_date: str) -> int:
    return sum(1 for candidate in load_candidates(payload) if candidate_date_is_same_day(candidate, run_date))


def parse_feed_datetime(value: str) -> str:
    text = html.unescape(str(value or "")).strip()
    if not text:
        return ""
    parsed = parse_iso_datetime(text)
    if parsed:
        return parsed.isoformat()
    try:
        dt = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def xml_child_text(node: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in list(node):
        tag = child.tag.rsplit("}", 1)[-1].lower()
        if tag in wanted:
            return "".join(child.itertext()).strip()
    return ""


def xml_link(node: ET.Element) -> str:
    for child in list(node):
        tag = child.tag.rsplit("}", 1)[-1].lower()
        if tag != "link":
            continue
        href = str(child.attrib.get("href") or "").strip()
        if href:
            return href
        text = "".join(child.itertext()).strip()
        if text:
            return text
    return ""


def fetch_feed_items(feed_url: str, *, timeout: int = 20) -> list[dict[str, str]]:
    request = urllib.request.Request(
        feed_url,
        headers={
            "User-Agent": "Mozilla/5.0 AI-Daily-Discovery/1.0",
            "Accept": "application/rss+xml, application/atom+xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(2_500_000)
    root = ET.fromstring(body)
    nodes = list(root.findall(".//item")) or list(root.findall(".//{*}entry"))
    items: list[dict[str, str]] = []
    for node in nodes[:30]:
        title = xml_child_text(node, "title")
        link = xml_link(node) or xml_child_text(node, "guid", "id")
        summary = xml_child_text(node, "description", "summary", "content", "content:encoded")
        published = xml_child_text(node, "pubDate", "published", "updated", "dc:date")
        if title and link:
            items.append(
                {
                    "title": html.unescape(re.sub(r"\s+", " ", title)).strip(),
                    "url": link.strip(),
                    "summary": html.unescape(re.sub(r"\s+", " ", summary)).strip(),
                    "published_at": parse_feed_datetime(published),
                }
            )
    return items


def direct_public_fallback(run_date: str, *, window_hours: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    feed_reports: list[dict[str, Any]] = []
    for name, kind, lane, feed_url in DIRECT_PUBLIC_FEEDS:
        try:
            items = fetch_feed_items(feed_url)
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as exc:
            feed_reports.append({"name": name, "url": feed_url, "status": "failed", "error": str(exc)[:500]})
            continue
        accepted = 0
        for item in items:
            if item.get("published_at") and not within_window(item["published_at"], window_hours):
                continue
            url = canonicalize_url(item["url"])
            if not url:
                continue
            candidates.append(
                {
                    "canonical_url": url,
                    "url": url,
                    "title": item["title"],
                    "source_kind": kind,
                    "source_label": name,
                    "published_at": item.get("published_at", ""),
                    "feed_url": feed_url,
                    "snippet": item.get("summary", "")[:1600],
                    "signal_lane": lane,
                    "signal_score": 1.0,
                    "discovery_origin": "direct_public_fallback",
                    "evidence_count": 1,
                    "source_independence": 1,
                }
            )
            accepted += 1
        feed_reports.append({"name": name, "url": feed_url, "status": "ok", "accepted": accepted, "seen": len(items)})
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date": run_date,
        "window_hours": window_hours,
        "discovery_method": "direct_public_fallback",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "feed_reports": feed_reports,
        "stale_or_seed_only": False,
    }
    return payload, feed_reports


def load_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        return [item for item in candidates if isinstance(item, dict)]
    items = payload.get("items")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def candidate_url(candidate: dict[str, Any]) -> str:
    return str(candidate.get("canonical_url") or candidate.get("url") or "").strip().lower()


def title_tokens(value: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9+._-]{3,}", value or "")
        if len(token) >= 4
    }


def title_similarity(left: str, right: str) -> float:
    left_tokens = title_tokens(left)
    right_tokens = title_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)


def source_host(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return urlparse(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def canonicalize_url(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        return ""
    try:
        parsed = urllib.parse.urlparse(value)
    except ValueError:
        return value
    if not parsed.scheme or not parsed.netloc:
        return value
    return urllib.parse.urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower().removeprefix("www."),
            parsed.path.rstrip("/") or "/",
            "",
            parsed.query,
            "",
        )
    )


def within_window(published_at: str, window_hours: int) -> bool:
    published = parse_iso_datetime(published_at)
    if not published:
        return False
    age_hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600.0
    return -1.0 <= age_hours <= max(float(window_hours), 1.0)


def merge_discovery_payloads(
    *,
    rsshub_payload: dict[str, Any],
    early_payload: dict[str, Any],
    out_path: Path,
    run_date: str,
    window_hours: int,
    config_path: Path,
    early_config_path: Path,
) -> dict[str, Any]:
    merged: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    def add_candidate(candidate: dict[str, Any], origin: str) -> None:
        url = candidate_url(candidate)
        if not url:
            return
        duplicate: dict[str, Any] | None = None
        for existing in merged:
            existing_url = candidate_url(existing)
            if url == existing_url:
                duplicate = existing
                break
            if source_host(url) and source_host(url) == source_host(existing_url) and title_similarity(
                str(candidate.get("title") or ""), str(existing.get("title") or "")
            ) >= 0.72:
                duplicate = existing
                break
        if duplicate is not None:
            evidence = duplicate.setdefault("secondary_evidence", [])
            if isinstance(evidence, list):
                evidence.append(
                    {
                        "origin": origin,
                        "title": candidate.get("title"),
                        "url": candidate.get("canonical_url") or candidate.get("url"),
                        "signal_lane": candidate.get("signal_lane"),
                        "signal_score": candidate.get("signal_score"),
                    }
                )
            duplicate["evidence_count"] = int(duplicate.get("evidence_count") or 1) + int(candidate.get("evidence_count") or 1)
            duplicate["source_independence"] = max(
                int(duplicate.get("source_independence") or 1), int(candidate.get("source_independence") or 1)
            )
            return
        if url in seen_urls:
            return
        seen_urls.add(url)
        item = dict(candidate)
        item.setdefault("discovery_origin", origin)
        item.setdefault("evidence_count", 1)
        item.setdefault("source_independence", 1)
        merged.append(item)

    for candidate in load_candidates(rsshub_payload):
        add_candidate(candidate, "rsshub")
    for candidate in load_candidates(early_payload):
        add_candidate(candidate, "early_signal")

    merged.sort(
        key=lambda item: (
            float(item.get("signal_score") or item.get("score") or item.get("hot_score") or 0.0),
            int(item.get("evidence_count") or 1),
            str(item.get("published_at") or ""),
        ),
        reverse=True,
    )
    lane_counts: dict[str, int] = {}
    origin_counts: dict[str, int] = {}
    for candidate in merged:
        lane = str(candidate.get("signal_lane") or candidate.get("source_kind") or "unknown")
        origin = str(candidate.get("discovery_origin") or "unknown")
        lane_counts[lane] = lane_counts.get(lane, 0) + 1
        origin_counts[origin] = origin_counts.get(origin, 0) + 1

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date": run_date,
        "config_path": str(config_path),
        "early_config_path": str(early_config_path),
        "window_hours": window_hours,
        "discovery_method": "merged",
        "rsshub_candidate_count": candidate_count(rsshub_payload),
        "early_signal_candidate_count": candidate_count(early_payload),
        "candidate_count": len(merged),
        "lane_counts": lane_counts,
        "origin_counts": origin_counts,
        "early_signal_status": early_payload.get("status") if early_payload else None,
        "early_signal_targets_met": early_payload.get("targets_met") if early_payload else None,
        "candidates": merged,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def run_cmd(
    cmd: list[str],
    *,
    check: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(cmd, timeout, output=stdout, stderr=stderr) from exc
    completed = subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)
    if check and completed.returncode != 0:
        raise subprocess.CalledProcessError(completed.returncode, cmd, output=stdout, stderr=stderr)
    return completed


def safe_load_json(path: Path) -> dict[str, Any]:
    try:
        return load_json(path)
    except Exception:  # noqa: BLE001
        return {}


def run_healthcheck(
    *,
    config_path: Path,
    out_path: Path,
    check_x_browser: bool,
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(HEALTHCHECK_SCRIPT),
        "--config",
        str(config_path),
        "--out",
        str(out_path),
    ]
    if check_x_browser:
        cmd.append("--check-x-browser")
    try:
        result = run_cmd(cmd, check=False, timeout=180 if check_x_browser else 90)
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "path": str(out_path),
            "check_x_browser": check_x_browser,
        }

    payload = safe_load_json(out_path)
    payload.setdefault("status", "ok" if result.returncode == 0 else "failed")
    payload["path"] = str(out_path)
    payload["check_x_browser"] = check_x_browser
    payload["returncode"] = result.returncode
    return payload


def main() -> int:
    args = parse_args()
    run_date = args.date or local_today()
    config_path = Path(args.config).expanduser().resolve()
    early_config_path = Path(args.early_config).expanduser().resolve()
    discovery_dir = tech_daily_discovery_dir(run_date)
    discovery_dir.mkdir(parents=True, exist_ok=True)

    rsshub_json = (
        Path(args.discovery_json).expanduser().resolve()
        if args.discovery_json
        else discovery_dir / "rsshub-candidates.json"
    )
    early_signal_json = (
        Path(args.early_signal_json).expanduser().resolve()
        if args.early_signal_json
        else discovery_dir / "early-signal-candidates.json"
    )
    merged_discovery_json = (
        Path(args.merged_discovery_json).expanduser().resolve()
        if args.merged_discovery_json
        else discovery_dir / "merged-candidates.json"
    )
    effective_discovery_json = rsshub_json if args.skip_early_signal else merged_discovery_json
    search_terms_json = (
        Path(args.search_terms_json).expanduser().resolve()
        if args.search_terms_json
        else discovery_dir / "search-terms.json"
    )

    healthcheck_out = (
        Path(args.healthcheck_out).expanduser().resolve()
        if args.healthcheck_out
        else discovery_dir / "feed-healthcheck.json"
    )
    min_candidate_target = max(args.min_candidates, 0)
    min_search_term_target = max(args.min_search_terms, 0)
    reuse_threshold = max(args.reuse_min_candidates, min_candidate_target)
    max_attempts = max(args.max_attempts, 1)
    window_hours = max(int(args.window_hours or 24), 1)
    discovery_timeout_seconds = max(int(args.discovery_timeout_seconds or 900), 60)
    early_timeout_seconds = max(int(args.early_timeout_seconds or 720), 60)
    research_window_hours = max(int(args.research_window_hours or 72), window_hours)
    reuse_max_age_minutes = max(int(args.reuse_max_age_minutes or 120), 1)

    def meets_targets(
        *,
        candidates: int,
        search_terms: int,
        same_day_candidates: int,
        early_targets_met: bool | None = None,
        stale_or_seed_only: bool = False,
    ) -> bool:
        if stale_or_seed_only:
            return False
        if same_day_candidates <= 0:
            return False
        if min_candidate_target and candidates < min_candidate_target:
            return False
        if min_search_term_target and search_terms < min_search_term_target:
            return False
        if not args.skip_early_signal and early_targets_met is False:
            return False
        return True

    def run_search_terms() -> dict[str, Any]:
        run_cmd(
            [
                sys.executable,
                str(SEARCH_TERMS_SCRIPT),
                "--discovery-json",
                str(effective_discovery_json),
                "--out",
                str(search_terms_json),
            ]
        )
        return safe_load_json(search_terms_json)

    def run_early_signal() -> tuple[dict[str, Any], dict[str, Any]]:
        if args.skip_early_signal:
            return {}, {"status": "skipped"}
        early_summary_out = (
            Path(args.summary_out).expanduser().resolve().parent / "early-signal-preflight.json"
            if args.summary_out
            else discovery_dir.parent / "qa" / "early-signal-preflight.json"
        )
        cmd = [
            sys.executable,
            str(EARLY_SIGNAL_SCRIPT),
            "--date",
            run_date,
            "--config",
            str(early_config_path),
            "--rsshub-json",
            str(rsshub_json),
            "--out",
            str(early_signal_json),
            "--summary-out",
            str(early_summary_out),
            "--window-hours",
            str(window_hours),
            "--research-window-hours",
            str(research_window_hours),
            "--timeout-seconds",
            str(early_timeout_seconds),
        ]
        try:
            run_cmd(cmd, timeout=early_timeout_seconds + 20)
            payload = safe_load_json(early_signal_json)
            return payload, {
                "status": payload.get("status") or "ok",
                "candidate_count": candidate_count(payload),
                "lane_counts": payload.get("lane_counts") or {},
                "targets_met": payload.get("targets_met"),
                "summary_out": str(early_summary_out),
            }
        except subprocess.TimeoutExpired as exc:
            return {}, {"status": "timeout", "error": str(exc), "summary_out": str(early_summary_out)}
        except subprocess.CalledProcessError as exc:
            return safe_load_json(early_signal_json), {
                "status": "failed",
                "error": (exc.stderr or exc.stdout or str(exc)).strip()[:1200],
                "summary_out": str(early_summary_out),
            }

    def build_effective_discovery(rsshub_payload: dict[str, Any], early_payload: dict[str, Any]) -> dict[str, Any]:
        if args.skip_early_signal:
            return rsshub_payload
        return merge_discovery_payloads(
            rsshub_payload=rsshub_payload,
            early_payload=early_payload,
            out_path=merged_discovery_json,
            run_date=run_date,
            window_hours=window_hours,
            config_path=config_path,
            early_config_path=early_config_path,
        )

    reused_discovery = False
    discovery_payload: dict[str, Any] = {}
    rsshub_payload: dict[str, Any] = {}
    early_signal_payload: dict[str, Any] = {}
    early_signal_status: dict[str, Any] | None = None
    search_terms_payload: dict[str, Any] = {}
    attempts: list[dict[str, Any]] = []
    healthcheck_runs: list[dict[str, Any]] = []

    if effective_discovery_json.exists() and not args.refresh:
        existing_payload = safe_load_json(effective_discovery_json)
        existing_window = int(existing_payload.get("window_hours") or 0)
        if (
            existing_window == window_hours
            and candidate_count(existing_payload) >= reuse_threshold
            and discovery_cache_is_recent(existing_payload, max_age_minutes=reuse_max_age_minutes)
        ):
            reused_discovery = True
            discovery_payload = existing_payload
            rsshub_payload = safe_load_json(rsshub_json)
            early_signal_payload = safe_load_json(early_signal_json)
            early_signal_status = {
                "status": early_signal_payload.get("status") if early_signal_payload else "reused",
                "candidate_count": candidate_count(early_signal_payload),
                "lane_counts": early_signal_payload.get("lane_counts") if early_signal_payload else {},
                "targets_met": early_signal_payload.get("targets_met") if early_signal_payload else None,
            }
            search_terms_payload = run_search_terms()
            if not meets_targets(
                candidates=candidate_count(discovery_payload),
                search_terms=term_count(search_terms_payload),
                same_day_candidates=same_day_candidate_count(discovery_payload, run_date),
                early_targets_met=early_signal_status.get("targets_met") if early_signal_status else None,
                stale_or_seed_only=bool(discovery_payload.get("stale_or_seed_only")),
            ):
                reused_discovery = False
                discovery_payload = {}
                rsshub_payload = {}
                early_signal_payload = {}
                early_signal_status = None
                search_terms_payload = {}

    if not reused_discovery:
        for attempt_index in range(1, max_attempts + 1):
            if not args.skip_healthcheck:
                healthcheck_runs.append(
                    run_healthcheck(
                        config_path=config_path,
                        out_path=healthcheck_out,
                        check_x_browser=args.check_x_browser or attempt_index > 1,
                    )
                )

            discovery_cmd = [
                sys.executable,
                str(DISCOVERY_SCRIPT),
                "--config",
                str(config_path),
                "--out",
                str(rsshub_json),
                "--window-hours",
                str(window_hours),
            ]
            discovery_status = "success"
            discovery_error = ""
            try:
                run_cmd(discovery_cmd, timeout=discovery_timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                discovery_status = "timeout"
                discovery_error = str(exc)
            except subprocess.CalledProcessError as exc:
                discovery_status = "failed"
                discovery_error = (exc.stderr or exc.stdout or str(exc)).strip()[:1200]

            rsshub_payload = safe_load_json(rsshub_json)
            early_signal_payload, early_signal_status = run_early_signal()
            discovery_payload = build_effective_discovery(rsshub_payload, early_signal_payload) if rsshub_payload or early_signal_payload else {}
            search_terms_payload = run_search_terms() if discovery_payload else {}

            attempt_summary = {
                "attempt": attempt_index,
                "rsshub_status": discovery_status,
                "early_signal_status": early_signal_status,
                "rsshub_candidate_count": candidate_count(rsshub_payload),
                "early_signal_candidate_count": candidate_count(early_signal_payload),
                "candidate_count": candidate_count(discovery_payload),
                "search_term_count": term_count(search_terms_payload),
                "targets_met": meets_targets(
                    candidates=candidate_count(discovery_payload),
                    search_terms=term_count(search_terms_payload),
                    same_day_candidates=same_day_candidate_count(discovery_payload, run_date),
                    early_targets_met=early_signal_status.get("targets_met") if early_signal_status else None,
                    stale_or_seed_only=bool(discovery_payload.get("stale_or_seed_only")),
                ),
            }
            if discovery_error:
                attempt_summary["rsshub_error"] = discovery_error
            attempts.append(attempt_summary)
            if attempt_summary["targets_met"]:
                break
            if attempt_index < max_attempts:
                time.sleep(min(5, attempt_index))

    recovery_payload: dict[str, Any] = {}
    recovery_feed_reports: list[dict[str, Any]] = []
    if not reused_discovery and not meets_targets(
        candidates=candidate_count(discovery_payload),
        search_terms=term_count(search_terms_payload),
        same_day_candidates=same_day_candidate_count(discovery_payload, run_date),
        early_targets_met=early_signal_status.get("targets_met") if early_signal_status else None,
        stale_or_seed_only=bool(discovery_payload.get("stale_or_seed_only")),
    ):
        recovery_payload, recovery_feed_reports = direct_public_fallback(run_date, window_hours=window_hours)
        if candidate_count(recovery_payload) > candidate_count(discovery_payload):
            discovery_payload = build_effective_discovery(rsshub_payload, recovery_payload)
            early_signal_payload = recovery_payload
            early_signal_status = {
                "status": "direct_public_fallback",
                "candidate_count": candidate_count(recovery_payload),
                "lane_counts": recovery_payload.get("lane_counts") or {},
                "targets_met": False,
                "summary_out": None,
            }
            search_terms_payload = run_search_terms() if discovery_payload else {}

    summary = {
        "date": run_date,
        "config": str(config_path),
        "early_config": str(early_config_path),
        "window_hours": window_hours,
        "reused_discovery": reused_discovery,
        "skip_early_signal": args.skip_early_signal,
        "thresholds": {
            "reuse_min_candidates": args.reuse_min_candidates,
            "min_candidates": min_candidate_target,
            "min_search_terms": min_search_term_target,
            "max_attempts": max_attempts,
            "window_hours": window_hours,
            "discovery_timeout_seconds": discovery_timeout_seconds,
            "early_timeout_seconds": early_timeout_seconds,
            "research_window_hours": research_window_hours,
            "reuse_max_age_minutes": reuse_max_age_minutes,
        },
        "rsshub_candidate_count": candidate_count(rsshub_payload),
        "early_signal_candidate_count": candidate_count(early_signal_payload),
        "early_signal_status": early_signal_status,
        "candidate_count": candidate_count(discovery_payload),
        "search_term_count": term_count(search_terms_payload),
        "same_day_candidate_count": same_day_candidate_count(discovery_payload, run_date),
        "rsshub_json": str(rsshub_json),
        "early_signal_json": str(early_signal_json),
        "merged_discovery_json": str(merged_discovery_json),
        "discovery_json": str(effective_discovery_json),
        "search_terms_json": str(search_terms_json),
        "healthcheck": healthcheck_runs[-1] if healthcheck_runs else None,
        "healthcheck_runs": healthcheck_runs,
        "attempts": attempts,
        "recovery_candidates": {
            "candidate_count": candidate_count(recovery_payload),
            "feed_reports": recovery_feed_reports,
            "stale_or_seed_only": True,
            "note": "Direct public fallback candidates are usable as seeds only until archived and validated in collection-summary.json.",
        }
        if recovery_payload
        else None,
    }
    summary["targets_met"] = meets_targets(
        candidates=summary["candidate_count"],
        search_terms=summary["search_term_count"],
        same_day_candidates=summary["same_day_candidate_count"],
        early_targets_met=early_signal_status.get("targets_met") if early_signal_status else None,
        stale_or_seed_only=bool(discovery_payload.get("stale_or_seed_only")),
    )
    if summary["targets_met"]:
        summary["status"] = "pass"
    elif summary["candidate_count"] >= max(20, (min_candidate_target // 2) or 20):
        summary["status"] = "warn"
    else:
        summary["status"] = "fail"

    if args.summary_out:
        summary_out = Path(args.summary_out).expanduser().resolve()
        summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.strict and not summary["targets_met"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
