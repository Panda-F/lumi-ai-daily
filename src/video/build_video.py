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

import argparse
import html
import importlib
import importlib.util
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

SRC_DIR = _SRC_DIR
REPO_ROOT = SRC_DIR.parent

from tech_daily_parser import (
    TechDailyItem,
    TechDailyReport,
    load_report_json_sidecar,
    parse_report,
    report_json_path_for_markdown,
    shorten_text,
    source_domain,
    write_report_json,
)
from source_utils import compact_label, load_emoji_icon_map, require_mapped_emoji, sanitize_display_title
from llm_content import load_content_manifest
from video_script_payload import build_video_script_payload

try:
    from fish_tts_runtime import (
        DEFAULT_ENDPOINT as FISH_DEFAULT_ENDPOINT,
        DEFAULT_FORMAT as FISH_DEFAULT_FORMAT,
        DEFAULT_REFERENCE_ID as FISH_DEFAULT_REFERENCE_ID,
        DEFAULT_TIMEOUT as FISH_DEFAULT_TIMEOUT,
        fish_tts_curl_proxy_args,
    )
except Exception:  # noqa: BLE001
    FISH_DEFAULT_ENDPOINT = "http://192.168.1.13:8888/v1/tts"
    FISH_DEFAULT_REFERENCE_ID = "female_student"
    FISH_DEFAULT_FORMAT = "wav"
    FISH_DEFAULT_TIMEOUT = 45

    def fish_tts_curl_proxy_args() -> list[str]:
        proxy = os.environ.get("AI_DAILY_FISH_TTS_CURL_PROXY", "").strip()
        return ["--proxy", proxy] if proxy else []

REMOTION_DIR = Path(__file__).resolve().parent / "remotion"
REMOTION_RENDER_SCRIPT = REMOTION_DIR / "render.mjs"
REMOTION_PUBLIC_DIR = REMOTION_DIR / "public"
DAILY_REPORTS_ROOT = Path(os.environ.get("AI_DAILY_REPORTS_ROOT", REPO_ROOT.parent)).expanduser().resolve()
HTML_BASELINE = "light"
LUMI_FIXED_SLOGAN = "于数字荒原，点燃认知之火。"
FRIENDLY_OUTPUT_SIZE_MB = 20.0
OFFICIAL_ISSUE_START_DATE = os.environ.get("AI_DAILY_OFFICIAL_START_DATE", "2026-04-13").strip()
TTS_PREFLIGHT_TIMEOUT = 2.5
SUBTITLE_MAX_WEIGHT = 15.4
SUBTITLE_MAX_VISUAL_UNITS = 26.8
SUBTITLE_MAX_RAW_CHARS = 30

FPS = 60
WIDTH = 1920
HEIGHT = 1080
INTRO_MIN_FRAMES = 210
INTRO_TAIL_FRAMES = 20


ITEM_ENTRY_FRAMES = 28
ITEM_TAIL_FRAMES = 30
OUTRO_FRAMES = 160
TRANSITION_SFX_OFFSET_FRAMES = 8

FISH_STYLE_PRESETS: dict[str, str] = {
    "none": "",
    "bright": "[excited] [emphasis]",
    "playful": "[laugh] [emphasis]",
    "gentle": "[pause] [exhale]",
    "secret": "[whisper] [pause]",
    "serious": "[pause] [emphasis]",
    "comfort": "[exhale] [pause]",
    "surprised": "[surprised] [gasp]",
    "news": "[emphasis] [pause]",
}

_WHISPER_MODEL_CACHE: dict[str, Any] = {}
_PIL_MODULE_CACHE: Any | None = None


def tail_text(text: str, limit: int = 1200) -> str:
    value = str(text or "")
    return value[-limit:] if len(value) > limit else value

DECORATIVE_IMAGE_HINTS = (
    "opengraph",
    "og-image",
    "og_",
    "illustration",
    "hero",
    "banner",
    "logo",
    "wordmark",
    "icon",
    "avatar",
    "gradient",
)
INFORMATIVE_IMAGE_HINTS = (
    "chart",
    "graph",
    "table",
    "benchmark",
    "result",
    "results",
    "eval",
    "matrix",
    "paper",
    "screenshot",
    "dashboard",
)
TEXT_HEAVY_HINTS = (
    "tweet",
    "thread",
    "email",
    "mail",
    "docs",
    "readme",
    "screenshot",
    "screen",
    "terminal",
    "repo",
    "github",
    "paper",
    "arxiv",
)

GENERATIVE_FILLER_HINTS = (
    "gemini_generated_image",
    "generated_image_",
    "midjourney",
    "stablediffusion",
    "stable-diffusion",
    "dalle",
    "flux-dev",
)

GENERIC_DOMAIN_TOKENS = {
    "www",
    "com",
    "co",
    "cn",
    "net",
    "org",
    "io",
    "ai",
    "blog",
    "news",
    "www2",
}

TOPIC_TERM_STOPWORDS = {
    "today",
    "daily",
    "briefing",
    "report",
    "release",
    "preview",
    "product",
    "products",
    "news",
    "about",
    "using",
    "into",
    "from",
    "with",
    "this",
    "that",
    "their",
    "these",
    "those",
    "engineering",
    "system",
    "systems",
    "models",
    "model",
    "agent",
    "agents",
    "eval",
    "evals",
    "assistant",
    "default",
}

URL_SLUG_STOPWORDS = TOPIC_TERM_STOPWORDS | {
    "best",
    "way",
    "store",
    "app",
    "apps",
    "file",
    "files",
    "dataset",
    "datasets",
    "together",
    "team",
    "teams",
    "preview",
    "partner",
    "partners",
}

OFFICIAL_MEDIA_DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "openai": ("openai.com",),
    "codex": ("openai.com",),
    "anthropic": ("anthropic.com",),
    "claude": ("anthropic.com",),
    "hugging face": ("huggingface.co",),
    "buckets": ("huggingface.co",),
    "meta": ("meta.ai", "ai.meta.com", "about.fb.com", "facebook.com"),
    "muse spark": ("meta.ai", "ai.meta.com", "about.fb.com", "facebook.com"),
}

CHINESE_TOPIC_HINT_TRANSLATIONS = {
    "存储": "storage",
    "安全": "safety",
    "评测": "evals",
    "环境": "environment",
    "发布": "launch",
    "应用": "app",
}

DAILY_KEYWORD_TRANSLATIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bcredential|credentials\b", re.I), "凭证风险"),
    (re.compile(r"\bregression\s+harness\b|\bsecurity\s+regression\b", re.I), "安全回归测试"),
    (re.compile(r"\btalent\s+pipeline\b", re.I), "人才培养链"),
    (re.compile(r"\blocal\s+ai\s+coding\s+agents?\b", re.I), "本地编程代理"),
    (re.compile(r"\bstrategic\s+reasoning\s+risks?\b", re.I), "策略推理风险"),
    (re.compile(r"\btaxonomy[-\s]+driven\b", re.I), "分类评测"),
    (re.compile(r"\bmulti[-\s]+agent\b", re.I), "多代理协作"),
    (re.compile(r"\bneural\s+cellular\s+automata\b", re.I), "神经元胞自动机"),
    (re.compile(r"\bbacklash\b|反弹|州议员", re.I), "公共反弹"),
    (re.compile(r"\bMCP\b|\bMCP-integrated\b", re.I), "MCP 接入"),
)

EMOJI_RE = re.compile(r"[\U00010000-\U0010ffff]")
DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
OPENING_PUNCTUATION = {"“", "‘", "（", "(", "《", "【"}
PUNCTUATION_RE = re.compile(r"^[，。！？；：、“”‘’（）()《》【】—…,.!?;:\-]+$")
TTS_TAG_RE = re.compile(r"\[[A-Za-z][^\[\]\n]{0,80}\]")

DISPLAY_LANGUAGE_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\battackers\s+went\s+for\s+the\s+credentials\b", re.I), "攻击者直奔凭证"),
    (re.compile(r"\bwent\s+for\s+the\s+credentials\b", re.I), "直奔凭证"),
    (re.compile(r"\bgot\s+hacked\b", re.I), "遭攻击"),
    (re.compile(r"\bAI\s+threatens\s+Big\s+Law'?s\s+talent\s+pipeline\b", re.I), "AI 正在挤压大型律所的人才培养链"),
    (re.compile(r"\bAI\s+talks?\s+draw\s+backlash\s+from\s+Mass\.?\s+state\s+lawmakers\b", re.I), "AI 会谈引发 Massachusetts 州议员反弹"),
    (re.compile(r"\bdraw\s+backlash\s+from\s+Mass\.?\s+state\s+lawmakers\b", re.I), "引发 Massachusetts 州议员反弹"),
    (re.compile(r"\broll\s+your\s+own\s+local\s+AI\s+coding\s+agents?\s+to\s+save\s+money\b", re.I), "自建本地 AI 编程智能体来省钱"),
    (re.compile(r"\broll\s+your\s+own\b", re.I), "自建"),
    (re.compile(r"\binteractive\s+multi[-\s]+agent\s+neural\s+cellular\s+automata\b", re.I), "交互式多智能体神经元胞自动机"),
    (re.compile(r"\bmulti[-\s]+agent\b", re.I), "多智能体"),
    (re.compile(r"\bneural\s+cellular\s+automata\b", re.I), "神经元胞自动机"),
    (re.compile(r"\bevaluation\s+framework\b", re.I), "评测框架"),
    (re.compile(r"\bcredentials?\b", re.I), "凭证"),
    (re.compile(r"\bAgent\s+Security\s+Regression\s+Harness\b", re.I), "智能体安全回归测试框架"),
    (re.compile(r"\bSecurity\s+Regression\s+Harness\b", re.I), "安全回归测试框架"),
    (re.compile(r"\bagentic\s+applications\b", re.I), "智能体应用"),
    (re.compile(r"\bMCP[-\s]+integrated\s+systems\b", re.I), "MCP 集成系统"),
    (re.compile(r"\bAI talks?\b", re.I), "AI 会谈"),
    (re.compile(r"\bbacklash\b", re.I), "反弹"),
    (re.compile(r"\btalent\s+pipeline\b", re.I), "人才培养链"),
    (re.compile(r"\bBig\s+Law\b", re.I), "大型律所"),
    (re.compile(r"\blocal\s+AI\s+coding\s+agents?\b", re.I), "本地 AI 编程智能体"),
    (re.compile(r"\bAI\s+coding\s+agents?\b", re.I), "AI 编程智能体"),
    (re.compile(r"\bcoding\s+agents?\b", re.I), "编程智能体"),
    (re.compile(r"\bagents?\b", re.I), "智能体"),
    (re.compile(r"\bStrategic\s+Reasoning\s+Risks?\b", re.I), "策略推理风险"),
    (re.compile(r"\btaxonomy[-\s]+driven\b", re.I), "分类体系驱动"),
    (re.compile(r"\btaxonomy\b", re.I), "分类体系"),
    (re.compile(r"\bevals?\b", re.I), "评测"),
)

TITLE_REWRITE_PATTERNS: list[tuple[re.Pattern[str], str]] = []
PUBLIC_TITLE_REWRITE_PATTERNS: list[tuple[re.Pattern[str], str]] = list(DISPLAY_LANGUAGE_REWRITES)
SPOKEN_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = []
PUBLIC_SPOKEN_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = list(DISPLAY_LANGUAGE_REWRITES)
PUBLIC_TREND_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = list(DISPLAY_LANGUAGE_REWRITES)
SPOKEN_ALIAS_RULES: list[tuple[str, re.Pattern[str], str]] = []

SCENE_STYLE_VARIANTS = {
    "intro": "intro_light",
    "quote_dominant": "quote_dominant",
    "media_then_quote": "media_then_quote",
    "fact_dominant_fallback": "fact_dominant_fallback",
    "research_quote_fallback": "research_quote_fallback",
    "outro": "outro_light",
}


def _latest_daily_report_asset(filename: str) -> Path | None:
    if not DAILY_REPORTS_ROOT.exists():
        return None
    candidates = sorted(DAILY_REPORTS_ROOT.glob(f"20??-??-??/video-build/{filename}"))
    return candidates[-1] if candidates else None


_ASSETS_DIR = Path(os.environ.get("AI_DAILY_ASSETS_DIR", REPO_ROOT / "assets")).expanduser().resolve()
DEFAULT_LUMI_INTRO_IMAGE = (
    _ASSETS_DIR / "lumi" / "lumi-broadcasting-clean.png"
    if (_ASSETS_DIR / "lumi" / "lumi-broadcasting-clean.png").exists()
    else _ASSETS_DIR / "lumi" / "lumi-broadcasting.png"
    if (_ASSETS_DIR / "lumi" / "lumi-broadcasting.png").exists()
    else (
        _ASSETS_DIR / "lumi-dance.gif"
        if (_ASSETS_DIR / "lumi-dance.gif").exists()
        else _latest_daily_report_asset("lumi-dance.gif") or REPO_ROOT / "assets" / "lumi" / "lumi-avatar.png"
    )
)
DEFAULT_LUMI_AVATAR_IMAGE = (
    _ASSETS_DIR / "lumi" / "lumi-quote-avatar.png"
    if (_ASSETS_DIR / "lumi" / "lumi-quote-avatar.png").exists()
    else (
        _ASSETS_DIR / "lumi-avatar.png"
        if (_ASSETS_DIR / "lumi-avatar.png").exists()
        else _latest_daily_report_asset("lumi-avatar.png")
    )
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a narrated tech-daily video from Markdown with Remotion.")
    parser.add_argument("--report", required=True, help="Path to the tech daily Markdown report")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument("--title-pack", help="Optional title-pack.json used for issue label and outward-facing metadata")
    parser.add_argument("--content-manifest", help="Optional content-manifest.json path")
    parser.add_argument("--voice", default="Tingting", help="macOS say voice name")
    parser.add_argument("--rate", type=int, default=245, help="macOS say rate")
    parser.add_argument("--max-items", type=int, default=6, help="Max items to keep")
    parser.add_argument("--manifest", help="Prebuilt asset manifest")
    parser.add_argument("--tts-endpoint", default=FISH_DEFAULT_ENDPOINT, help="Optional HTTP TTS endpoint")
    parser.add_argument("--tts-reference-id", default=FISH_DEFAULT_REFERENCE_ID, help="Optional remote TTS voice/reference id")
    parser.add_argument("--tts-format", default=FISH_DEFAULT_FORMAT, help="Remote TTS response format")
    parser.add_argument("--tts-use-memory-cache", default="on", help="Remote TTS cache flag")
    parser.add_argument("--tts-timeout", type=int, default=FISH_DEFAULT_TIMEOUT, help="Remote TTS request timeout in seconds")
    parser.add_argument("--tts-style-preset", default="news", help="Optional Fish style preset")
    parser.add_argument("--tts-style-tags", help="Optional Fish inline style tags, e.g. [emphasis] [pause]")
    parser.add_argument("--require-fish", action="store_true", help="Fail the build if any spoken segment falls back away from Fish")
    parser.add_argument(
        "--remotion-public-dir",
        help="Writable Remotion public directory. Defaults to AI_DAILY_REMOTION_PUBLIC_DIR or the template public dir.",
    )
    parser.add_argument(
        "--stills-only",
        action="store_true",
        help="Render only video page screenshots from the latest content manifest; do not synthesize TTS or render MP4/SRT.",
    )
    _default_bgm = _ASSETS_DIR / "bgm-lofi-morning.mp3"
    parser.add_argument("--bgm-path", default=str(_default_bgm) if _default_bgm.exists() else None, help="Optional background music path; if omitted, generate a subtle instrumental bed")
    parser.add_argument("--bgm-analysis", help="Optional bgm-analysis.json with recommended trim points")
    parser.add_argument("--bgm-volume", type=float, default=0.32, help="Background music mix volume (0-1)")
    parser.add_argument("--no-bgm", action="store_true", help="Disable background music")
    parser.add_argument("--disable-outro-bgm", action="store_true", help="Keep BGM out of the outro")
    parser.add_argument(
        "--transition-sfx-path",
        help="Optional transition sound effect path; if omitted, generate a subtle digital sweep",
    )
    parser.add_argument("--transition-sfx-volume", type=float, default=0.09, help="Transition SFX mix volume (0-1)")
    parser.add_argument("--no-transition-sfx", action="store_true", help="Disable transition sound effects between news")
    parser.add_argument(
        "--min-reviewed-images",
        type=int,
        default=2,
        help="Minimum reviewed images required per news item before the build is allowed to continue",
    )
    parser.add_argument("--lumi-intro-image", default=str(DEFAULT_LUMI_INTRO_IMAGE), help="Optional Lumi intro image path")
    parser.add_argument(
        "--lumi-avatar-image",
        default=str(DEFAULT_LUMI_AVATAR_IMAGE) if DEFAULT_LUMI_AVATAR_IMAGE else None,
        help="Optional Lumi avatar path",
    )
    parser.add_argument("--whisper-model", default="base", help="faster-whisper model name")
    parser.add_argument("--no-whisper", action="store_true", help="Disable faster-whisper word alignment")
    return parser.parse_args()


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=check,
        capture_output=capture_output,
        text=text,
    )


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def reset_generated_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def compose_fish_tts_text(
    text: str,
    style_preset: str,
    style_tags: str | None,
    *,
    add_prefix: bool = True,
) -> str:
    if not add_prefix:
        return text.strip()
    preset = FISH_STYLE_PRESETS.get((style_preset or "none").strip().lower(), "")
    shaped = text.strip()
    parts = [preset.strip()]
    if style_tags:
        parts.append(style_tags.strip())
    prefix = " ".join(part for part in parts if part)
    voiced = f"[inhale] {shaped}".strip()
    return f"{prefix} {voiced}".strip() if prefix else voiced


