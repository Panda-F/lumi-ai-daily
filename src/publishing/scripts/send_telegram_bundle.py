#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

OPENCLAW_JSON = Path("/Users/dystopia/.openclaw/openclaw.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a tech-daily Telegram bundle via the Telegram Bot API.")
    parser.add_argument("--manifest", required=True, help="Path to telegram-send.json")
    parser.add_argument("--target", required=True, help="Telegram chat id or @username")
    parser.add_argument("--thread-id", help="Optional Telegram topic thread id")
    parser.add_argument("--steps", help="Optional comma-separated delivery steps override, for example cover_image,video")
    parser.add_argument("--token", help="Optional Telegram bot token override")
    parser.add_argument("--reply-chain", action="store_true", help="Reply each follow-up message to the previous bundle message")
    parser.add_argument("--silent", action="store_true", help="Send messages without notification sound")
    parser.add_argument("--timeout", type=int, default=90, help="Per-request timeout in seconds")
    parser.add_argument("--allow-missing", action="store_true", help="Skip missing requested files instead of failing.")
    parser.add_argument("--check-only", action="store_true", help="Validate the requested bundle steps without sending.")
    return parser.parse_args()


def load_openclaw_json() -> dict[str, Any]:
    if not OPENCLAW_JSON.exists():
        return {}
    try:
        return json.loads(OPENCLAW_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def load_token(explicit_token: str | None) -> str:
    if explicit_token:
        return explicit_token
    env_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if env_token:
        return env_token
    config_token = load_openclaw_json().get("channels", {}).get("telegram", {}).get("botToken")
    if config_token:
        return str(config_token)
    raise SystemExit("No Telegram bot token found. Set TELEGRAM_BOT_TOKEN or configure channels.telegram.botToken in ~/.openclaw/openclaw.json.")


def load_manifest(path: str) -> dict[str, Any]:
    manifest_path = Path(path).expanduser().resolve()
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if isinstance(manifest, dict):
        manifest["_manifest_path"] = str(manifest_path)
    return manifest


def _run_curl(cmd: list[str]) -> dict[str, Any]:
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"curl failed: {completed.stderr[-1000:]}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Telegram returned non-JSON output: {completed.stdout[-1000:]}") from exc
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API call failed: {payload}")
    return payload


def _media_command(
    *,
    token: str,
    method: str,
    target: str,
    field_name: str,
    file_path: Path,
    timeout: int,
    thread_id: str | None,
    reply_to: int | None,
    silent: bool,
) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    cmd = [
        "curl",
        "-sS",
        "--max-time",
        str(timeout),
        "-X",
        "POST",
        url,
        "-F",
        f"chat_id={target}",
        "-F",
        f"{field_name}=@{file_path}",
    ]
    if silent:
        cmd += ["-F", "disable_notification=true"]
    if thread_id:
        cmd += ["-F", f"message_thread_id={thread_id}"]
    if reply_to:
        cmd += ["-F", f"reply_to_message_id={reply_to}"]
    if method == "sendVideo":
        cmd += ["-F", "supports_streaming=true"]
    if method == "sendDocument":
        cmd += ["-F", "disable_content_type_detection=true"]
    return _run_curl(cmd)


def _send_text(
    *,
    token: str,
    target: str,
    text: str,
    timeout: int,
    thread_id: str | None,
    reply_to: int | None,
    silent: bool,
) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    cmd = [
        "curl",
        "-sS",
        "--max-time",
        str(timeout),
        "-X",
        "POST",
        url,
        "--data-urlencode",
        f"chat_id={target}",
        "--data-urlencode",
        f"text={text}",
    ]
    if silent:
        cmd += ["--data-urlencode", "disable_notification=true"]
    if thread_id:
        cmd += ["--data-urlencode", f"message_thread_id={thread_id}"]
    if reply_to:
        cmd += ["--data-urlencode", f"reply_to_message_id={reply_to}"]
    return _run_curl(cmd)


def _existing_file(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path).expanduser().resolve()
    return path if path.exists() else None


