#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ai_daily_paths import tech_daily_cover_lab_dir

DEFAULT_DOWNLOADS_DIR = Path("/tmp/openclaw/downloads")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _resolve_path(raw: str | Path | None) -> Path | None:
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_absolute() else path.resolve()


def _resolve_paths(raw: Any) -> list[Path]:
    if raw is None:
        return []
    if isinstance(raw, (str, Path)):
        path = _resolve_path(raw)
        return [path] if path else []
    if isinstance(raw, list):
        return [path for item in raw if (path := _resolve_path(item))]
    if isinstance(raw, dict):
        return [path for item in raw.values() if (path := _resolve_path(item))]
    return []


def default_cover_result_path(date: str) -> Path:
    return DEFAULT_DOWNLOADS_DIR / f"tech-cover-{date}.result.json"


def load_cover_result(path: str | Path | None) -> dict[str, Any] | None:
    result_path = _resolve_path(path)
    if not result_path or not result_path.exists():
        return None
    try:
        return json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _cover_image_from_result(payload: dict[str, Any]) -> Path | None:
    for downloaded in _resolve_paths(payload.get("downloaded")):
        if downloaded.exists() and downloaded.suffix.lower() in IMAGE_SUFFIXES:
            return downloaded

    artifacts = payload.get("artifacts")
    candidates: list[Path] = []
    if isinstance(artifacts, list):
        candidates = [candidate for item in artifacts if (candidate := _resolve_path(item))]
    elif isinstance(artifacts, dict):
        candidates = [candidate for item in artifacts.values() if (candidate := _resolve_path(item))]

    for candidate in candidates:
        if candidate.exists() and candidate.suffix.lower() in IMAGE_SUFFIXES:
            return candidate
    return None


def _cover_lab_final_image(date: str) -> tuple[Path | None, str | None]:
    cover_lab_dir = tech_daily_cover_lab_dir(date)
    final_json = cover_lab_dir / "final-cover.json"
    payload: dict[str, Any] = {}
    json_exists = final_json.exists()
    if final_json.exists():
        try:
            payload = json.loads(final_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        preferred = _resolve_path(payload.get("image"))
        if preferred and preferred.exists() and preferred.suffix.lower() in IMAGE_SUFFIXES:
            return preferred, str(final_json)

        # If metadata explicitly says this handoff failed, do not silently reuse
        # a sibling final-cover.png and pretend it is a successful final asset.
        final_stage = str(payload.get("final_stage") or "").strip().lower()
        provider = str(payload.get("provider") or "").strip().lower()
        ok_flag = payload.get("ok")
        metadata_marks_failure = (
            ok_flag is False
            or final_stage in {"login_required", "fallback_collage", "failed"}
            or final_stage.endswith("_failed")
            or provider == "fallback_collage"
        )
        if metadata_marks_failure:
            return None, str(final_json)

    for suffix in sorted(IMAGE_SUFFIXES):
        candidate = cover_lab_dir / f"final-cover{suffix}"
        if candidate.exists():
            return candidate, str(final_json) if json_exists else None
    return None, str(final_json) if json_exists else None


def resolve_daily_cover(
    *,
    date: str,
    explicit_cover_image: str | Path | None = None,
    explicit_cover_result: str | Path | None = None,
    fallback_video_cover: str | Path | None = None,
) -> dict[str, Any]:
    explicit_path = _resolve_path(explicit_cover_image)
    if explicit_path and explicit_path.exists():
        return {
            "path": explicit_path,
            "source": "explicit_cover_image",
            "provider": "explicit",
            "result_json": None,
            "used_fallback": False,
        }

    cover_lab_image, cover_lab_meta = _cover_lab_final_image(date)
    if cover_lab_image and cover_lab_image.exists():
        return {
            "path": cover_lab_image,
            "source": "cover_lab_final",
            "provider": "cover_lab_final",
            "result_json": cover_lab_meta,
            "used_fallback": False,
        }

    result_path = _resolve_path(explicit_cover_result) or default_cover_result_path(date)
    payload = load_cover_result(result_path)
    if payload:
        resolved_path = _cover_image_from_result(payload)
        if resolved_path and resolved_path.exists():
            provider = str(payload.get("provider") or "unknown")
            source = "cover_result_fallback_collage" if provider == "fallback_collage" else "cover_result_downloaded"
            return {
                "path": resolved_path,
                "source": source,
                "provider": provider,
                "result_json": str(result_path),
                "used_fallback": provider == "fallback_collage",
            }

    video_cover_path = _resolve_path(fallback_video_cover)
    if video_cover_path and video_cover_path.exists():
        return {
            "path": video_cover_path,
            "source": "video_cover_fallback",
            "provider": "video_cover",
            "result_json": str(result_path) if result_path else None,
            "used_fallback": True,
        }

    return {
        "path": None,
        "source": None,
        "provider": None,
        "result_json": str(result_path) if result_path else None,
        "used_fallback": False,
    }


def stage_daily_cover(source: str | Path | None, out_dir: str | Path, stem: str = "daily-cover") -> Path | None:
    source_path = _resolve_path(source)
    if not source_path or not source_path.exists():
        return None
    destination_dir = Path(out_dir).expanduser().resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    suffix = source_path.suffix.lower() or ".png"
    destination = destination_dir / f"{stem}{suffix}"
    if source_path.resolve() != destination.resolve():
        shutil.copy2(source_path, destination)
    return destination