def split_remote_tts_chunks(text: str, *, max_chars: int = 86) -> list[str]:
    compact = normalize_spoken_text(text)
    if not compact:
        return []
    sentences = [part.strip() for part in re.split(r"(?<=[。！？!?；;])", compact) if part and part.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        pieces = [sentence]
        if len(sentence) > max_chars:
            pieces = [part.strip() for part in re.split(r"(?<=[，,:：])", sentence) if part and part.strip()]
        for piece in pieces:
            if len(piece) > max_chars:
                start = 0
                while start < len(piece):
                    end = min(len(piece), start + max_chars)
                    segment = piece[start:end].strip()
                    if segment:
                        if current and len(current) + len(segment) > max_chars:
                            chunks.append(current.strip())
                            current = ""
                        if len(segment) >= max_chars:
                            chunks.append(segment)
                        else:
                            current = f"{current}{segment}".strip()
                    start = end
                continue
            candidate = f"{current}{piece}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current.strip())
                current = piece
            else:
                current = candidate
    if current:
        chunks.append(current.strip())
    return [chunk for chunk in chunks if chunk]


def strip_tts_tags(text: str) -> str:
    return TTS_TAG_RE.sub("", text or "").strip()


def install_python_package(package: str) -> bool:
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", package], check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def ensure_faster_whisper_module() -> Any | None:
    spec = importlib.util.find_spec("faster_whisper")
    if spec is None:
        print("[whisper] faster-whisper not found, attempting install...", file=sys.stderr)
        if not install_python_package("faster-whisper"):
            print("[whisper] install failed, falling back to sentence-level subtitles.", file=sys.stderr)
            return None
    module = importlib.import_module("faster_whisper")
    return module


def ensure_pillow_module() -> Any:
    global _PIL_MODULE_CACHE
    if _PIL_MODULE_CACHE is not None:
        return _PIL_MODULE_CACHE
    spec = importlib.util.find_spec("PIL")
    if spec is None:
        print("[images] Pillow not found, attempting install...", file=sys.stderr)
        if not install_python_package("Pillow"):
            raise RuntimeError("Pillow unavailable")
    _PIL_MODULE_CACHE = importlib.import_module("PIL")
    return _PIL_MODULE_CACHE



def ensure_remotion_deps() -> None:
    node_modules = REMOTION_DIR / "node_modules"
    if (node_modules / "remotion").exists() and (node_modules / "@remotion" / "renderer").exists():
        return
    print("[remotion] dependencies missing, running npm install...", file=sys.stderr)
    subprocess.run(["npm", "install"], cwd=REMOTION_DIR, check=True)


def aspect_ratio_label(width: int, height: int) -> str:
    divisor = math.gcd(width, height) or 1
    return f"{width // divisor}:{height // divisor}"


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def normalize_search_text(value: str) -> str:
    text = urllib.parse.unquote((value or "").strip()).lower()
    text = html.unescape(text)
    text = re.sub(r"[“”\"'`]+", " ", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff./:_-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalized_media_identity(value: str) -> str:
    candidate = (value or "").strip().lower()
    if not candidate:
        return ""
    candidate = re.sub(r"^\d+-", "", candidate)
    candidate = re.sub(r"-[0-9a-f]{8,}(?=(\.[a-z0-9]+)?$)", "", candidate)
    return candidate


def media_identity_key(asset: dict[str, Any]) -> str:
    source = source_domain(str(asset.get("page_final_url") or asset.get("source_page") or ""))
    image_url = str(asset.get("image_url") or "")
    image_name = Path(urllib.parse.urlparse(image_url).path).name or Path(str(asset.get("file") or "")).name
    normalized_name = normalized_media_identity(image_name)
    return f"{source}:{normalized_name}" if normalized_name else str(asset.get("file") or "")


def preferred_media_domains(item: TechDailyItem) -> set[str]:
    domains: set[str] = set()
    source = source_domain(item.source_url).lower()
    if source and source not in {"x.com", "twitter.com", "t.co"}:
        domains.add(source)
    blob = normalize_search_text(f"{item.title} {item.content} {item.quote or ''} {item.source_url}")
    for phrase, mapped_domains in OFFICIAL_MEDIA_DOMAIN_HINTS.items():
        if phrase in blob:
            domains.update(mapped_domains)
    return {domain for domain in domains if domain}


def domain_keyword_terms(domain: str) -> set[str]:
    host = source_domain(domain).lower() or normalize_search_text(domain).split(" ", 1)[0]
    if not host:
        return set()
    terms: set[str] = set()
    for part in re.split(r"[._-]+", host):
        if not part or part in GENERIC_DOMAIN_TOKENS or part.isdigit() or len(part) < 3:
            continue
        terms.add(part)
        if part == "huggingface":
            terms.update({"hugging", "face"})
    return terms


def item_brand_terms(item: TechDailyItem) -> set[str]:
    terms: set[str] = set()
    for domain in preferred_media_domains(item) | {source_domain(item.source_url).lower()}:
        terms.update(domain_keyword_terms(domain))
    return terms


def slugify_phrase(value: str) -> str:
    words = re.findall(r"[a-z0-9]+", normalize_search_text(value))
    return "-".join(words[:4]).strip("-")


def item_topic_terms(item: TechDailyItem, *, limit: int = 14) -> list[str]:
    blob = normalize_search_text(f"{display_title_text(item.title)} {item.content} {item.quote or ''}")
    terms = re.findall(r"[a-z][a-z0-9.+-]{2,}|[\u4e00-\u9fff]{2,}", blob)
    filtered = [
        term
        for term in unique(terms)
        if term not in TOPIC_TERM_STOPWORDS and len(term) >= 2
    ]
    return filtered[:limit]


def item_topic_phrases(item: TechDailyItem, *, limit: int = 8) -> list[str]:
    phrases: list[str] = []
    title_blob = normalize_search_text(display_title_text(item.title))
    for phrase in re.findall(r"[a-z][a-z0-9.+-]*(?:\s+[a-z][a-z0-9.+-]*){1,2}", title_blob):
        compact = phrase.replace(" ", "")
        if len(compact) >= 7:
            phrases.append(phrase)
    source_path = normalize_search_text(urllib.parse.urlparse(item.source_url).path.replace("-", " "))
    if source_path:
        for phrase in re.findall(r"[a-z][a-z0-9.+-]*(?:\s+[a-z][a-z0-9.+-]*){0,2}", source_path):
            compact = phrase.replace(" ", "")
            if len(compact) >= 7:
                phrases.append(phrase)
    return unique(phrases)[:limit]


def item_translated_topic_terms(item: TechDailyItem, *, limit: int = 4) -> list[str]:
    blob = f"{item.title} {item.content} {item.quote or ''}"
    translated: list[str] = []
    for zh_term, en_term in CHINESE_TOPIC_HINT_TRANSLATIONS.items():
        if zh_term in blob:
            translated.append(en_term)
    return unique(translated)[:limit]


def item_priority_ascii_terms(item: TechDailyItem, *, limit: int = 6) -> list[str]:
    brand_terms = item_brand_terms(item)
    source_path = urllib.parse.urlparse(item.source_url).path.replace("-", " ")
    raw_terms = re.findall(
        r"[A-Za-z][A-Za-z0-9.+-]{2,}",
        f"{display_title_text(item.title)} {item.quote or ''} {source_path}",
    )
    normalized_terms = [term.lower().strip(".") for term in raw_terms if term]
    filtered = [
        term
        for term in unique(normalized_terms)
        if term and term not in brand_terms and term not in URL_SLUG_STOPWORDS
    ]
    return filtered[:limit]


def topic_overlap_score(item: TechDailyItem, text: str) -> tuple[int, int]:
    blob = normalize_search_text(text)
    term_hits = sum(1 for term in item_topic_terms(item) if term in blob)
    phrase_hits = sum(1 for phrase in item_topic_phrases(item) if phrase and phrase in blob)
    return term_hits, phrase_hits


def topic_specific_overlap_score(item: TechDailyItem, text: str) -> tuple[int, int]:
    blob = normalize_search_text(text)
    brand_terms = item_brand_terms(item)
    term_hits = sum(1 for term in item_topic_terms(item) if term not in brand_terms and term in blob)
    phrase_hits = 0
    for phrase in item_topic_phrases(item):
        phrase_terms = [part for part in phrase.split() if part]
        if phrase_terms and all(part in brand_terms for part in phrase_terms):
            continue
        if phrase and phrase in blob:
            phrase_hits += 1
    return term_hits, phrase_hits


def is_rootish_url(url: str) -> bool:
    path = urllib.parse.urlparse(url).path.strip("/")
    return not path or path in {"index.html", "index.htm", "home"}


def url_exists(url: str, timeout: int = 10) -> bool:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(getattr(response, "status", 200)) < 400
    except Exception:  # noqa: BLE001
        return False


def official_story_url_candidates(item: TechDailyItem, *, limit: int = 10) -> list[str]:
    social_domains = {"x.com", "twitter.com", "t.co"}
    brand_terms = item_brand_terms(item)
    source_domain_name = source_domain(item.source_url).lower()
    domains = [
        domain
        for domain in sorted(preferred_media_domains(item))
        if domain and domain not in social_domains
    ]
    if source_domain_name and source_domain_name not in social_domains and source_domain_name not in domains:
        domains.insert(0, source_domain_name)

    slug_candidates: list[str] = []
    source_path = urllib.parse.urlparse(item.source_url).path.strip("/")
    if source_path and source_domain_name not in social_domains:
        slug_candidates.append(source_path)
        slug_candidates.append(source_path.split("/")[-1])

    for phrase in item_topic_phrases(item):
        phrase_terms = [part for part in phrase.split() if part]
        if phrase_terms and all(part in brand_terms for part in phrase_terms):
            continue
        slug = slugify_phrase(phrase)
        if slug:
            slug_candidates.append(slug)

    prioritized_ascii_terms = item_priority_ascii_terms(item)
    ascii_specific_terms = prioritized_ascii_terms + [
        term
        for term in item_topic_terms(item)
        if term not in brand_terms and term not in prioritized_ascii_terms and re.fullmatch(r"[a-z0-9.+-]{3,}", term)
    ]
    translated_terms = item_translated_topic_terms(item)
    if translated_terms and ascii_specific_terms:
        slug_candidates.append("-".join((translated_terms[:1] + ascii_specific_terms[:1])[:2]))
        slug_candidates.append("-".join((translated_terms[:1] + ascii_specific_terms[:2])[:3]))
    slug_candidates.extend(ascii_specific_terms[:6])

    prefixes = ("", "blog", "news", "index", "engineering", "research", "articles")
    candidates: list[str] = []
    for domain in domains:
        for slug in unique([candidate for candidate in slug_candidates if candidate]):
            for prefix in prefixes:
                path = slug if not prefix else f"{prefix}/{slug}"
                candidates.append(f"https://{domain}/{path}")
    return unique(candidates)[:limit]


def media_domain_matches(item: TechDailyItem, *domains: str) -> bool:
    preferred = preferred_media_domains(item)
    for raw in domains:
        domain = (raw or "").lower()
        if not domain:
            continue
        if domain in preferred or any(domain.endswith(f".{candidate}") for candidate in preferred):
            return True
    return False


def reuse_previous_build_selected_media(item: TechDailyItem, out_dir: Path) -> list[dict[str, object]]:
    try:
        build_root = out_dir.resolve().parents[2]
    except IndexError:
        return []
    day_root = build_root.parent
    if not day_root.exists():
        return []
    previous_roots = [
        candidate
        for candidate in sorted(day_root.glob("video-build*"), reverse=True)
        if candidate.resolve() != build_root and (candidate / "build-summary.json").exists()
    ]
    public_roots = [
        resolve_remotion_public_dir(None),
        REMOTION_PUBLIC_DIR,
        REMOTION_DIR / ".bundle" / "public",
    ]
    for previous_root in previous_roots:
        manifest_path = previous_root / "remotion-manifest.json"
        if not manifest_path.exists():
            continue
        try:
            payload = json.loads(manifest_path.read_text())
        except Exception:  # noqa: BLE001
            continue
        scenes = payload.get("scenes") or []
        for scene in scenes:
            if scene.get("kind") != "item" or int(scene.get("index") or 0) != item.index:
                continue
            cached_candidates: list[dict[str, object]] = []
            reused: list[dict[str, object]] = []
            for asset in scene.get("media_assets") or []:
                src = str(asset.get("src") or "")
                if not src:
                    continue
                existing_file = None
                for root in public_roots:
                    candidate = (root / src).resolve()
                    if candidate.exists():
                        existing_file = candidate
                        break
                if not existing_file:
                    desired_image_url = str(asset.get("image_url") or "")
                    desired_name = Path(urllib.parse.urlparse(desired_image_url).path).name or Path(src).name
                    for candidate_asset in cached_candidates:
                        candidate_file = Path(str(candidate_asset.get("file") or "")).resolve()
                        candidate_image_url = str(candidate_asset.get("image_url") or "")
                        candidate_name = Path(urllib.parse.urlparse(candidate_image_url).path).name or candidate_file.name
                        if candidate_file.exists() and (
                            (desired_image_url and candidate_image_url == desired_image_url)
                            or candidate_name == desired_name
                        ):
                            existing_file = candidate_file
                            break
                if not existing_file:
                    continue
                reused.append(
                    {
                        "file": str(existing_file),
                        "kind": asset.get("kind") or "image",
                        "selector": "cached-selected",
                        "image_url": asset.get("image_url") or src,
                        "source_page": asset.get("source_page") or asset.get("image_url") or "",
                        "page_final_url": asset.get("source_page") or asset.get("image_url") or "",
                        "search_title": asset.get("search_title") or str(scene.get("title") or ""),
                        "image_rank": len(reused) + 1,
                        "content_type": "",
                        "size_bytes": existing_file.stat().st_size,
                    }
                )
            if reused:
                return reused
    return []


def merge_media_candidates(*groups: list[dict[str, Any]], max_images: int = 2) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for group in groups:
        for candidate in group or []:
            file_path = str(candidate.get("file") or "")
            identity = media_identity_key(candidate)
            if not file_path or not identity or identity in seen_keys:
                continue
            seen_keys.add(identity)
            merged.append(candidate)
            if len(merged) >= max_images:
                return merged
    return merged


def combine_reject_reasons(*reasons: str | None) -> str | None:
    values = [reason.strip() for reason in reasons if reason and reason.strip()]
    return " | ".join(values) if values else None


def load_assets(manifest_path: Path | None) -> list[dict[str, object]]:
    if not manifest_path or not manifest_path.exists():
        return []
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        manifest_root = manifest_path.parent
        pack_assets_by_url: dict[str, list[dict[str, object]]] = {}
        for pack_name in ("reference-pack", "source-pack"):
            pack_root = manifest_root / pack_name
            if not pack_root.exists():
                continue
            for meta_path in pack_root.glob("*/meta.json"):
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                if not isinstance(meta, dict):
                    continue
                urls = {
                    str(meta.get("url") or "").strip(),
                    str(meta.get("final_url") or "").strip(),
                }
                urls = {url for url in urls if url}
                maybe_enrich_pack_media(meta_path.parent)
                image_dir = meta_path.parent / "images"
                if not urls or not image_dir.exists():
                    continue
                image_files = sorted(
                    [
                        candidate
                        for candidate in image_dir.iterdir()
                        if candidate.is_file() and candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webm", ".mp4"}
                    ]
                )
                if not image_files:
                    continue
                assets = [
                    {
                        "file": str(image_file),
                        "source_page": str(meta.get("final_url") or meta.get("url") or ""),
                        "page_final_url": str(meta.get("final_url") or meta.get("url") or ""),
                        "selector": pack_name,
                        "image_url": image_file.name,
                        "image_rank": index,
                        "content_type": "",
                    }
                    for index, image_file in enumerate(image_files, start=1)
                ]
                for url in urls:
                    pack_assets_by_url.setdefault(url, []).extend(assets)

        converted: list[dict[str, object]] = []
        seen_files: set[str] = set()
        for item in payload["items"]:
            if not isinstance(item, dict):
                continue
            source_url = str(item.get("source_url") or "").strip()
            for pack_asset in pack_assets_by_url.get(source_url, []):
                file_path = str(pack_asset.get("file") or "")
                if file_path and file_path not in seen_files:
                    converted.append(pack_asset)
                    seen_files.add(file_path)
            selected_image = str(item.get("selected_image") or "").strip()
            if not selected_image:
                continue
            if selected_image in seen_files:
                continue
            matched_url = str(item.get("matched_url") or "").strip()
            if not matched_url:
                selected_path = Path(selected_image).expanduser()
                try:
                    selected_path.relative_to(manifest_root)
                except ValueError:
                    continue
            converted.append(
                {
                    "file": selected_image,
                    "source_page": str(item.get("matched_url") or source_url),
                    "page_final_url": source_url,
                    "selector": str(item.get("image_source") or "manifest"),
                    "image_url": Path(selected_image).name,
                    "image_rank": 1,
                    "content_type": "",
                }
            )
            seen_files.add(selected_image)
        if converted:
            return converted
    return [
        asset
        for asset in payload.get("assets", [])
        if isinstance(asset, dict) and asset.get("file")
    ]


def media_kind_from_asset(asset: dict[str, object]) -> str:
    content_type = str(asset.get("content_type") or "").lower()
    file_path = Path(str(asset.get("file") or ""))
    suffix = file_path.suffix.lower()
    if "gif" in content_type or suffix == ".gif":
        return "gif"
    if content_type.startswith("video/") or suffix in {".mp4", ".mov", ".webm", ".m4v"}:
        return "video"
    return "image"


def media_kind_from_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".gif":
        return "gif"
    if suffix in {".mp4", ".mov", ".webm", ".m4v"}:
        return "video"
    return "image"


def media_priority(asset: dict[str, object], item_url: str) -> int:
    score = 0
    source_page = str(asset.get("source_page") or "")
    final_url = str(asset.get("page_final_url") or "")
    selector = str(asset.get("selector") or "").lower()
    image_url = str(asset.get("image_url") or "").lower()
    rank = int(asset.get("image_rank") or 0)

    if item_url and (source_page == item_url or final_url == item_url):
        score += 240
    elif item_url and source_domain(source_page or final_url) == source_domain(item_url):
        score += 90

    if selector == "meta":
        score += 70
    if selector == "img":
        score += 45

    for keyword, bonus in (
        ("hero", 72),
        ("featured", 64),
        ("cover", 48),
        ("lead", 42),
        ("main", 24),
        ("og-image", 60),
        ("opengraph", 60),
    ):
        if keyword in image_url:
            score += bonus

    if media_kind_from_asset(asset) == "gif":
        score += 28
    if rank > 0:
        score += max(0, 18 - rank)
    return score


def fullscreen_fit_bucket(width: int, height: int) -> int:
    area = width * height
    min_side = min(width, height)
    if area >= 1_800_000 and min_side >= 900:
        return 3
    if area >= 900_000 and min_side >= 700:
        return 2
    if area >= 450_000 and min_side >= 450:
        return 1
    return 0


def editorial_frame_bucket(width: int, height: int) -> int:
    if width <= 0 or height <= 0:
        return 0
    aspect = width / max(height, 1)
    if 1.25 <= aspect <= 2.25:
        return 2
    if 0.75 <= aspect <= 1.25:
        return 1
    return 0


def maybe_enrich_pack_media(pack_dir: Path) -> None:
    maybe_download_twitter_large_variants(pack_dir)
    maybe_generate_pdf_preview(pack_dir)


def maybe_download_twitter_large_variants(pack_dir: Path) -> None:
    images_json = pack_dir / "images.json"
    image_dir = pack_dir / "images"
    if not images_json.exists() or not image_dir.exists():
        return
    try:
        payload = json.loads(images_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    image_entries = payload.get("images") if isinstance(payload, dict) else None
    if not isinstance(image_entries, list):
        return

    for index, asset in enumerate(image_entries, start=1):
        if not isinstance(asset, dict):
            continue
        image_url = str(asset.get("url") or "").strip()
        if "pbs.twimg.com" not in image_url:
            continue
        if "name=small" not in image_url and "name=medium" not in image_url:
            continue
        extension = Path(str(asset.get("file") or "")).suffix or ".jpg"
        for variant in ("large", "orig"):
            variant_url = re.sub(r"([?&])name=(small|medium)(?=(&|$))", rf"\1name={variant}", image_url)
            if variant_url == image_url:
                continue
            target = image_dir / f"{index:02d}-{variant}{extension}"
            if target.exists() and target.stat().st_size > 0:
                break
            try:
                download_file(variant_url, target)
            except (urllib.error.URLError, TimeoutError, OSError):
                if target.exists():
                    target.unlink(missing_ok=True)
                continue
            break


def maybe_generate_pdf_preview(pack_dir: Path) -> None:
    image_dir = pack_dir / "images"
    existing_images = list(image_dir.glob("*")) if image_dir.exists() else []
    if existing_images:
        return
    documents_dir = pack_dir / "assets" / "documents"
    pdf_files = sorted(path for path in documents_dir.glob("*.pdf") if path.is_file())
    if not pdf_files:
        return
    image_dir.mkdir(parents=True, exist_ok=True)
    preview_target = image_dir / f"{pdf_files[0].stem}.pdf.png"
    if preview_target.exists() and preview_target.stat().st_size > 0:
        return
    try:
        run(
            ["qlmanage", "-t", "-s", "1800", "-o", str(image_dir), str(pdf_files[0])],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return


def download_file(url: str, destination: Path, timeout: int = 20) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
        },
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        destination.write_bytes(response.read())


def normalize_media_url(url: str) -> str:
    return str(url or "").strip().rstrip("/")


def pack_assets_for_item_refs(item: TechDailyItem, day_dir: Path) -> list[dict[str, object]]:
    target_urls = {
        normalize_media_url(url)
        for url in [str(item.source_url or "").strip(), *(item.source_refs or [])]
        if str(url or "").strip()
    }
    if not target_urls:
        return []

    assets: list[dict[str, object]] = []
    seen_files: set[str] = set()
    for pack_name, pack_dir in (
        ("reference-pack", day_dir / "reference-pack"),
        ("source-pack", day_dir / "source-pack"),
    ):
        if not pack_dir.exists():
            continue
        for meta_path in sorted(pack_dir.glob("*/meta.json")):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if not isinstance(meta, dict):
                continue
            meta_urls = {
                normalize_media_url(str(meta.get("url") or "")),
                normalize_media_url(str(meta.get("final_url") or "")),
            }
            meta_urls = {url for url in meta_urls if url}
            if not meta_urls.intersection(target_urls):
                continue
            pack_root = meta_path.parent
            maybe_enrich_pack_media(pack_root)
            image_dir = pack_root / "images"
            if not image_dir.exists():
                continue
            image_files = sorted(
                [
                    candidate
                    for candidate in image_dir.iterdir()
                    if candidate.is_file() and candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webm", ".mp4", ".webp"}
                ]
            )
            for index, image_file in enumerate(image_files, start=1):
                file_path = str(image_file.resolve())
                if file_path in seen_files:
                    continue
                seen_files.add(file_path)
                canonical_url = next(iter(sorted(meta_urls)), "")
                assets.append(
                    {
                        "file": file_path,
                        "source_page": canonical_url,
                        "page_final_url": canonical_url,
                        "selector": pack_name,
                        "image_url": image_file.name,
                        "image_rank": index,
                        "content_type": "",
                    }
                )
    return assets


def choose_images(images: list[dict[str, object]], item: TechDailyItem, max_images: int = 6) -> list[dict[str, object]]:
    item_url = normalize_media_url(str(item.source_url or "").strip())
    item_urls = {
        normalize_media_url(url)
        for url in [str(item.source_url or "").strip(), *(item.source_refs or [])]
        if str(url or "").strip()
    }
    item_domain = source_domain(item.source_url)
    item_domains = {source_domain(url) for url in item_urls if source_domain(url)}
    if item_domain:
        item_domains.add(item_domain)
    exact_matches: list[dict[str, object]] = []
    same_domain_matches: list[dict[str, object]] = []
    for asset in images:
        page = normalize_media_url(str(asset.get("source_page") or ""))
        final_url = normalize_media_url(str(asset.get("page_final_url") or ""))
        page_domain = source_domain(page or final_url)
        if item_urls and ({page, final_url} - {""}).intersection(item_urls):
            exact_matches.append(asset)
        elif item_domains and page_domain in item_domains:
            same_domain_matches.append(asset)

    candidates = exact_matches or same_domain_matches
    ordered = sorted(candidates, key=lambda asset: media_priority(asset, item_url), reverse=True)
    deduped: list[dict[str, object]] = []
    seen_files: set[str] = set()
    for asset in ordered:
        file_path = str(asset.get("file") or "")
        if not file_path or file_path in seen_files:
            continue
        seen_files.add(file_path)
        deduped.append(asset)
        if len(deduped) >= max_images:
            break
    return deduped


def audit_image_candidates(
    item: TechDailyItem,
    image_assets: list[dict[str, object]],
    *,
    max_images: int = 3,
) -> dict[str, Any]:
    if not image_assets:
        return {"approved_assets": [], "reviewed_assets": [], "media_reject_reason": "no-matching-media"}

    ensure_pillow_module()
    from PIL import Image, ImageFilter, ImageStat  # type: ignore

    reviewed: list[dict[str, Any]] = []
    item_domain = source_domain(item.source_url).lower()
    preferred_domains = preferred_media_domains(item)
    title_terms = {
        term.lower()
        for term in re.findall(r"[A-Za-z]{3,}|[\u4e00-\u9fff]{2,}", f"{item.title} {item.content} {item.quote or ''}")
        if len(term) >= 2
    }

    for asset in image_assets:
        file_path = Path(str(asset.get("file") or "")).expanduser()
        if not file_path.exists():
            continue

        reasons: list[str] = []
        penalties: list[str] = []
        media_kind = media_kind_from_asset(asset)
        try:
            with Image.open(file_path) as image:
                rgb = image.convert("RGB")
                width, height = rgb.size
                area = width * height
                aspect_ratio = width / max(height, 1)
                stat = ImageStat.Stat(rgb)
                avg_stddev = sum(float(value) for value in stat.stddev) / max(len(stat.stddev), 1)
                entropy = float(rgb.entropy())
                grayscale = rgb.convert("L")
                edges = grayscale.filter(ImageFilter.FIND_EDGES)
                edge_mean = float(ImageStat.Stat(edges).mean[0])
                animated = bool(getattr(image, "is_animated", False))
        except Exception as exc:  # noqa: BLE001
            reviewed.append(
                {
                    "file": str(file_path),
                    "score": -999,
                    "approved": False,
                    "kind": media_kind,
                    "reason": [f"image-open-failed:{exc}"],
                    "selector": asset.get("selector"),
                    "image_url": asset.get("image_url"),
                }
            )
            continue

        image_hint_blob = " ".join(
            [
                str(asset.get("image_url") or ""),
                str(file_path.name),
                str(asset.get("selector") or ""),
                str(asset.get("search_title") or ""),
            ]
        ).lower()
        page_url = str(asset.get("page_final_url") or asset.get("source_page") or "")
        selector = str(asset.get("selector") or "")
        origin_domain = source_domain(
            page_url or item.source_url
        ).lower()
        image_domain = source_domain(str(asset.get("image_url") or "")).lower()
        overlap_terms = [term for term in title_terms if term in image_hint_blob]
        topic_term_hits, topic_phrase_hits = topic_overlap_score(
            item,
            " ".join(
                [
                    str(asset.get("search_title") or ""),
                    str(asset.get("source_page") or ""),
                    str(asset.get("page_final_url") or ""),
                    str(asset.get("image_url") or ""),
                    file_path.name,
                ]
            ),
        )
        specific_term_hits, specific_phrase_hits = topic_specific_overlap_score(
            item,
            " ".join(
                [
                    str(asset.get("search_title") or ""),
                    str(asset.get("source_page") or ""),
                    str(asset.get("page_final_url") or ""),
                    str(asset.get("image_url") or ""),
                    file_path.name,
                ]
            ),
        )
        image_term_hits, image_phrase_hits = topic_overlap_score(
            item,
            " ".join([str(asset.get("image_url") or ""), file_path.name]),
        )
        image_specific_term_hits, image_specific_phrase_hits = topic_specific_overlap_score(
            item,
            " ".join([str(asset.get("image_url") or ""), file_path.name]),
        )
        official_media_match = media_domain_matches(item, origin_domain, image_domain)
        exact_source_match = item_domain and origin_domain == item_domain

        score = 0.0
        score += min(12.0, area / 800_000)
        score += edge_mean * 6.0
        score += entropy * 12.0
        score += avg_stddev / 4.0
        score += min(6.0, float(asset.get("size_bytes") or 0) / 40_000)
        score += min(16.0, topic_term_hits * 4.0)
        score += min(18.0, topic_phrase_hits * 9.0)
        score += min(12.0, specific_term_hits * 5.0)
        score += min(14.0, specific_phrase_hits * 10.0)

        if overlap_terms:
            score += min(8.0, len(overlap_terms) * 2.5)
            reasons.append(f"title-match:{','.join(overlap_terms[:3])}")
        if topic_term_hits:
            reasons.append(f"topic-match:{topic_term_hits}")
        if topic_phrase_hits:
            reasons.append(f"topic-phrase:{topic_phrase_hits}")
        if specific_term_hits:
            reasons.append(f"specific-topic:{specific_term_hits}")
        if specific_phrase_hits:
            reasons.append(f"specific-phrase:{specific_phrase_hits}")
        if official_media_match:
            score += 22.0
            reasons.append("official-domain")
        elif exact_source_match:
            score += 10.0
            reasons.append("source-domain")
        if any(hint in image_hint_blob for hint in INFORMATIVE_IMAGE_HINTS):
            score += 10.0
            reasons.append("informative-hint")
        if media_kind == "gif" or animated:
            score += 12.0
            reasons.append("animated-media")
        if selector == "img":
            score += 4.0
            reasons.append("page-image")
        if selector == "meta":
            score -= 4.0
            penalties.append("meta-image")
            if origin_domain and origin_domain != item_domain and not official_media_match:
                score -= 18.0
                penalties.append("off-domain-meta")
            if not official_media_match and image_term_hits == 0 and image_phrase_hits == 0:
                score -= 26.0
                penalties.append("generic-meta-image")
        if (
            selector.startswith("search-")
            and not official_media_match
            and int(asset.get("image_rank") or 0) <= 1
            and image_term_hits == 0
            and image_phrase_hits == 0
        ):
            score -= 24.0
            penalties.append("generic-lead-image")
        if selector.startswith("search-") and not official_media_match and topic_term_hits < 2 and topic_phrase_hits == 0:
            score -= 28.0
            penalties.append("weak-topic-match")
        if (
            selector.startswith("search-")
            and official_media_match
            and specific_term_hits == 0
            and specific_phrase_hits == 0
            and image_specific_term_hits == 0
            and image_specific_phrase_hits == 0
        ):
            score -= 30.0
            penalties.append("brand-only-match")
        if (
            selector.startswith("search-")
            and official_media_match
            and (
                is_rootish_url(page_url)
                or "/homepage/" in str(asset.get("image_url") or "").lower()
            )
            and image_specific_term_hits == 0
            and image_specific_phrase_hits == 0
        ):
            score -= 34.0
            penalties.append("homepage-generic")
        if (
            official_media_match
            and not exact_source_match
            and image_specific_term_hits == 0
            and image_specific_phrase_hits == 0
            and any(
                hint in str(asset.get("image_url") or "").lower() or hint in file_path.name.lower()
                for hint in ("thumbnail", "thumb", "cover", "hero", "/image", "homepage")
            )
        ):
            score -= 28.0
            penalties.append("official-generic-asset")
        if any(hint in image_hint_blob for hint in DECORATIVE_IMAGE_HINTS):
            score -= 20.0
            penalties.append("decorative-hint")
        if any(hint in image_hint_blob for hint in GENERATIVE_FILLER_HINTS):
            score -= 30.0
            penalties.append("generative-filler")
        if any(hint in image_hint_blob for hint in TEXT_HEAVY_HINTS):
            score -= 20.0
            penalties.append("text-heavy-hint")
        if origin_domain in {"github.com", "arxiv.org", "x.com"} and media_kind == "image":
            score -= 16.0
            penalties.append("text-prone-domain")
        # Hard-reject PDF paper previews and arxiv screenshots — they look terrible in video
        if origin_domain in {"arxiv.org", "ui.adsabs.harvard.edu", "awesomeagents.ai"} and any(
            hint in image_name for image_name in [file_path.name.lower()] for hint in ("pdf", "paper", "page", "abstract", "report")
        ):
            score -= 60.0
            penalties.append("paper-pdf-hard-reject")
        if origin_domain == "code.claude.com" and media_kind == "image":
            score -= 16.0
            penalties.append("docs-domain")
        if origin_domain in {"code.claude.com", "github.com", "arxiv.org"} and media_kind == "image":
            image_name = file_path.name.lower()
            if any(hint in image_name for hint in ("og", "readme", "docs", "paper", "preview", "page")):
                score -= 14.0
                penalties.append("document-like-preview")
        if edge_mean < 2.2:
            score -= 18.0
            penalties.append("low-edge-density")
        if entropy < 2.0:
            score -= 14.0
            penalties.append("low-entropy")
        if avg_stddev < 28.0:
            score -= 8.0
            penalties.append("low-contrast")
        if area < 250_000:
            score -= 28.0
            penalties.append("very-small-resolution")
        elif area < 600_000:
            score -= 10.0
            penalties.append("small-resolution")
        if width < 800 or height < 450:
            score -= 14.0
            penalties.append("sub-hd-resolution")
        if aspect_ratio < 0.45 or aspect_ratio > 3.2:
            score -= 8.0
            penalties.append("extreme-aspect")
        if width < 64 or height < 64 or area < 10_000:
            score -= 90.0
            penalties.append("tracking-or-tiny")

        approve_threshold = 50.0 if media_kind in {"gif", "video"} else 58.0
        broadcast_friendly = (
            fullscreen_fit_bucket(width, height) >= 2
            and entropy >= 2.0
            and "decorative-hint" not in penalties
            and "text-heavy-hint" not in penalties
        )
        hard_reject = (
            "decorative-hint" in penalties
            or "generative-filler" in penalties
            or "text-heavy-hint" in penalties
            or "docs-domain" in penalties
            or "document-like-preview" in penalties
            or "weak-topic-match" in penalties
            or "generic-meta-image" in penalties
            or "generic-lead-image" in penalties
            or "brand-only-match" in penalties
            or "homepage-generic" in penalties
            or "official-generic-asset" in penalties
            or "tracking-or-tiny" in penalties
            or ("off-domain-meta" in penalties and not overlap_terms and "informative-hint" not in reasons)
            or (origin_domain in {"github.com", "arxiv.org", "code.claude.com"} and media_kind == "image")
            or ("text-prone-domain" in penalties and media_kind == "image" and "informative-hint" not in reasons)
        )
        approved = (score >= approve_threshold or broadcast_friendly) and not hard_reject
        if approved:
            reasons.append("approved")
            if broadcast_friendly:
                reasons.append("broadcast-hero")
        else:
            penalties.append("rejected")

        reviewed.append(
            {
                "file": str(file_path),
                "score": round(score, 2),
                "approved": approved,
                "kind": media_kind,
                "reason": reasons,
                "penalties": penalties,
                "selector": asset.get("selector"),
                "image_url": asset.get("image_url"),
                "source_page": asset.get("source_page"),
                "page_final_url": asset.get("page_final_url"),
                "source_domain": source_domain(str(asset.get("page_final_url") or asset.get("source_page") or item.source_url)),
                "image_domain": image_domain,
                "search_title": asset.get("search_title"),
                "topic_term_hits": topic_term_hits,
                "topic_phrase_hits": topic_phrase_hits,
                "image_term_hits": image_term_hits,
                "image_phrase_hits": image_phrase_hits,
                "priority": media_priority(asset, item.source_url),
                "content_type": asset.get("content_type"),
                "size_bytes": asset.get("size_bytes"),
                "width": width,
                "height": height,
                "animated": animated,
                "edge_mean": round(edge_mean, 2),
                "entropy": round(entropy, 2),
                "contrast": round(avg_stddev, 2),
            }
        )

    approved_assets = [candidate for candidate in reviewed if candidate["approved"]]
    sort_key = lambda candidate: (
        1 if media_domain_matches(item, str(candidate.get("source_domain") or ""), str(candidate.get("image_domain") or "")) else 0,
        int(candidate.get("topic_phrase_hits") or 0),
        int(candidate.get("topic_term_hits") or 0),
        fullscreen_fit_bucket(int(candidate.get("width") or 0), int(candidate.get("height") or 0)),
        editorial_frame_bucket(int(candidate.get("width") or 0), int(candidate.get("height") or 0)),
        int(candidate.get("priority") or 0),
        float(candidate["score"]),
        candidate.get("width") or 0,
        candidate.get("height") or 0,
    )
    approved_assets.sort(key=sort_key, reverse=True)
    approved_assets = approved_assets[:max_images]
    support_assets = [
        candidate
        for candidate in reviewed
        if not any(
            penalty in set(candidate.get("penalties") or [])
            for penalty in (
                "decorative-hint",
                "low-edge-density",
                "low-entropy",
                "very-small-resolution",
                "sub-hd-resolution",
            )
        )
        and "document-like-preview" not in set(candidate.get("penalties") or [])
        and "docs-domain" not in set(candidate.get("penalties") or [])
    ]
    support_assets.sort(key=sort_key, reverse=True)
    support_assets = support_assets[:max_images]
    rejected_assets = [candidate for candidate in reviewed if not candidate["approved"]]
    rejection_bits: list[str] = []
    for candidate in rejected_assets[:3]:
        penalties = ",".join(candidate.get("penalties") or [])
        if penalties:
            rejection_bits.append(f"{Path(str(candidate['file'])).name}:{penalties}")
    media_reject_reason = " | ".join(rejection_bits) if rejection_bits else None
    return {
        "approved_assets": approved_assets,
        "support_assets": support_assets,
        "reviewed_assets": reviewed,
        "media_reject_reason": media_reject_reason,
    }


def build_media_alignment_review(
    item: TechDailyItem,
    oral_script: str,
    selected_assets: list[dict[str, Any]],
    *,
    min_required: int = 2,
) -> dict[str, Any]:
    oral_term_hits, oral_phrase_hits = topic_overlap_score(item, oral_script)
    oral_specific_term_hits, oral_specific_phrase_hits = topic_specific_overlap_score(item, oral_script)
    script_relevant = (
        oral_specific_phrase_hits > 0
        or oral_specific_term_hits > 0
        or oral_phrase_hits > 0
        or oral_term_hits >= 2
    )

    asset_reviews: list[dict[str, Any]] = []
    approved_assets = 0
    for asset in selected_assets:
        blob = " ".join(
            [
                str(asset.get("image_url") or ""),
                str(asset.get("search_title") or ""),
                str(asset.get("source_page") or ""),
                str(asset.get("page_final_url") or ""),
                str(asset.get("source_domain") or ""),
                str(asset.get("selector") or ""),
                Path(str(asset.get("file") or "")).name,
            ]
        )
        topic_term_hits, topic_phrase_hits = topic_overlap_score(item, blob)
        specific_term_hits, specific_phrase_hits = topic_specific_overlap_score(item, blob)
        official_match = media_domain_matches(
            item,
            str(asset.get("source_domain") or ""),
            source_domain(str(asset.get("image_url") or "")),
        )
        aligned = (
            official_match
            or specific_phrase_hits > 0
            or specific_term_hits > 0
            or topic_phrase_hits > 0
            or topic_term_hits >= 2
        )
        approved_assets += 1 if aligned else 0
        asset_reviews.append(
            {
                "file": str(asset.get("file") or ""),
                "source_domain": str(asset.get("source_domain") or ""),
                "selector": str(asset.get("selector") or ""),
                "image_url": str(asset.get("image_url") or ""),
                "official_match": official_match,
                "topic_term_hits": topic_term_hits,
                "topic_phrase_hits": topic_phrase_hits,
                "specific_term_hits": specific_term_hits,
                "specific_phrase_hits": specific_phrase_hits,
                "status": "pass" if aligned else "warn",
            }
        )

    if len(selected_assets) < min_required:
        status = "fail"
        summary = f"仅保留 {len(selected_assets)} 张已审配图，低于要求的 {min_required} 张。"
    elif not script_relevant:
        status = "warn"
        summary = "口播与新闻主线存在弱相关，建议继续复核文案。"
    elif approved_assets < min_required:
        status = "warn"
        summary = f"已选配图中仅有 {approved_assets} 张与新闻主线强相关。"
    else:
        status = "pass"
        summary = f"口播主线通过审查，{approved_assets} 张配图与新闻事实保持一致。"

    return {
        "status": status,
        "summary": summary,
        "min_required": min_required,
        "selected_count": len(selected_assets),
        "script_relevant": script_relevant,
        "oral_term_hits": oral_term_hits,
        "oral_phrase_hits": oral_phrase_hits,
        "oral_specific_term_hits": oral_specific_term_hits,
        "oral_specific_phrase_hits": oral_specific_phrase_hits,
        "asset_reviews": asset_reviews,
    }


def seconds_to_frames(seconds: float) -> int:
    return max(1, int(round(seconds * FPS)))


def clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def normalize_spoken_text(text: str) -> str:
    value = EMOJI_RE.sub("", text or "")
    value = DATE_RE.sub(
        lambda match: f"{int(match.group(1))}年{int(match.group(2))}月{int(match.group(3))}日",
        value,
    )
    value = re.sub(r"(?<=[A-Za-z])-(?=[A-Za-z])", " ", value)
    value = re.sub(r"(?<=\d)-(?=\d)", " 到 ", value)
    value = re.sub(r"\s+-\s+", "，", value)
    value = value.replace("—", "，").replace("–", "，")
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value)
    value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[，。！？；：])", "", value)
    value = re.sub(r"(?<=[（【《“])\s+", "", value)
    value = re.sub(r"\s+(?=[）】》”])", "", value)
    return value.strip()


def split_spoken_units(text: str) -> list[str]:
    cleaned = normalize_spoken_text(text)
    if not cleaned:
        return []
    for needle in ("，不再", "，而是", "，而不是", "，重点是", "，核心是", "，核心不是", "，等于", "，相当于"):
        cleaned = cleaned.replace(needle, f"。{needle.lstrip('，')}")
    parts = re.split(r"[。！？；]", cleaned)
    return [part.strip(" ，、") for part in parts if part.strip(" ，、")]


def spokenize_sentence(text: str) -> str:
    value = normalize_spoken_text(text)
    for pattern, replacement in SPOKEN_REPLACEMENTS:
        value = pattern.sub(replacement, value)
    value = re.sub(r"“([^”]{2,8})”", r"\1", value)
    value = re.sub(r"(规划模式)\s*\1", r"\1", value)
    value = re.sub(r"(文档)\s*\1", r"\1", value)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"([，。！？；])\1+", r"\1", value)
    return value.strip(" ，。；")


