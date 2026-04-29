#!/usr/bin/env python3

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any


WORKSPACE_DIR = Path(__file__).resolve().parents[3]
REMOTION_DIR = Path(__file__).resolve().parents[1] / "remotion"
EXPECTED_SIZE = (1920, 1080)

INTRO_REGIONS = {
    "brand_tag": (0.73, 0.03, 0.97, 0.12),
    "headline": (0.47, 0.13, 0.88, 0.37),
    "trend_tags": (0.47, 0.31, 0.82, 0.42),
    "agenda_card": (0.47, 0.37, 0.96, 0.73),
    "status_bar": (0.0, 0.96, 1.0, 1.0),
}

ITEM_REGIONS = {
    "header": (0.0, 0.0, 1.0, 0.09),
    "left_title": (0.03, 0.12, 0.44, 0.36),
    "left_cards": (0.03, 0.31, 0.45, 0.63),
    "right_quote": (0.47, 0.16, 0.97, 0.58),
    "bottom_bar": (0.0, 0.92, 1.0, 1.0),
}

PALETTE_SAMPLES = {
    "bg_top_left": (24, 24),
    "bg_top_right": (1896, 24),
    "bg_bottom_right": (1896, 1040),
    "subtitle_bar": (960, 1050),
}

EXPECTED_TOKENS = {
    "bg_top_left": (255, 248, 245),
    "bg_top_right": (255, 240, 248),
    "bg_bottom_right": (245, 240, 255),
    "subtitle_bar": (55, 65, 81),
}


def _ensure_pillow() -> None:
    try:
        import PIL  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Pillow unavailable: {exc}") from exc


def _chrome_shell_candidates() -> list[Path]:
    cached = sorted(
        (REMOTION_DIR / "node_modules/.remotion").glob("chrome-headless-shell/**/chrome-headless-shell")
    )
    system = [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
    ]
    return [*cached, *[path for path in system if path.exists()]]


def _find_chrome_shell() -> Path:
    for candidate in _chrome_shell_candidates():
        if candidate.exists():
            return candidate
    raise RuntimeError("Could not find a Chrome headless shell for HTML baseline screenshots")


def _render_html_to_png(html_path: Path, output_path: Path) -> Path:
    chrome = _find_chrome_shell()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(chrome),
            "--headless=old",
            "--disable-gpu",
            "--hide-scrollbars",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=3500",
            "--window-size=1920,1080",
            f"--screenshot={output_path}",
            html_path.resolve().as_uri(),
        ],
        check=True,
        cwd=str(html_path.parent),
        capture_output=True,
        text=True,
    )
    return output_path


def _resolve_html_baselines(report_path: Path, out_dir: Path, html_baseline: str) -> dict[str, Path]:
    intro_name = "lumi-intro-light.html" if html_baseline == "light" else "lumi-intro-16x9.html"
    item_name = "lumi-item-light.html" if html_baseline == "light" else "lumi-item-16x9.html"
    search_roots = [
        out_dir,
        out_dir.parent / "video-build",
        report_path.parent / "video-build",
        report_path.parent,
    ]
    for root in search_roots:
        intro = root / intro_name
        item = root / item_name
        if intro.exists() and item.exists():
            return {"root": root, "intro": intro, "item": item}
    daily_reports_root = report_path.parent.parent
    if daily_reports_root.exists():
        for report_dir in sorted(daily_reports_root.glob("20??-??-??"), reverse=True):
            intro = report_dir / "video-build" / intro_name
            item = report_dir / "video-build" / item_name
            if intro.exists() and item.exists():
                return {"root": report_dir / "video-build", "intro": intro, "item": item}
    raise RuntimeError(f"Could not resolve HTML baselines for {html_baseline}")


def _open_image(path: Path):
    _ensure_pillow()
    from PIL import Image  # type: ignore

    image = Image.open(path).convert("RGB")
    if image.size != EXPECTED_SIZE:
        image = image.resize(EXPECTED_SIZE)
    return image