def _daily_root_from_manifest(manifest: dict[str, Any]) -> Path | None:
    manifest_path = manifest.get("_manifest_path")
    if manifest_path:
        path = Path(str(manifest_path)).expanduser().resolve()
        if path.parent.name == "publish":
            return path.parent.parent
    for key in ("cover_image_file", "video_file", "text_file"):
        raw_path = manifest.get(key)
        if not raw_path:
            continue
        path = Path(str(raw_path)).expanduser()
        parts = path.parts
        if "AI-Daily-Reports" in parts:
            idx = parts.index("AI-Daily-Reports")
            if idx + 1 < len(parts):
                return Path(*parts[: idx + 2])
    return None


def _fallback_file_for_step(manifest: dict[str, Any], step: str) -> Path | None:
    root = _daily_root_from_manifest(manifest)
    if not root:
        return None
    candidates: list[Path]
    if step == "cover_image":
        candidates = [
            root / "cover-lab" / "final-cover.png",
            root / "publish" / "cover.png",
            root / "publish" / "video-screenshots" / "cover.png",
        ]
    elif step == "video":
        candidates = [
            root / "final" / "video.mp4",
            root / "build" / "video" / "video.mp4",
        ]
        candidates.extend(sorted((root / "final").glob("*.mp4")) if (root / "final").exists() else [])
    elif step == "text":
        candidates = [root / "publish" / "telegram.txt"]
    else:
        return None
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.exists() and resolved.is_file():
            return resolved
    return None


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _validate_video_quality_before_send(manifest: dict[str, Any], video_path: Path) -> None:
    root = _daily_root_from_manifest(manifest)
    if not root:
        return
    summary_path = root / "build" / "video" / "build-summary.json"
    summary = _load_json(summary_path)
    if not summary:
        raise SystemExit(f"Video build summary missing or invalid before Telegram send: {summary_path}")
    findings: list[str] = []
    if summary.get("result") != "success":
        findings.append("video_build_not_success")
    if summary.get("fallback_render"):
        findings.append("video_fallback_render_used")
    note = " ".join(str(summary.get(key) or "") for key in ("fallback_note", "audio_note")).lower()
    if "silent" in note or "placeholder" in note:
        findings.append("video_silent_placeholder")
    tts = summary.get("tts") if isinstance(summary.get("tts"), dict) else {}
    effective_provider = str(tts.get("effective_provider") or summary.get("voice_engine") or "").strip()
    if effective_provider != "fish-speech":
        findings.append(f"tts_provider_not_fish:{effective_provider or 'missing'}")
    if int(tts.get("remote_fallback_segments") or 0) > 0:
        findings.append("tts_remote_fallback_segments_present")
    if bool(tts.get("remote_preflight_checked")) and not bool(tts.get("remote_preflight_ok")):
        findings.append("tts_remote_preflight_failed")
    if findings:
        raise SystemExit(
            "Refusing to send invalid video via Telegram: "
            + ", ".join(sorted(set(findings)))
            + f" | video={video_path} | summary={summary_path}"
        )


def _validate_daily_pipeline_before_send(manifest: dict[str, Any]) -> None:
    root = _daily_root_from_manifest(manifest)
    if not root or root.parent.name != "AI-Daily-Reports":
        return
    summary_path = root / "qa" / "pipeline-summary.json"
    summary = _load_json(summary_path)
    if not summary:
        raise SystemExit(f"Pipeline summary missing or invalid before Telegram send: {summary_path}")
    findings: list[str] = []
    if summary.get("result") != "success":
        findings.append(f"pipeline_not_success:{summary.get('result') or 'missing'}")
    video_quality = summary.get("video_build_quality") if isinstance(summary.get("video_build_quality"), dict) else {}
    if video_quality and video_quality.get("status") != "pass":
        findings.append("video_build_quality_not_pass")
    screenshot_payload = summary.get("video_screenshot_payload") if isinstance(summary.get("video_screenshot_payload"), dict) else {}
    if screenshot_payload and screenshot_payload.get("status") != "pass":
        findings.append("video_screenshot_package_not_pass")
    if findings:
        raise SystemExit(
            "Refusing to send AI Daily because the production pipeline did not pass: "
            + ", ".join(sorted(set(findings)))
            + f" | summary={summary_path}"
        )