def audience_friendly_sentence(text: str) -> str:
    value = spokenize_sentence(text)
    for pattern, replacement in PUBLIC_SPOKEN_REPLACEMENTS:
        value = pattern.sub(replacement, value)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\.(?=$|\s)", "。", value)
    value = re.sub(r"(?<=[。！？；])\s+", "", value)
    value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value)
    value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[，。！？；：])", "", value)
    value = re.sub(r"(?<=[（【《“])\s+", "", value)
    value = re.sub(r"\s+(?=[）】》”])", "", value)
    value = re.sub(r"([，。！？；])\1+", r"\1", value)
    return value.strip(" ，。；")


def localize_script_sentence(text: str) -> str:
    raw = normalize_spoken_text(text)
    value = audience_friendly_sentence(raw)
    if not value:
        return ""
    tail = raw.rstrip()[-1:] if raw.rstrip() else ""
    if tail in "！？!?":
        stop = "！" if tail in "！!" else "？"
    elif tail in "。.":
        stop = "。"
    else:
        stop = ""
    if stop and value[-1] not in "。！？!?":
        value += stop
    return value


def audience_friendly_title(text: str) -> str:
    value = spoken_title_summary(text)
    for pattern, replacement in PUBLIC_TITLE_REWRITE_PATTERNS:
        value = pattern.sub(replacement, value)
    value = audience_friendly_sentence(value)
    for pattern, replacement in PUBLIC_TITLE_REWRITE_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def audience_friendly_trend_word(text: str) -> str:
    value = spokenize_sentence(voice_text(text, 18))
    for pattern, replacement in PUBLIC_TREND_REPLACEMENTS:
        value = pattern.sub(replacement, value)
    value = audience_friendly_sentence(value)
    for pattern, replacement in PUBLIC_TREND_REPLACEMENTS:
        value = pattern.sub(replacement, value)
    return value


def daily_keyword_labels(
    selected_items: list[TechDailyItem],
    *,
    report: TechDailyReport,
    title_pack: dict[str, Any] | None = None,
    limit: int = 3,
) -> list[str]:
    labels: list[str] = []
    item_blobs = [
        " ".join([item.title, item.content, item.interpretation, item.quote or "", item.source_url])
        for item in selected_items
    ]
    for pattern, label in DAILY_KEYWORD_TRANSLATIONS:
        if any(pattern.search(blob) for blob in item_blobs):
            labels.append(label)
    for line in (title_pack or {}).get("cover_left") or []:
        labels.append(str(line))
    for line in (title_pack or {}).get("cover_right") or []:
        labels.append(str(line))
    for term in report.trend_words or report.trend_lines:
        labels.append(audience_friendly_trend_word(term))
    cleaned: list[str] = []
    for label in unique(labels):
        value = sanitize_display_title(str(label))
        if value and not re.search(r"真实配图|人的影响|可复核来源", value):
            cleaned.append(value)
    return cleaned[:limit] or ["凭证风险", "安全回归测试", "人才培养链"]


def spoken_aliases_for_text(text: str) -> list[dict[str, str]]:
    aliases: list[dict[str, str]] = []
    for raw_label, pattern, replacement in SPOKEN_ALIAS_RULES:
        if pattern.search(text or "") and all(alias["from"] != raw_label for alias in aliases):
            aliases.append({"from": raw_label, "to": replacement})
    return aliases


def display_title_text(text: str) -> str:
    return sanitize_display_title(audience_friendly_sentence(text))


def spoken_title_summary(title: str) -> str:
    value = spokenize_sentence(voice_text(title, 28))
    value = re.sub(r"^[^A-Za-z0-9\u4e00-\u9fff]+", "", value)
    for pattern, replacement in TITLE_REWRITE_PATTERNS:
        value = pattern.sub(replacement, value)
    return value.strip(" ，。；")


def voice_text(text: str, limit: int) -> str:
    value = shorten_text(text, limit)
    value = re.sub(r"\s*状态：\s*\[[^\]]+\]\s*$", "", value)
    value = normalize_spoken_text(value)
    return value.strip(" 。；，、!?！？")


def ensure_spoken_stop(text: str) -> str:
    value = normalize_spoken_text(text).strip()
    if not value:
        return ""
    if value[-1] not in "。！？!?":
        value += "。"
    return value


def join_display_sentences(parts: Iterable[str]) -> str:
    cleaned: list[str] = []
    for part in parts:
        value = audience_friendly_sentence(str(part or "")).strip(" \n\r\t。！？!?；;，,")
        if value:
            cleaned.append(value)
    return f"{'。'.join(cleaned)}。" if cleaned else ""


def display_sentence_chunks(text: str, *, max_items: int | None = None) -> list[str]:
    chunks: list[str] = []
    for raw in re.split(r"(?<=[。！？!?；;])", normalize_spoken_text(text or "")):
        value = localize_script_sentence(raw).strip()
        if value:
            chunks.append(value)
        if max_items and len(chunks) >= max_items:
            break
    return chunks


def visual_summary_chunks(chunks: list[str]) -> list[str]:
    skipped_markers = (
        "标题就叫",
        "标题是",
        "发布了一篇文章",
        "发了一篇文章",
        "刊出一篇",
        "来源页标题",
    )
    cleaned_chunks: list[str] = []
    for chunk in chunks:
        cleaned = re.sub(r"^[\s》）】」』\"'“”‘’。！？!?；;，,、:：]+", "", str(chunk or "")).strip()
        if cleaned:
            cleaned_chunks.append(cleaned)
    filtered = [chunk for chunk in cleaned_chunks if not any(marker in chunk for marker in skipped_markers)]
    return filtered or chunks


def clamp_visual_summary(text: str, limit: int) -> str:
    cleaned = str(text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    clipped = cleaned[:limit].rstrip(" ，,；;：:、。")
    return f"{clipped}。" if clipped else cleaned[:limit]


def two_line_visual_explanation_from_oral(item: TechDailyItem, oral: dict[str, Any]) -> str:
    chunks = display_sentence_chunks(str(oral.get("oral_script") or ""), max_items=9)
    if not chunks:
        chunks = display_sentence_chunks(join_display_sentences([oral.get("takeaway", ""), item.interpretation, oral.get("hook", "")]), max_items=4)
    if not chunks:
        return shorten_text(join_display_sentences([item.interpretation, item.content]), 170)

    chunks = visual_summary_chunks(chunks)
    first = chunks[0]
    impact = next(
        (
            chunk
            for chunk in reversed(chunks[1:])
            if any(
                marker in chunk
                for marker in (
                    "对",
                    "来说",
                    "影响",
                    "意味着",
                    "会让",
                    "会把",
                    "需要",
                    "接下来",
                    "所以",
                    "提醒",
                    "成本",
                    "信任",
                )
            )
        ),
        "",
    )
    selected = unique([first, impact or (chunks[1] if len(chunks) > 1 else "")])
    if len("".join(selected)) < 72 and len(chunks) > 2:
        selected = unique([*selected, chunks[2]])
    text = "".join(selected)
    limit = 58
    if len(text) <= limit:
        return text
    compact_chunks = display_sentence_chunks(text)
    kept: list[str] = []
    total = 0
    for chunk in compact_chunks:
        if kept and total + len(chunk) > limit:
            break
        if not kept and len(chunk) > limit:
            return clamp_visual_summary(chunk, limit)
        kept.append(chunk)
        total += len(chunk)
    return "".join(kept).strip() or clamp_visual_summary(text, limit)


def compact_source_note(item: TechDailyItem) -> str:
    note_bits = [source_domain(item.source_url) or "原始信源"]
    if item.status:
        cleaned_status = voice_text(str(item.status), 20)
        if cleaned_status:
            note_bits.append(cleaned_status)
    joined = "，".join(bit for bit in note_bits if bit)
    return spokenize_sentence(joined)


def compact_spoken_bits(parts: list[str], *, limit: int = 2, max_chars: int = 26) -> list[str]:
    compacted: list[str] = []
    for part in parts:
        cleaned = spokenize_sentence(voice_text(part, max_chars))
        if not cleaned:
            continue
        if all(cleaned != existing for existing in compacted):
            compacted.append(cleaned)
        if len(compacted) >= limit:
            break
    return compacted


def friendly_date(date_text: str) -> str:
    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_text.strip())
    if not match:
        return date_text
    return f"{int(match.group(2))}月{int(match.group(3))}日"


def distilled_memory_line(*candidates: str, max_chars: int = 20) -> str:
    for candidate in candidates:
        cleaned = spokenize_sentence(voice_text(candidate, max_chars))
        if cleaned:
            return cleaned
    return ""


