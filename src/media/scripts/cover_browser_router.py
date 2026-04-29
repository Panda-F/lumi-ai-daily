#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from gemini_cover_browser import DOWNLOADS_ROOT, write_json


SCRIPT_DIR = Path(__file__).resolve().parent
CHATGPT_SCRIPT = SCRIPT_DIR / "chatgpt_cover_browser.py"
GEMINI_SCRIPT = SCRIPT_DIR / "gemini_cover_browser.py"


def derive_output_path(date_value: str) -> Path:
    return DOWNLOADS_ROOT / f"cover-router-{date_value}.png"


def derive_result_path(output_path: Path) -> Path:
    return output_path.with_suffix(".result.json")


def derive_diag_dir(output_path: Path) -> Path:
    return output_path.parent / f"{output_path.stem}.diagnostics"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def run_helper(script: Path, args: list[str]) -> tuple[int, dict[str, Any]]:
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
    )
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        for token in reversed((proc.stdout or "").splitlines()):
            token = token.strip()
            if not token:
                continue
            try:
                payload = json.loads(token)
                break
            except json.JSONDecodeError:
                continue
    return proc.returncode, payload


def helper_args(
    *,
    args,
    output_path: Path,
    result_json: Path,
    diag_dir: Path,
    max_attempts: int,
    no_fallback: bool,
) -> list[str]:
    payload = [
        "--profile",
        args.profile,
        "--cdp-endpoint",
        args.cdp_endpoint,
        "--date",
        args.date,
        "--collage",
        str(args.collage),
        "--prompt-file",
        str(args.prompt_file),
        "--output",
        str(output_path),
        "--result-json",
        str(result_json),
        "--diag-dir",
        str(diag_dir),
        "--max-attempts",
        str(max_attempts),
    ]
    if args.user_data_dir:
        payload.extend(["--user-data-dir", str(args.user_data_dir)])
    if args.chrome_path:
        payload.extend(["--chrome-path", args.chrome_path])
    if args.manifest:
        payload.extend(["--manifest", str(args.manifest)])
    for asset in args.asset:
        payload.extend(["--asset", str(asset)])
    if no_fallback:
        payload.append("--no-fallback")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Route cover generation through Gemini first, then ChatGPT fallback.")
    parser.add_argument("--profile", default="openclaw")
    parser.add_argument("--user-data-dir", type=Path, help="Optional Chrome user-data directory override")
    parser.add_argument("--chrome-path", help="Optional Chrome executable path override")
    parser.add_argument("--cdp-endpoint", default="http://127.0.0.1:18800")
    parser.add_argument("--date", required=True, help="Date folder used for staging, e.g. 2026-04-07")
    parser.add_argument("--collage", required=True, type=Path, help="Local collage image path")
    parser.add_argument("--asset", action="append", default=[], type=Path, help="Additional reference asset path")
    parser.add_argument("--manifest", type=Path, help="Optional manifest.json; strongest assets are used when --asset is omitted")
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Download path inside /tmp/openclaw/downloads")
    parser.add_argument("--result-json", type=Path, help="Optional structured result JSON output path")
    parser.add_argument("--diag-dir", type=Path, help="Optional diagnostics directory override")
    parser.add_argument("--chatgpt-max-attempts", type=int, default=2)
    parser.add_argument("--gemini-max-attempts", type=int, default=2)
    parser.add_argument("--no-fallback", action="store_true", help="Disable the final collage fallback inside Gemini")
    args = parser.parse_args()

    output_path = args.output or derive_output_path(args.date)
    if not str(output_path).startswith(str(DOWNLOADS_ROOT)):
        raise SystemExit(f"--output must stay within {DOWNLOADS_ROOT}")

    result_json = args.result_json or derive_result_path(output_path)
    diag_dir = args.diag_dir or derive_diag_dir(output_path)
    diag_dir.mkdir(parents=True, exist_ok=True)

    chatgpt_result_path = diag_dir / "chatgpt.result.json"
    gemini_result_path = diag_dir / "gemini.result.json"
    chatgpt_diag_dir = diag_dir / "chatgpt"
    gemini_diag_dir = diag_dir / "gemini"

    # --- Gemini first ---
    gemini_code, gemini_payload = run_helper(
        GEMINI_SCRIPT,
        helper_args(
            args=args,
            output_path=output_path,
            result_json=gemini_result_path,
            diag_dir=gemini_diag_dir,
            max_attempts=args.gemini_max_attempts,
            no_fallback=args.no_fallback,
        ),
    )

    final_payload: dict[str, Any] = {
        "ok": False,
        "provider": "gemini",
        "final_stage": "gemini_failed",
        "downloaded": None,
        "image": None,
        "artifacts": {
            "result_json": str(result_json),
            "chatgpt_result_json": str(chatgpt_result_path),
            "chatgpt_diagnostics_dir": str(chatgpt_diag_dir),
            "gemini_result_json": str(gemini_result_path),
            "gemini_diagnostics_dir": str(gemini_diag_dir),
        },
        "prompt_file": str(args.prompt_file),
        "manifest": str(args.manifest) if args.manifest else None,
        "providers_tried": ["gemini"],
        "gemini": gemini_payload or load_json(gemini_result_path),
    }

    chosen = final_payload["gemini"] if isinstance(final_payload["gemini"], dict) else {}
    if chosen.get("ok") and chosen.get("downloaded"):
        final_payload.update(
            {
                "ok": True,
                "provider": str(chosen.get("provider") or "gemini"),
                "final_stage": str(chosen.get("final_stage") or "downloaded"),
                "downloaded": chosen.get("downloaded"),
                "image": chosen.get("image") or chosen.get("downloaded"),
            }
        )
        write_json(result_json, final_payload)
        print(json.dumps(final_payload, ensure_ascii=False, indent=2))
        return 0

    # --- ChatGPT fallback ---
    chatgpt_code, chatgpt_payload = run_helper(
        CHATGPT_SCRIPT,
        helper_args(
            args=args,
            output_path=output_path,
            result_json=chatgpt_result_path,
            diag_dir=chatgpt_diag_dir,
            max_attempts=args.chatgpt_max_attempts,
            no_fallback=True,
        ),
    )
    final_payload["providers_tried"] = ["gemini", "chatgpt"]
    final_payload["chatgpt"] = chatgpt_payload or load_json(chatgpt_result_path)

    chosen = final_payload["chatgpt"] if isinstance(final_payload["chatgpt"], dict) else {}
    if chosen.get("ok") and chosen.get("downloaded"):
        final_payload.update(
            {
                "ok": True,
                "provider": "chatgpt",
                "final_stage": str(chosen.get("final_stage") or "downloaded"),
                "downloaded": chosen.get("downloaded"),
                "image": chosen.get("image") or chosen.get("downloaded"),
            }
        )
        write_json(result_json, final_payload)
        print(json.dumps(final_payload, ensure_ascii=False, indent=2))
        return 0

    final_payload.update(
        {
            "provider": "gemini_then_chatgpt",
            "final_stage": str(chosen.get("final_stage") or "failed"),
            "downloaded": None,
            "image": None,
            "gemini_exit_code": gemini_code,
            "chatgpt_exit_code": chatgpt_code,
        }
    )
    write_json(result_json, final_payload)
    print(json.dumps(final_payload, ensure_ascii=False, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