def validate_delivery_manifest(
    manifest: dict[str, Any],
    delivery_order: list[str],
    *,
    allow_missing: bool,
) -> tuple[dict[str, Path], list[dict[str, str]]]:
    _validate_daily_pipeline_before_send(manifest)
    step_file_keys = {
        "cover_image": "cover_image_file",
        "video": "video_file",
        "text": "text_file",
    }
    resolved: dict[str, Path] = {}
    skipped: list[dict[str, str]] = []
    for step in delivery_order:
        key = step_file_keys.get(step)
        if not key:
            if allow_missing:
                skipped.append({"step": step, "reason": "unknown_step"})
                continue
            raise SystemExit(f"Unknown Telegram delivery step requested: {step}")
        path = _existing_file(manifest.get(key)) or _fallback_file_for_step(manifest, step)
        if not path:
            if allow_missing:
                skipped.append({"step": step, "reason": f"missing_{key}"})
                continue
            raise SystemExit(f"Manifest step {step} missing required file: {key}")
        resolved[step] = path
        if step == "video":
            _validate_video_quality_before_send(manifest, path)
    return resolved, skipped


def main() -> int:
    args = parse_args()
    manifest = load_manifest(args.manifest)

    reply_to: int | None = None
    deliveries: list[dict[str, Any]] = []

    delivery_order = manifest.get("delivery_order", [])
    if args.steps:
        delivery_order = [step.strip() for step in args.steps.split(",") if step.strip()]
    if not isinstance(delivery_order, list):
        raise SystemExit("Manifest delivery_order must be a list.")
    resolved_files, skipped = validate_delivery_manifest(
        manifest,
        delivery_order,
        allow_missing=args.allow_missing,
    )

    if args.check_only:
        print(
            json.dumps(
                {
                    "result": "success",
                    "manifest": str(Path(args.manifest).expanduser().resolve()),
                    "delivery_order": delivery_order,
                    "resolved_files": {step: str(path) for step, path in resolved_files.items()},
                    "skipped": skipped,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    token = load_token(args.token)

    for step in delivery_order:
        if step == "cover_image":
            cover_path = resolved_files.get(step)
            if not cover_path:
                continue
            payload = _media_command(
                token=token,
                method=manifest.get("cover_method") or "sendPhoto",
                target=args.target,
                field_name="photo",
                file_path=cover_path,
                timeout=args.timeout,
                thread_id=args.thread_id,
                reply_to=reply_to,
                silent=args.silent,
            )
        elif step == "video":
            video_path = resolved_files.get(step)
            if not video_path:
                continue
            video_method = manifest.get("video_method") or "sendVideo"
            video_field = "video" if video_method == "sendVideo" else "document"
            payload = _media_command(
                token=token,
                method=video_method,
                target=args.target,
                field_name=video_field,
                file_path=video_path,
                timeout=args.timeout,
                thread_id=args.thread_id,
                reply_to=reply_to,
                silent=args.silent,
            )
        elif step == "text":
            text_path = resolved_files.get(step)
            if not text_path:
                continue
            payload = _send_text(
                token=token,
                target=args.target,
                text=text_path.read_text(encoding="utf-8").strip(),
                timeout=args.timeout,
                thread_id=args.thread_id,
                reply_to=reply_to,
                silent=args.silent,
            )
        else:
            if args.allow_missing:
                continue
            raise SystemExit(f"Unknown Telegram delivery step requested: {step}")

        message = payload.get("result", {})
        deliveries.append(
            {
                "step": step,
                "message_id": message.get("message_id"),
                "date": message.get("date"),
            }
        )
        if args.reply_chain and message.get("message_id"):
            reply_to = int(message["message_id"])

    print(
        json.dumps(
            {
                "result": "success",
                "target": args.target,
                "manifest": str(Path(args.manifest).expanduser().resolve()),
                "delivery_order": delivery_order,
                "deliveries": deliveries,
                "skipped": skipped,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