def _required_bundle_text(payload: dict[str, Any], key: str, path: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise RuntimeError(f"Content manifest missing {path}.{key}")
    return value


def _bundle_aliases(raw: dict[str, Any], text: str) -> list[str]:
    aliases = [str(alias).strip() for alias in raw.get("spoken_aliases") or [] if str(alias).strip()]
    return aliases or spoken_aliases_for_text(text)


def _bundle_tts_script(raw: dict[str, Any], oral_script: str) -> str:
    value = str(raw.get("tts_script") or raw.get("tts_text") or "").strip()
    return normalize_spoken_text(value) if value else oral_script


def _normalize_sentence_pairs(raw: dict[str, Any], *, context: str) -> list[dict[str, Any]]:
    pairs = raw.get("sentence_pairs")
    if not isinstance(pairs, list):
        raise RuntimeError(f"Content manifest missing {context}.sentence_pairs")
    normalized: list[dict[str, Any]] = []
    for offset, pair in enumerate(pairs, start=1):
        if not isinstance(pair, dict):
            raise RuntimeError(f"{context}.sentence_pairs[{offset}] must be an object")
        sentence_id = str(pair.get("sentence_id") or f"s{offset:02d}").strip()
        oral = localize_script_sentence(str(pair.get("oral") or ""))
        subtitle = localize_script_sentence(str(pair.get("subtitle") or ""))
        tags_raw = pair.get("tts_tags")
        tts_tags = [str(tag).strip().strip("[]") for tag in tags_raw if str(tag).strip()] if isinstance(tags_raw, list) else []
        emotion_hint = str(pair.get("emotion_hint") or "").strip()
        if not oral or not subtitle:
            raise RuntimeError(f"{context}.sentence_pairs[{offset}] requires oral and subtitle")
        normalized.append(
            {
                "sentence_id": sentence_id,
                "oral": oral,
                "subtitle": subtitle,
                "tts_tags": tts_tags,
                "emotion_hint": emotion_hint,
            }
        )
    if not normalized:
        raise RuntimeError(f"{context}.sentence_pairs is empty")
    return normalized


def _scripts_from_sentence_pairs(pairs: list[dict[str, Any]]) -> tuple[str, str, str]:
    oral_script = "".join(pair["oral"] for pair in pairs)
    subtitle_script = "".join(pair["subtitle"] for pair in pairs)
    tts_chunks: list[str] = []
    for pair in pairs:
        tags = "".join(f"[{tag}]" for tag in pair.get("tts_tags") or [] if str(tag).strip())
        tts_chunks.append(f"{tags}{pair['oral']}")
    return oral_script, subtitle_script, "".join(tts_chunks)


def _normalize_card_points(card: dict[str, Any]) -> list[str]:
    raw_points = card.get("points")
    points: list[str] = []
    if isinstance(raw_points, list):
        points = [str(point).strip() for point in raw_points if str(point).strip()]
    if len(points) < 2:
        body = str(card.get("body") or "").strip()
        points = [
            part.strip(" ：:、,")
            for part in re.split(r"[；;]\s*", body)
            if part.strip(" ：:、,")
        ]
    return points[:3]


def _normalize_screen_cards(raw: dict[str, Any], item: TechDailyItem) -> list[dict[str, Any]]:
    cards = raw.get("screen_cards")
    if not isinstance(cards, list):
        raise RuntimeError(f"Content manifest missing video_script.items[{item.index}].screen_cards")
    normalized: list[dict[str, Any]] = []
    for offset, card in enumerate(cards, start=1):
        if not isinstance(card, dict):
            raise RuntimeError(f"screen_cards[{offset}] for item {item.index} must be an object")
        heading = audience_friendly_sentence(str(card.get("heading") or ""))
        body = audience_friendly_sentence(str(card.get("body") or ""))
        icon_hint = str(card.get("icon_hint") or "").strip()
        emphasis = audience_friendly_sentence(str(card.get("emphasis") or ""))
        points = [audience_friendly_sentence(point) for point in _normalize_card_points(card)]
        points = [point for point in points if point]
        if not heading or not body or not icon_hint or not emphasis:
            raise RuntimeError(
                f"screen_cards[{offset}] for item {item.index} requires heading, body, icon_hint and emphasis"
            )
        if offset == 1 and len(points) < 2:
            raise RuntimeError(f"screen_cards[1] for item {item.index} must include 2-3 concrete fact points")
        if offset > 1 and not points:
            points = [body]
        normalized.append(
            {
                "heading": heading,
                "body": body,
                "points": points,
                "icon_hint": icon_hint,
                "emphasis": emphasis,
            }
        )
    if len(normalized) != 3:
        raise RuntimeError(f"video_script.items[{item.index}].screen_cards must contain exactly 3 cards")
    return normalized


def _normalize_intro_oral(raw: dict[str, Any]) -> dict[str, Any]:
    sentence_pairs = _normalize_sentence_pairs(raw, context="video_script.intro")
    oral_script, subtitle_script, tts_script = _scripts_from_sentence_pairs(sentence_pairs)
    return {
        "opening": str(raw.get("opening") or "").strip(),
        "agenda": str(raw.get("agenda") or "").strip(),
        "transition": str(raw.get("transition") or "").strip(),
        "oral_script": oral_script,
        "tts_script": tts_script or _bundle_tts_script(raw, oral_script),
        "subtitle_script": subtitle_script,
        "sentence_pairs": sentence_pairs,
        "spoken_title": _required_bundle_text(raw, "spoken_title", "video_script.intro"),
        "spoken_aliases": _bundle_aliases(raw, oral_script),
        "display_title": _required_bundle_text(raw, "display_title", "video_script.intro"),
        "style_variant": str(raw.get("style_variant") or SCENE_STYLE_VARIANTS["intro"]),
        "tts_style_tags": str(raw.get("tts_style_tags") or "").strip(),
    }


def _normalize_item_oral(raw: dict[str, Any], item: TechDailyItem) -> dict[str, Any]:
    context = f"video_script.items[{item.index}]"
    sentence_pairs = _normalize_sentence_pairs(raw, context=context)
    oral_script, subtitle_script, tts_script = _scripts_from_sentence_pairs(sentence_pairs)
    screen_cards = _normalize_screen_cards(raw, item)
    return {
        "hook": str(raw.get("hook") or "").strip(),
        "takeaway": str(raw.get("takeaway") or "").strip(),
        "fact_points": [str(point).strip() for point in raw.get("fact_points") or [] if str(point).strip()],
        "source_note": str(raw.get("source_note") or "").strip(),
        "outro": str(raw.get("outro") or "").strip(),
        "decision_impact": str(
            raw.get("decision_impact")
            or raw.get("takeaway")
            or raw.get("outro")
            or ""
        ).strip(),
        "oral_script": oral_script,
        "tts_script": tts_script or _bundle_tts_script(raw, oral_script),
        "subtitle_script": subtitle_script,
        "sentence_pairs": sentence_pairs,
        "spoken_title": _required_bundle_text(raw, "spoken_title", f"video_script.items[{item.index}]"),
        "spoken_aliases": _bundle_aliases(raw, " ".join([item.title, oral_script])),
        "display_title": _required_bundle_text(raw, "display_title", f"video_script.items[{item.index}]"),
        "screen_cards": screen_cards,
        "media_summary": str(raw.get("media_summary") or "").strip(),
        "nav_label": str(raw.get("nav_label") or "").strip(),
        "style_variant": str(raw.get("style_variant") or ""),
        "tts_style_tags": str(raw.get("tts_style_tags") or "").strip(),
    }


def _normalize_outro_oral(raw: dict[str, Any]) -> dict[str, Any]:
    sentence_pairs = _normalize_sentence_pairs(raw, context="video_script.outro")
    oral_script, subtitle_script, tts_script = _scripts_from_sentence_pairs(sentence_pairs)
    return {
        "oral_script": oral_script,
        "tts_script": tts_script or _bundle_tts_script(raw, oral_script),
        "subtitle_script": subtitle_script,
        "sentence_pairs": sentence_pairs,
        "display_title": str(raw.get("display_title") or "").strip(),
        "spoken_title": str(raw.get("spoken_title") or "").strip(),
        "spoken_aliases": _bundle_aliases(raw, oral_script),
        "style_variant": str(raw.get("style_variant") or SCENE_STYLE_VARIANTS["outro"]),
        "tts_style_tags": str(raw.get("tts_style_tags") or "").strip(),
        "line_one": str(raw.get("line_one") or "").strip(),
        "line_two": str(raw.get("line_two") or "").strip(),
        "quote_id": str(raw.get("quote_id") or "").strip(),
        "quote_text": str(raw.get("quote_text") or "").strip(),
        "quote_translation": str(raw.get("quote_translation") or "").strip(),
        "quote_author": str(raw.get("quote_author") or "").strip(),
    }


def load_bundle_orals(bundle: dict[str, Any], selected_items: list[TechDailyItem]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    video_script = bundle.get("video_script") if isinstance(bundle.get("video_script"), dict) else {}
    intro_raw = video_script.get("intro") if isinstance(video_script.get("intro"), dict) else {}
    item_raws = video_script.get("items") if isinstance(video_script.get("items"), list) else []
    outro_raw = video_script.get("outro") if isinstance(video_script.get("outro"), dict) else {}
    raw_by_index = {
        int(raw.get("index")): raw
        for raw in item_raws
        if isinstance(raw, dict) and str(raw.get("index") or "").isdigit()
    }
    intro_oral = _normalize_intro_oral(intro_raw)
    item_orals = []
    for item in selected_items:
        raw = raw_by_index.get(item.index)
        if raw is None:
            raise RuntimeError(f"Content manifest missing video_script item {item.index}")
        item_orals.append(_normalize_item_oral(raw, item))
    outro_oral = _normalize_outro_oral(outro_raw)
    return intro_oral, item_orals, outro_oral


def say_to_audio(text: str, voice: str, rate: int, out_path: Path) -> None:
    ensure_dir(out_path.parent)
    aiff_path = out_path.with_suffix(".aiff")
    subprocess.run(
        ["say", "-v", voice, "-r", str(rate), "-o", str(aiff_path), text],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(aiff_path),
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "aac",
            str(out_path),
        ],
        check=True,
    )
    aiff_path.unlink(missing_ok=True)


def fish_tts_to_audio(
    *,
    endpoint: str,
    texts: list[str],
    reference_id: str,
    out_path: Path,
    response_format: str,
    use_memory_cache: str,
    timeout: int,
) -> None:
    ensure_dir(out_path.parent)
    tts_texts = [text.strip() for text in texts if text and text.strip()]
    if not tts_texts:
        raise RuntimeError("remote TTS received no text")

    chunk_dir = out_path.parent / f".{out_path.stem}-fish"
    reset_generated_dir(chunk_dir)
    raw_paths: list[Path] = []
    try:
        for index, text in enumerate(tts_texts, start=1):
            raw_path = chunk_dir / f"{index:02d}.{response_format}"
            headers_path = raw_path.with_suffix(f"{raw_path.suffix}.headers.txt")
            payload = json.dumps(
                {
                    "text": text,
                    "reference_id": reference_id,
                    "format": response_format,
                    "use_memory_cache": use_memory_cache,
                },
                ensure_ascii=False,
            ).encode("utf-8")
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
                str(raw_path),
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
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                    raw_path.unlink(missing_ok=True)
                    headers_path.unlink(missing_ok=True)
                    if attempt >= max(1, retries):
                        raise
                    print(
                        f"[tts] Fish Speech curl attempt {attempt}/{retries} failed; retrying: {exc}",
                        file=sys.stderr,
                    )
                    time.sleep(min(2 * attempt, 6))
            body = raw_path.read_bytes() if raw_path.exists() else b""
            content_type = ""
            if headers_path.exists():
                for line in headers_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.lower().startswith("content-type:"):
                        content_type = line.split(":", 1)[1].strip()
                        break
            headers_path.unlink(missing_ok=True)
            if not body:
                raise RuntimeError("remote TTS returned an empty body")
            if response_format.lower() == "wav" and not body.startswith(b"RIFF"):
                preview = body[:200].decode("utf-8", "replace")
                raise RuntimeError(f"remote TTS did not return WAV audio: {content_type} {preview}")
            raw_paths.append(raw_path)

        input_paths: list[Path] = []
        silence_path: Path | None = None
        if len(raw_paths) > 1:
            silence_path = chunk_dir / f"gap.{response_format}"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=channel_layout=mono:sample_rate=48000",
                    "-t",
                    "0.14",
                    str(silence_path),
                ],
                check=True,
            )
        for index, raw_path in enumerate(raw_paths):
            input_paths.append(raw_path)
            if silence_path and index < len(raw_paths) - 1:
                input_paths.append(silence_path)

        ffmpeg_cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        for input_path in input_paths:
            ffmpeg_cmd.extend(["-i", str(input_path)])
        filter_parts: list[str] = []
        labels: list[str] = []
        for index in range(len(input_paths)):
            filter_parts.append(
                f"[{index}:a]aresample=48000,aformat=sample_fmts=s16:channel_layouts=mono[a{index}]"
            )
            labels.append(f"[a{index}]")
        filter_parts.append(f"{''.join(labels)}concat=n={len(input_paths)}:v=0:a=1[out]")
        ffmpeg_cmd.extend(
            [
                "-filter_complex",
                ";".join(filter_parts),
                "-map",
                "[out]",
                "-c:a",
                "aac",
                str(out_path),
            ]
        )
        subprocess.run(ffmpeg_cmd, check=True)
    finally:
        if chunk_dir.exists():
            shutil.rmtree(chunk_dir, ignore_errors=True)


def synthesize_audio(
    *,
    text: str,
    voice: str,
    rate: int,
    out_path: Path,
    tts_endpoint: str | None,
    tts_reference_id: str | None,
    tts_format: str,
    tts_use_memory_cache: str,
    tts_timeout: int,
    tts_style_preset: str,
    tts_style_tags: str | None,
    tts_state: dict[str, Any] | None = None,
) -> dict[str, object]:
    has_inline_tts_tags = bool(TTS_TAG_RE.search(text or ""))
    remote_allowed = bool(
        text
        and tts_endpoint
        and tts_reference_id
        and not (tts_state or {}).get("remote_disabled", False)
    )
    if remote_allowed:
        preflight_checked = bool((tts_state or {}).get("remote_preflight_checked"))
        if not preflight_checked:
            reachable, detail = remote_tts_preflight(str(tts_endpoint or ""), TTS_PREFLIGHT_TIMEOUT)
            if tts_state is not None:
                tts_state["remote_preflight_checked"] = True
                tts_state["remote_preflight_ok"] = reachable
                tts_state["remote_preflight_detail"] = detail
            if not reachable:
                if tts_state is not None:
                    tts_state["remote_disabled"] = True
                    tts_state["last_remote_error"] = f"preflight: {detail}"
                print(f"[tts] Fish Speech preflight failed, skipping remote TTS: {detail}", file=sys.stderr)
                remote_allowed = False
    if remote_allowed:
        text_chunks = split_remote_tts_chunks(text)
        tts_chunks = [
            compose_fish_tts_text(
                chunk,
                tts_style_preset,
                tts_style_tags,
                add_prefix=not has_inline_tts_tags,
            )
            for chunk in (text_chunks or [text])
            if chunk.strip()
        ]
        tts_text = "\n".join(tts_chunks)
        try:
            fish_tts_to_audio(
                endpoint=tts_endpoint,
                texts=tts_chunks,
                reference_id=tts_reference_id,
                out_path=out_path,
                response_format=tts_format,
                use_memory_cache=tts_use_memory_cache,
                timeout=tts_timeout,
            )
            return {
                "provider": "fish-speech",
                "voice": tts_reference_id,
                "tts_text": tts_text,
                "tts_style_preset": tts_style_preset,
                "tts_style_tags": tts_style_tags,
                "remote_tts_requested": True,
                "remote_tts_skipped": False,
            }
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            RuntimeError,
            ConnectionError,
        ) as exc:
            if tts_state is not None:
                tts_state["remote_disabled"] = True
                tts_state["last_remote_error"] = str(exc)
            print(f"[tts] Fish Speech failed, falling back to say: {exc}", file=sys.stderr)
    if text:
        say_to_audio(strip_tts_tags(text) if has_inline_tts_tags else text, voice, rate, out_path)
    else:
        ensure_dir(out_path.parent)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=mono:sample_rate=48000",
                "-t",
                "0.1",
                "-c:a",
                "aac",
                str(out_path),
            ],
            check=True,
        )
    return {
        "provider": "macos-say" if text else "silence",
        "voice": voice if text else "none",
        "tts_text": text,
        "tts_style_preset": tts_style_preset,
        "tts_style_tags": tts_style_tags,
        "remote_tts_requested": bool(tts_endpoint and tts_reference_id and text),
        "remote_tts_skipped": bool(tts_endpoint and tts_reference_id and text),
    }


def audio_duration(path: Path, *, context: dict[str, Any] | None = None) -> float:
    completed = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    raw_value = completed.stdout.strip()
    try:
        return float(raw_value)
    except ValueError as exc:
        detail = {
            "audio_file": str(path),
            "ffprobe_stdout": raw_value,
            "ffprobe_stderr": (completed.stderr or "").strip()[:800],
        }
        if context:
            detail.update(context)
        raise RuntimeError(f"Could not read audio duration: {json.dumps(detail, ensure_ascii=False)}") from exc


def probe_fish_audio(
    *,
    endpoint: str | None,
    reference_id: str | None,
    response_format: str,
    use_memory_cache: str,
    timeout: int,
    audio_dir: Path,
    tts_state: dict[str, Any],
) -> None:
    if not endpoint or not reference_id:
        raise RuntimeError("Fish Speech was required, but endpoint or reference id is missing.")
    reachable, detail = remote_tts_preflight(str(endpoint), TTS_PREFLIGHT_TIMEOUT)
    tts_state["remote_preflight_checked"] = True
    tts_state["remote_preflight_ok"] = reachable
    tts_state["remote_preflight_detail"] = detail
    if not reachable:
        tts_state["remote_disabled"] = True
        tts_state["last_remote_error"] = f"preflight: {detail}"
        raise RuntimeError(f"Fish Speech socket preflight failed: {detail}")
    probe_path = audio_dir / "00-fish-preflight.m4a"
    try:
        fish_tts_to_audio(
            endpoint=endpoint,
            texts=["日报预飞检查，确认今天的真实配音链路可用。"],
            reference_id=reference_id,
            out_path=probe_path,
            response_format=response_format,
            use_memory_cache=use_memory_cache,
            timeout=timeout,
        )
        duration = audio_duration(
            probe_path,
            context={
                "provider": "fish-speech",
                "endpoint": endpoint,
                "reference_id": reference_id,
                "probe": True,
            },
        )
        if duration <= 0:
            raise RuntimeError(f"Fish Speech probe duration is not positive: {duration}")
        tts_state["remote_audio_probe_ok"] = True
        tts_state["remote_audio_probe_duration"] = duration
    except Exception as exc:  # noqa: BLE001
        tts_state["remote_disabled"] = True
        tts_state["last_remote_error"] = str(exc)
        raise RuntimeError(f"Fish Speech audio probe failed: {exc}") from exc
    finally:
        probe_path.unlink(missing_ok=True)


def normalize_word_text(text: str) -> str:
    value = text.strip()
    value = value.replace("\u3000", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def script_tokens(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned:
        return []
    pattern = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*|[\u4e00-\u9fff]|[，。！？；：、“”‘’（）()《》【】—…,.!?;:\-]")
    tokens = pattern.findall(cleaned)
    return [token for token in tokens if token.strip()]


def subtitle_tokens(text: str) -> list[str]:
    tokens = script_tokens(text)
    if not tokens:
        return []

    merged: list[str] = []
    pending_prefix = ""
    for token in tokens:
        if PUNCTUATION_RE.fullmatch(token):
            if token in OPENING_PUNCTUATION:
                pending_prefix += token
            elif merged:
                merged[-1] = f"{merged[-1]}{token}"
            else:
                pending_prefix += token
            continue
        merged.append(f"{pending_prefix}{token}")
        pending_prefix = ""
    if pending_prefix and merged:
        merged[-1] = f"{merged[-1]}{pending_prefix}"
    return merge_atomic_subtitle_tokens([token for token in merged if token.strip()])


def _subtitle_token_core(token: str) -> str:
    return re.sub(r"^[，。！？；：、“”‘’（）()《》【】—…,.!?;:\-]+|[，。！？；：、“”‘’（）()《》【】—…,.!?;:\-]+$", "", token)


def merge_atomic_subtitle_tokens(tokens: list[str]) -> list[str]:
    merged: list[str] = []
    index = 0
    while index < len(tokens):
        current = tokens[index]
        current_core = _subtitle_token_core(current)
        if (
            index + 3 < len(tokens)
            and re.fullmatch(r"\d{1,2}", current_core)
            and _subtitle_token_core(tokens[index + 1]) == "月"
            and re.fullmatch(r"\d{1,2}", _subtitle_token_core(tokens[index + 2]))
            and _subtitle_token_core(tokens[index + 3]).startswith("日")
        ):
            merged.append(f"{current}{tokens[index + 1]}{tokens[index + 2]}{tokens[index + 3]}")
            index += 4
            continue
        if (
            index + 1 < len(tokens)
            and re.fullmatch(r"\d+(?:\.\d+)?", current_core)
            and _subtitle_token_core(tokens[index + 1]) in {"次", "倍"}
        ):
            merged.append(f"{current}{tokens[index + 1]}")
            index += 2
            continue
        merged.append(current)
        index += 1
    return merged


def subtitle_token_weight(token: str) -> float:
    clean = _subtitle_token_core(token)
    if not clean:
        return 0.8
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ ]*", clean):
        return max(1.8, len(clean.replace(" ", "")) * 0.9)
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", clean))
    if cjk_count:
        return max(1.0, cjk_count * 1.05)
    return max(1.0, len(clean) * 0.8)


def subtitle_phrase_tokens(text: str) -> list[str]:
    tokens = subtitle_tokens(text)
    if not tokens:
        return []

    grouped: list[str] = []
    for token in tokens:
        clean = _subtitle_token_core(token)
        if not grouped:
            grouped.append(token)
            continue

        previous = grouped[-1]
        previous_clean = _subtitle_token_core(previous)
        previous_has_punctuation = previous != previous_clean
        previous_is_ascii = bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ ]*", previous_clean))
        current_is_ascii = bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ ]*", clean))
        previous_is_cjk = bool(re.fullmatch(r"[\u4e00-\u9fff]+", previous_clean))
        current_is_cjk = bool(re.fullmatch(r"[\u4e00-\u9fff]+", clean))

        if previous_is_ascii and current_is_ascii and not previous_has_punctuation:
            grouped[-1] = f"{previous} {token}"
            continue
        if previous_is_cjk and current_is_cjk and not previous_has_punctuation:
            grouped[-1] = f"{previous}{token}"
            continue
        grouped.append(token)
    return grouped


def subtitle_visual_units(text: str) -> float:
    units = 0.0
    for char in text:
        if re.fullmatch(r"[\u4e00-\u9fff]", char):
            units += 1.0
        elif re.fullmatch(r"[A-Za-z0-9]", char):
            units += 0.56
        elif char.isspace():
            units += 0.24
        elif re.fullmatch(r"[，。！？；：、“”‘’（）()《》【】—…,.!?;:\-+/]", char):
            units += 0.42
        else:
            units += 0.72
    return units


def estimated_words_from_script(text: str, audio_frames: int) -> list[dict[str, Any]]:
    tokens = subtitle_tokens(text)
    if not tokens or audio_frames <= 1:
        return []
    weights = [subtitle_token_weight(token) for token in tokens]
    total_weight = sum(weights) or float(len(tokens))
    cursor = 0.0
    words: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        start = int(round(cursor))
        span = max(1, int(round(audio_frames * weights[index] / total_weight)))
        if index == len(tokens) - 1:
            end = audio_frames
        else:
            end = min(audio_frames, max(start + 1, start + span))
        words.append(
            {
                "text": token,
                "start_frame": start,
                "end_frame": end,
            }
        )
        cursor = end
    return words


