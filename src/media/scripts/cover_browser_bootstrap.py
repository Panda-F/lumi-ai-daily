#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

PROFILE = "openclaw"
PROFILE_DIR = Path("/Users/dystopia/.openclaw/browser/openclaw/user-data")
TARGETS = [
    {
        "name": "chatgpt_images",
        "label": "ChatGPT Images",
        "url": "https://chatgpt.com/images",
        "login_markers": ["登录", "Log in", "注册", "Sign up"],
        "ready_markers": ["创建图片", "Create images", "上传文件", "图片"],
    },
    {
        "name": "gemini",
        "label": "Gemini",
        "url": "https://gemini.google.com/app",
        "login_markers": ["登录", "Sign in", "Choose an account", "Use your Google Account"],
        "ready_markers": ["Gemini", "制作图片", "Create images", "上传文件"],
    },
]


def run(cmd: list[str]) -> str:
    completed = subprocess.run(cmd, check=True, text=True, capture_output=True)
    return completed.stdout.strip()


def browser_cmd(*args: str) -> list[str]:
    return ["openclaw", "browser", "--browser-profile", PROFILE, *args]


def tabs_json() -> list[dict]:
    output = run(browser_cmd("--json", "tabs"))
    payload = json.loads(output)
    if isinstance(payload, dict):
        for key in ("tabs", "targets", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    if isinstance(payload, list):
        return payload
    return []


def focus_tab(target_id: str) -> None:
    run(browser_cmd("focus", target_id))


def snapshot_text(limit: int = 220) -> str:
    return run(browser_cmd("snapshot", "--limit", str(limit)))


def infer_state(snapshot: str, ready_markers: list[str], login_markers: list[str]) -> str:
    for marker in login_markers:
        if marker in snapshot:
            return "login_required"
    for marker in ready_markers:
        if marker in snapshot:
            return "ready"
    return "unknown"


def find_target_tab(url: str, tabs: list[dict]) -> dict | None:
    normalized = url.rstrip("/")
    for tab in tabs:
        tab_url = str(tab.get("url") or "").rstrip("/")
        if tab_url == normalized:
            return tab
    return None


def open_and_probe(target: dict) -> dict:
    open_output = run(browser_cmd("open", target["url"]))
    tabs = tabs_json()
    tab = find_target_tab(target["url"], tabs)
    if tab and tab.get("id"):
        focus_tab(str(tab["id"]))
    snapshot = snapshot_text()
    state = infer_state(snapshot, target["ready_markers"], target["login_markers"])
    return {
        "name": target["name"],
        "label": target["label"],
        "url": target["url"],
        "open_output": open_output,
        "tab_id": tab.get("id") if isinstance(tab, dict) else None,
        "state": state,
        "profile_dir": str(PROFILE_DIR),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Open ChatGPT Images and Gemini in the reusable OpenClaw browser profile.")
    parser.add_argument("--json", action="store_true", help="Return machine-readable output")
    args = parser.parse_args()

    run(browser_cmd("start"))
    results = [open_and_probe(target) for target in TARGETS]
    payload = {
        "result": "success",
        "profile": PROFILE,
        "profile_dir": str(PROFILE_DIR),
        "targets": results,
        "next_step": "Log into any target whose state is login_required. Future daily runs will reuse this OpenClaw profile directory.",
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
