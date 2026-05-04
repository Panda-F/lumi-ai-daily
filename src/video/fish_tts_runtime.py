#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = next(parent for parent in (_THIS_FILE.parent, *_THIS_FILE.parents) if parent.name == "src")
for _IMPORT_DIR in (
    _SRC_DIR / "common",
    _SRC_DIR / "content",
    _SRC_DIR / "discovery",
    _SRC_DIR / "visuals",
    _SRC_DIR / "video",
):
    if str(_IMPORT_DIR) not in sys.path:
        sys.path.insert(0, str(_IMPORT_DIR))

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any


DEFAULT_ENDPOINT = os.environ.get("AI_DAILY_FISH_TTS_ENDPOINT", "http://192.168.1.13:8888/v1/tts")
DEFAULT_REFERENCE_ID = "female_student"
DEFAULT_FORMAT = "wav"
DEFAULT_TIMEOUT = 45
DEFAULT_SOUL_TIMEOUT = 90
DEFAULT_TAG_TIMEOUT = 90

TAG_PATTERN = re.compile(r"\[([A-Za-z][^\[\]\n]{0,80}?)\]")
CHINESE_BRACKET_PATTERN = re.compile(r"【[^】]+】")


def fish_tts_curl_proxy_args() -> list[str]:
    proxy = os.environ.get("AI_DAILY_FISH_TTS_CURL_PROXY", "").strip()
    return ["--proxy", proxy] if proxy else []


OFFICIAL_FISH_TAGS = [
    "[pause]",
    "[short pause]",
    "[inhale]",
    "[exhale]",
    "[panting]",
    "[clearing throat]",
    "[emphasis]",
    "[interrupting]",
    "[laughing]",
    "[laughing tone]",
    "[chuckle]",
    "[chuckling]",
    "[audience laughter]",
    "[volume up]",
    "[volume down]",
    "[loud]",
    "[low volume]",
    "[whisper]",
    "[low voice]",
    "[screaming]",
    "[shouting]",
    "[excited]",
    "[excited tone]",
    "[delight]",
    "[surprised]",
    "[shocked]",
    "[angry]",
    "[sad]",
    "[sigh]",
    "[moaning]",
    "[singing]",
    "[echo]",
    "[tsk]",
    "[with strong accent]",
]

REFERENCE_LIBRARY: dict[str, dict[str, str]] = {
    "ad_sister": {"label": "中文女声·女仆", "role": "maid"},
    "qianzao_aiyin": {"label": "日语女声·偶像", "role": "idol"},
    "calm_male": {"label": "中文男声·平稳", "role": "steady_male"},
    "gentle_female": {"label": "中文女声·温柔", "role": "gentle_female"},
    "female_student": {"label": "中文女声·女大学生", "role": "female_student"},
    "dingzhen": {"label": "中文男声·丁真", "role": "dingzhen"},
}

STYLE_PRESET_HINTS: dict[str, str] = {
    "none": "",
    "bright": "upbeat, lively, smiling, energetic",
    "playful": "playful, teasing, lively",
    "gentle": "soft, warm, gentle, close",
    "secret": "private, whispery, secretive",
    "serious": "steady, focused, restrained",
    "comfort": "comforting, soft, reassuring",
    "surprised": "surprised, animated, expressive",
    "news": "professional broadcast tone, clear and paced",
}

ROLE_KEYWORDS: list[tuple[str, str]] = [
    ("qianzao_aiyin", "千花书记"),
    ("qianzao_aiyin", "chika"),
    ("qianzao_aiyin", "偶像"),
    ("qianzao_aiyin", "idol"),
    ("qianzao_aiyin", "日语角色"),
    ("qianzao_aiyin", "日语女声"),
    ("qianzao_aiyin", "日语"),
    ("qianzao_aiyin", "anime"),
    ("ad_sister", "女仆"),
    ("ad_sister", "maid"),
    ("gentle_female", "温柔"),
    ("gentle_female", "gentle"),
    ("gentle_female", "安慰"),
    ("gentle_female", "晚安"),
    ("gentle_female", "soft"),
    ("calm_male", "男声"),
    ("calm_male", "male"),
    ("calm_male", "沉稳"),
    ("calm_male", "平稳"),
    ("calm_male", "播报男声"),
    ("dingzhen", "丁真"),
    ("dingzhen", "dingzhen"),
    ("female_student", "女大学生"),
    ("female_student", "学生"),
    ("female_student", "student"),
    ("female_student", "学妹"),
    ("female_student", "中文女声"),
]


class FishTtsError(RuntimeError):
    pass


def ensure_dir(path: pathlib.Path) -> pathlib.Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(text: str, fallback: str = "voice-note") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", text.strip().lower()).strip("-")
    return cleaned[:60] or fallback