def expand_alignment_spans(aligned_words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for word in aligned_words:
        raw = normalize_word_text(str(word.get("text") or ""))
        start_frame = int(word["start_frame"])
        end_frame = int(word["end_frame"])
        duration = max(1, end_frame - start_frame)
        if re.fullmatch(r"[\u4e00-\u9fff]{2,}", raw):
            split_count = min(len(raw), max(1, duration // 8))
        else:
            split_count = 1
        for index in range(split_count):
            part_start = start_frame + int(round(duration * index / split_count))
            part_end = start_frame + int(round(duration * (index + 1) / split_count))
            spans.append(
                {
                    "start_frame": part_start,
                    "end_frame": max(part_start + 1, part_end),
                }
            )
    return spans


def split_span(span: dict[str, Any]) -> list[dict[str, Any]]:
    start_frame = int(span["start_frame"])
    end_frame = int(span["end_frame"])
    duration = max(1, end_frame - start_frame)
    midpoint = start_frame + max(1, duration // 2)
    return [
        {
            "start_frame": start_frame,
            "end_frame": max(start_frame + 1, midpoint),
        },
        {
            "start_frame": max(start_frame + 1, midpoint),
            "end_frame": end_frame,
        },
    ]


def expand_spans_to_target(spans: list[dict[str, Any]], target_count: int) -> list[dict[str, Any]]:
    expanded = list(spans)
    while len(expanded) < target_count:
        index = max(
            range(len(expanded)),
            key=lambda candidate: expanded[candidate]["end_frame"] - expanded[candidate]["start_frame"],
            default=-1,
        )
        if index < 0:
            break
        duration = expanded[index]["end_frame"] - expanded[index]["start_frame"]
        if duration < 4:
            break
        expanded[index : index + 1] = split_span(expanded[index])
    return expanded


def split_alignment_groups(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not words:
        return []
    groups: list[list[dict[str, Any]]] = [[words[0]]]
    for word in words[1:]:
        if word["start_frame"] - groups[-1][-1]["end_frame"] > int(0.35 * FPS):
            groups.append([word])
        else:
            groups[-1].append(word)
    return groups


def weighted_token_spans(tokens: list[str], start_frame: int, end_frame: int) -> list[dict[str, Any]]:
    duration = max(1, end_frame - start_frame)
    if not tokens:
        return []
    weights = []
    for token in tokens:
        if re.fullmatch(r"[，。！？；：、“”‘’（）()《》—…,.!?;:]", token):
            weights.append(0.6)
        elif re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", token):
            weights.append(max(1.4, len(token) * 0.7))
        else:
            weights.append(1.0)
    total_weight = sum(weights) or float(len(tokens))
    cursor = float(start_frame)
    words: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        token_start = int(round(cursor))
        span = max(1, int(round(duration * weights[index] / total_weight)))
        token_end = end_frame if index == len(tokens) - 1 else min(end_frame, max(token_start + 1, token_start + span))
        words.append({"text": token, "start_frame": token_start, "end_frame": token_end})
        cursor = token_end
    return words


def timed_script_words(
    text: str,
    audio_frames: int,
    aligned_words: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    tokens = subtitle_tokens(text)
    if not tokens:
        return []
    if not aligned_words:
        return estimated_words_from_script(text, audio_frames)

    spans = expand_alignment_spans(aligned_words)
    if not spans:
        return estimated_words_from_script(text, audio_frames)

    spans = expand_spans_to_target(spans, len(tokens))
    if len(spans) < len(tokens):
        return estimated_words_from_script(text, audio_frames)

    span_durations = [max(1, span["end_frame"] - span["start_frame"]) for span in spans]
    total_duration = sum(span_durations) or len(tokens)
    weights = [subtitle_token_weight(token) for token in tokens]
    remaining_duration = total_duration
    remaining_weight = sum(weights) or float(len(tokens))
    cursor = 0
    retimed: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        remaining_tokens = len(tokens) - index
        remaining_spans = len(spans) - cursor
        if remaining_spans <= 0:
            break
        if index == len(tokens) - 1:
            token_spans = spans[cursor:]
            cursor = len(spans)
        else:
            target_duration = max(1.0, remaining_duration * weights[index] / max(remaining_weight, 1.0))
            span_start = cursor
            accumulated = 0
            max_cursor = len(spans) - (remaining_tokens - 1)
            while cursor < max_cursor:
                span_duration = max(1, spans[cursor]["end_frame"] - spans[cursor]["start_frame"])
                if accumulated > 0 and accumulated + span_duration > target_duration * 1.18:
                    break
                accumulated += span_duration
                cursor += 1
                if accumulated >= target_duration:
                    break
            if cursor == span_start:
                cursor += 1
            token_spans = spans[span_start:cursor]
            remaining_duration -= sum(
                max(1, span["end_frame"] - span["start_frame"]) for span in token_spans
            )
            remaining_weight -= weights[index]
        retimed.append(
            {
                "text": token,
                "start_frame": int(token_spans[0]["start_frame"]),
                "end_frame": max(int(token_spans[0]["start_frame"]) + 1, int(token_spans[-1]["end_frame"])),
            }
        )
    return retimed if retimed else estimated_words_from_script(text, audio_frames)


def get_whisper_model(model_name: str) -> Any:
    if model_name not in _WHISPER_MODEL_CACHE:
        module = ensure_faster_whisper_module()
        if module is None:
            raise RuntimeError("faster-whisper unavailable")
        whisper_model = module.WhisperModel(model_name, device="cpu", compute_type="int8")
        _WHISPER_MODEL_CACHE[model_name] = whisper_model
    return _WHISPER_MODEL_CACHE[model_name]


def transcribe_words(audio_path: Path, model_name: str) -> list[dict[str, Any]]:
    model = get_whisper_model(model_name)
    segments, _ = model.transcribe(
        str(audio_path),
        language="zh",
        word_timestamps=True,
    )
    words: list[dict[str, Any]] = []
    for segment in segments:
        for word in getattr(segment, "words", []) or []:
            raw = normalize_word_text(word.word or "")
            if not raw:
                continue
            start_frame = max(0, int(math.floor(float(word.start) * FPS)))
            end_frame = max(start_frame + 1, int(math.ceil(float(word.end) * FPS)))
            words.append(
                {
                    "text": raw,
                    "start_frame": start_frame,
                    "end_frame": end_frame,
                }
            )
    return words


def sentence_chunks(text: str) -> list[str]:
    if not text.strip():
        return []
    parts = re.split(r"(?<=[。！？!?；;])", text.replace("\n", ""))
    chunks = [chunk.strip() for chunk in parts if chunk and chunk.strip()]
    return chunks or [text.strip()]


def subtitle_sentence_chunks(
    text: str,
    *,
    max_weight: float = SUBTITLE_MAX_WEIGHT,
    max_visual_units: float = SUBTITLE_MAX_VISUAL_UNITS,
    max_raw_chars: int = SUBTITLE_MAX_RAW_CHARS,
) -> list[str]:
    compact = normalize_spoken_text(text).replace("\n", " ")
    if not compact.strip():
        return []

    def append_token(rendered: str, token: str) -> str:
        if not rendered:
            return token
        if re.search(r"[A-Za-z0-9]$", rendered) and re.match(r"[A-Za-z0-9]", token):
            return f"{rendered} {token}"
        return f"{rendered}{token}"

    sentences = re.split(r"(?<=[。！？!?；;])", compact)
    cues: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        tokens = subtitle_phrase_tokens(sentence)
        if not tokens:
            continue
        current_tokens: list[str] = []
        current_weight = 0.0
        for token in tokens:
            token_weight = subtitle_token_weight(token)
            candidate_tokens = [*current_tokens, token]
            rendered_candidate = candidate_tokens[0]
            for tail_token in candidate_tokens[1:]:
                rendered_candidate = append_token(rendered_candidate, tail_token)
            candidate_chars = len(rendered_candidate.replace(" ", ""))
            candidate_visual_units = subtitle_visual_units(rendered_candidate)
            if current_tokens and (
                current_weight + token_weight > max_weight
                or candidate_chars > max_raw_chars
                or candidate_visual_units > max_visual_units
            ):
                rendered = current_tokens[0]
                for tail_token in current_tokens[1:]:
                    rendered = append_token(rendered, tail_token)
                cues.append(rendered)
                current_tokens = [token]
                current_weight = token_weight
                continue
            current_tokens.append(token)
            current_weight += token_weight
        if current_tokens:
            rendered = current_tokens[0]
            for tail_token in current_tokens[1:]:
                rendered = append_token(rendered, tail_token)
            cues.append(rendered)

    merged: list[str] = []
    for cue in cues:
        cleaned = cue.strip()
        if not cleaned:
            continue
        if PUNCTUATION_RE.fullmatch(cleaned):
            continue
        if cleaned:
            if (
                merged
                and re.search(r"[A-Za-z0-9][A-Za-z0-9+._-]*$", merged[-1])
                and re.match(r"^[A-Za-z0-9][A-Za-z0-9+._-]*", cleaned)
            ):
                candidate = f"{merged[-1]} {cleaned}"
                candidate_chars = len(candidate.replace(" ", ""))
                if (
                    subtitle_token_weight(candidate) <= max_weight * 1.22
                    and candidate_chars <= max_raw_chars
                    and subtitle_visual_units(candidate) <= max_visual_units
                ):
                    merged[-1] = candidate
                    continue
            merged.append(cleaned)
    return merged


def build_subtitle_cues(
    text: str,
    *,
    scene_start: int,
    audio_offset_frames: int,
    audio_frames: int,
    timed_words: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    chunks = subtitle_sentence_chunks(text)
    if not chunks or audio_frames <= 0:
        return []

    absolute_start = scene_start + audio_offset_frames
    absolute_end = absolute_start + audio_frames
    if timed_words:
        all_tokens = subtitle_tokens(text)
        word_tokens = [normalize_word_text(str(word.get("text") or "")) for word in timed_words]
        if len(all_tokens) == len(timed_words) and len(word_tokens) == len(all_tokens):
            cues: list[dict[str, Any]] = []
            cursor = 0
            alignment_complete = True
            for index, chunk in enumerate(chunks):
                chunk_tokens = subtitle_tokens(chunk)
                token_count = len(chunk_tokens)
                if token_count <= 0 or cursor + token_count > len(timed_words):
                    alignment_complete = False
                    break
                chunk_words = timed_words[cursor : cursor + token_count]
                cursor += token_count
                cue_start = max(absolute_start, absolute_start + int(chunk_words[0]["start_frame"]) - 2)
                cue_end_base = absolute_start + int(chunk_words[-1]["end_frame"])
                if cursor < len(timed_words):
                    next_start = absolute_start + int(timed_words[cursor]["start_frame"]) - 2
                    cue_end = min(absolute_end, max(cue_end_base + 4, next_start))
                else:
                    cue_end = min(absolute_end, cue_end_base + 4)
                if cues:
                    cue_start = max(cues[-1]["end_frame"], cue_start)
                cues.append(
                    {
                        "start_frame": cue_start,
                        "end_frame": max(cue_start + 1, cue_end),
                        "text": chunk,
                    }
                )
            if alignment_complete and cues:
                return cues

    weights = [max(1.0, len(re.sub(r"\s+", "", chunk))) for chunk in chunks]
    total_weight = sum(weights) or float(len(chunks))
    cursor = absolute_start
    fallback_cues: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        remaining = len(chunks) - index
        if index == len(chunks) - 1:
            cue_end = absolute_end
        else:
            proportional = max(12, int(round(audio_frames * weights[index] / total_weight)))
            max_end = absolute_end - (remaining - 1) * 10
            cue_end = min(max_end, max(cursor + 10, cursor + proportional))
        fallback_cues.append(
            {
                "start_frame": cursor,
                "end_frame": max(cursor + 1, cue_end),
                "text": chunk,
            }
        )
        cursor = cue_end
    if fallback_cues:
        fallback_cues[-1]["end_frame"] = absolute_end
    return fallback_cues


def srt_timestamp(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def regroup_word_cues(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not words:
        return []
    cues: list[dict[str, Any]] = []
    current_texts: list[str] = []
    cue_start = words[0]["absolute_start_frame"]
    cue_end = words[0]["absolute_end_frame"]

    def flush() -> None:
        nonlocal current_texts, cue_start, cue_end
        text = "".join(current_texts).strip()
        if text:
            cues.append(
                {
                    "start_frame": cue_start,
                    "end_frame": cue_end,
                    "text": text,
                }
            )
        current_texts = []

    for index, word in enumerate(words):
        text = word["text"]
        if current_texts and word["absolute_start_frame"] - cue_end > int(0.35 * FPS):
            flush()
        if not current_texts:
            cue_start = word["absolute_start_frame"]
        current_texts.append(text)
        cue_end = word["absolute_end_frame"]
        next_word = words[index + 1] if index + 1 < len(words) else None
        if (
            re.search(r"[。！？!?；;，,：:)]$", text)
            or next_word is None
            or len("".join(current_texts)) >= 30
        ):
            flush()
    return cues


def build_srt(entries: list[dict[str, Any]], out_path: Path, whisper_enabled: bool) -> None:
    del whisper_enabled
    cues: list[str] = []
    cue_index = 1
    for entry in entries:
        for cue in entry.get("subtitle_cues", []) or []:
            cues.append(
                "\n".join(
                    [
                        str(cue_index),
                        f"{srt_timestamp(cue['start_frame'] / FPS)} --> {srt_timestamp(cue['end_frame'] / FPS)}",
                        str(cue["text"]),
                    ]
                )
            )
            cue_index += 1
    out_path.write_text("\n\n".join(cues) + "\n", encoding="utf-8")


def issue_label_for_report(report: TechDailyReport, item_count: int) -> str:
    issue_override = os.environ.get("AI_DAILY_ISSUE_NO", "").strip()
    if issue_override:
        try:
            issue_no = int(issue_override)
        except ValueError as exc:
            raise SystemExit(f"AI_DAILY_ISSUE_NO must be an integer: {issue_override}") from exc
        if issue_no <= 0:
            raise SystemExit(f"AI_DAILY_ISSUE_NO must be positive: {issue_override}")
        return f"第 {issue_no} 期"

    if not report.date:
        return f"今日 {item_count} 条"
    candidates: list[Path] = []
    if DAILY_REPORTS_ROOT.exists():
        candidates.extend(DAILY_REPORTS_ROOT.glob("20??-??-??/process/report.md"))
    workspace_reports = REPO_ROOT / "reports"
    if workspace_reports.exists():
        candidates.extend(workspace_reports.glob("tech-daily-20??-??-??.md"))

    unique_candidates = {str(candidate): candidate for candidate in candidates}.values()

    def report_date_for_candidate(candidate: Path) -> str | None:
        if candidate.name == "report.md" and candidate.parent.name == "process":
            return candidate.parent.parent.name
        match = re.fullmatch(r"tech-daily-(\d{4}-\d{2}-\d{2})\.md", candidate.name)
        if not match:
            return None
        return match.group(1)

    if OFFICIAL_ISSUE_START_DATE and report.date >= OFFICIAL_ISSUE_START_DATE:
        unique_candidates = [
            candidate
            for candidate in unique_candidates
            if (candidate_date := report_date_for_candidate(candidate)) and candidate_date >= OFFICIAL_ISSUE_START_DATE
        ]

    ordered = sorted(unique_candidates, key=lambda item: report_date_for_candidate(item) or item.name)
    for index, candidate in enumerate(ordered, start=1):
        if report_date_for_candidate(candidate) == report.date:
            return f"第 {index} 期"
    return f"今日 {item_count} 条"


def detect_card_type(item: TechDailyItem, media_assets: list[dict[str, Any]]) -> str:
    if media_assets:
        return "screenshot"
    if item.quote:
        return "quote"
    return "text"


def detect_layout_variant(item: TechDailyItem, media_assets: list[dict[str, Any]]) -> str:
    if media_assets:
        return "full_media"
    if item.quote:
        return "quote_card"
    return "fact_card"


def detect_template_variant(item: TechDailyItem, media_assets: list[dict[str, Any]]) -> str:
    if media_assets:
        return SCENE_STYLE_VARIANTS["media_then_quote"]
    if item.item_kind == "research" or re.search(r"\bLPM\b|研究|论文|Diffusion", item.title, flags=re.I):
        return SCENE_STYLE_VARIANTS["research_quote_fallback"]
    if item.quote:
        return SCENE_STYLE_VARIANTS["quote_dominant"]
    return SCENE_STYLE_VARIANTS["fact_dominant_fallback"]


def convert_gif_to_video(source: Path, out_path: Path) -> Path:
    ensure_dir(out_path.parent)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-ignore_loop",
            "1",
            "-i",
            str(source),
            "-movflags",
            "+faststart",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2:flags=lanczos",
            str(out_path),
        ],
        check=True,
    )
    return out_path


def gif_first_frame_png(source: Path, out_path: Path) -> Path:
    ensure_pillow_module()
    from PIL import Image  # type: ignore

    ensure_dir(out_path.parent)
    with Image.open(source) as image:
        image.seek(0)
        frame = image.convert("RGBA")
        width, height = frame.size
        if width < 2 or height < 2:
            raise ValueError(f"gif frame too small for fallback render: {width}x{height}")
        frame.save(out_path)
    return out_path


def stage_public_asset(
    source: Path | None,
    target_root: Path,
    public_prefix: str,
    relative_path: str,
) -> str | None:
    if not source or not source.exists():
        return None
    destination = target_root / relative_path
    ensure_dir(destination.parent)
    joined = Path(public_prefix) / relative_path
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    return joined.as_posix()


def stage_public_media_asset(
    *,
    source: Path,
    media_kind: str,
    target_root: Path,
    public_prefix: str,
    relative_stub: str,
) -> dict[str, Any] | None:
    staged_source = source
    staged_suffix = source.suffix
    render_kind = media_kind
    if media_kind == "gif":
        try:
            staged_source = convert_gif_to_video(source, target_root / f"{relative_stub}.mp4")
            staged_suffix = staged_source.suffix
            render_kind = "video"
        except (subprocess.CalledProcessError, ValueError):
            try:
                staged_source = gif_first_frame_png(source, target_root / f"{relative_stub}.png")
                staged_suffix = staged_source.suffix
                render_kind = "image"
            except Exception:  # noqa: BLE001
                return None
    relative_path = f"{relative_stub}{staged_suffix}"
    public_src = stage_public_asset(staged_source, target_root, public_prefix, relative_path)
    if not public_src:
        return None
    return {
        "src": public_src,
        "kind": render_kind,
    }


def generate_default_bgm(out_path: Path, duration_seconds: float) -> None:
    ensure_dir(out_path.parent)
    safe_duration = max(12.0, duration_seconds)
    fade_out_start = max(0.0, safe_duration - 3.2)
    bass_pad = (
        f"aevalsrc=(0.018*sin(2*PI*55*t)+0.014*sin(2*PI*82.5*t)+0.010*sin(2*PI*110*t))"
        f"*(0.60+0.40*sin(2*PI*0.06*t)):s=48000:d={safe_duration:.2f}"
    )
    warm_pad = (
        f"aevalsrc=(0.010*sin(2*PI*220*t)+0.009*sin(2*PI*277.18*t)+0.008*sin(2*PI*329.63*t))"
        f"*(0.48+0.52*sin(2*PI*0.10*t+0.9)):s=48000:d={safe_duration:.2f}"
    )
    soft_clicks = (
        f"aevalsrc=(0.03*sin(2*PI*660*t)+0.02*sin(2*PI*880*t))*"
        f"exp(-18*mod(t\\,0.75)):s=48000:d={safe_duration:.2f}"
    )
    air_noise = f"anoisesrc=color=pink:amplitude=0.008:sample_rate=48000:d={safe_duration:.2f}"
    filter_complex = (
        "[0:a]lowpass=f=780,highpass=f=55,volume=0.88,pan=stereo|c0=c0|c1=0.92*c0[a0];"
        "[1:a]lowpass=f=2200,highpass=f=170,volume=0.44,"
        "aecho=0.7:0.3:120|220:0.14|0.08,pan=stereo|c0=0.92*c0|c1=c0[a1];"
        "[2:a]lowpass=f=3000,highpass=f=480,volume=0.10,"
        "afade=t=in:st=0:d=0.05,pan=stereo|c0=0.78*c0|c1=1.0*c0[a2];"
        "[3:a]lowpass=f=420,highpass=f=120,volume=0.05,pan=stereo|c0=0.82*c0|c1=1.14*c0[a3];"
        f"[a0][a1][a2][a3]amix=inputs=4:normalize=0,alimiter=limit=0.82,"
        f"afade=t=in:st=0:d=2.2,afade=t=out:st={fade_out_start:.2f}:d=3.0[out]"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            bass_pad,
            "-f",
            "lavfi",
            "-i",
            warm_pad,
            "-f",
            "lavfi",
            "-i",
            soft_clicks,
            "-f",
            "lavfi",
            "-i",
            air_noise,
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-c:a",
            "aac",
            str(out_path),
        ],
        check=True,
    )


def prepare_bgm_track(
    *,
    bgm_path: Path | None,
    no_bgm: bool,
    volume: float,
    duration_seconds: float,
    audio_dir: Path,
    public_root: Path,
    public_prefix: str,
) -> dict[str, Any] | None:
    if no_bgm:
        return None

    gain = round(clamp_unit(volume), 3)
    if bgm_path:
        resolved = bgm_path.expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"BGM path does not exist: {resolved}")
        public_src = stage_public_asset(resolved, public_root, public_prefix, f"audio/zz-bgm{resolved.suffix.lower()}")
        if not public_src:
            return None
        return {
            "provider": "file",
            "label": resolved.stem,
            "audio_path": str(resolved),
            "public_audio_src": public_src,
            "volume": gain,
        }

    generated_bgm = audio_dir / "zz-bgm.m4a"
    generate_default_bgm(generated_bgm, duration_seconds)
    public_src = stage_public_asset(generated_bgm, public_root, public_prefix, "audio/zz-bgm.m4a")
    if not public_src:
        return None
    return {
        "provider": "generated-tech-bed",
        "label": "ai-news-ambient-bed",
        "audio_path": str(generated_bgm),
        "public_audio_src": public_src,
        "volume": gain,
    }


def generate_default_transition_sfx(out_path: Path) -> None:
    ensure_dir(out_path.parent)
    duration_seconds = 0.28
    tonal_sweep = (
        f"aevalsrc=(0.10*sin(2*PI*(480*t+1450*t*t))+0.05*sin(2*PI*(860*t+2100*t*t)))"
        f"*(1-0.94*(t/{duration_seconds:.2f})):s=48000:d={duration_seconds:.2f}"
    )
    air_sweep = f"anoisesrc=color=pink:amplitude=0.16:sample_rate=48000:d={duration_seconds:.2f}"
    soft_click = (
        f"aevalsrc=(0.05*sin(2*PI*980*t)+0.03*sin(2*PI*1240*t))*exp(-32*t):s=48000:d={duration_seconds:.2f}"
    )
    filter_complex = (
        "[0:a]highpass=f=340,lowpass=f=6200,volume=0.50,"
        "afade=t=in:st=0:d=0.015,afade=t=out:st=0.18:d=0.10,"
        "pan=stereo|c0=0.96*c0|c1=1.02*c0[tone];"
        "[1:a]highpass=f=900,lowpass=f=9200,volume=0.12,"
        "afade=t=in:st=0:d=0.01,afade=t=out:st=0.14:d=0.12,"
        "pan=stereo|c0=1.04*c0|c1=0.92*c0[air];"
        "[2:a]highpass=f=700,lowpass=f=4000,volume=0.22,"
        "afade=t=in:st=0:d=0.004,afade=t=out:st=0.05:d=0.08,"
        "pan=stereo|c0=c0|c1=0.95*c0[click];"
        "[tone][air][click]amix=inputs=3:normalize=0,alimiter=limit=0.84[out]"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            tonal_sweep,
            "-f",
            "lavfi",
            "-i",
            air_sweep,
            "-f",
            "lavfi",
            "-i",
            soft_click,
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-c:a",
            "aac",
            str(out_path),
        ],
        check=True,
    )


def prepare_transition_sfx(
    *,
    sfx_path: Path | None,
    no_sfx: bool,
    volume: float,
    audio_dir: Path,
    public_root: Path,
    public_prefix: str,
) -> dict[str, Any] | None:
    if no_sfx:
        return None

    gain = round(clamp_unit(volume), 3)
    if sfx_path:
        resolved = sfx_path.expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Transition SFX path does not exist: {resolved}")
        public_src = stage_public_asset(
            resolved,
            public_root,
            public_prefix,
            f"audio/zz-transition{resolved.suffix.lower()}",
        )
        if not public_src:
            return None
        return {
            "provider": "file",
            "label": resolved.stem,
            "audio_path": str(resolved),
            "public_audio_src": public_src,
            "volume": gain,
        }

    generated_sfx = audio_dir / "zz-transition.m4a"
    generate_default_transition_sfx(generated_sfx)
    public_src = stage_public_asset(generated_sfx, public_root, public_prefix, "audio/zz-transition.m4a")
    if not public_src:
        return None
    return {
        "provider": "generated-digital-sweep",
        "label": "ai-news-transition-sweep",
        "audio_path": str(generated_sfx),
        "public_audio_src": public_src,
        "volume": gain,
    }


def build_transition_markers(
    scenes: list[dict[str, Any]],
    *,
    offset_frames: int = TRANSITION_SFX_OFFSET_FRAMES,
) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    for scene in scenes:
        if scene.get("kind") != "item":
            continue
        current_index = int(scene.get("current_index") or 0)
        if current_index <= 1:
            continue
        scene_start = int(scene.get("start_frame") or 0)
        markers.append(
            {
                "frame": max(0, scene_start + max(0, offset_frames)),
                "scene_id": str(scene.get("id") or f"item-{current_index:02d}"),
                "scene_kind": "item",
                "scene_start_frame": scene_start,
            }
        )
    return markers


def resolve_remotion_public_dir(raw_path: str | None = None) -> Path:
    configured = raw_path or os.environ.get("AI_DAILY_REMOTION_PUBLIC_DIR")
    return Path(configured).expanduser().resolve() if configured else REMOTION_PUBLIC_DIR


def prepare_public_root(slug: str, public_dir: Path) -> Path:
    root = public_dir / "generated" / slug
    if root.exists():
        shutil.rmtree(root)
    ensure_dir(root / "audio")
    ensure_dir(root / "images")
    return root


def render_slug(report: TechDailyReport) -> str:
    base = report.date or "latest"
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", base).strip("-") or "latest"


def write_json(path: Path, payload: dict[str, Any] | list[Any]) -> Path:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        return {}
    raw = json.loads(resolved.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def parse_json_payloads(raw_text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    payloads: list[dict[str, Any]] = []
    index = 0
    while index < len(raw_text):
        start = raw_text.find("{", index)
        if start < 0:
            break
        try:
            payload, end = decoder.raw_decode(raw_text[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
        index = start + end
    return payloads


def existing_path_str(path: Path | None) -> str | None:
    if not path or not path.exists():
        return None
    return str(path)


def collect_existing_artifacts(paths: dict[str, Path | None]) -> dict[str, str | None]:
    return {name: existing_path_str(path) for name, path in paths.items()}


def remote_tts_preflight(endpoint: str, timeout_s: float) -> tuple[bool, str]:
    parsed = urllib.parse.urlparse((endpoint or "").strip())
    if not parsed.scheme or not parsed.hostname:
        return False, "invalid_endpoint"
    if fish_tts_curl_proxy_args():
        return True, "proxy_configured"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((parsed.hostname, port), timeout=timeout_s):
            return True, "ok"
    except OSError as exc:
        return False, str(exc)


def summarize_tts_usage(audio_specs: list[dict[str, Any]], tts_state: dict[str, Any]) -> dict[str, Any]:
    provider_counts: dict[str, int] = {}
    remote_requested_segments = 0
    remote_fallback_segments = 0
    for spec in audio_specs:
        tts = spec.get("tts") or {}
        provider = str(tts.get("provider") or "unknown")
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
        if tts.get("remote_tts_requested"):
            remote_requested_segments += 1
        if tts.get("remote_tts_requested") and provider != "fish-speech":
            remote_fallback_segments += 1
    providers = sorted(provider_counts.items(), key=lambda item: (-item[1], item[0]))
    effective_provider = providers[0][0] if providers else "unknown"
    return {
        "effective_provider": effective_provider,
        "provider_counts": provider_counts,
        "remote_requested_segments": remote_requested_segments,
        "remote_fallback_segments": remote_fallback_segments,
        "remote_disabled": bool(tts_state.get("remote_disabled")),
        "remote_preflight_checked": bool(tts_state.get("remote_preflight_checked")),
        "remote_preflight_ok": bool(tts_state.get("remote_preflight_ok")),
        "remote_preflight_detail": str(tts_state.get("remote_preflight_detail") or ""),
        "remote_audio_probe_ok": bool(tts_state.get("remote_audio_probe_ok")),
        "remote_audio_probe_duration": tts_state.get("remote_audio_probe_duration"),
        "last_remote_error": str(tts_state.get("last_remote_error") or ""),
    }


def build_scene_manifest(
    *,
    report: TechDailyReport,
    selected_items: list[TechDailyItem],
    audio_specs: list[dict[str, Any]],
    outro_audio_spec: dict[str, Any],
    image_specs: list[dict[str, Any]],
    issue_label: str,
    date_label: str,
    item_count_label: str,
    lumi_intro_src: str | None,
    lumi_intro_kind: str | None,
    lumi_avatar_src: str | None,
    whisper_enabled: bool,
    tts_reference_id: str,
    title_pack: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cursor = 0
    scenes: list[dict[str, Any]] = []
    summary_entries: list[dict[str, Any]] = []
    emoji_map = load_emoji_icon_map()
    item_labels: list[str] = []
    for offset, item in enumerate(selected_items, start=1):
        oral = audio_specs[offset].get("oral") if offset < len(audio_specs) and isinstance(audio_specs[offset], dict) else {}
        nav_label = str((oral or {}).get("nav_label") or "").strip()
        item_labels.append(display_title_text(nav_label) if nav_label else compact_label(display_title_text(item.title), limit=8))
    opening_items = [
        {
            "index": offset,
            "label": display_title_text(
                str(
                    (
                        audio_specs[offset].get("oral", {})
                        if offset < len(audio_specs) and isinstance(audio_specs[offset], dict)
                        else {}
                    ).get("display_title")
                    or item.title
                )
            ),
            "icon": require_mapped_emoji(item.title, emoji_map),
        }
        for offset, item in enumerate(selected_items, start=1)
    ]

    intro_audio = audio_specs[0]
    intro_oral = intro_audio["oral"]
    intro_words = intro_audio["words"]
    intro_duration_frames = max(INTRO_MIN_FRAMES, intro_audio["audio_frames"] + INTRO_TAIL_FRAMES)
    intro_points = max(1, len(selected_items))
    intro_agenda_lines = [str(entry["label"]) for entry in opening_items[:intro_points]]
    intro_lead = next((spec for spec in image_specs if spec.get("primary_media_src")), None)
    intro_lead_media = intro_lead["primary_media_src"] if intro_lead else lumi_intro_src
    intro_lead_kind = intro_lead["primary_media_kind"] if intro_lead else lumi_intro_kind
    intro_shots = [
        {"kind": "intro_title", "start_frame": 0, "end_frame": max(40, int(round(intro_duration_frames * 0.34)))},
        {
            "kind": "intro_agenda",
            "start_frame": max(40, int(round(intro_duration_frames * 0.34))),
            "end_frame": max(80, int(round(intro_duration_frames * 0.68))),
        },
        {
            "kind": "intro_lead",
            "start_frame": max(80, int(round(intro_duration_frames * 0.68))),
            "end_frame": intro_duration_frames,
        },
    ]
    intro_scene = {
        "id": "intro",
        "kind": "intro",
        "start_frame": cursor,
        "end_frame": cursor + intro_duration_frames,
        "duration_frames": intro_duration_frames,
        "still_frame": cursor + min(intro_duration_frames - 1, intro_shots[0]["start_frame"] + 20),
        "script": intro_audio["script"],
        "oral_script": intro_oral["oral_script"],
        "tts_script": intro_oral.get("tts_script", intro_oral["oral_script"]),
        "subtitle_script": intro_oral["subtitle_script"],
        "sentence_pairs": intro_oral.get("sentence_pairs", []),
        "audio_src": intro_audio["public_audio_src"],
        "audio_offset_frames": 0,
        "audio_duration_frames": intro_audio["audio_frames"],
        "words": [
            {
                **word,
                "absolute_start_frame": cursor + word["start_frame"],
                "absolute_end_frame": cursor + word["end_frame"],
            }
            for word in intro_words
        ],
        "subtitle_cues": build_subtitle_cues(
            intro_oral["subtitle_script"],
            scene_start=cursor,
            audio_offset_frames=0,
            audio_frames=intro_audio["audio_frames"],
            timed_words=intro_audio["words"],
        ),
        "layout_variant": "intro",
        "template_variant": SCENE_STYLE_VARIANTS["intro"],
        "shot_regions": [
            {
                **shot,
                "absolute_start_frame": cursor + shot["start_frame"],
                "absolute_end_frame": cursor + shot["end_frame"],
            }
            for shot in intro_shots
        ],
        "date_label": date_label,
        "item_count_label": item_count_label,
        "issue_label": issue_label,
        "title": "AI速递",
        "subtitle": f"{date_label} · 今日 {len(selected_items)} 条",
        "trend_words": daily_keyword_labels(selected_items, report=report, title_pack=title_pack),
        "headlines": [display_title_text(item.title) for item in selected_items],
        "opening": intro_oral["opening"],
        "agenda": intro_oral["agenda"],
        "transition": intro_oral["transition"],
        "agenda_lines": intro_agenda_lines[:intro_points],
        "opening_items": opening_items[:intro_points],
        "lead_title": display_title_text(selected_items[0].title) if selected_items else "今日 AI 速递",
        "lead_media_src": intro_lead_media,
        "media_assets": [{"src": intro_lead_media, "kind": intro_lead_kind or "image", "source_domain": "", "priority": 0}] if intro_lead_media else [],
        "primary_media_src": intro_lead_media,
        "primary_media_kind": intro_lead_kind,
        "lumi_intro_src": lumi_intro_src,
        "lumi_intro_kind": lumi_intro_kind,
    }
    scenes.append(intro_scene)
    summary_entries.append(
        {
            "segment": 0,
            "kind": "intro",
            "title": "AI速递",
            "script": intro_audio["script"],
            "oral_script": intro_oral["oral_script"],
            "tts_script": intro_oral.get("tts_script", intro_oral["oral_script"]),
            "subtitle_script": intro_oral["subtitle_script"],
            "sentence_pairs": intro_oral.get("sentence_pairs", []),
            "duration": intro_duration_frames / FPS,
            "duration_frames": intro_duration_frames,
            "audio": intro_audio["audio_path"],
            "tts_provider": intro_audio["tts"]["provider"],
            "tts_voice": intro_audio["tts"]["voice"],
            "tts_text": intro_audio["tts"]["tts_text"],
            "tts_style_preset": intro_audio["tts"]["tts_style_preset"],
            "tts_style_tags": intro_audio["tts"]["tts_style_tags"],
            "tts_remote_requested": intro_audio["tts"]["remote_tts_requested"],
            "tts_remote_skipped": intro_audio["tts"]["remote_tts_skipped"],
            "start_frame": cursor,
            "end_frame": cursor + intro_duration_frames,
            "audio_offset_frames": 0,
            "words_count": len(intro_scene["words"]),
            "subtitle_cues": intro_scene["subtitle_cues"],
            "layout_variant": intro_scene["layout_variant"],
            "template_variant": intro_scene["template_variant"],
            "media_assets": intro_scene["media_assets"],
            "primary_media_src": intro_scene["primary_media_src"],
            "media_usage": "image" if intro_scene["primary_media_src"] else "fallback_card",
            "slide": None,
            "video": None,
            "image": intro_scene["primary_media_src"],
        }
    )
    cursor += intro_duration_frames

    for offset, item in enumerate(selected_items, start=1):
        audio_spec = audio_specs[offset]
        image_spec = image_specs[offset - 1]
        oral = audio_spec["oral"]
        card_type = image_spec["card_type"]
        scene_duration_frames = audio_spec["audio_frames"] + ITEM_ENTRY_FRAMES + ITEM_TAIL_FRAMES
        shot_switch = ITEM_ENTRY_FRAMES + max(42, int(round(audio_spec["audio_frames"] * 0.56)))
        words = [
            {
                **word,
                "absolute_start_frame": cursor + ITEM_ENTRY_FRAMES + word["start_frame"],
                "absolute_end_frame": cursor + ITEM_ENTRY_FRAMES + word["end_frame"],
            }
            for word in audio_spec["words"]
        ]
        scene = {
            "id": f"item-{offset:02d}",
            "kind": "item",
            "start_frame": cursor,
            "end_frame": cursor + scene_duration_frames,
            "duration_frames": scene_duration_frames,
            "still_frame": cursor + min(scene_duration_frames - 1, ITEM_ENTRY_FRAMES + 30),
            "script": audio_spec["script"],
            "oral_script": oral["oral_script"],
            "tts_script": oral.get("tts_script", oral["oral_script"]),
            "subtitle_script": oral["subtitle_script"],
            "sentence_pairs": oral.get("sentence_pairs", []),
            "audio_src": audio_spec["public_audio_src"],
            "audio_offset_frames": ITEM_ENTRY_FRAMES,
            "audio_duration_frames": audio_spec["audio_frames"],
            "words": words,
            "subtitle_cues": build_subtitle_cues(
                oral["subtitle_script"],
                scene_start=cursor,
                audio_offset_frames=ITEM_ENTRY_FRAMES,
                audio_frames=audio_spec["audio_frames"],
                timed_words=audio_spec["words"],
            ),
            "layout_variant": image_spec["layout_variant"],
            "template_variant": image_spec["template_variant"],
            "shot_regions": [
                {
                    "kind": "hook",
                    "start_frame": 0,
                    "end_frame": shot_switch,
                    "absolute_start_frame": cursor,
                    "absolute_end_frame": cursor + shot_switch,
                },
                {
                    "kind": "facts",
                    "start_frame": shot_switch,
                    "end_frame": scene_duration_frames,
                    "absolute_start_frame": cursor + shot_switch,
                    "absolute_end_frame": cursor + scene_duration_frames,
                },
            ],
            "item_kind": item.item_kind,
            "index": item.index,
            "current_index": offset,
            "total_items": len(selected_items),
            "title": item.title,
            "display_title": display_title_text(oral["display_title"]),
            "spoken_title": oral["spoken_title"],
            "spoken_aliases": oral["spoken_aliases"],
            "short_title": display_title_text(oral["display_title"] or item.title),
            "display_icon": require_mapped_emoji(item.title, emoji_map),
            "content": shorten_text(item.content, 180),
            "interpretation": shorten_text(item.interpretation, 220),
            "media_summary": two_line_visual_explanation_from_oral(item, oral),
            "quote": shorten_text(display_title_text(item.quote or item.title), 68),
            "hook": oral["hook"],
            "takeaway": oral["takeaway"],
            "fact_points": oral["fact_points"],
            "screen_cards": oral["screen_cards"],
            "source_note": oral["source_note"],
            "outro": oral["outro"],
            "source_domain": source_domain(item.source_url),
            "source_url": item.source_url,
            "status": item.status,
            "card_type": card_type,
            "image_src": image_spec["primary_media_src"],
            "image_srcs": image_spec["public_image_srcs"],
            "media_assets": image_spec["media_assets"],
            "primary_media_src": image_spec["primary_media_src"],
            "primary_media_kind": image_spec["primary_media_kind"],
            "media_usage": image_spec["media_usage"],
            "truthful_visual_count": image_spec["truthful_visual_count"],
            "scene_visual_count": image_spec["scene_visual_count"],
            "visual_coverage_status": image_spec["visual_coverage_status"],
            "media_alignment_review": image_spec["media_alignment_review"],
            "media_reject_reason": image_spec["media_reject_reason"],
            "style_variant": image_spec["template_variant"],
        }
        scenes.append(scene)
        summary_entries.append(
            {
                "segment": offset,
                "kind": "item",
                "item_index": item.index,
                "title": item.title,
                "display_title": oral["display_title"],
                "spoken_title": oral["spoken_title"],
                "spoken_aliases": oral["spoken_aliases"],
                "script": audio_spec["script"],
                "oral_script": oral["oral_script"],
                "tts_script": oral.get("tts_script", oral["oral_script"]),
                "subtitle_script": oral["subtitle_script"],
                "sentence_pairs": oral.get("sentence_pairs", []),
                "screen_cards": oral["screen_cards"],
                "duration": scene_duration_frames / FPS,
                "duration_frames": scene_duration_frames,
                "audio_duration": audio_spec["audio_duration"],
                "audio": audio_spec["audio_path"],
                "tts_provider": audio_spec["tts"]["provider"],
                "tts_voice": audio_spec["tts"]["voice"],
                "tts_text": audio_spec["tts"]["tts_text"],
                "tts_style_preset": audio_spec["tts"]["tts_style_preset"],
                "tts_style_tags": audio_spec["tts"]["tts_style_tags"],
                "tts_remote_requested": audio_spec["tts"]["remote_tts_requested"],
                "tts_remote_skipped": audio_spec["tts"]["remote_tts_skipped"],
                "start_frame": cursor,
                "end_frame": cursor + scene_duration_frames,
                "audio_offset_frames": ITEM_ENTRY_FRAMES,
                "words_count": len(words),
                "subtitle_cues": scene["subtitle_cues"],
                "layout_variant": scene["layout_variant"],
                "template_variant": scene["template_variant"],
                "slide": None,
                "video": None,
                "image": image_spec["image_paths"][0] if image_spec["image_paths"] else None,
                "images": image_spec["image_paths"],
                "image_src": image_spec["primary_media_src"],
                "image_srcs": image_spec["public_image_srcs"],
                "media_assets": image_spec["media_assets"],
                "primary_media_src": image_spec["primary_media_src"],
                "primary_media_kind": image_spec["primary_media_kind"],
                "media_usage": image_spec["media_usage"],
                "image_reviews": image_spec["image_reviews"],
                "approved_image_count": image_spec["approved_image_count"],
                "truthful_visual_count": image_spec["truthful_visual_count"],
                "scene_visual_count": image_spec["scene_visual_count"],
                "visual_coverage_status": image_spec["visual_coverage_status"],
                "media_alignment_review": image_spec["media_alignment_review"],
                "media_reject_reason": image_spec["media_reject_reason"],
                "card_type": card_type,
                "source_url": item.source_url,
                "style_variant": image_spec["template_variant"],
            }
        )
        cursor += scene_duration_frames

    outro_oral = outro_audio_spec["oral"]
    outro_duration_frames = max(OUTRO_FRAMES, outro_audio_spec["audio_frames"] + 12)
    outro_scene = {
        "id": "outro",
        "kind": "outro",
        "start_frame": cursor,
        "end_frame": cursor + outro_duration_frames,
        "duration_frames": outro_duration_frames,
        "still_frame": cursor + 48,
        "script": outro_oral["oral_script"],
        "oral_script": outro_oral["oral_script"],
        "tts_script": outro_oral.get("tts_script", outro_oral["oral_script"]),
        "subtitle_script": outro_oral["subtitle_script"],
        "sentence_pairs": outro_oral.get("sentence_pairs", []),
        "audio_src": outro_audio_spec["public_audio_src"],
        "audio_offset_frames": 0,
        "audio_duration_frames": outro_audio_spec["audio_frames"],
        "words": [
            {
                **word,
                "absolute_start_frame": cursor + word["start_frame"],
                "absolute_end_frame": cursor + word["end_frame"],
            }
            for word in outro_audio_spec["words"]
        ],
        "subtitle_cues": build_subtitle_cues(
            outro_oral["subtitle_script"],
            scene_start=cursor,
            audio_offset_frames=0,
            audio_frames=outro_audio_spec["audio_frames"],
            timed_words=outro_audio_spec["words"],
        ),
        "layout_variant": "fact_card",
        "template_variant": SCENE_STYLE_VARIANTS["outro"],
        "shot_regions": [],
        "media_assets": [],
        "primary_media_src": None,
        "primary_media_kind": None,
        "line_one": str(outro_oral.get("line_one") or ""),
        "line_two": str(outro_oral.get("line_two") or ""),
        "quote_id": str(outro_oral.get("quote_id") or ""),
        "quote_text": str(outro_oral.get("quote_text") or ""),
        "quote_translation": str(outro_oral.get("quote_translation") or ""),
        "quote_author": str(outro_oral.get("quote_author") or ""),
    }
    scenes.append(outro_scene)
    summary_entries.append(
        {
            "segment": len(summary_entries),
            "kind": "outro",
            "title": "片尾",
            "script": outro_oral["oral_script"],
            "oral_script": outro_oral["oral_script"],
            "tts_script": outro_oral.get("tts_script", outro_oral["oral_script"]),
            "subtitle_script": outro_oral["subtitle_script"],
            "sentence_pairs": outro_oral.get("sentence_pairs", []),
            "duration": outro_duration_frames / FPS,
            "duration_frames": outro_duration_frames,
            "audio_duration": outro_audio_spec["audio_duration"],
            "audio": outro_audio_spec["audio_path"],
            "tts_provider": outro_audio_spec["tts"]["provider"],
            "tts_voice": outro_audio_spec["tts"]["voice"],
            "tts_text": outro_audio_spec["tts"]["tts_text"],
            "tts_style_preset": outro_audio_spec["tts"]["tts_style_preset"],
            "tts_style_tags": outro_audio_spec["tts"]["tts_style_tags"],
            "tts_remote_requested": outro_audio_spec["tts"]["remote_tts_requested"],
            "tts_remote_skipped": outro_audio_spec["tts"]["remote_tts_skipped"],
            "start_frame": cursor,
            "end_frame": cursor + outro_duration_frames,
            "audio_offset_frames": 0,
            "words_count": len(outro_scene["words"]),
            "subtitle_cues": outro_scene["subtitle_cues"],
            "layout_variant": "fact_card",
            "template_variant": outro_scene["template_variant"],
            "media_assets": [],
            "primary_media_src": None,
            "media_usage": "fallback_card",
            "slide": None,
            "video": None,
            "image": lumi_avatar_src,
        }
    )
    cursor += outro_duration_frames

    manifest = {
        "renderer": "remotion",
        "version": 1,
        "meta": {
            "date": date_label,
            "title": str((title_pack or {}).get("primary_hook") or "AI速递"),
            "issue_label": issue_label,
            "item_count": len(selected_items),
            "item_labels": item_labels,
            "total_frames": cursor,
            "width": WIDTH,
            "height": HEIGHT,
            "design_width": 1920,
            "design_height": 1080,
            "aspect_ratio": aspect_ratio_label(WIDTH, HEIGHT),
            "fps": FPS,
            "layout": "editorial_title_card",
            "intro_style": "sample_anchor",
            "subtitle_mode": "cinematic_wrap",
            "tts_reference_id": tts_reference_id,
            "html_baseline": HTML_BASELINE,
            "intro_duration_sec": round(intro_duration_frames / FPS, 2),
            "lumi_avatar_src": lumi_avatar_src,
            "lumi_intro_kind": lumi_intro_kind,
            "editorial_title_card": True,
            "card_preview_media": False,
            "primary_hook": str((title_pack or {}).get("primary_hook") or ""),
            "issue_quote_text": LUMI_FIXED_SLOGAN,
            "issue_quote_original": "",
            "issue_quote_author": "Lumi",
            "quote_id": str(outro_oral.get("quote_id") or ""),
        },
        "report": {
            "trend_words": daily_keyword_labels(selected_items, report=report, title_pack=title_pack),
            "items": [
                {
                    "index": item.index,
                    "title": display_title_text(item.title),
                    "item_label": item_labels[offset - 1],
                    "source_url": item.source_url,
                }
                for offset, item in enumerate(selected_items, start=1)
            ],
        },
        "scenes": scenes,
    }
    return manifest, summary_entries


def render_video(manifest_path: Path, stills_path: Path, final_video: Path | None, *, public_dir: Path) -> dict[str, Any]:
    ensure_remotion_deps()
    cmd = [
        "node",
        str(REMOTION_RENDER_SCRIPT),
        "--manifest",
        str(manifest_path),
        "--public-dir",
        str(public_dir),
    ]
    if final_video is not None:
        cmd.extend(["--video", str(final_video)])
    cmd.extend(["--stills", str(stills_path)])
    completed = run(
        cmd,
        cwd=REMOTION_DIR,
    )
    cleaned = completed.stdout.strip()
    payloads = parse_json_payloads(cleaned)
    for payload in reversed(payloads):
        if payload.get("result") == "success":
            return payload
    if payloads:
        return payloads[-1]
    if final_video is None:
        return {"result": "success", "video": None, "stills": []}
    if final_video.exists():
        return {"result": "success", "video": str(final_video), "stills": []}
    raise RuntimeError("Could not parse Remotion render output")


def still_specs_for_manifest(remotion_manifest: dict[str, Any], slides_dir: Path) -> list[dict[str, Any]]:
    scenes = remotion_manifest.get("scenes") if isinstance(remotion_manifest.get("scenes"), list) else []
    if not scenes:
        raise RuntimeError("Remotion manifest has no scenes for still rendering")
    intro_scene = next((scene for scene in scenes if scene.get("kind") == "intro"), scenes[0])
    still_specs = [
        {
            "output": str(slides_dir / "00-intro.png"),
            "frame": int(intro_scene["still_frame"]),
        },
    ]
    opening_shot = next(
        (shot for shot in intro_scene.get("shot_regions") or [] if shot.get("kind") == "intro_agenda"),
        None,
    )
    if opening_shot:
        opening_start = int(opening_shot.get("absolute_start_frame") or 0)
        opening_frame = opening_start + 28
        opening_end = int(opening_shot.get("absolute_end_frame") or opening_frame + 1)
        still_specs.append(
            {
                "output": str(slides_dir / "00-opening.png"),
                "frame": min(max(opening_frame, opening_start), max(opening_start, opening_end - 1)),
            }
        )
    item_scenes = [scene for scene in scenes if scene.get("kind") == "item"]
    for index, scene in enumerate(item_scenes, start=1):
        start_frame = int(scene.get("start_frame") or 0)
        end_frame = int(scene.get("end_frame") or scene.get("still_frame") or start_frame)
        card_frame = int(scene["still_frame"])
        media_frame = max(card_frame + 1, min(end_frame - 8, start_frame + int((end_frame - start_frame) * 0.62)))
        still_specs.append(
            {
                "output": str(slides_dir / f"{index:02d}-item.png"),
                "frame": card_frame,
            }
        )
        if media_frame > card_frame and media_frame < end_frame:
            still_specs.append(
                {
                    "output": str(slides_dir / f"{index:02d}-item-media.png"),
                    "frame": media_frame,
                }
            )
    outro_scene = next((scene for scene in scenes if scene.get("kind") == "outro"), None)
    if outro_scene:
        still_specs.append(
            {
                "output": str(slides_dir / "99-outro.png"),
                "frame": int(outro_scene["still_frame"]),
            }
        )
    return still_specs


def rendered_still_map(still_specs: list[dict[str, Any]]) -> dict[str, str]:
    return {Path(str(item["output"])).name: str(item["output"]) for item in still_specs}


def attach_still_paths(summary_entries: list[dict[str, Any]], still_specs: list[dict[str, Any]]) -> None:
    rendered_stills = rendered_still_map(still_specs)
    item_counter = 0
    for entry in summary_entries:
        if entry["kind"] == "intro":
            entry["slide"] = rendered_stills.get("00-intro.png")
            entry["opening_slide"] = rendered_stills.get("00-opening.png")
        elif entry["kind"] == "item":
            item_counter += 1
            entry["slide"] = rendered_stills.get(f"{item_counter:02d}-item.png")
        elif entry["kind"] == "outro":
            entry["slide"] = rendered_stills.get("99-outro.png")


def build_stills_contact_sheet(still_specs: list[dict[str, Any]], output_path: Path) -> str | None:
    paths = [Path(str(spec.get("output") or "")) for spec in still_specs]
    paths = [path for path in paths if path.exists()]
    if not paths:
        return None

    from PIL import Image, ImageDraw, ImageFont  # type: ignore

    columns = 2
    thumb_width = 480
    thumb_height = round(thumb_width * HEIGHT / WIDTH)
    label_height = 30
    rows = math.ceil(len(paths) / columns)
    sheet = Image.new("RGB", (columns * thumb_width, rows * (thumb_height + label_height)), "#fbf5f7")
    draw = ImageDraw.Draw(sheet)

    font = ImageFont.load_default()
    for font_path in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ):
        try:
            font = ImageFont.truetype(font_path, 14)
            break
        except Exception:  # noqa: BLE001
            continue

    for index, path in enumerate(paths):
        row, column = divmod(index, columns)
        x = column * thumb_width
        y = row * (thumb_height + label_height)
        with Image.open(path) as image:
            thumbnail = image.convert("RGB")
            thumbnail.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)
            frame = Image.new("RGB", (thumb_width, thumb_height), "#fffafa")
            frame.paste(thumbnail, ((thumb_width - thumbnail.width) // 2, (thumb_height - thumbnail.height) // 2))
        sheet.paste(frame, (x, y))
        draw.rectangle([x, y + thumb_height, x + thumb_width, y + thumb_height + label_height], fill="#fbf5f7")
        draw.text((x + 8, y + thumb_height + 7), path.name, fill="#333333", font=font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, quality=90, optimize=True)
    return str(output_path)


def estimate_stills_audio_frames(text: str, *, min_seconds: float, max_seconds: float) -> int:
    compact = re.sub(r"\s+", "", normalize_spoken_text(text or ""))
    estimated_seconds = max(min_seconds, min(max_seconds, len(compact) / 5.8))
    return seconds_to_frames(estimated_seconds)


def stills_only_audio_spec(
    *,
    script: str,
    oral: dict[str, Any],
    audio_path: Path,
    audio_frames: int,
    tts_reference_id: str,
) -> dict[str, Any]:
    return {
        "script": script,
        "oral": oral,
        "audio_path": str(audio_path),
        "public_audio_src": None,
        "audio_duration": audio_frames / FPS,
        "audio_frames": audio_frames,
        "tts": {
            "provider": "stills-only",
            "voice": tts_reference_id,
            "tts_text": script,
            "tts_style_preset": "none",
            "tts_style_tags": "",
            "remote_tts_requested": False,
            "remote_tts_skipped": True,
        },
        "words": timed_script_words(oral.get("subtitle_script") or script, audio_frames, None),
    }


def build_collected_image_specs(
    *,
    selected_items: list[TechDailyItem],
    item_orals: list[dict[str, Any]],
    images: list[dict[str, Any]],
    public_root: Path,
    public_prefix: str,
    min_reviewed_images: int,
) -> list[dict[str, Any]]:
    image_specs: list[dict[str, Any]] = []
    for offset, item in enumerate(selected_items, start=1):
        item_oral = item_orals[offset - 1]
        item_script = item_oral.get("tts_script") or item_oral["oral_script"]
        matched_assets = choose_images(images, item)
        media_review = audit_image_candidates(item, matched_assets, max_images=4)
        approved_assets = list(media_review["approved_assets"])
        support_assets = list(media_review.get("support_assets") or [])
        reviewed_assets = merge_media_candidates(
            approved_assets,
            support_assets,
            max_images=2,
        )
        if len(reviewed_assets) < min_reviewed_images:
            raise RuntimeError(
                f"Item {offset} has {len(reviewed_assets)} usable collected images; "
                f"required {min_reviewed_images}. Collect official or source-grounded images before building video pages."
            )
        media_alignment_review = build_media_alignment_review(
            item,
            item_script,
            reviewed_assets,
            min_required=min_reviewed_images,
        )
        if media_alignment_review["status"] == "fail":
            raise RuntimeError(f"Item {offset} failed media alignment review: {media_alignment_review['summary']}")
        image_paths = [str(candidate["file"]) for candidate in reviewed_assets]
        public_media_assets: list[dict[str, Any]] = []
        public_images: list[str] = []
        for image_index, candidate in enumerate(reviewed_assets, start=1):
            image_file = Path(str(candidate["file"])).expanduser().resolve()
            staged = stage_public_media_asset(
                source=image_file,
                media_kind=str(candidate.get("kind") or "image"),
                target_root=public_root,
                public_prefix=public_prefix,
                relative_stub=f"media/{offset:02d}-{image_index:02d}-{re.sub(r'[^a-zA-Z0-9._-]+', '-', image_file.stem)}",
            )
            if not staged:
                continue
            public_images.append(staged["src"])
            public_media_assets.append(
                {
                    "src": staged["src"],
                    "kind": staged["kind"],
                    "source_domain": candidate.get("source_domain") or source_domain(item.source_url),
                    "priority": int(candidate.get("priority") or 0),
                    "selector": candidate.get("selector"),
                    "image_url": candidate.get("image_url"),
                }
            )
        if len(public_media_assets) < min_reviewed_images:
            raise RuntimeError(
                f"Item {offset} staged {len(public_media_assets)} public media assets; required {min_reviewed_images}."
            )
        layout_variant = detect_layout_variant(item, public_media_assets)
        template_variant = detect_template_variant(item, public_media_assets)
        image_specs.append(
            {
                "image_paths": image_paths,
                "public_image_src": public_images[0],
                "public_image_srcs": public_images,
                "media_assets": public_media_assets,
                "primary_media_src": public_media_assets[0]["src"],
                "primary_media_kind": public_media_assets[0]["kind"],
                "media_usage": public_media_assets[0]["kind"],
                "layout_variant": layout_variant,
                "template_variant": template_variant,
                "card_type": detect_card_type(item, public_media_assets),
                "image_reviews": media_review["reviewed_assets"],
                "approved_image_count": len(reviewed_assets),
                "truthful_visual_count": len(reviewed_assets),
                "scene_visual_count": len(public_media_assets),
                "visual_coverage_status": "pass",
                "media_alignment_review": media_alignment_review,
                "media_reject_reason": combine_reject_reasons(
                    None if len(reviewed_assets) >= 2 else media_review["media_reject_reason"],
                ),
            }
        )
    return image_specs


def extract_loudnorm_json(stderr: str) -> dict[str, str]:
    match = re.search(r"\{\s*\"input_i\".*?\}", stderr, flags=re.S)
    if not match:
        raise RuntimeError("Could not parse loudnorm measurement output")
    payload = json.loads(match.group(0))
    return {str(key): str(value) for key, value in payload.items()}


def normalize_video_audio(video_path: Path) -> dict[str, Any]:
    measured = extract_loudnorm_json(
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-i",
                str(video_path),
                "-af",
                "loudnorm=I=-16:LRA=11:TP=-1.5:print_format=json",
                "-f",
                "null",
                "-",
            ]
        ).stderr
    )

    temp_path = video_path.with_name(f"{video_path.stem}.normalized{video_path.suffix}")
    filter_spec = (
        "loudnorm=I=-16:LRA=11:TP=-1.5:"
        f"measured_I={measured['input_i']}:"
        f"measured_LRA={measured['input_lra']}:"
        f"measured_TP={measured['input_tp']}:"
        f"measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:"
        "linear=true:print_format=summary"
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-i",
            str(video_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "26",
            "-tune",
            "stillimage",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            "-af",
            filter_spec,
            str(temp_path),
        ]
    )
    temp_path.replace(video_path)
    return {
        "enabled": True,
        "tool": "ffmpeg-loudnorm",
        "target_i": -16,
        "target_lra": 11,
        "target_tp": -1.5,
        "video_crf": 26,
        "video_preset": "slow",
        "measured": measured,
    }


def main() -> int:
    args = parse_args()
    out_dir = ensure_dir(Path(args.out_dir).expanduser().resolve())
    summary_path = out_dir / "build-summary.json"
    report_path = Path(args.report).expanduser().resolve()
    title_pack_path = Path(args.title_pack).expanduser().resolve() if args.title_pack else None
    content_manifest_arg = args.content_manifest
    content_manifest_path = Path(content_manifest_arg).expanduser().resolve() if content_manifest_arg else None
    report_json_path: Path | None = None
    video_script_path: Path | None = out_dir / "video-script.json"
    manifest_path: Path | None = Path(args.manifest).expanduser().resolve() if args.manifest else None
    remotion_manifest_path: Path | None = out_dir / "remotion-manifest.json"
    timeline_path: Path | None = out_dir / "timeline.json"
    srt_path: Path | None = out_dir / "video.srt"
    final_video: Path | None = out_dir / "video.mp4"
    cover_path: Path | None = out_dir / "slides" / "00-intro.png"
    remotion_public_dir = resolve_remotion_public_dir(args.remotion_public_dir)
    audio_specs: list[dict[str, Any]] = []
    outro_audio_spec: dict[str, Any] | None = None
    current_stage = "parse_report"
    tts_state: dict[str, Any] = {
        "remote_disabled": False,
        "remote_preflight_checked": False,
        "remote_preflight_ok": False,
        "remote_preflight_detail": "",
    }

    try:
        report = parse_report(report_path)
        current_stage = "prepare_report_sidecar"
        report_sidecar = load_report_json_sidecar(report.path)
        sidecar_items = report_sidecar.get("items") if isinstance(report_sidecar, dict) else None
        sidecar_by_index: dict[int, dict[str, Any]] = {}
        if isinstance(sidecar_items, list):
            sidecar_by_index = {
                int(item.get("index")): item
                for item in sidecar_items
                if isinstance(item, dict) and str(item.get("index") or "").isdigit()
            }
        for item in report.items:
            payload = sidecar_by_index.get(item.index) or {}
            if payload.get("decision_impact"):
                item.decision_impact = str(payload["decision_impact"]).strip()
            if payload.get("source_refs") and isinstance(payload.get("source_refs"), list):
                item.source_refs = [str(entry).strip() for entry in payload["source_refs"] if str(entry).strip()]
            if payload.get("item_kind"):
                item.item_kind = str(payload["item_kind"]).strip()
            if payload.get("duplicate_key"):
                item.duplicate_key = str(payload["duplicate_key"]).strip()
            if not item.source_refs:
                item.source_refs = [ref for ref in [str(item.source_url or "").strip()] if ref]

        selected_items = report.items[: args.max_items]
        title_pack = load_json(args.title_pack)
        editorial_bundle = load_content_manifest(content_manifest_arg, report_path=report.path, date=report.date)
        bgm_analysis = load_json(args.bgm_analysis)

        current_stage = "prepare_output_dir"
        for stale in (
            out_dir / "video.mp4",
            out_dir / "video.srt",
            out_dir / f"tech-daily-video-{report.date or 'latest'}.mp4",
            out_dir / f"tech-daily-video-{report.date or 'latest'}.srt",
            out_dir / "build-summary.json",
            out_dir / "remotion-manifest.json",
            out_dir / "remotion-stills.json",
            out_dir / "timeline.json",
            out_dir / "video-script.json",
        ):
            stale.unlink(missing_ok=True)
        for pattern in ("*.mp4", "*.srt"):
            for stale in out_dir.glob(pattern):
                stale.unlink(missing_ok=True)
        for stale_dir in (out_dir / "assets", out_dir / "audio", out_dir / "slides"):
            if stale_dir.exists():
                shutil.rmtree(stale_dir)

        issue_label = str(title_pack.get("issue_label") or issue_label_for_report(report, len(selected_items)))
        intro_oral, item_orals, outro_oral = load_bundle_orals(editorial_bundle, selected_items)
        for item, oral in zip(selected_items, item_orals):
            if not item.decision_impact.strip():
                item.decision_impact = str(
                    oral.get("decision_impact")
                    or oral.get("takeaway")
                    or oral.get("outro")
                    or ""
                ).strip()
        intro_script = intro_oral.get("tts_script") or intro_oral["oral_script"]
        video_script_payload = build_video_script_payload(
            report,
            selected_items,
            issue_label=issue_label,
            intro_oral=intro_oral,
            item_orals=item_orals,
            outro_oral=outro_oral,
        )

        current_stage = "write_video_script"
        video_script_path = write_json(out_dir / "video-script.json", video_script_payload)
        report_json_path = write_report_json(report, report_json_path_for_markdown(report.path))

        assets_dir = ensure_dir(out_dir / "assets")
        audio_dir = reset_generated_dir(out_dir / "audio")
        slides_dir = reset_generated_dir(out_dir / "slides")

        current_stage = "resolve_collected_image_manifest"
        manifest_path = Path(args.manifest).expanduser().resolve() if args.manifest else None
        if manifest_path and not manifest_path.exists():
            report_manifest = Path(report.path).with_name(f"{Path(report.path).stem}.image-manifest.json")
            manifest_path = report_manifest if report_manifest.exists() else None
        elif not manifest_path:
            report_manifest = Path(report.path).with_name(f"{Path(report.path).stem}.image-manifest.json")
            if report_manifest.exists():
                manifest_path = report_manifest
        day_dir = out_dir.parent.parent if out_dir.parent.name == "build" else out_dir.parent
        images = load_assets(manifest_path)
        images.extend(load_assets(day_dir / "curated-video-assets" / "manifest.json"))
        for item in selected_items:
            images.extend(pack_assets_for_item_refs(item, day_dir))

        current_stage = "stage_brand_assets"
        slug = render_slug(report)
        public_root = prepare_public_root(slug, remotion_public_dir)
        public_prefix = f"generated/{slug}"

        lumi_intro_path = Path(args.lumi_intro_image).expanduser().resolve() if args.lumi_intro_image else None
        lumi_avatar_path = Path(args.lumi_avatar_image).expanduser().resolve() if args.lumi_avatar_image else None
        public_lumi_intro_spec = (
            stage_public_media_asset(
                source=lumi_intro_path,
                media_kind=media_kind_from_path(lumi_intro_path),
                target_root=public_root,
                public_prefix=public_prefix,
                relative_stub="images/lumi-intro",
            )
            if lumi_intro_path and lumi_intro_path.exists()
            else None
        )
        public_lumi_intro = public_lumi_intro_spec["src"] if public_lumi_intro_spec else None
        public_lumi_intro_kind = public_lumi_intro_spec["kind"] if public_lumi_intro_spec else None
        public_lumi_avatar = stage_public_asset(
            lumi_avatar_path,
            public_root,
            public_prefix,
            f"images/lumi-avatar{lumi_avatar_path.suffix}" if lumi_avatar_path and lumi_avatar_path.exists() else "images/lumi-avatar.png",
        )

        date_label = report.date.replace("-", ".") if report.date else "今日"
        item_count_label = f"今日 {len(selected_items)} 条"

        if args.stills_only:
            current_stage = "build_stills_only_scene_manifest"
            intro_audio_frames = estimate_stills_audio_frames(intro_script, min_seconds=12.0, max_seconds=22.0)
            audio_specs.append(
                stills_only_audio_spec(
                    script=intro_script,
                    oral=intro_oral,
                    audio_path=audio_dir / "00-intro.stills-only.m4a",
                    audio_frames=intro_audio_frames,
                    tts_reference_id=args.tts_reference_id,
                )
            )
            image_specs = build_collected_image_specs(
                selected_items=selected_items,
                item_orals=item_orals,
                images=images,
                public_root=public_root,
                public_prefix=public_prefix,
                min_reviewed_images=args.min_reviewed_images,
            )
            for offset, item in enumerate(selected_items, start=1):
                item_oral = item_orals[offset - 1]
                item_script = item_oral.get("tts_script") or item_oral["oral_script"]
                audio_specs.append(
                    stills_only_audio_spec(
                        script=item_script,
                        oral=item_oral,
                        audio_path=audio_dir / f"{offset:02d}-item.stills-only.m4a",
                        audio_frames=estimate_stills_audio_frames(item_script, min_seconds=14.0, max_seconds=28.0),
                        tts_reference_id=args.tts_reference_id,
                    )
                )

            outro_script = outro_oral.get("tts_script") or outro_oral["oral_script"]
            outro_audio_spec = stills_only_audio_spec(
                script=outro_script,
                oral=outro_oral,
                audio_path=audio_dir / "99-outro.stills-only.m4a",
                audio_frames=estimate_stills_audio_frames(outro_script, min_seconds=7.0, max_seconds=16.0),
                tts_reference_id=args.tts_reference_id,
            )

            video_script_payload["segments"][0]["trend_words"] = daily_keyword_labels(
                selected_items,
                report=report,
                title_pack=title_pack,
            )
            video_script_payload["segments"][0]["display_title"] = intro_oral["display_title"]
            video_script_payload["segments"][0]["spoken_title"] = intro_oral["spoken_title"]
            video_script_payload["segments"][0]["spoken_aliases"] = intro_oral["spoken_aliases"]
            video_script_payload["segments"][0]["style_variant"] = intro_oral["style_variant"]
            item_segments = [segment for segment in video_script_payload["segments"] if segment.get("kind") == "item"]
            for segment, oral, image_spec in zip(item_segments, item_orals, image_specs):
                segment["display_title"] = oral["display_title"]
                segment["spoken_title"] = oral["spoken_title"]
                segment["spoken_aliases"] = oral["spoken_aliases"]
                segment["sentence_pairs"] = oral.get("sentence_pairs", [])
                segment["screen_cards"] = oral.get("screen_cards", [])
                segment["nav_label"] = oral.get("nav_label", "")
                segment["style_variant"] = image_spec["template_variant"]
            outro_segments = [segment for segment in video_script_payload["segments"] if segment.get("kind") == "outro"]
            if outro_segments:
                outro_segments[-1].update(
                    {
                        "title": outro_oral.get("display_title") or outro_oral.get("spoken_title") or "片尾",
                        "display_title": outro_oral.get("display_title") or "片尾",
                        "spoken_title": outro_oral.get("spoken_title") or "片尾",
                        "spoken_aliases": outro_oral.get("spoken_aliases", []),
                        "style_variant": outro_oral.get("style_variant") or SCENE_STYLE_VARIANTS["outro"],
                        "tts_style_tags": outro_oral.get("tts_style_tags", ""),
                        "script": outro_oral["oral_script"],
                        "oral_script": outro_oral["oral_script"],
                        "tts_script": outro_oral.get("tts_script") or outro_oral["oral_script"],
                        "subtitle_script": outro_oral["subtitle_script"],
                        "sentence_pairs": outro_oral.get("sentence_pairs", []),
                    }
                )
            video_script_path = write_json(out_dir / "video-script.json", video_script_payload)

            remotion_manifest, summary_entries = build_scene_manifest(
                report=report,
                selected_items=selected_items,
                audio_specs=audio_specs,
                outro_audio_spec=outro_audio_spec,
                image_specs=image_specs,
                issue_label=issue_label,
                date_label=date_label,
                item_count_label=item_count_label,
                lumi_intro_src=public_lumi_intro,
                lumi_intro_kind=public_lumi_intro_kind,
                lumi_avatar_src=public_lumi_avatar,
                whisper_enabled=False,
                tts_reference_id=args.tts_reference_id,
                title_pack=title_pack,
            )
            remotion_manifest["meta"]["bgm_src"] = None
            remotion_manifest["meta"]["bgm_volume"] = 0.0
            remotion_manifest["meta"]["bgm_provider"] = "none"
            remotion_manifest["meta"]["bgm_label"] = ""
            remotion_manifest["meta"]["bgm_start_frame"] = 0
            remotion_manifest["meta"]["bgm_end_frame"] = None
            remotion_manifest["meta"]["outro_bgm_enabled"] = False
            remotion_manifest["meta"]["transition_sfx_src"] = None
            remotion_manifest["meta"]["transition_sfx_volume"] = 0.0
            remotion_manifest["meta"]["transition_sfx_provider"] = "none"
            remotion_manifest["meta"]["transition_sfx_label"] = ""
            remotion_manifest["meta"]["transition_markers"] = []
            remotion_manifest["meta"]["stills_only"] = True

            remotion_manifest_path = write_json(out_dir / "remotion-manifest.json", remotion_manifest)
            still_specs = still_specs_for_manifest(remotion_manifest, slides_dir)
            stills_path = write_json(out_dir / "remotion-stills.json", still_specs)

            current_stage = "render_stills_only"
            render_result = render_video(remotion_manifest_path, stills_path, None, public_dir=remotion_public_dir)
            attach_still_paths(summary_entries, still_specs)
            contact_sheet_path = build_stills_contact_sheet(still_specs, out_dir / "slides-contact-sheet.jpg")
            timeline_path = write_json(
                out_dir / "timeline.json",
                {
                    "fps": FPS,
                    "segments": summary_entries,
                    "stills_only": True,
                },
            )
            remotion_manifest_path = write_json(out_dir / "remotion-manifest.json", remotion_manifest)
            tts_summary = summarize_tts_usage(audio_specs + [outro_audio_spec], tts_state)
            summary = {
                "result": "success",
                "renderer": "remotion",
                "stills_only": True,
                "fps": FPS,
                "width": WIDTH,
                "height": HEIGHT,
                "aspect_ratio": aspect_ratio_label(WIDTH, HEIGHT),
                "layout": "editorial_title_card",
                "report": report.to_dict(),
                "voice": args.tts_reference_id,
                "voice_engine": "stills-only",
                "tts": tts_summary,
                "manifest": str(manifest_path) if manifest_path else None,
                "manifest_json": str(remotion_manifest_path),
                "timeline_json": str(timeline_path),
                "report_json": str(report_json_path),
                "video_script": str(video_script_path),
                "cover_image": str(slides_dir / "00-intro.png"),
                "video_cover_image": str(slides_dir / "00-intro.png"),
                "video": None,
                "srt": None,
                "segments": summary_entries,
                "render": render_result,
                "title_pack": title_pack,
                "content_manifest": str(content_manifest_path) if content_manifest_path else None,
                "primary_hook": str(title_pack.get("primary_hook") or ""),
                "top_story_title": str(title_pack.get("top_story_title") or title_pack.get("primary_hook") or ""),
                "item_labels": list(remotion_manifest["meta"].get("item_labels") or []),
                "quote_id": str(remotion_manifest["meta"].get("quote_id") or ""),
                "stills": [str(Path(spec["output"])) for spec in still_specs],
                "contact_sheet": contact_sheet_path,
            }
            write_json(summary_path, summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0

        if args.require_fish:
            current_stage = "fish_audio_preflight"
            probe_fish_audio(
                endpoint=args.tts_endpoint,
                reference_id=args.tts_reference_id,
                response_format=args.tts_format,
                use_memory_cache=args.tts_use_memory_cache,
                timeout=args.tts_timeout,
                audio_dir=audio_dir,
                tts_state=tts_state,
            )

        current_stage = "synthesize_intro"
        intro_audio_path = audio_dir / "00-intro.m4a"
        intro_tts = synthesize_audio(
            text=intro_script,
            voice=args.voice,
            rate=args.rate,
            out_path=intro_audio_path,
            tts_endpoint=args.tts_endpoint,
            tts_reference_id=args.tts_reference_id,
            tts_format=args.tts_format,
            tts_use_memory_cache=args.tts_use_memory_cache,
            tts_timeout=args.tts_timeout,
            tts_style_preset=args.tts_style_preset,
            tts_style_tags=intro_oral.get("tts_style_tags") or args.tts_style_tags,
            tts_state=tts_state,
        )
        if args.require_fish and intro_tts["provider"] != "fish-speech":
            raise RuntimeError("Fish Speech was required, but the intro narration fell back to a local voice.")
        public_intro_audio = stage_public_asset(intro_audio_path, public_root, public_prefix, "audio/00-intro.m4a")
        intro_audio_seconds = audio_duration(
            intro_audio_path,
            context={
                "provider": intro_tts.get("provider"),
                "endpoint": args.tts_endpoint,
                "reference_id": args.tts_reference_id,
                "segment": "intro",
            },
        )
        audio_specs.append(
            {
                "script": intro_script,
                "oral": intro_oral,
                "audio_path": str(intro_audio_path),
                "public_audio_src": public_intro_audio,
                "audio_duration": intro_audio_seconds,
                "audio_frames": seconds_to_frames(intro_audio_seconds),
                "tts": intro_tts,
                "words": [],
            }
        )

        current_stage = "synthesize_items"
        for offset, item in enumerate(selected_items, start=1):
            item_oral = item_orals[offset - 1]
            item_script = item_oral.get("tts_script") or item_oral["oral_script"]
            audio_path = audio_dir / f"{offset:02d}-item.m4a"
            item_tts = synthesize_audio(
                text=item_script,
                voice=args.voice,
                rate=args.rate,
                out_path=audio_path,
                tts_endpoint=args.tts_endpoint,
                tts_reference_id=args.tts_reference_id,
                tts_format=args.tts_format,
                tts_use_memory_cache=args.tts_use_memory_cache,
                tts_timeout=args.tts_timeout,
                tts_style_preset=args.tts_style_preset,
                tts_style_tags=item_oral.get("tts_style_tags") or args.tts_style_tags,
                tts_state=tts_state,
            )
            if args.require_fish and item_tts["provider"] != "fish-speech":
                raise RuntimeError(f"Fish Speech was required, but item {offset} narration fell back to a local voice.")
            audio_seconds = audio_duration(
                audio_path,
                context={
                    "provider": item_tts.get("provider"),
                    "endpoint": args.tts_endpoint,
                    "reference_id": args.tts_reference_id,
                    "segment": f"item-{offset:02d}",
                },
            )
            public_audio = stage_public_asset(audio_path, public_root, public_prefix, f"audio/{offset:02d}-item.m4a")
            audio_specs.append(
                {
                    "script": item_script,
                    "oral": item_oral,
                    "audio_path": str(audio_path),
                    "public_audio_src": public_audio,
                    "audio_duration": audio_seconds,
                    "audio_frames": seconds_to_frames(audio_seconds),
                    "tts": item_tts,
                    "words": [],
                }
            )

        current_stage = "prepare_item_images"
        image_specs = build_collected_image_specs(
            selected_items=selected_items,
            item_orals=item_orals,
            images=images,
            public_root=public_root,
            public_prefix=public_prefix,
            min_reviewed_images=args.min_reviewed_images,
        )

        video_script_payload["segments"][0]["trend_words"] = daily_keyword_labels(
            selected_items,
            report=report,
            title_pack=title_pack,
        )
        video_script_payload["segments"][0]["display_title"] = intro_oral["display_title"]
        video_script_payload["segments"][0]["spoken_title"] = intro_oral["spoken_title"]
        video_script_payload["segments"][0]["spoken_aliases"] = intro_oral["spoken_aliases"]
        video_script_payload["segments"][0]["style_variant"] = intro_oral["style_variant"]
        outro_segments = [segment for segment in video_script_payload["segments"] if segment.get("kind") == "outro"]
        if outro_segments:
            outro_segments[-1].update(
                {
                    "title": outro_oral.get("display_title") or outro_oral.get("spoken_title") or "片尾",
                    "display_title": outro_oral.get("display_title") or "片尾",
                    "spoken_title": outro_oral.get("spoken_title") or "片尾",
                    "spoken_aliases": outro_oral.get("spoken_aliases", []),
                    "style_variant": outro_oral.get("style_variant") or SCENE_STYLE_VARIANTS["outro"],
                    "tts_style_tags": outro_oral.get("tts_style_tags", ""),
                    "script": outro_oral["oral_script"],
                    "oral_script": outro_oral["oral_script"],
                    "tts_script": outro_oral.get("tts_script") or outro_oral["oral_script"],
                    "subtitle_script": outro_oral["subtitle_script"],
                    "sentence_pairs": outro_oral.get("sentence_pairs", []),
                }
            )
        item_segments = [segment for segment in video_script_payload["segments"] if segment.get("kind") == "item"]
        for segment, oral, image_spec in zip(item_segments, item_orals, image_specs):
            segment["display_title"] = oral["display_title"]
            segment["spoken_title"] = oral["spoken_title"]
            segment["spoken_aliases"] = oral["spoken_aliases"]
            segment["sentence_pairs"] = oral.get("sentence_pairs", [])
            segment["style_variant"] = image_spec["template_variant"]

        video_script_path = write_json(out_dir / "video-script.json", video_script_payload)

        current_stage = "synthesize_outro"
        outro_audio_path = audio_dir / "99-outro.m4a"
        outro_tts = synthesize_audio(
            text=outro_oral.get("tts_script") or outro_oral["oral_script"],
            voice=args.voice,
            rate=args.rate,
            out_path=outro_audio_path,
            tts_endpoint=args.tts_endpoint,
            tts_reference_id=args.tts_reference_id,
            tts_format=args.tts_format,
            tts_use_memory_cache=args.tts_use_memory_cache,
            tts_timeout=args.tts_timeout,
            tts_style_preset=args.tts_style_preset,
            tts_style_tags=outro_oral.get("tts_style_tags") or args.tts_style_tags,
            tts_state=tts_state,
        )
        if args.require_fish and outro_tts["provider"] != "fish-speech":
            raise RuntimeError("Fish Speech was required, but the outro narration fell back to a local voice.")
        public_outro_audio = stage_public_asset(outro_audio_path, public_root, public_prefix, "audio/99-outro.m4a")
        outro_audio_seconds = audio_duration(
            outro_audio_path,
            context={
                "provider": outro_tts.get("provider"),
                "endpoint": args.tts_endpoint,
                "reference_id": args.tts_reference_id,
                "segment": "outro",
            },
        )
        outro_audio_spec = {
            "script": outro_oral.get("tts_script") or outro_oral["oral_script"],
            "oral": outro_oral,
            "audio_path": str(outro_audio_path),
            "public_audio_src": public_outro_audio,
            "audio_duration": outro_audio_seconds,
            "audio_frames": seconds_to_frames(outro_audio_seconds),
            "tts": outro_tts,
            "words": [],
        }

        current_stage = "whisper_alignment"
        whisper_enabled = False
        try:
            all_audio_specs = [*audio_specs, outro_audio_spec]
            for spec in all_audio_specs:
                aligned_words = None
                if not args.no_whisper and spec["script"].strip():
                    try:
                        aligned_words = transcribe_words(Path(spec["audio_path"]), args.whisper_model)
                        whisper_enabled = whisper_enabled or bool(aligned_words)
                    except Exception as exc:  # noqa: BLE001
                        print(f"[whisper] alignment skipped for {spec['audio_path']}: {exc}", file=sys.stderr)
                spec["words"] = timed_script_words(spec["script"], spec["audio_frames"], aligned_words)
        except Exception as exc:  # noqa: BLE001
            print(f"[whisper] alignment failed, falling back to estimated timings: {exc}", file=sys.stderr)
            for spec in [*audio_specs, outro_audio_spec]:
                spec["words"] = timed_script_words(spec["script"], spec["audio_frames"], None)

        current_stage = "build_scene_manifest"
        remotion_manifest, summary_entries = build_scene_manifest(
            report=report,
            selected_items=selected_items,
            audio_specs=audio_specs,
            outro_audio_spec=outro_audio_spec,
            image_specs=image_specs,
            issue_label=issue_label,
            date_label=date_label,
            item_count_label=item_count_label,
            lumi_intro_src=public_lumi_intro,
            lumi_intro_kind=public_lumi_intro_kind,
            lumi_avatar_src=public_lumi_avatar,
            whisper_enabled=whisper_enabled,
            tts_reference_id=args.tts_reference_id,
            title_pack=title_pack,
        )
        bgm_spec = prepare_bgm_track(
            bgm_path=Path(args.bgm_path) if args.bgm_path else None,
            no_bgm=args.no_bgm,
            volume=args.bgm_volume,
            duration_seconds=remotion_manifest["meta"]["total_frames"] / FPS,
            audio_dir=audio_dir,
            public_root=public_root,
            public_prefix=public_prefix,
        )
        transition_sfx_spec = prepare_transition_sfx(
            sfx_path=Path(args.transition_sfx_path) if args.transition_sfx_path else None,
            no_sfx=args.no_transition_sfx,
            volume=args.transition_sfx_volume,
            audio_dir=audio_dir,
            public_root=public_root,
            public_prefix=public_prefix,
        )
        transition_markers = build_transition_markers(remotion_manifest["scenes"]) if transition_sfx_spec else []
        remotion_manifest["meta"]["bgm_src"] = bgm_spec["public_audio_src"] if bgm_spec else None
        remotion_manifest["meta"]["bgm_volume"] = bgm_spec["volume"] if bgm_spec else 0.0
        remotion_manifest["meta"]["bgm_provider"] = bgm_spec["provider"] if bgm_spec else "none"
        remotion_manifest["meta"]["bgm_label"] = bgm_spec["label"] if bgm_spec else ""
        bgm_start_sec = float(bgm_analysis.get("recommended_in_sec") or 0.0)
        bgm_end_sec = float(bgm_analysis.get("recommended_out_sec") or 0.0)
        intro_end_frame = next(
            (int(scene.get("end_frame") or 0) for scene in remotion_manifest["scenes"] if scene.get("kind") == "intro"),
            0,
        )
        remotion_manifest["meta"]["bgm_start_frame"] = max(0, seconds_to_frames(bgm_start_sec))
        trimmed_bgm_end_frame = seconds_to_frames(bgm_end_sec) if bgm_end_sec > bgm_start_sec else None
        if intro_end_frame > 0:
            remotion_manifest["meta"]["bgm_end_frame"] = min(trimmed_bgm_end_frame or intro_end_frame, intro_end_frame)
        else:
            remotion_manifest["meta"]["bgm_end_frame"] = trimmed_bgm_end_frame
        remotion_manifest["meta"]["outro_bgm_enabled"] = not args.disable_outro_bgm
        if not remotion_manifest["meta"].get("bgm_src") or remotion_manifest["meta"].get("bgm_end_frame") is None:
            raise RuntimeError("missing_intro_bgm_asset")
        if (
            public_lumi_intro
            and lumi_intro_path
            and lumi_intro_path.suffix.lower() == ".gif"
            and public_lumi_intro_kind != "video"
        ):
            raise RuntimeError("gif_asset_not_rendered_as_video")
        remotion_manifest["meta"]["transition_sfx_src"] = transition_sfx_spec["public_audio_src"] if transition_sfx_spec else None
        remotion_manifest["meta"]["transition_sfx_volume"] = transition_sfx_spec["volume"] if transition_sfx_spec else 0.0
        remotion_manifest["meta"]["transition_sfx_provider"] = transition_sfx_spec["provider"] if transition_sfx_spec else "none"
        remotion_manifest["meta"]["transition_sfx_label"] = transition_sfx_spec["label"] if transition_sfx_spec else ""
        remotion_manifest["meta"]["transition_markers"] = transition_markers

        final_video = out_dir / "video.mp4"
        cover_path = slides_dir / "00-intro.png"
        still_specs = still_specs_for_manifest(remotion_manifest, slides_dir)

        remotion_manifest_path = write_json(out_dir / "remotion-manifest.json", remotion_manifest)
        stills_path = write_json(out_dir / "remotion-stills.json", still_specs)

        current_stage = "render_video"
        render_result = render_video(remotion_manifest_path, stills_path, final_video, public_dir=remotion_public_dir)
        audio_normalization = normalize_video_audio(final_video)
        rendered_stills = rendered_still_map(still_specs)
        contact_sheet_path = build_stills_contact_sheet(still_specs, out_dir / "slides-contact-sheet.jpg")

        for entry in summary_entries:
            if entry["kind"] == "intro":
                entry["slide"] = rendered_stills.get("00-intro.png")
            elif entry["kind"] == "item":
                local_index = len([candidate for candidate in summary_entries[: entry["segment"] + 1] if candidate["kind"] == "item"])
                entry["slide"] = rendered_stills.get(f"{local_index:02d}-item.png")
            elif entry["kind"] == "outro":
                entry["slide"] = rendered_stills.get("99-outro.png")

            matching_scene = next(
                (scene for scene in remotion_manifest["scenes"] if scene["start_frame"] == entry["start_frame"] and scene["kind"] == entry["kind"]),
                None,
            )
            if matching_scene:
                entry["words"] = matching_scene.get("words", [])
                entry["subtitle_cues"] = matching_scene.get("subtitle_cues", [])

        media_usage = {
            "image": sum(1 for entry in summary_entries if entry.get("kind") == "item" and entry.get("media_usage") == "image"),
            "gif": sum(1 for entry in summary_entries if entry.get("kind") == "item" and entry.get("media_usage") == "gif"),
            "video": sum(1 for entry in summary_entries if entry.get("kind") == "item" and entry.get("media_usage") == "video"),
            "fallback_card": sum(
                1 for entry in summary_entries if entry.get("kind") == "item" and entry.get("media_usage") == "fallback_card"
            ),
        }

        srt_path = out_dir / "video.srt"
        build_srt(summary_entries, srt_path, whisper_enabled)
        timeline_path = write_json(
            out_dir / "timeline.json",
            {
                "fps": FPS,
                "segments": summary_entries,
            },
        )
        style_notes: dict[str, Any] = {"warnings": []}
        item_media_alignment_reviews = [
            {
                "segment": entry.get("segment"),
                "title": entry.get("display_title") or entry.get("title"),
                **(entry.get("media_alignment_review") or {}),
            }
            for entry in summary_entries
            if entry.get("kind") == "item"
        ]
        media_alignment_review = {
            "status": (
                "fail"
                if any(review.get("status") == "fail" for review in item_media_alignment_reviews)
                else "warn"
                if any(review.get("status") == "warn" for review in item_media_alignment_reviews)
                else "pass"
            ),
            "total_items": len(item_media_alignment_reviews),
            "pass_items": sum(1 for review in item_media_alignment_reviews if review.get("status") == "pass"),
            "warn_items": sum(1 for review in item_media_alignment_reviews if review.get("status") == "warn"),
            "fail_items": sum(1 for review in item_media_alignment_reviews if review.get("status") == "fail"),
            "items": item_media_alignment_reviews,
        }
        item_visual_coverage_reviews = [
            {
                "segment": entry.get("segment"),
                "title": entry.get("display_title") or entry.get("title"),
                "scene_visual_count": int(entry.get("scene_visual_count") or 0),
                "truthful_visual_count": int(entry.get("truthful_visual_count") or 0),
                "coverage_status": str(entry.get("visual_coverage_status") or "fail"),
            }
            for entry in summary_entries
            if entry.get("kind") == "item"
        ]
        visual_coverage_review = {
            "status": (
                "fail"
                if any(review.get("coverage_status") == "fail" for review in item_visual_coverage_reviews)
                else "pass"
            ),
            "total_items": len(item_visual_coverage_reviews),
            "pass_items": sum(1 for review in item_visual_coverage_reviews if review.get("coverage_status") == "pass"),
            "fail_items": sum(1 for review in item_visual_coverage_reviews if review.get("coverage_status") == "fail"),
            "items": item_visual_coverage_reviews,
        }
        output_size_mb = round(final_video.stat().st_size / (1024 * 1024), 2) if final_video.exists() else 0.0
        media_rejections = [
            {
                "segment": entry.get("segment"),
                "title": entry.get("display_title") or entry.get("title"),
                "media_reject_reason": entry.get("media_reject_reason"),
            }
            for entry in summary_entries
            if entry.get("kind") == "item" and entry.get("media_reject_reason")
        ]
        if output_size_mb > FRIENDLY_OUTPUT_SIZE_MB:
            style_notes["warnings"].append(
                f"最终视频体积 {output_size_mb}MB，超过推荐上限 {FRIENDLY_OUTPUT_SIZE_MB}MB。"
            )
        remotion_manifest["meta"]["media_alignment_review_status"] = media_alignment_review["status"]
        remotion_manifest["meta"]["visual_coverage_review_status"] = visual_coverage_review["status"]
        remotion_manifest_path = write_json(out_dir / "remotion-manifest.json", remotion_manifest)
        tts_summary = summarize_tts_usage([*audio_specs, outro_audio_spec], tts_state)

        current_stage = "finalize_summary"
        summary = {
            "result": "success",
            "renderer": "remotion",
            "fps": FPS,
            "width": WIDTH,
            "height": HEIGHT,
            "aspect_ratio": aspect_ratio_label(WIDTH, HEIGHT),
            "layout": "editorial_title_card",
            "intro_style": "sample_anchor",
            "subtitle_mode": "cinematic_wrap",
            "editorial_title_card": True,
            "card_preview_media": False,
            "media_usage": media_usage,
            "html_baseline": HTML_BASELINE,
            "report": report.to_dict(),
            "voice": args.tts_reference_id,
            "voice_engine": tts_summary["effective_provider"],
            "fallback_voice": args.voice,
            "rate": args.rate,
            "intro_duration_sec": remotion_manifest["meta"]["intro_duration_sec"],
            "output_size_mb": output_size_mb,
            "bgm": bgm_spec,
            "bgm_analysis": bgm_analysis,
            "bgm_scope": "intro_only",
            "bgm_src": remotion_manifest["meta"].get("bgm_src"),
            "bgm_start_frame": remotion_manifest["meta"].get("bgm_start_frame"),
            "bgm_end_frame": remotion_manifest["meta"].get("bgm_end_frame"),
            "outro_bgm_enabled": not args.disable_outro_bgm,
            "transition_sfx": transition_sfx_spec,
            "transition_markers": transition_markers,
            "tts_endpoint": args.tts_endpoint,
            "tts_reference_id": args.tts_reference_id,
            "tts_style_preset": args.tts_style_preset,
            "tts_style_tags": args.tts_style_tags,
            "tts": tts_summary,
            "remotion_public_dir": str(remotion_public_dir),
            "manifest": str(manifest_path) if manifest_path else None,
            "manifest_json": str(remotion_manifest_path),
            "timeline_json": str(timeline_path),
            "report_json": str(report_json_path),
            "video_script": str(video_script_path),
            "cover_image": str(cover_path),
            "video_cover_image": str(cover_path),
            "video": str(final_video),
            "srt": str(srt_path),
            "segments": summary_entries,
            "media_rejections": media_rejections,
            "style_notes": style_notes,
            "media_alignment_review": media_alignment_review,
            "visual_coverage_review": visual_coverage_review,
            "render": render_result,
            "contact_sheet": contact_sheet_path,
            "audio_normalization": audio_normalization,
            "title_pack": title_pack,
            "content_manifest": str(content_manifest_path) if content_manifest_path else None,
            "primary_hook": str(title_pack.get("primary_hook") or ""),
            "top_story_title": str(title_pack.get("top_story_title") or title_pack.get("primary_hook") or ""),
            "top_story_confirmed": bool(title_pack.get("top_story_confirmed")),
            "confirmation_sources": list(title_pack.get("confirmation_sources") or []),
            "item_labels": list(remotion_manifest["meta"].get("item_labels") or []),
            "quote_id": str(remotion_manifest["meta"].get("quote_id") or ""),
        }
        write_json(summary_path, summary)

        report_root = out_dir.parent
        if report_root.exists():
            for child in sorted(report_root.iterdir()):
                if child.is_dir() and child.name.startswith("tmp-"):
                    shutil.rmtree(child, ignore_errors=True)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        failure_summary = {
            "result": "failed",
            "failed_stage": current_stage,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=20),
            "report": str(report_path),
            "out_dir": str(out_dir),
            "title_pack": str(title_pack_path) if title_pack_path else None,
            "content_manifest": str(content_manifest_path) if content_manifest_path else None,
            "manifest": str(manifest_path) if manifest_path else None,
            "report_json": str(report_json_path) if report_json_path else None,
            "tts": summarize_tts_usage([*audio_specs, *([outro_audio_spec] if outro_audio_spec else [])], tts_state),
            "partial_artifacts": collect_existing_artifacts(
                {
                    "build_summary": summary_path,
                    "video_script": video_script_path,
                    "report_json": report_json_path,
                    "manifest_json": remotion_manifest_path,
                    "timeline_json": timeline_path,
                    "video": final_video,
                    "srt": srt_path,
                    "cover_image": cover_path,
                }
            ),
        }
        if isinstance(exc, subprocess.CalledProcessError):
            failure_summary["failed_command"] = " ".join(str(part) for part in exc.cmd)
            failure_summary["failed_returncode"] = exc.returncode
            failure_summary["failed_stdout_tail"] = tail_text(exc.stdout or "")
            failure_summary["failed_stderr_tail"] = tail_text(exc.stderr or "")
        write_json(summary_path, failure_summary)
        print(json.dumps(failure_summary, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
