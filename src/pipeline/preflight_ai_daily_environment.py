#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_ROOT = Path("/Users/dystopia/Desktop/AI-Daily-Reports")
DEFAULT_WORKSPACE = Path("/Users/dystopia/.openclaw/workspace")
DEFAULT_FISH_ENDPOINT = "http://192.168.1.13:8888/v1/tts"
DEFAULT_FISH_REFERENCE_ID = "female_student"
DEFAULT_FISH_FORMAT = "wav"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preflight the AI daily automation environment.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--out", help="Optional JSON output path")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="AI daily output root")
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE), help="OpenClaw workspace root")
    parser.add_argument("--require-fish", action="store_true", help="Block when Fish socket or audio probe fails")
    parser.add_argument("--require-network", action="store_true", help="Block when DNS/network check fails")
    parser.add_argument("--require-remotion-public", action="store_true", help="Block when Remotion public dir is not writable")
    parser.add_argument("--require-video-tools", action="store_true", help="Block when node/npm Remotion tools are missing")
    parser.add_argument("--fish-endpoint", default=DEFAULT_FISH_ENDPOINT)
    parser.add_argument("--fish-reference-id", default=DEFAULT_FISH_REFERENCE_ID)
    parser.add_argument("--fish-format", default=DEFAULT_FISH_FORMAT)
    parser.add_argument("--remotion-public-dir", help="Writable public dir for this day's Remotion assets")
    parser.add_argument("--rsshub-host", default="127.0.0.1")
    parser.add_argument("--rsshub-port", type=int, default=1200)
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_writable_dir(path: Path) -> dict[str, Any]:
    started = time.monotonic()
    result: dict[str, Any] = {"path": str(path), "status": "fail"}
    try:
        ensure_dir(path)
        fd, temp_name = tempfile.mkstemp(prefix=".ai-daily-preflight-", dir=str(path))
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("ok\n")
        Path(temp_name).unlink(missing_ok=True)
        result["status"] = "pass"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    result["duration_sec"] = round(time.monotonic() - started, 3)
    return result


def check_socket(host: str, port: int, *, timeout: float = 3.0) -> dict[str, Any]:
    started = time.monotonic()
    result: dict[str, Any] = {"host": host, "port": port, "status": "fail"}
    try:
        with socket.create_connection((host, port), timeout=timeout):
            result["status"] = "pass"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    result["duration_sec"] = round(time.monotonic() - started, 3)
    return result


def check_dns(host: str = "openai.com") -> dict[str, Any]:
    started = time.monotonic()
    result: dict[str, Any] = {"host": host, "status": "fail"}
    try:
        addresses = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        result["status"] = "pass"
        result["address_count"] = len(addresses)
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    result["duration_sec"] = round(time.monotonic() - started, 3)
    return result


def ffprobe_duration(path: Path) -> dict[str, Any]:
    started = time.monotonic()
    result: dict[str, Any] = {"path": str(path), "status": "fail"}
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    result["returncode"] = completed.returncode
    result["stdout"] = (completed.stdout or "").strip()[:200]
    result["stderr"] = (completed.stderr or "").strip()[:500]
    if completed.returncode == 0:
        try:
            duration = float(result["stdout"])
            if duration > 0:
                result["duration"] = duration
                result["status"] = "pass"
        except (TypeError, ValueError):
            result["error"] = f"ffprobe_duration_not_numeric:{result['stdout']!r}"
    result["duration_sec"] = round(time.monotonic() - started, 3)
    return result