def extract_tags(text: str) -> list[str]:
    return [f"[{match.group(1).strip()}]" for match in TAG_PATTERN.finditer(text or "")]


def dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def strip_tags(text: str) -> str:
    return TAG_PATTERN.sub("", text or "").strip()


def validate_tag(tag: str) -> bool:
    if not tag.startswith("[") or not tag.endswith("]"):
        return False
    body = tag[1:-1].strip()
    if not body or body.startswith("/"):
        return False
    if "[" in body or "]" in body:
        return False
    return bool(re.search(r"[A-Za-z]", body))


def reference_label(reference_id: str) -> str:
    return REFERENCE_LIBRARY.get(reference_id, {}).get("label", reference_id)


def resolve_reference_id(
    *,
    reference_id: str | None,
    voice_role: str | None,
    source_text: str | None,
    default_reference_id: str = DEFAULT_REFERENCE_ID,
    scan_source_text: bool = True,
) -> dict[str, str | None]:
    explicit = (reference_id or "").strip()
    if explicit:
        if explicit not in REFERENCE_LIBRARY:
            raise FishTtsError(
                f"Unknown Fish reference_id: {explicit}. Known ids: {', '.join(sorted(REFERENCE_LIBRARY))}"
            )
        return {
            "reference_id": explicit,
            "label": reference_label(explicit),
            "resolved_from": "reference_id",
            "matched_keyword": None,
            "voice_role": voice_role,
        }

    hint_parts: list[str] = []
    if voice_role:
        hint_parts.append(voice_role.lower())
    if scan_source_text and source_text:
        hint_parts.append(source_text.lower())
    hint_blob = " ".join(hint_parts)

    for resolved_id, keyword in ROLE_KEYWORDS:
        if keyword.lower() in hint_blob:
            resolved_from = "voice_role" if voice_role and keyword.lower() in voice_role.lower() else "source_text"
            return {
                "reference_id": resolved_id,
                "label": reference_label(resolved_id),
                "resolved_from": resolved_from,
                "matched_keyword": keyword,
                "voice_role": voice_role,
            }

    return {
        "reference_id": default_reference_id,
        "label": reference_label(default_reference_id),
        "resolved_from": "default",
        "matched_keyword": None,
        "voice_role": voice_role,
    }


def _extract_agent_text(payload: dict[str, Any]) -> str:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise FishTtsError("Internal agent run returned an unexpected payload shape.")
    payloads = result.get("payloads")
    if not isinstance(payloads, list):
        raise FishTtsError("Internal agent run did not return payloads.")
    texts = [
        item.get("text", "")
        for item in payloads
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    ]
    merged = "\n".join(text.strip() for text in texts if text.strip()).strip()
    if not merged:
        raise FishTtsError("Internal agent run returned empty text.")
    return merged


