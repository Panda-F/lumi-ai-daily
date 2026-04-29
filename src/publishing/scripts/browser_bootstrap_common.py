#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parents[3]
DEFAULT_PROFILE = "openclaw"

PLATFORM_CONFIG = {
    "bilibili": {
        "label": "Bilibili",
        "url": "https://member.bilibili.com/platform/upload/video/frame",
        "ready_markers": [
            "上传视频",
            "稿件投递",
            "上传封面",
            "投稿",
            "创作中心",
        ],
        "login_markers": [
            "扫码登录",
            "请输入账号",
            "密码登录",
            "登录",
        ],
        "risk_markers": [
            "风控",
            "验证",
            "安全中心",
        ],
    },
}


def run(cmd: list[str]) -> str:
    completed = subprocess.run(cmd, check=True, text=True, capture_output=True)
    return completed.stdout


def browser_cmd(profile: str, *args: str) -> list[str]:
    return ["openclaw", "browser", "--browser-profile", profile, *args]


def infer_state(platform: str, snapshot: str) -> dict[str, str]:
    config = PLATFORM_CONFIG[platform]
    for marker in config["risk_markers"]:
        if marker in snapshot:
            return {
                "state": "risk_check",
                "next_step": f"Complete the visible {config['label']} risk check in the browser, then rerun the pipeline.",
            }
    for marker in config["ready_markers"]:
        if marker in snapshot:
            return {
                "state": "ready_for_compose",
                "next_step": f"The {config['label']} compose surface looks available.",
            }
    for marker in config["login_markers"]:
        if marker in snapshot:
            return {
                "state": "login_required",
                "next_step": f"Please log into {config['label']} in the OpenClaw browser tab, then rerun the pipeline.",
            }
    return {
        "state": "unknown",
        "next_step": f"Inspect the current {config['label']} tab manually; the page did not match the known login/compose heuristics yet.",
    }


def bootstrap_platform(platform: str, profile: str = DEFAULT_PROFILE, url: str | None = None) -> dict[str, object]:
    if platform not in PLATFORM_CONFIG:
        raise KeyError(f"Unknown platform: {platform}")

    final_url = url or PLATFORM_CONFIG[platform]["url"]
    run(browser_cmd(profile, "start"))
    opened = run(browser_cmd(profile, "open", final_url))
    snapshot = run(browser_cmd(profile, "snapshot", "--limit", "180"))
    state = infer_state(platform, snapshot)
    return {
        "result": "success",
        "platform": platform,
        "profile": profile,
        "url": final_url,
        "open_output": opened.strip(),
        "state": state["state"],
        "next_step": state["next_step"],
    }


def print_bootstrap_result(result: dict[str, object]) -> int:
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