def _crop_box(size: tuple[int, int], region: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    width, height = size
    left = max(0, int(width * region[0]))
    top = max(0, int(height * region[1]))
    right = min(width, int(width * region[2]))
    bottom = min(height, int(height * region[3]))
    return left, top, right, bottom


def _region_metrics(image_path: Path, regions: dict[str, tuple[float, float, float, float]]) -> dict[str, dict[str, float]]:
    _ensure_pillow()
    from PIL import ImageFilter, ImageStat  # type: ignore

    image = _open_image(image_path)
    metrics: dict[str, dict[str, float]] = {}
    for name, region in regions.items():
        crop = image.crop(_crop_box(image.size, region))
        stat = ImageStat.Stat(crop)
        edge_mean = float(ImageStat.Stat(crop.convert("L").filter(ImageFilter.FIND_EDGES)).mean[0])
        metrics[name] = {
            "mean_r": float(stat.mean[0]),
            "mean_g": float(stat.mean[1]),
            "mean_b": float(stat.mean[2]),
            "std_r": float(stat.stddev[0]),
            "std_g": float(stat.stddev[1]),
            "std_b": float(stat.stddev[2]),
            "edge_mean": edge_mean,
        }
    return metrics


def _color_distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _compare_region_metrics(
    baseline_metrics: dict[str, dict[str, float]],
    actual_metrics: dict[str, dict[str, float]],
    *,
    color_tolerance: float,
    std_tolerance: float,
    edge_tolerance: float,
) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    for name, baseline in baseline_metrics.items():
        actual = actual_metrics[name]
        color_delta = _color_distance(
            (baseline["mean_r"], baseline["mean_g"], baseline["mean_b"]),
            (actual["mean_r"], actual["mean_g"], actual["mean_b"]),
        )
        std_delta = _color_distance(
            (baseline["std_r"], baseline["std_g"], baseline["std_b"]),
            (actual["std_r"], actual["std_g"], actual["std_b"]),
        )
        edge_delta = abs(baseline["edge_mean"] - actual["edge_mean"])
        passed = color_delta <= color_tolerance and std_delta <= std_tolerance and edge_delta <= edge_tolerance
        comparisons.append(
            {
                "region": name,
                "passed": passed,
                "color_delta": round(color_delta, 2),
                "std_delta": round(std_delta, 2),
                "edge_delta": round(edge_delta, 2),
            }
        )
    return comparisons


def _palette_sample_points(scene_kind: str) -> dict[str, tuple[int, int]]:
    points = dict(PALETTE_SAMPLES)
    if scene_kind == "item":
        points["bg_bottom_right"] = (1896, 900)
    return points


def _sample_palette(image_path: Path, *, scene_kind: str) -> dict[str, dict[str, Any]]:
    image = _open_image(image_path)
    samples: dict[str, dict[str, Any]] = {}
    for name, point in _palette_sample_points(scene_kind).items():
        if scene_kind == "intro" and name == "subtitle_bar":
            continue
        pixel = image.getpixel(point)
        delta = _color_distance(tuple(float(value) for value in pixel), tuple(float(v) for v in EXPECTED_TOKENS[name]))
        samples[name] = {
            "pixel": list(pixel),
            "expected": list(EXPECTED_TOKENS[name]),
            "delta": round(delta, 2),
            "passed": delta <= (30.0 if name != "subtitle_bar" else 320.0),
        }
    return samples


def _occupancy_check(image_path: Path, region: tuple[float, float, float, float], *, min_edge: float) -> dict[str, Any]:
    metrics = _region_metrics(image_path, {"slot": region})["slot"]
    return {
        "edge_mean": round(metrics["edge_mean"], 2),
        "passed": metrics["edge_mean"] >= min_edge,
    }


def _scene_slide_map(out_dir: Path, slides_dir: Path) -> dict[str, Path]:
    manifest_path = out_dir / "remotion-manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    scenes = payload.get("scenes") or []
    mapping: dict[str, Path] = {}
    for scene in scenes:
        if not isinstance(scene, dict) or scene.get("kind") != "item":
            continue
        current_index = int(scene.get("current_index") or 0)
        if current_index <= 0:
            continue
        slide_path = slides_dir / f"{current_index:02d}-item.png"
        if slide_path.exists():
            mapping[f"item:{current_index}"] = slide_path
            if scene.get("primary_media_src") and "with_media" not in mapping:
                mapping["with_media"] = slide_path
            if not scene.get("primary_media_src") and "without_media" not in mapping:
                mapping["without_media"] = slide_path
    return mapping


def review_style_consistency(
    *,
    report_path: Path,
    out_dir: Path,
    slides_dir: Path,
    html_baseline: str = "light",
) -> dict[str, Any]:
    try:
        baseline = _resolve_html_baselines(report_path, out_dir, html_baseline)
    except RuntimeError as exc:
        manual_targets = [
            str(path)
            for path in (
                slides_dir / "00-intro.png",
                slides_dir / "01-item.png",
                slides_dir / "03-item.png",
            )
            if path.exists()
        ]
        return {
            "status": "warn",
            "html_baseline": html_baseline,
            "baseline_root": None,
            "baseline_screenshots": {},
            "actual_screenshots": {
                "intro": str(slides_dir / "00-intro.png"),
                "item": str(slides_dir / "01-item.png"),
            },
            "structure_checks": {},
            "token_checks": {},
            "manual_targets": manual_targets,
            "blocking_findings": [],
            "warnings": [f"HTML 基准模板缺失，已跳过自动样式对比：{exc}"],
        }
    baseline_dir = out_dir / "style-baselines"
    intro_baseline_png = _render_html_to_png(baseline["intro"], baseline_dir / "intro-baseline.png")
    item_baseline_png = _render_html_to_png(baseline["item"], baseline_dir / "item-baseline.png")

    scene_slides = _scene_slide_map(out_dir, slides_dir)
    item_slide_candidates = sorted(slides_dir.glob("[0-9][0-9]-item.png"))
    intro_slide = slides_dir / "00-intro.png"
    item_slide = slides_dir / "01-item.png"
    no_media_slide = scene_slides.get("without_media") or (item_slide_candidates[0] if item_slide_candidates else slides_dir / "06-item.png")
    media_slide = scene_slides.get("with_media") or (item_slide_candidates[min(1, max(0, len(item_slide_candidates) - 1))] if item_slide_candidates else slides_dir / "04-item.png")

    intro_comparisons = _compare_region_metrics(
        _region_metrics(intro_baseline_png, INTRO_REGIONS),
        _region_metrics(intro_slide, INTRO_REGIONS),
        color_tolerance=38.0,
        std_tolerance=36.0,
        edge_tolerance=22.0,
    )
    item_comparisons = _compare_region_metrics(
        _region_metrics(item_baseline_png, ITEM_REGIONS),
        _region_metrics(item_slide, ITEM_REGIONS),
        color_tolerance=42.0,
        std_tolerance=40.0,
        edge_tolerance=26.0,
    )

    occupancy_checks = {
        "no_media_quote_slot": _occupancy_check(no_media_slide, ITEM_REGIONS["right_quote"], min_edge=5.5)
        if no_media_slide.exists()
        else {"passed": False, "reason": "missing-slide"},
        "media_slot": _occupancy_check(media_slide, (0.53, 0.16, 0.93, 0.42), min_edge=7.0)
        if media_slide.exists()
        else {"passed": False, "reason": "missing-slide"},
    }

    palette_checks = {
        "intro": _sample_palette(intro_slide, scene_kind="intro"),
        "item": _sample_palette(item_slide, scene_kind="item"),
    }

    warnings: list[str] = []
    blocking_findings: list[str] = []
    intro_failures = [entry["region"] for entry in intro_comparisons if not entry["passed"]]
    item_failures = [
        entry["region"] for entry in item_comparisons if not entry["passed"] and entry["region"] not in {"bottom_bar"}
    ]
    if len(intro_failures) >= 2:
        blocking_findings.append(f"片头 still 与 HTML 基准差异过大：{', '.join(intro_failures)}。")
    elif intro_failures:
        warnings.append(f"片头 still 仍有轻微差异：{', '.join(intro_failures)}。")
    if len(item_failures) >= 2:
        blocking_findings.append(f"条目 still 与 HTML 基准差异过大：{', '.join(item_failures)}。")
    elif item_failures:
        warnings.append(f"条目 still 仍有轻微差异：{', '.join(item_failures)}。")
    if not occupancy_checks["no_media_quote_slot"]["passed"]:
        warnings.append("无媒体条目右侧 quote 区域留白仍然偏多。")
    if not occupancy_checks["media_slot"]["passed"]:
        warnings.append("强媒体条目主视觉占比仍然不够稳定。")
    if any(
        not sample["passed"]
        for group in palette_checks.values()
        for sample in group.values()
    ):
        warnings.append("背景或字幕条颜色与 Lumi light token 仍有偏差。")

    status = "fail" if blocking_findings else "pass"
    return {
        "status": status,
        "html_baseline": html_baseline,
        "baseline_root": str(baseline["root"]),
        "baseline_screenshots": {
            "intro": str(intro_baseline_png),
            "item": str(item_baseline_png),
        },
        "actual_screenshots": {
            "intro": str(intro_slide),
            "item": str(item_slide),
            "media": str(media_slide),
            "no_media": str(no_media_slide),
        },
        "structure_checks": {
            "intro": intro_comparisons,
            "item": item_comparisons,
            "occupancy": occupancy_checks,
        },
        "token_checks": palette_checks,
        "manual_targets": [
            str(intro_slide),
            str(item_slide),
            str(media_slide),
            str(no_media_slide),
            str(slides_dir / "03-item.png"),
        ],
        "blocking_findings": blocking_findings,
        "warnings": warnings,
    }


def review_alignment_consistency(summary_entries: list[dict[str, Any]], *, fps: int) -> dict[str, Any]:
    lead_limit_frames = max(1, int(round(fps * 0.12)))
    lag_limit_frames = max(1, int(round(fps * 0.18)))
    subtitle_char_limit = 30
    scene_reviews: list[dict[str, Any]] = []
    blocking_findings: list[str] = []
    warnings: list[str] = []

    for entry in summary_entries:
        if entry.get("kind") not in {"intro", "item", "outro"}:
            continue
        cues = entry.get("subtitle_cues") or []
        words = entry.get("words") or []
        title = str(entry.get("display_title") or entry.get("title") or entry.get("kind"))
        if not cues or not words:
            warnings.append(f"{title} 缺少字幕或词时间戳，无法做完整对齐检查。")
            continue
        first_lead = int(cues[0]["start_frame"]) - int(words[0]["absolute_start_frame"])
        last_lag = int(cues[-1]["end_frame"]) - int(words[-1]["absolute_end_frame"])
        max_chars = max((len(str(cue.get("text") or "")) for cue in cues), default=0)
        review = {
            "segment": entry.get("segment"),
            "title": title,
            "lead_ms": round(first_lead * 1000 / fps, 2),
            "lag_ms": round(last_lag * 1000 / fps, 2),
            "max_chars": max_chars,
            "passed": first_lead >= -lead_limit_frames and last_lag <= lag_limit_frames and max_chars <= subtitle_char_limit,
        }
        scene_reviews.append(review)
        if first_lead < -lead_limit_frames:
            blocking_findings.append(f"{title} 的首条字幕比发声早 {abs(review['lead_ms'])}ms。")
        if last_lag > lag_limit_frames:
            blocking_findings.append(f"{title} 的尾字幕比尾词晚 {review['lag_ms']}ms。")
        if max_chars > subtitle_char_limit:
            warnings.append(f"{title} 存在长度 {max_chars} 的长字幕，可能挤成两行以上。")

    status = "fail" if blocking_findings else "pass"
    return {
        "status": status,
        "fps": fps,
        "limits": {
            "lead_ms": round(lead_limit_frames * 1000 / fps, 2),
            "lag_ms": round(lag_limit_frames * 1000 / fps, 2),
            "max_chars": subtitle_char_limit,
        },
        "scenes": scene_reviews,
        "blocking_findings": blocking_findings,
        "warnings": warnings,
    }