def _parse_json_blob(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise FishTtsError("Internal agent returned empty output.")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise FishTtsError("Internal agent returned non-JSON output.")
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise FishTtsError(f"Internal agent JSON parse failed: {exc}") from exc


def _codex_binary() -> str:
    configured_raw = os.environ.get("AI_DAILY_CONTENT_CODEX_BIN", "").strip()
    if configured_raw:
        configured = pathlib.Path(configured_raw).expanduser()
        if configured.exists():
            return str(configured)
    discovered = shutil.which("codex")
    if discovered:
        return discovered
    app_binary = pathlib.Path("/Applications/Codex.app/Contents/Resources/codex")
    if app_binary.exists():
        return str(app_binary)
    raise FishTtsError("Codex CLI not found; Fish TTS text planning must run through Codex.")


def _run_internal_agent(
    *,
    prompt: str,
    session_id: str,
    thinking: str,
    timeout: int,
) -> dict[str, Any]:
    reasoning_effort = {"minimal": "low"}.get((thinking or "").strip().lower(), (thinking or "low").strip())
    with tempfile.TemporaryDirectory(prefix=f"{session_id}-") as tmp:
        output_path = pathlib.Path(tmp) / "codex-output.txt"
        completed = subprocess.run(
            [
                _codex_binary(),
                "exec",
                "--skip-git-repo-check",
                "--sandbox",
                "danger-full-access",
                "-m",
                os.environ.get("AI_DAILY_TTS_CODEX_MODEL", "gpt-5.4"),
                "-c",
                f"model_reasoning_effort={json.dumps(reasoning_effort)}",
                "-o",
                str(output_path),
                prompt,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = output_path.read_text(encoding="utf-8", errors="replace") if output_path.exists() else completed.stdout
    if completed.returncode != 0:
        raise FishTtsError(
            f"Internal agent run failed: {(completed.stderr or completed.stdout)[-1200:]}"
        )
    return {"status": "ok", "result": {"payloads": [{"text": output.strip()}]}}


def generate_soul_text(
    *,
    source_text: str,
    soul_brief: str | None,
    max_chars: int,
    thinking: str,
    timeout: int,
    persona_hint: str = "Lumi / 千花书记",
) -> str:
    extra = soul_brief.strip() if soul_brief else "无额外要求"
    prompt = (
        "# 角色\n"
        f"你是中文口播编辑，负责把文字改成适合 Fish TTS 直接朗读的自然口语。语气可以带有 {persona_hint} 的气质，但必须自然、可读、靠谱。\n\n"
        "# 任务\n"
        "把输入意图改写成一条最终朗读正文。先保留事实和语义，再优化节奏、停顿感和顺口程度。\n\n"
        "# 硬约束\n"
        "只输出最终要朗读的正文；不要解释；不要标题；不要 markdown；不要项目符号；不要舞台说明；不要方括号情绪标签。"
        "不得新增事实、数字、身份、地点或结论。"
        f"默认控制在 {max_chars} 个中文字符以内，除非原文明确要求更长。\n\n"
        "# 额外风格要求\n"
        f"{extra}\n\n"
        "# 原始意图\n"
        f"{source_text.strip()}"
    )
    payload = _run_internal_agent(
        prompt=prompt,
        session_id="internal-fish-tts-soul",
        thinking=thinking,
        timeout=timeout,
    )
    return _extract_agent_text(payload)


def _choose_fallback_tags(task_type: str, reference_id: str) -> list[str]:
    if task_type == "daily_video_narration":
        return ["[professional broadcast tone]", "[short pause]"]
    if reference_id == "gentle_female":
        return ["[low voice]", "[short pause]"]
    if reference_id == "qianzao_aiyin":
        return ["[excited tone]"]
    if reference_id == "dingzhen":
        return ["[with strong accent]", "[short pause]"]
    if reference_id == "calm_male":
        return ["[short pause]", "[emphasis]"]
    return ["[emphasis]"]


def plan_tts_text(
    *,
    source_text: str,
    task_type: str,
    reference_id: str,
    voice_role: str | None = None,
    with_soul: bool = False,
    tag_hint: str | None = None,
    style_preset: str | None = None,
    thinking: str = "minimal",
    timeout: int = DEFAULT_TAG_TIMEOUT,
) -> dict[str, Any]:
    base_text = " ".join(part.strip() for part in [source_text] if part and part.strip()).strip()
    if not base_text:
        raise FishTtsError("Cannot plan TTS tags for empty text.")

    existing_tags = [tag for tag in extract_tags(base_text) if validate_tag(tag)]
    preset_hint = STYLE_PRESET_HINTS.get((style_preset or "none").strip().lower(), "")
    hint_line = tag_hint.strip() if tag_hint else "无额外语气提示"
    prompt = (
        "# 角色\n"
        "你是 Fish Speech S2 Pro 的中文口播标注编辑，负责把干净口播稿处理成可直接合成的 tts_text。\n\n"
        "# 任务\n"
        "在不改变事实内容的前提下，选择少量英文方括号 tag 放到需要强调、降速、转折、提气或收束的句段前。"
        "tag 要服务语义，不要把文本演成舞台剧。\n\n"
        "# 可用参考\n"
        f"官方 tag 参考：{' '.join(OFFICIAL_FISH_TAGS)}。也允许少量自然英文 tag，但必须清楚、短、单一意图。\n\n"
        "# 硬性格式规则\n"
        "1. tag 必须是英文方括号形式，比如 [emphasis]。\n"
        "2. tag 必须放在被修饰句段前，不要闭合语法，不要 [/emphasis]。\n"
        "3. 如果输入里已经有 tag，必须保留。\n"
        "4. 最终只输出 JSON，不要解释，不要 markdown。\n"
        "5. JSON 格式固定为："
        '{"tts_text":"...","applied_tags":["[tag1]","[tag2]"],"tag_strategy":"..."}'
        "\n"
        "6. tts_text 必须仍然是可直接朗读的正文，不要掺入说明。\n"
        "7. 不要大幅改写事实内容，只允许做轻微口语顺滑和停顿优化。\n\n"
        "# 输入配置\n"
        f"- 任务类型：{task_type}\n"
        f"- reference_id：{reference_id}\n"
        f"- 声线风格：{reference_label(reference_id)}\n"
        f"- 角色提示：{voice_role or '无'}\n"
        f"- 是否已经过 soul 改写：{'是' if with_soul else '否'}\n"
        f"- preset 提示：{preset_hint or '无'}\n"
        f"- 额外语气提示：{hint_line}\n\n"
        "# 输入文本\n"
        f"{base_text}"
    )

    strategy = "model-planned"
    try:
        payload = _run_internal_agent(
            prompt=prompt,
            session_id="internal-fish-tts-tags",
            thinking=thinking,
            timeout=timeout,
        )
        agent_text = _extract_agent_text(payload)
        planned = _parse_json_blob(agent_text)
        candidate = str(planned.get("tts_text", "")).strip()
        candidate_tags = [tag for tag in extract_tags(candidate) if validate_tag(tag)]
        if CHINESE_BRACKET_PATTERN.search(candidate) or "[/" in candidate:
            raise FishTtsError("Planner returned invalid tag syntax.")
        if not strip_tags(candidate):
            raise FishTtsError("Planner returned no readable text.")

        missing_existing = [tag for tag in existing_tags if tag not in candidate_tags]
        if missing_existing:
            extra_tags = [tag for tag in candidate_tags if tag not in existing_tags]
            candidate = " ".join(extra_tags + [base_text]).strip()
            candidate_tags = [tag for tag in extract_tags(candidate) if validate_tag(tag)]
            strategy = "model-planned-preserve-existing-tags"

        if not candidate_tags:
            raise FishTtsError("Planner returned no tags.")

        applied_tags = dedupe_preserve(
            [
                tag
                for tag in planned.get("applied_tags", [])
                if isinstance(tag, str) and validate_tag(tag)
            ]
            + candidate_tags
        )
        return {
            "tts_text": candidate,
            "applied_tags": applied_tags,
            "tag_strategy": str(planned.get("tag_strategy", strategy or "model-planned")).strip() or strategy,
        }
    except FishTtsError:
        fallback_tags = dedupe_preserve(existing_tags + _choose_fallback_tags(task_type, reference_id))
        candidate = " ".join(fallback_tags + [strip_tags(base_text)]).strip()
        return {
            "tts_text": candidate,
            "applied_tags": fallback_tags,
            "tag_strategy": "fallback-format-safe",
        }


def synthesize_fish(
    *,
    endpoint: str,
    text: str,
    reference_id: str,
    source_path: pathlib.Path,
    response_format: str = DEFAULT_FORMAT,
    use_memory_cache: str = "on",
    timeout: int = DEFAULT_TIMEOUT,
) -> None:
    headers_path = source_path.with_suffix(f"{source_path.suffix}.headers.txt")
    payload = json.dumps(
        {
            "text": text,
            "reference_id": reference_id,
            "format": response_format,
            "use_memory_cache": use_memory_cache,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    try:
        curl_cmd = [
            "curl",
            "--silent",
            "--show-error",
            "--fail",
            "--max-time",
            str(timeout),
            "-D",
            str(headers_path),
            "-X",
            "POST",
            *fish_tts_curl_proxy_args(),
            endpoint,
            "-H",
            "Content-Type: application/json",
            "--data-binary",
            "@-",
            "--output",
            str(source_path),
        ]
        retries = int(os.environ.get("AI_DAILY_FISH_TTS_RETRIES", "3") or "3")
        for attempt in range(1, max(1, retries) + 1):
            try:
                subprocess.run(
                    curl_cmd,
                    input=payload,
                    check=True,
                    timeout=timeout + 5,
                )
                break
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                source_path.unlink(missing_ok=True)
                headers_path.unlink(missing_ok=True)
                if attempt >= max(1, retries):
                    raise
                time.sleep(min(2 * attempt, 6))
    except subprocess.TimeoutExpired as exc:
        source_path.unlink(missing_ok=True)
        headers_path.unlink(missing_ok=True)
        raise FishTtsError(f"Fish TTS timed out: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        source_path.unlink(missing_ok=True)
        headers_path.unlink(missing_ok=True)
        raise FishTtsError(f"Fish TTS request failed: {exc}") from exc

    body = source_path.read_bytes() if source_path.exists() else b""
    content_type = ""
    if headers_path.exists():
        for line in headers_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("content-type:"):
                content_type = line.split(":", 1)[1].strip()
                break
        headers_path.unlink(missing_ok=True)

    if not body:
        source_path.unlink(missing_ok=True)
        raise FishTtsError("Fish TTS returned an empty body.")

    if response_format.lower() == "wav" and not body.startswith(b"RIFF"):
        preview = body[:200].decode("utf-8", "replace")
        source_path.unlink(missing_ok=True)
        raise FishTtsError(f"Fish TTS did not return WAV audio: {content_type} {preview}")


def convert_to_m4a(source_path: pathlib.Path, out_path: pathlib.Path) -> None:
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source_path),
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "aac",
            str(out_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FishTtsError(f"ffmpeg failed while converting to m4a: {result.stderr[-1000:]}")
