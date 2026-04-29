#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)")
SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze BGM head/tail silence and recommend trim points.")
    parser.add_argument("--bgm", required=True, help="Audio file path.")
    parser.add_argument("--out", required=True, help="Output JSON path.")
    parser.add_argument("--noise-db", type=float, default=-42.0, help="silencedetect noise threshold in dB.")
    parser.add_argument("--duration", type=float, default=0.20, help="silencedetect minimum silence duration.")
    parser.add_argument("--fade-in-sec", type=float, default=0.18, help="Suggested fade-in duration.")
    parser.add_argument("--fade-out-sec", type=float, default=0.45, help="Suggested fade-out duration.")
    return parser.parse_args()


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=True)


def probe_duration(path: Path) -> float:
    completed = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            str(path),
        ]
    )
    return float(completed.stdout.strip())


def detect_silence(path: Path, noise_db: float, duration: float) -> tuple[float, float]:
    completed = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            f"silencedetect=noise={noise_db}dB:d={duration:.2f}",
            "-f",
            "null",
            "-",
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    stderr = completed.stderr
    head_silence_end = 0.0
    tail_silence_start = 0.0
    current_starts: list[float] = []
    for line in stderr.splitlines():
        start_match = SILENCE_START_RE.search(line)
        if start_match:
            current_starts.append(float(start_match.group(1)))
            continue
        end_match = SILENCE_END_RE.search(line)
        if not end_match:
            continue
        silence_end = float(end_match.group(1))
        silence_duration = float(end_match.group(2))
        silence_start = current_starts[-1] if current_starts else max(0.0, silence_end - silence_duration)
        if silence_start <= 0.05:
            head_silence_end = max(head_silence_end, silence_end)
        tail_silence_start = max(tail_silence_start, silence_start)
    return head_silence_end, tail_silence_start


def main() -> int:
    args = parse_args()
    bgm_path = Path(args.bgm).expanduser().resolve()
    if not bgm_path.exists():
        raise SystemExit(f"BGM not found: {bgm_path}")

    duration_sec = probe_duration(bgm_path)
    head_silence_end, tail_silence_start = detect_silence(bgm_path, args.noise_db, args.duration)
    recommended_in_sec = round(head_silence_end, 3)
    recommended_out_sec = round(tail_silence_start if tail_silence_start > 0 else duration_sec, 3)
    payload = {
        "result": "success",
        "status": "pass",
        "bgm_path": str(bgm_path),
        "duration_sec": round(duration_sec, 3),
        "head_silence_sec": round(head_silence_end, 3),
        "tail_silence_sec": round(max(duration_sec - tail_silence_start, 0.0), 3) if tail_silence_start > 0 else 0.0,
        "recommended_in_sec": recommended_in_sec,
        "recommended_out_sec": recommended_out_sec,
        "fade_in_sec": round(args.fade_in_sec, 3),
        "fade_out_sec": round(args.fade_out_sec, 3),
        "reason": "trim_detected_head_tail_silence",
        "blocking_findings": [],
    }
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