def fish_probe(endpoint: str, reference_id: str, response_format: str) -> dict[str, Any]:
    parsed = urlparse(endpoint)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    result: dict[str, Any] = {
        "endpoint": endpoint,
        "reference_id": reference_id,
        "socket": check_socket(host, int(port)) if host else {"status": "fail", "error": "missing_host"},
        "status": "fail",
    }
    if result["socket"].get("status") != "pass":
        result["error"] = "fish_socket_failed"
        return result

    response_format = (response_format or DEFAULT_FISH_FORMAT).strip().lower()
    probe_path = Path(tempfile.gettempdir()) / f"ai-daily-fish-probe-{int(time.time())}.{response_format}"
    payload = {
        "text": "日报预飞检查，确认今天的真实配音链路可用。",
        "reference_id": reference_id,
        "format": response_format,
        "use_memory_cache": "off",
    }
    started = time.monotonic()
    completed = subprocess.run(
        [
            "curl",
            "-sS",
            "--fail-with-body",
            "--max-time",
            "45",
            "-X",
            "POST",
            endpoint,
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps(payload, ensure_ascii=False),
            "-o",
            str(probe_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    result["http"] = {
        "returncode": completed.returncode,
        "stderr": (completed.stderr or "").strip()[:800],
        "duration_sec": round(time.monotonic() - started, 3),
        "output": str(probe_path),
        "bytes": probe_path.stat().st_size if probe_path.exists() else 0,
    }
    if completed.returncode != 0 or not probe_path.exists() or probe_path.stat().st_size <= 0:
        result["error"] = "fish_http_probe_failed"
        return result
    duration = ffprobe_duration(probe_path)
    result["audio"] = duration
    if duration.get("status") == "pass":
        result["status"] = "pass"
    else:
        result["error"] = "fish_audio_probe_failed"
    probe_path.unlink(missing_ok=True)
    return result


def main() -> int:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    workspace = Path(args.workspace).expanduser().resolve()
    day_dir = root / args.date
    qa_dir = day_dir / "qa"
    remotion_public_dir = (
        Path(args.remotion_public_dir).expanduser().resolve()
        if args.remotion_public_dir
        else day_dir / "build" / "video" / "remotion-public"
    )
    swift_cache_dir = day_dir / "build" / "swift-module-cache"
    sessions_dir = Path("/Users/dystopia/.openclaw/agents/main/sessions")

    checks: dict[str, Any] = {
        "desktop_root_writable": check_writable_dir(root),
        "day_qa_writable": check_writable_dir(qa_dir),
        "workspace_exists": {"path": str(workspace), "status": "pass" if workspace.exists() else "fail"},
        "openclaw_sessions_writable": check_writable_dir(sessions_dir) if sessions_dir.exists() else {"status": "warn", "path": str(sessions_dir), "error": "missing_sessions_dir"},
        "dns": check_dns(),
        "rsshub_socket": check_socket(args.rsshub_host, args.rsshub_port),
        "remotion_public_writable": check_writable_dir(remotion_public_dir),
        "swift_module_cache_writable": check_writable_dir(swift_cache_dir),
        "imagegen_skill": {
            "path": "/Users/dystopia/.codex/skills/.system/imagegen/SKILL.md",
            "status": "pass" if Path("/Users/dystopia/.codex/skills/.system/imagegen/SKILL.md").exists() else "warn",
            "openai_api_key_present": bool(os.environ.get("OPENAI_API_KEY")),
        },
        "required_bins": {
            name: {"status": "pass" if shutil.which(name) else "fail", "path": shutil.which(name)}
            for name in ("python3", "ffprobe", "curl", "node", "npm")
        },
    }
    checks["fish_probe"] = fish_probe(args.fish_endpoint, args.fish_reference_id, args.fish_format)

    blocking: list[str] = []
    warnings: list[str] = []
    if checks["desktop_root_writable"].get("status") != "pass" or checks["day_qa_writable"].get("status") != "pass":
        blocking.append("desktop_report_root_not_writable")
    if checks["workspace_exists"].get("status") != "pass":
        blocking.append("openclaw_workspace_missing")
    if args.require_network and checks["dns"].get("status") != "pass":
        blocking.append("dns_probe_failed")
    elif checks["dns"].get("status") != "pass":
        warnings.append("dns_probe_failed")
    if checks["rsshub_socket"].get("status") != "pass":
        warnings.append("rsshub_socket_unavailable")
    if args.require_remotion_public and checks["remotion_public_writable"].get("status") != "pass":
        blocking.append("remotion_public_dir_not_writable")
    if checks["swift_module_cache_writable"].get("status") != "pass":
        warnings.append("swift_module_cache_not_writable")
    for name, value in checks["required_bins"].items():
        if value.get("status") != "pass" and name in {"python3", "curl", "ffprobe"}:
            blocking.append(f"missing_required_binary:{name}")
        elif value.get("status") != "pass" and args.require_video_tools:
            blocking.append(f"missing_required_binary:{name}")
        elif value.get("status") != "pass":
            warnings.append(f"missing_optional_binary:{name}")
    if args.require_fish and checks["fish_probe"].get("status") != "pass":
        blocking.append("fish_audio_probe_failed")
    elif checks["fish_probe"].get("status") != "pass":
        warnings.append("fish_audio_probe_failed")

    payload: dict[str, Any] = {
        "result": "failed" if blocking else "success",
        "status": "fail" if blocking else "pass",
        "date": args.date,
        "generated_at": utc_now_iso(),
        "root": str(root),
        "workspace": str(workspace),
        "remotion_public_dir": str(remotion_public_dir),
        "blocking_findings": sorted(set(blocking)),
        "warnings": sorted(set(warnings)),
        "checks": checks,
    }
    if args.out:
        write_json(Path(args.out).expanduser().resolve(), payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
