#!/usr/bin/env python3
"""
Archive X / WeChat / Zhihu / Xueqiu source text into a local source pack.

Designed for report runs that already selected or materially used social URLs and
want a durable local corpus for follow-up Q&A.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse, urlunparse

import requests


URL_RE = re.compile(r"https?://[^\s<>()\"']+")
TRAILING_PUNCTUATION = ".,;:!?)>]}\"'"
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
SUPPORTED_HOSTS = {
    "x.com": "x",
    "twitter.com": "x",
    "mp.weixin.qq.com": "wechat",
    "weixin.qq.com": "wechat",
    "www.zhihu.com": "zhihu",
    "zhihu.com": "zhihu",
    "zhuanlan.zhihu.com": "zhihu",
    "www.xueqiu.com": "xueqiu",
    "xueqiu.com": "xueqiu",
}
MIN_OK_TEXT_CHARS = {
    "x": 40,
    "wechat": 180,
    "zhihu": 180,
    "xueqiu": 140,
    "xiaohongshu": 120,
}
MIN_SCORING_TEXT_CHARS = {
    "x": 60,
    "wechat": 320,
    "zhihu": 260,
    "xueqiu": 220,
    "xiaohongshu": 180,
}
METHOD_CONFIDENCE = {
    "x-reader": 0.95,
    "browser": 0.92,
    "browser:openclaw": 0.9,
    "github-raw": 0.9,
    "direct-html": 0.82,
    "r.jina.ai": 0.56,
    "direct-html-meta": 0.35,
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg", ".avif", ".heic", ".heif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv", ".gifv", ".m3u8"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".flac", ".opus"}
DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".key",
    ".pages",
    ".xls",
    ".xlsx",
    ".csv",
    ".tsv",
    ".txt",
    ".md",
    ".rtf",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".epub",
}
ARCHIVE_EXTENSIONS = {".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz"}
MODEL_EXTENSIONS = {".gguf", ".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".onnx"}
DOWNLOADABLE_ASSET_KINDS = {"image", "video", "audio", "document"}
ASSET_MAX_BYTES = {
    "image": 15 * 1024 * 1024,
    "video": 40 * 1024 * 1024,
    "audio": 20 * 1024 * 1024,
    "document": 25 * 1024 * 1024,
    "archive": 10 * 1024 * 1024,
    "model": 10 * 1024 * 1024,
    "other": 8 * 1024 * 1024,
}
ASSET_DOWNLOAD_LIMITS = {
    "image": 6,
    "video": 2,
    "audio": 2,
    "document": 6,
    "archive": 1,
    "model": 1,
    "other": 2,
}
IMAGE_BLOCKLIST_FRAGMENTS = (
    "avatar",
    "icon",
    "emoji",
    "favicon",
    "flag",
    "logo",
    "spinner",
    "placeholder",
    "qrcode",
    "qr-code",
    "barcode",
    "loading",
    "sitemap",
    "atom.xml",
    "rss.xml",
    "site.webmanifest",
    "apple-touch-icon",
    "manifest.json",
    "opensearch",
)
ASSET_KIND_PRIORITY = {
    "image": 7,
    "video": 6,
    "audio": 5,
    "document": 4,
    "archive": 3,
    "model": 2,
    "other": 1,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str, limit: int = 80) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return clean[:limit] or "source"


def trim_url_token(url: str) -> str:
    while url and url[-1] in TRAILING_PUNCTUATION:
        url = url[:-1]
    return url


def extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    for match in URL_RE.findall(text or ""):
        url = trim_url_token(match)
        if url:
            urls.append(url)
    return urls


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    query = parsed.query
    fragment = ""
    if netloc in {"twitter.com", "www.twitter.com"}:
        netloc = "x.com"
    if netloc in {"x.com", "www.x.com"}:
        query = ""
    return urlunparse((scheme, netloc, path, "", query, fragment))


def detect_kind(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    for supported, kind in SUPPORTED_HOSTS.items():
        if host == supported or host.endswith("." + supported):
            return kind
    return None


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def x_reader_path() -> Path:
    return workspace_root() / "skills" / "x-reader-skill" / "x-reader.py"


class TextStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip_depth > 0:
            self.skip_depth -= 1
        elif tag in {"p", "br", "div", "section", "article", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        raw = unescape("".join(self.parts))
        raw = re.sub(r"\r", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        raw = re.sub(r"[ \t]+", " ", raw)
        return raw.strip()


class SectionExtractor(HTMLParser):
    def __init__(self, target_id: str) -> None:
        super().__init__()
        self.target_id = target_id
        self.active_depth = 0
        self.skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if self.active_depth == 0 and attrs_dict.get("id") == self.target_id:
            self.active_depth = 1
            return

        if self.active_depth > 0:
            self.active_depth += 1
            if tag in {"script", "style", "noscript"}:
                self.skip_depth += 1
            elif tag in {"p", "br", "div", "section", "article", "li", "h1", "h2", "h3"}:
                self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.active_depth == 0:
            return

        if tag in {"script", "style", "noscript"} and self.skip_depth > 0:
            self.skip_depth -= 1
        elif tag in {"p", "br", "div", "section", "article", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

        self.active_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.active_depth > 0 and self.skip_depth == 0:
            self.parts.append(data)

    def text(self) -> str:
        raw = unescape("".join(self.parts))
        raw = re.sub(r"\r", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        raw = re.sub(r"[ \t]+", " ", raw)
        return raw.strip()


class SectionHTMLExtractor(HTMLParser):
    def __init__(self, target_id: str) -> None:
        super().__init__()
        self.target_id = target_id
        self.active_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if self.active_depth == 0 and attrs_dict.get("id") == self.target_id:
            self.active_depth = 1
            return

        if self.active_depth > 0:
            self.active_depth += 1
            self.parts.append(self.get_starttag_text())

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if self.active_depth == 0 and attrs_dict.get("id") == self.target_id:
            return
        if self.active_depth > 0:
            self.parts.append(self.get_starttag_text())

    def handle_endtag(self, tag: str) -> None:
        if self.active_depth == 0:
            return
        self.active_depth -= 1
        if self.active_depth > 0:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self.active_depth > 0:
            self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if self.active_depth > 0:
            self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self.active_depth > 0:
            self.parts.append(f"&#{name};")

    def html(self) -> str:
        return "".join(self.parts).strip()


class HTMLToMarkdownParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0
        self.pre_depth = 0
        self.blockquote_depth = 0
        self.list_depth = 0

    def _append(self, text: str) -> None:
        if not text:
            return
        self.parts.append(text)

    def _newline(self, count: int = 1) -> None:
        if not self.parts:
            return
        existing = 0
        for part in reversed(self.parts):
            if not part:
                continue
            tail = len(part) - len(part.rstrip("\n"))
            existing = tail
            break
        needed = max(count - existing, 0)
        if needed:
            self.parts.append("\n" * needed)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in {"article", "section", "div", "p"}:
            self._newline(2)
        elif tag == "br":
            self._newline(1)
        elif tag in {"h1", "h2", "h3", "h4"}:
            self._newline(2)
            prefix = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### "}.get(tag, "## ")
            self._append(prefix)
        elif tag in {"ul", "ol"}:
            self.list_depth += 1
            self._newline(1)
        elif tag == "li":
            self._newline(1)
            indent = "  " * max(self.list_depth - 1, 0)
            self._append(f"{indent}- ")
        elif tag == "blockquote":
            self.blockquote_depth += 1
            self._newline(1)
            self._append("> ")
        elif tag in {"strong", "b"}:
            self._append("**")
        elif tag in {"em", "i"}:
            self._append("*")
        elif tag == "pre":
            self.pre_depth += 1
            self._newline(2)
            self._append("```\n")
        elif tag == "code" and self.pre_depth == 0:
            self._append("`")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip_depth > 0:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag in {"article", "section", "div", "p"}:
            self._newline(2)
        elif tag in {"h1", "h2", "h3", "h4"}:
            self._newline(2)
        elif tag in {"ul", "ol"} and self.list_depth > 0:
            self.list_depth -= 1
            self._newline(2)
        elif tag == "li":
            self._newline(1)
        elif tag == "blockquote" and self.blockquote_depth > 0:
            self.blockquote_depth -= 1
            self._newline(2)
        elif tag in {"strong", "b"}:
            self._append("**")
        elif tag in {"em", "i"}:
            self._append("*")
        elif tag == "pre" and self.pre_depth > 0:
            self.pre_depth -= 1
            self._append("\n```")
            self._newline(2)
        elif tag == "code" and self.pre_depth == 0:
            self._append("`")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = unescape(data)
        if not text.strip():
            if self.pre_depth:
                self._append(text)
            return
        if self.blockquote_depth and (not self.parts or self.parts[-1].endswith("\n")):
            self._append("> ")
        if self.pre_depth:
            self._append(text)
        else:
            self._append(re.sub(r"\s+", " ", text))

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = re.sub(r"[ \t]+\n", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        raw = re.sub(r"[ \t]{2,}", " ", raw)
        return raw.strip()


def normalize_asset_url(raw: str, base_url: str) -> str:
    value = (raw or "").strip()
    if not value or value.startswith(("data:", "javascript:", "blob:")):
        return ""
    if value.startswith("//"):
        value = "https:" + value
    return urljoin(base_url, value)


def normalize_image_url(raw: str, base_url: str) -> str:
    return normalize_asset_url(raw, base_url)


def suffix_candidates(url: str) -> list[str]:
    path = (urlparse(url).path or "").lower()
    parts = Path(path).suffixes
    combined: list[str] = []
    if len(parts) >= 2:
        combined.append("".join(parts[-2:]))
    if parts:
        combined.append(parts[-1])
    return combined


def asset_kind_from_extension(url: str) -> str:
    for suffix in suffix_candidates(url):
        if suffix in IMAGE_EXTENSIONS:
            return "image"
        if suffix in VIDEO_EXTENSIONS:
            return "video"
        if suffix in AUDIO_EXTENSIONS:
            return "audio"
        if suffix in DOCUMENT_EXTENSIONS:
            return "document"
        if suffix in ARCHIVE_EXTENSIONS:
            return "archive"
        if suffix in MODEL_EXTENSIONS:
            return "model"
    return ""


def asset_kind_from_content_type(content_type: str) -> str:
    value = (content_type or "").split(";", 1)[0].strip().lower()
    if not value:
        return ""
    if value.startswith("image/"):
        return "image"
    if value.startswith("video/") or value in {"application/x-mpegurl", "application/vnd.apple.mpegurl"}:
        return "video"
    if value.startswith("audio/"):
        return "audio"
    if value in {
        "application/pdf",
        "application/msword",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/plain",
        "text/markdown",
        "text/csv",
        "application/json",
        "application/xml",
        "text/xml",
    }:
        return "document"
    if value in {
        "application/zip",
        "application/x-7z-compressed",
        "application/x-rar-compressed",
        "application/gzip",
        "application/x-tar",
    }:
        return "archive"
    if value in {
        "application/octet-stream",
        "application/x-gguf",
    }:
        return "model"
    return ""


def classify_asset_kind(url: str, hinted_kind: str = "", content_type: str = "") -> str:
    if hinted_kind:
        return hinted_kind
    guessed = asset_kind_from_content_type(content_type)
    if guessed:
        return guessed
    return asset_kind_from_extension(url)


def is_probable_asset_href(url: str) -> bool:
    return bool(asset_kind_from_extension(url))


class AssetCandidateParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.assets: list[dict[str, object]] = []
        self.media_stack: list[str] = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: (value or "") for key, value in attrs}
        lower_tag = tag.lower()
        if lower_tag in {"video", "audio"}:
            self.media_stack.append(lower_tag)

        if lower_tag == "meta":
            prop = (attrs_dict.get("property") or attrs_dict.get("name") or "").strip().lower()
            if prop in {"og:image", "twitter:image", "twitter:image:src"}:
                image_url = normalize_asset_url(attrs_dict.get("content", ""), self.base_url)
                if image_url:
                    self.assets.append(
                        {
                            "url": image_url,
                            "asset_kind": "image",
                            "alt": "",
                            "class_name": "",
                            "width": 0,
                            "height": 0,
                            "source": "meta",
                            "label": prop,
                            "content_type": "",
                        }
                    )
            return

        if lower_tag == "img":
            image_url = pick_image_url(attrs_dict, self.base_url)
            if not image_url:
                return
            self.assets.append(
                {
                    "url": image_url,
                    "asset_kind": "image",
                    "alt": whitespace_compact(attrs_dict.get("alt", "")),
                    "class_name": whitespace_compact(attrs_dict.get("class", "")),
                    "width": parse_dimension(attrs_dict.get("width", "")),
                    "height": parse_dimension(attrs_dict.get("height", "")),
                    "source": "img",
                    "label": whitespace_compact(attrs_dict.get("title", "")),
                    "content_type": "",
                }
            )
            return

        if lower_tag == "video":
            poster_url = normalize_asset_url(attrs_dict.get("poster", ""), self.base_url)
            if poster_url:
                self.assets.append(
                    {
                        "url": poster_url,
                        "asset_kind": "image",
                        "alt": "",
                        "class_name": whitespace_compact(attrs_dict.get("class", "")),
                        "width": parse_dimension(attrs_dict.get("width", "")),
                        "height": parse_dimension(attrs_dict.get("height", "")),
                        "source": "video-poster",
                        "label": whitespace_compact(attrs_dict.get("title", "")),
                        "content_type": "",
                    }
                )
            video_url = normalize_asset_url(attrs_dict.get("src", ""), self.base_url)
            if video_url:
                self.assets.append(
                    {
                        "url": video_url,
                        "asset_kind": classify_asset_kind(video_url, hinted_kind="video", content_type=attrs_dict.get("type", "")),
                        "alt": "",
                        "class_name": whitespace_compact(attrs_dict.get("class", "")),
                        "width": parse_dimension(attrs_dict.get("width", "")),
                        "height": parse_dimension(attrs_dict.get("height", "")),
                        "source": "video",
                        "label": whitespace_compact(attrs_dict.get("title", "")),
                        "content_type": whitespace_compact(attrs_dict.get("type", "")),
                    }
                )
            return

        if lower_tag == "audio":
            audio_url = normalize_asset_url(attrs_dict.get("src", ""), self.base_url)
            if audio_url:
                self.assets.append(
                    {
                        "url": audio_url,
                        "asset_kind": classify_asset_kind(audio_url, hinted_kind="audio", content_type=attrs_dict.get("type", "")),
                        "alt": "",
                        "class_name": whitespace_compact(attrs_dict.get("class", "")),
                        "width": 0,
                        "height": 0,
                        "source": "audio",
                        "label": whitespace_compact(attrs_dict.get("title", "")),
                        "content_type": whitespace_compact(attrs_dict.get("type", "")),
                    }
                )
            return

        if lower_tag == "source":
            hinted_kind = self.media_stack[-1] if self.media_stack else ""
            media_url = normalize_asset_url(attrs_dict.get("src", ""), self.base_url)
            if media_url:
                self.assets.append(
                    {
                        "url": media_url,
                        "asset_kind": classify_asset_kind(media_url, hinted_kind=hinted_kind, content_type=attrs_dict.get("type", "")),
                        "alt": "",
                        "class_name": "",
                        "width": 0,
                        "height": 0,
                        "source": f"{hinted_kind or 'media'}-source",
                        "label": "",
                        "content_type": whitespace_compact(attrs_dict.get("type", "")),
                    }
                )
            return

        if lower_tag not in {"a", "link"}:
            return

        href = normalize_asset_url(attrs_dict.get("href", ""), self.base_url)
        if not href or not is_probable_asset_href(href):
            return
        self.assets.append(
            {
                "url": href,
                "asset_kind": classify_asset_kind(href, content_type=attrs_dict.get("type", "")),
                "alt": "",
                "class_name": whitespace_compact(attrs_dict.get("class", "")),
                "width": 0,
                "height": 0,
                "source": "anchor",
                "label": whitespace_compact(attrs_dict.get("title", "") or attrs_dict.get("download", "") or attrs_dict.get("rel", "")),
                "content_type": whitespace_compact(attrs_dict.get("type", "")),
            }
        )

    def handle_endtag(self, tag: str) -> None:
        lower_tag = tag.lower()
        if lower_tag in {"video", "audio"} and self.media_stack:
            self.media_stack.pop()


def strip_html(html: str) -> str:
    parser = TextStripper()
    parser.feed(html)
    return parser.text()


def extract_section_by_id(html: str, target_id: str) -> str:
    parser = SectionExtractor(target_id)
    parser.feed(html)
    return parser.text()


def extract_section_html_by_id(html: str, target_id: str) -> str:
    parser = SectionHTMLExtractor(target_id)
    parser.feed(html)
    return parser.html()


def html_to_markdown(fragment: str) -> str:
    parser = HTMLToMarkdownParser()
    parser.feed(fragment or "")
    return parser.text()


def parse_dimension(raw: str) -> int:
    value = (raw or "").strip()
    if not value:
        return 0
    match = re.search(r"(\d+)", value)
    return int(match.group(1)) if match else 0


def parse_srcset(value: str) -> list[str]:
    urls: list[str] = []
    for chunk in (value or "").split(","):
        candidate = chunk.strip().split(" ", 1)[0].strip()
        if candidate:
            urls.append(candidate)
    return urls


def pick_image_url(attrs: dict[str, str], base_url: str) -> str:
    candidates = [
        attrs.get("data-original", ""),
        attrs.get("data-src", ""),
        attrs.get("data-actualsrc", ""),
        attrs.get("src", ""),
    ]
    candidates.extend(reversed(parse_srcset(attrs.get("srcset", ""))))
    for raw in candidates:
        image_url = normalize_image_url(raw, base_url)
        if image_url:
            return image_url
    return ""


def asset_sort_key(candidate: dict[str, object]) -> tuple[int, int, int, int]:
    asset_kind = str(candidate.get("asset_kind") or "")
    source_bonus = 1 if str(candidate.get("source") or "") == "meta" else 0
    width = int(candidate.get("width") or 0)
    height = int(candidate.get("height") or 0)
    kind_priority = ASSET_KIND_PRIORITY.get(asset_kind, 0)
    return (kind_priority, source_bonus, width * height, width + height)


def is_content_image_candidate(candidate: dict[str, object]) -> bool:
    url = str(candidate.get("url") or "")
    source = str(candidate.get("source") or "")
    alt = str(candidate.get("alt") or "")
    class_name = str(candidate.get("class_name") or "")
    combined = " ".join([url, alt, class_name]).lower()
    if any(fragment in combined for fragment in IMAGE_BLOCKLIST_FRAGMENTS):
        return False
    width = int(candidate.get("width") or 0)
    height = int(candidate.get("height") or 0)
    if source != "meta" and width and height and min(width, height) < 80:
        return False
    return True


def is_content_asset_candidate(candidate: dict[str, object]) -> bool:
    asset_kind = str(candidate.get("asset_kind") or "")
    url = str(candidate.get("url") or "")
    if not asset_kind or not url:
        return False
    if asset_kind == "image":
        return is_content_image_candidate(candidate)
    combined = " ".join(
        [
            url,
            str(candidate.get("alt") or ""),
            str(candidate.get("label") or ""),
            str(candidate.get("class_name") or ""),
        ]
    ).lower()
    if any(fragment in combined for fragment in IMAGE_BLOCKLIST_FRAGMENTS):
        return False
    return True


def extract_asset_candidates(fragment: str, base_url: str) -> list[dict[str, object]]:
    parser = AssetCandidateParser(base_url)
    parser.feed(fragment or "")
    deduped: dict[str, dict[str, object]] = {}
    for candidate in parser.assets:
        if not is_content_asset_candidate(candidate):
            continue
        asset_url = str(candidate.get("url") or "")
        existing = deduped.get(asset_url)
        if not existing or asset_sort_key(candidate) > asset_sort_key(existing):
            deduped[asset_url] = candidate
    ranked = sorted(deduped.values(), key=asset_sort_key, reverse=True)
    return ranked[:20]


def extract_image_candidates(fragment: str, base_url: str) -> list[dict[str, object]]:
    return [candidate for candidate in extract_asset_candidates(fragment, base_url) if candidate.get("asset_kind") == "image"][:8]


def normalize_asset_candidates(
    candidates: list[dict[str, object]] | None,
    base_url: str,
) -> list[dict[str, object]]:
    deduped: dict[str, dict[str, object]] = {}
    for raw in candidates or []:
        asset_url = normalize_asset_url(str(raw.get("url") or ""), base_url)
        asset_kind = classify_asset_kind(
            asset_url,
            hinted_kind=str(raw.get("asset_kind") or ""),
            content_type=str(raw.get("content_type") or ""),
        )
        candidate = {
            "url": asset_url,
            "asset_kind": asset_kind,
            "alt": whitespace_compact(str(raw.get("alt") or "")),
            "label": whitespace_compact(str(raw.get("label") or "")),
            "class_name": whitespace_compact(str(raw.get("class_name") or "")),
            "width": int(raw.get("width") or 0),
            "height": int(raw.get("height") or 0),
            "source": str(raw.get("source") or "img"),
            "content_type": whitespace_compact(str(raw.get("content_type") or "")),
        }
        if not asset_url or not is_content_asset_candidate(candidate):
            continue
        existing = deduped.get(asset_url)
        if not existing or asset_sort_key(candidate) > asset_sort_key(existing):
            deduped[asset_url] = candidate
    return sorted(deduped.values(), key=asset_sort_key, reverse=True)[:20]


def normalize_image_candidates(
    candidates: list[dict[str, object]] | None,
    base_url: str,
) -> list[dict[str, object]]:
    return [candidate for candidate in normalize_asset_candidates(candidates, base_url) if candidate.get("asset_kind") == "image"][:8]


def extension_for_asset(url: str, asset_kind: str, content_type: str = "") -> str:
    for guessed in suffix_candidates(url):
        if asset_kind == "image" and guessed in IMAGE_EXTENSIONS:
            return ".jpg" if guessed == ".jpe" else guessed
        if asset_kind == "video" and guessed in VIDEO_EXTENSIONS:
            return guessed
        if asset_kind == "audio" and guessed in AUDIO_EXTENSIONS:
            return guessed
        if asset_kind == "document" and guessed in DOCUMENT_EXTENSIONS:
            return guessed
        if asset_kind == "archive" and guessed in ARCHIVE_EXTENSIONS:
            return guessed
        if asset_kind == "model" and guessed in MODEL_EXTENSIONS:
            return guessed
    if content_type:
        guessed_from_type = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if guessed_from_type:
            if guessed_from_type == ".jpe":
                return ".jpg"
            return guessed_from_type
    return {
        "image": ".jpg",
        "video": ".mp4",
        "audio": ".mp3",
        "document": ".pdf",
        "archive": ".zip",
        "model": ".bin",
    }.get(asset_kind, ".bin")


def relative_asset_path(asset_kind: str, filename: str) -> str:
    if asset_kind == "image":
        return f"images/{filename}"
    folder = asset_kind if asset_kind.endswith("s") else f"{asset_kind}s"
    return f"assets/{folder}/{filename}"


def asset_directory(item_dir: Path, asset_kind: str) -> Path:
    if asset_kind == "image":
        return item_dir / "images"
    folder = asset_kind if asset_kind.endswith("s") else f"{asset_kind}s"
    return item_dir / "assets" / folder


def download_asset_binary(
    session: requests.Session,
    url: str,
    headers: dict[str, str],
    max_bytes: int,
) -> tuple[bytes, str]:
    response = session.get(url, headers=headers, timeout=25, stream=True)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").strip()
    announced_size = int(response.headers.get("Content-Length", "0") or 0)
    if announced_size and announced_size > max_bytes:
        raise ValueError(f"asset too large: {announced_size} > {max_bytes}")

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"asset exceeded size limit: {total} > {max_bytes}")
        chunks.append(chunk)
    return b"".join(chunks), content_type


def download_asset_candidates(
    session: requests.Session,
    candidates: list[dict[str, object]],
    item_dir: Path,
    referer_url: str,
    limits: dict[str, int] | None = None,
) -> tuple[list[dict[str, object]], list[str], list[str], str, str]:
    manifest: list[dict[str, object]] = []
    asset_urls: list[str] = []
    asset_files: list[str] = []
    hero_image_url = ""
    hero_image_file = ""
    kind_seen: defaultdict[str, int] = defaultdict(int)
    effective_limits = dict(ASSET_DOWNLOAD_LIMITS)
    if limits:
        effective_limits.update({key: int(value) for key, value in limits.items()})

    for candidate in candidates:
        entry = dict(candidate)
        asset_url = str(entry.get("url") or "").strip()
        asset_kind = str(entry.get("asset_kind") or classify_asset_kind(asset_url))
        if not asset_url or not asset_kind:
            continue
        kind_seen[asset_kind] += 1
        entry["asset_kind"] = asset_kind
        entry["sequence"] = kind_seen[asset_kind]
        asset_urls.append(asset_url)
        if asset_kind == "image" and not hero_image_url:
            hero_image_url = asset_url

        headers = dict(REQUEST_HEADERS)
        if referer_url:
            headers["Referer"] = referer_url

        try:
            limit_for_kind = effective_limits.get(asset_kind, effective_limits.get("other", 1))
            if entry["sequence"] <= limit_for_kind and asset_kind in DOWNLOADABLE_ASSET_KINDS:
                content, content_type = download_asset_binary(
                    session,
                    asset_url,
                    headers,
                    ASSET_MAX_BYTES.get(asset_kind, ASSET_MAX_BYTES["other"]),
                )
                file_ext = extension_for_asset(asset_url, asset_kind, content_type)
                target_dir = asset_directory(item_dir, asset_kind)
                target_dir.mkdir(parents=True, exist_ok=True)
                file_path = target_dir / f"{entry['sequence']:02d}{file_ext}"
                file_path.write_bytes(content)
                relative_file = relative_asset_path(asset_kind, file_path.name)
                entry["file"] = relative_file
                entry["byte_size"] = len(content)
                entry["content_type"] = content_type
                entry["downloaded"] = True
                asset_files.append(relative_file)
                if asset_kind == "image" and not hero_image_file:
                    hero_image_file = relative_file
            else:
                entry["downloaded"] = False
                entry["download_skipped"] = True
                if asset_kind not in DOWNLOADABLE_ASSET_KINDS:
                    entry["download_reason"] = "link-only-kind"
                else:
                    entry["download_reason"] = "per-kind-limit"
        except Exception as exc:  # noqa: BLE001
            entry["error"] = str(exc)

        manifest.append(entry)

    return manifest, asset_urls, asset_files, hero_image_url, hero_image_file


def render_asset_lines(
    asset_manifest: list[dict[str, object]],
    hero_image_url: str,
    hero_image_file: str,
) -> list[str]:
    if not asset_manifest:
        return []
    lines = [
        "## Assets",
        "",
        f"- Hero Image URL: {hero_image_url}" if hero_image_url else "",
        f"- Hero Image File: {hero_image_file}" if hero_image_file else "",
    ]
    for index, entry in enumerate(asset_manifest, start=1):
        asset_url = str(entry.get("url") or "")
        asset_file = str(entry.get("file") or "")
        asset_kind = str(entry.get("asset_kind") or "")
        source = str(entry.get("source") or "")
        status = "downloaded" if asset_file else f"unavailable: {entry.get('error', entry.get('download_reason', 'not-downloaded'))}"
        bits = [f"{index}.", status]
        if asset_kind:
            bits.append(asset_kind)
        if source:
            bits.append(source)
        if asset_file:
            bits.append(asset_file)
        if asset_url:
            bits.append(asset_url)
        lines.append(" | ".join(bits))
    lines.append("")
    return [line for line in lines if line != ""]


def meta_content(html: str, key: str, attr: str = "property") -> str:
    pattern = re.compile(
        rf'<meta[^>]+{attr}=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']',
        re.I,
    )
    match = pattern.search(html)
    return unescape(match.group(1)).strip() if match else ""


def regex_capture(html: str, pattern: str) -> str:
    match = re.search(pattern, html, re.I | re.S)
    if not match:
        return ""
    return unescape(match.group(1)).strip()


def request_url(session: requests.Session, url: str, timeout: int = 25) -> requests.Response:
    response = session.get(url, headers=REQUEST_HEADERS, timeout=timeout)
    response.raise_for_status()
    return response


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class ArchiveResult:
    kind: str
    url: str
    final_url: str
    status: str
    method: str
    title: str
    excerpt: str
    note: str
    files: list[str]
    source_author: str = ""
    published_at: str = ""
    platform_id: str = ""
    text_chars: int = 0
    blocked_reason: str = ""
    usable_for_scoring: bool = False
    discovery_only: bool = False
    duplicate_key: str = ""
    content_hash: str = ""
    content_simhash: str = ""
    extraction_confidence: float = 0.0
    asset_count: int = 0
    asset_urls: list[str] | None = None
    asset_files: list[str] | None = None
    asset_type_counts: dict[str, int] | None = None
    image_count: int = 0
    image_urls: list[str] | None = None
    image_files: list[str] | None = None
    hero_image_url: str = ""
    hero_image_file: str = ""


@dataclass
class BrowserCapture:
    final_url: str
    title: str
    text: str
    html: str
    author: str
    published_at: str
    note: str
    method: str
    files: list[str]
    source_selector: str = ""
    asset_candidates: list[dict[str, object]] | None = None


def whitespace_compact(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text or "")).strip()


def non_whitespace_chars(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def unwrap_mirror_text(text: str) -> str:
    value = (text or "").strip()
    if "Markdown Content:" not in value:
        return value
    _, _, remainder = value.partition("Markdown Content:")
    return remainder.strip() or value


def normalize_body_text(text: str) -> str:
    value = unwrap_mirror_text(text)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"\n{3,}", "\n\n", value)
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def iso_from_epoch(value: str) -> str:
    raw = (value or "").strip()
    if not raw.isdigit():
        return ""
    try:
        return datetime.fromtimestamp(int(raw), timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return ""


def extract_platform_id(kind: str, url: str, final_url: str = "") -> str:
    target = final_url or url
    if kind == "x":
        match = re.search(r"/status/(\d+)", target)
        return match.group(1) if match else ""
    if kind == "zhihu":
        match = re.search(r"/p/(\d+)", target)
        return match.group(1) if match else ""
    if kind == "wechat":
        parsed = urlparse(target)
        if parsed.path.startswith("/s/"):
            return parsed.path.removeprefix("/s/").strip("/")
        return parsed.query or parsed.path.strip("/")
    if kind == "xueqiu":
        match = re.search(r"/(\d{6,})", target)
        return match.group(1) if match else ""
    return urlparse(target).path.strip("/")


def similarity_tokens(text: str) -> list[str]:
    compact = whitespace_compact(text)
    ascii_tokens = re.findall(r"[A-Za-z0-9_]{2,}", compact.lower())
    han_tokens: list[str] = []
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", compact):
        if len(chunk) <= 3:
            han_tokens.append(chunk)
            continue
        for idx in range(len(chunk) - 1):
            han_tokens.append(chunk[idx : idx + 2])
    return ascii_tokens + han_tokens


def compute_simhash(text: str) -> str:
    tokens = similarity_tokens(text)
    if not tokens:
        return ""
    vector = [0] * 64
    for token in tokens:
        digest = int(hashlib.sha1(token.encode("utf-8")).hexdigest()[:16], 16)
        for bit in range(64):
            vector[bit] += 1 if digest & (1 << bit) else -1
    value = 0
    for bit, score in enumerate(vector):
        if score >= 0:
            value |= 1 << bit
    return f"{value:016x}"


def detect_blocked_reason(kind: str, final_url: str, title: str, text: str, original_url: str = "") -> str:
    combined = " ".join([final_url or "", title or "", (text or "")[:1600]]).lower()
    match = ""

    if kind == "x":
        for fragment in [
            "something went wrong",
            "page isn't available",
            "sign in to x",
            "log in to twitter",
            "this page doesn",
        ]:
            if fragment in combined:
                return fragment

    if kind == "wechat":
        for fragment in [
            "wappoc_appmsgcaptcha",
            "appmsgcaptcha",
            "captcha",
            "人机验证",
            "验证码",
            "为了保护你的网络安全",
            "异常访问",
            "该内容已被发布者删除",
            "此内容因违规无法查看",
            "微信公众平台",
        ]:
            if fragment.lower() in combined:
                match = fragment
                break
        if match and non_whitespace_chars(text) < 320:
            return match
        return ""

    if kind == "zhihu":
        for fragment in [
            "知乎，让每一次点击都充满意义",
            "登录知乎",
            "加入知乎",
            "下载知乎app",
            "无障碍登录",
            "验证码",
            "安全验证",
            "当前内容暂不可见",
            "该回答已被删除",
            "该文章已被删除",
        ]:
            if fragment.lower() in combined:
                return fragment
        return ""

    if kind == "xueqiu":
        if "登录" in title and non_whitespace_chars(text) < 180:
            return "login-required"
        return ""

    if kind == "xiaohongshu":
        original_path = urlparse(original_url).path or ""
        final_path = urlparse(final_url).path or ""
        if re.search(r"^/explore/[^/]+", original_path) and final_path.rstrip("/") == "/explore":
            return "redirected-to-explore"
        for fragment in [
            "/404",
            "页面不见了",
            "当前笔记暂时无法浏览",
            "securitycompromiseerror",
            "anonymous access to domain www.xiaohongshu.com blocked",
            "登录后推荐更懂你的笔记",
            "请在手机上确认",
            "手机号登录",
        ]:
            if fragment.lower() in combined:
                return fragment
    return ""


def assessment_for_result(
    *,
    kind: str,
    url: str,
    final_url: str,
    method: str,
    title: str,
    text: str,
    author: str = "",
    published_at: str = "",
) -> dict[str, object]:
    normalized_text = normalize_body_text(text)
    text_chars = non_whitespace_chars(normalized_text)
    platform_id = extract_platform_id(kind, url, final_url)
    content_hash = hashlib.sha1(normalized_text.encode("utf-8")).hexdigest()[:16] if normalized_text else ""
    content_simhash = compute_simhash(normalized_text)
    duplicate_key = f"{kind}:{platform_id}" if platform_id else f"{kind}:{content_hash}" if content_hash else f"{kind}:{hashlib.sha1(canonicalize_url(url).encode('utf-8')).hexdigest()[:16]}"
    blocked_reason = detect_blocked_reason(kind, final_url, title, normalized_text, original_url=url)
    min_ok = MIN_OK_TEXT_CHARS.get(kind, 120)
    min_scoring = MIN_SCORING_TEXT_CHARS.get(kind, min_ok)
    has_metadata = bool(author.strip() or published_at.strip())
    discovery_only = False

    if blocked_reason:
        status = "failed" if text_chars < max(min_ok // 2, 20) else "partial"
        discovery_only = True
    elif text_chars == 0:
        status = "failed"
        discovery_only = True
    elif text_chars < min_ok:
        status = "partial"
        discovery_only = True
    else:
        status = "ok"
        if text_chars < min_scoring or (not has_metadata and text_chars < int(min_scoring * 1.4)):
            discovery_only = True

    usable_for_scoring = status == "ok" and not discovery_only
    base_confidence = METHOD_CONFIDENCE.get(method, 0.5)
    length_bonus = min(text_chars / max(min_scoring, 1), 1.0) * 0.18
    metadata_bonus = 0.06 if has_metadata else 0.0
    penalty = 0.0
    if discovery_only:
        penalty += 0.18
    if blocked_reason:
        penalty += 0.45
    extraction_confidence = max(0.0, min(1.0, base_confidence + length_bonus + metadata_bonus - penalty))

    return {
        "status": status,
        "text": normalized_text,
        "text_chars": text_chars,
        "blocked_reason": blocked_reason,
        "usable_for_scoring": usable_for_scoring,
        "discovery_only": discovery_only,
        "duplicate_key": duplicate_key,
        "platform_id": platform_id,
        "content_hash": content_hash,
        "content_simhash": content_simhash,
        "extraction_confidence": round(extraction_confidence, 3),
    }


def asset_type_counts(manifest: list[dict[str, object]]) -> dict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    for entry in manifest:
        kind = str(entry.get("asset_kind") or "")
        if kind:
            counts[kind] += 1
    return dict(sorted(counts.items()))


def render_markdown_header(title: str, url: str, final_url: str, method: str, note: str) -> list[str]:
    lines = [f"# {title or 'Untitled'}", "", f"- URL: {url}", f"- Final URL: {final_url}", f"- Method: {method}"]
    if note:
        lines.append(f"- Note: {note}")
    lines.append("")
    return lines


def render_quality_lines(result: ArchiveResult) -> list[str]:
    asset_types = ", ".join(f"{kind}:{count}" for kind, count in sorted((result.asset_type_counts or {}).items()))
    lines = [
        f"- Status: {result.status}",
        f"- Text Chars: {result.text_chars}",
        f"- Usable For Scoring: {'yes' if result.usable_for_scoring else 'no'}",
        f"- Discovery Only: {'yes' if result.discovery_only else 'no'}",
        f"- Extraction Confidence: {result.extraction_confidence:.3f}",
        f"- Asset Count: {result.asset_count}" if result.asset_count else "",
        f"- Asset Types: {asset_types}" if asset_types else "",
        f"- Image Count: {result.image_count}" if result.image_count else "",
        f"- Hero Image URL: {result.hero_image_url}" if result.hero_image_url else "",
        f"- Hero Image File: {result.hero_image_file}" if result.hero_image_file else "",
        f"- Duplicate Key: {result.duplicate_key}" if result.duplicate_key else "",
        f"- Platform ID: {result.platform_id}" if result.platform_id else "",
        f"- Content Hash: {result.content_hash}" if result.content_hash else "",
        f"- Content SimHash: {result.content_simhash}" if result.content_simhash else "",
        f"- Blocked Reason: {result.blocked_reason}" if result.blocked_reason else "",
        f"- Author: {result.source_author}" if result.source_author else "",
        f"- Published At: {result.published_at}" if result.published_at else "",
        "",
    ]
    return [line for line in lines if line != ""]


def render_x_reply_context_lines(payload: dict) -> list[str]:
    reply_contexts = payload.get("reply_contexts")
    if not isinstance(reply_contexts, list) or not reply_contexts:
        return []

    lines = ["## Reply Context", ""]
    for index, reply in enumerate(reply_contexts, start=1):
        if not isinstance(reply, dict):
            continue
        author = normalize_body_text(str(reply.get("author") or ""))
        username = normalize_body_text(str(reply.get("username") or "")).lstrip("@")
        created_at = normalize_body_text(str(reply.get("created_at") or ""))
        reply_text = normalize_body_text(str(reply.get("text") or ""))
        if not reply_text:
            continue

        header_bits = [f"{index}."]
        if author:
            header_bits.append(author)
        if username:
            header_bits.append(f"@{username}")
        if created_at:
            header_bits.append(created_at)

        metrics: list[str] = []
        for label, key in (
            ("Likes", "likes"),
            ("Retweets", "retweets"),
            ("Replies", "replies"),
            ("Quotes", "quotes"),
        ):
            value = reply.get(key)
            if value not in ("", None, 0):
                metrics.append(f"{label} {value}")
        if metrics:
            header_bits.append(", ".join(metrics))

        lines.append(" | ".join(header_bits))
        lines.append(reply_text)
        lines.append("")
    return [line for line in lines if line != ""]


def image_manifest_subset(asset_manifest: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[str], list[str]]:
    images = [entry for entry in asset_manifest if str(entry.get("asset_kind") or "") == "image"]
    image_urls = [str(entry.get("url") or "") for entry in images if str(entry.get("url") or "")]
    image_files = [str(entry.get("file") or "") for entry in images if str(entry.get("file") or "")]
    return images, image_urls, image_files


def archive_x(session: requests.Session, url: str, item_dir: Path, prefetch: dict | None = None) -> ArchiveResult:
    files: list[str] = []
    final_url = url
    method = "x-reader"
    note = ""
    title = ""
    excerpt = ""

    # --- Try batch-prefetched data first (single browser session for all X URLs) ---
    payload: dict | None = None
    if prefetch:
        # Match by canonical URL — x-reader normalises to https://x.com/user/status/id
        for pf_url, pf_data in prefetch.items():
            if pf_url == url or pf_url.rstrip("/") == url.rstrip("/"):
                payload = pf_data
                break
        # Also try matching by tweet ID if URL form differs
        if payload is None:
            import re as _re
            m = _re.search(r"/status/(\d+)", url)
            if m:
                tid = m.group(1)
                for pf_url, pf_data in prefetch.items():
                    if tid in pf_url:
                        payload = pf_data
                        break

    if payload is not None:
        # Save raw JSON for provenance
        raw_path = item_dir / "raw.json"
        files.append(raw_path.name)
        write_text(raw_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

        if not payload.get("error"):
            method = payload.get("source", method)
            title = payload.get("author") or payload.get("username") or "X Post"
            final_url = payload.get("url") or final_url
            author = (payload.get("author") or payload.get("username") or "").strip()
            published_at = (payload.get("created_at") or "").strip()
            assessment = assessment_for_result(
                kind="x",
                url=url,
                final_url=final_url,
                method=method,
                title=title,
                text=payload.get("text") or "",
                author=author,
                published_at=published_at,
            )
            excerpt = str(assessment["text"])[:280]
            note = append_note(note, str(assessment["blocked_reason"]))
            asset_candidates = normalize_asset_candidates(
                [
                    {
                        "url": media_url,
                        "asset_kind": "image",
                        "alt": "",
                        "class_name": "",
                        "width": 0,
                        "height": 0,
                        "source": "x-media",
                        "label": "",
                        "content_type": "",
                    }
                    for media_url in payload.get("media_urls", [])
                ],
                final_url,
            )
            asset_manifest, asset_urls, asset_files, hero_image_url, hero_image_file = download_asset_candidates(
                session,
                asset_candidates,
                item_dir,
                final_url,
            )
            image_manifest, image_urls, image_files = image_manifest_subset(asset_manifest)
            if asset_manifest:
                asset_manifest_path = item_dir / "assets.json"
                files.append(asset_manifest_path.name)
                write_json(asset_manifest_path, {"assets": asset_manifest})
            if image_manifest:
                image_manifest_path = item_dir / "images.json"
                files.append(image_manifest_path.name)
                write_json(image_manifest_path, {"images": image_manifest})
            for asset_file in asset_files:
                if asset_file not in files:
                    files.append(asset_file)
            result = ArchiveResult(
                "x",
                url,
                final_url,
                str(assessment["status"]),
                method,
                title,
                excerpt,
                note,
                files,
                source_author=author,
                published_at=published_at,
                platform_id=str(assessment["platform_id"]),
                text_chars=int(assessment["text_chars"]),
                blocked_reason=str(assessment["blocked_reason"]),
                usable_for_scoring=bool(assessment["usable_for_scoring"]),
                discovery_only=bool(assessment["discovery_only"]),
                duplicate_key=str(assessment["duplicate_key"]),
                content_hash=str(assessment["content_hash"]),
                content_simhash=str(assessment["content_simhash"]),
                extraction_confidence=float(assessment["extraction_confidence"]),
                asset_count=len(asset_urls),
                asset_urls=asset_urls,
                asset_files=asset_files,
                asset_type_counts=asset_type_counts(asset_manifest),
                image_count=len(image_urls),
                image_urls=image_urls,
                image_files=image_files,
                hero_image_url=hero_image_url,
                hero_image_file=hero_image_file,
            )
            content_lines = render_markdown_header(title, url, final_url, method, note)
            content_lines.extend(render_quality_lines(result))
            content_lines.extend(
                [
                    f"- Username: @{payload.get('username', '')}" if payload.get("username") else "",
                    f"- Likes: {payload.get('likes', '')}" if payload.get("likes") not in ("", None) else "",
                    f"- Retweets: {payload.get('retweets', '')}" if payload.get("retweets") not in ("", None) else "",
                    f"- Replies: {payload.get('replies', '')}" if payload.get("replies") not in ("", None) else "",
                    f"- Quotes: {payload.get('quotes', '')}" if payload.get("quotes") not in ("", None, 0) else "",
                    f"- Thread replies: {payload.get('thread_count', 0)}" if payload.get("thread_count") else "",
                    f"- Reply context: {payload.get('reply_context_count', 0)}" if payload.get("reply_context_count") else "",
                    "",
                    "## Text",
                    "",
                    str(assessment["text"]),
                    "",
                ]
            )
            content_lines.extend(render_x_reply_context_lines(payload))
            content_lines.extend(render_asset_lines(asset_manifest, hero_image_url, hero_image_file))

            content_md = "\n".join(line for line in content_lines if line != "")
            md_path = item_dir / "content.md"
            files.append(md_path.name)
            write_text(md_path, content_md + "\n")
            return result

        note = append_note(note, payload.get("error", "x-reader batch: tweet unreadable"))

    # --- Fallback: run x-reader for a single URL (only if no prefetch hit) ---
    reader = x_reader_path()
    if payload is None and reader.exists():
        try:
            proc = subprocess.run(
                [sys.executable, str(reader), url],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(workspace_root()),
            )
            raw_output = (proc.stdout or proc.stderr or "").strip()
            if raw_output:
                raw_path = item_dir / "raw.json"
                if raw_path.name not in files:
                    files.append(raw_path.name)
                write_text(raw_path, raw_output + "\n")
            try:
                payload = json.loads(raw_output) if raw_output else None
            except json.JSONDecodeError:
                payload = None

            if payload and not payload.get("error"):
                method = payload.get("source", method)
                title = payload.get("author") or payload.get("username") or "X Post"
                final_url = payload.get("url") or final_url
                author = (payload.get("author") or payload.get("username") or "").strip()
                published_at = (payload.get("created_at") or "").strip()
                assessment = assessment_for_result(
                    kind="x",
                    url=url,
                    final_url=final_url,
                    method=method,
                    title=title,
                    text=payload.get("text") or "",
                    author=author,
                    published_at=published_at,
                )
                excerpt = str(assessment["text"])[:280]
                note = append_note(note, str(assessment["blocked_reason"]))
                asset_candidates = normalize_asset_candidates(
                    [
                        {
                            "url": media_url,
                            "asset_kind": "image",
                            "alt": "",
                            "class_name": "",
                            "width": 0,
                            "height": 0,
                            "source": "x-media",
                            "label": "",
                            "content_type": "",
                        }
                        for media_url in payload.get("media_urls", [])
                    ],
                    final_url,
                )
                asset_manifest, asset_urls, asset_files, hero_image_url, hero_image_file = download_asset_candidates(
                    session,
                    asset_candidates,
                    item_dir,
                    final_url,
                )
                image_manifest, image_urls, image_files = image_manifest_subset(asset_manifest)
                if asset_manifest:
                    asset_manifest_path = item_dir / "assets.json"
                    files.append(asset_manifest_path.name)
                    write_json(asset_manifest_path, {"assets": asset_manifest})
                if image_manifest:
                    image_manifest_path = item_dir / "images.json"
                    files.append(image_manifest_path.name)
                    write_json(image_manifest_path, {"images": image_manifest})
                for asset_file in asset_files:
                    if asset_file not in files:
                        files.append(asset_file)
                result = ArchiveResult(
                    "x",
                    url,
                    final_url,
                    str(assessment["status"]),
                    method,
                    title,
                    excerpt,
                    note,
                    files,
                    source_author=author,
                    published_at=published_at,
                    platform_id=str(assessment["platform_id"]),
                    text_chars=int(assessment["text_chars"]),
                    blocked_reason=str(assessment["blocked_reason"]),
                    usable_for_scoring=bool(assessment["usable_for_scoring"]),
                    discovery_only=bool(assessment["discovery_only"]),
                    duplicate_key=str(assessment["duplicate_key"]),
                    content_hash=str(assessment["content_hash"]),
                    content_simhash=str(assessment["content_simhash"]),
                    extraction_confidence=float(assessment["extraction_confidence"]),
                    asset_count=len(asset_urls),
                    asset_urls=asset_urls,
                    asset_files=asset_files,
                    asset_type_counts=asset_type_counts(asset_manifest),
                    image_count=len(image_urls),
                    image_urls=image_urls,
                    image_files=image_files,
                    hero_image_url=hero_image_url,
                    hero_image_file=hero_image_file,
                )
                content_lines = render_markdown_header(title, url, final_url, method, note)
                content_lines.extend(render_quality_lines(result))
                content_lines.extend(
                    [
                        f"- Username: @{payload.get('username', '')}" if payload.get("username") else "",
                        f"- Likes: {payload.get('likes', '')}" if payload.get("likes") not in ("", None) else "",
                        f"- Retweets: {payload.get('retweets', '')}" if payload.get("retweets") not in ("", None) else "",
                        f"- Replies: {payload.get('replies', '')}" if payload.get("replies") not in ("", None) else "",
                        f"- Quotes: {payload.get('quotes', '')}" if payload.get("quotes") not in ("", None, 0) else "",
                        f"- Thread replies: {payload.get('thread_count', 0)}" if payload.get("thread_count") else "",
                        f"- Reply context: {payload.get('reply_context_count', 0)}" if payload.get("reply_context_count") else "",
                        "",
                        "## Text",
                        "",
                        str(assessment["text"]),
                        "",
                    ]
                )
                content_lines.extend(render_x_reply_context_lines(payload))
                content_lines.extend(render_asset_lines(asset_manifest, hero_image_url, hero_image_file))
                content_md = "\n".join(line for line in content_lines if line != "")
                md_path = item_dir / "content.md"
                files.append(md_path.name)
                write_text(md_path, content_md + "\n")
                return result

            note = append_note(note, payload.get("error", "") if isinstance(payload, dict) else "x-reader failed")
        except Exception as exc:  # noqa: BLE001
            note = f"x-reader failed: {exc}"

    try:
        response = request_url(session, url)
        final_url = response.url or final_url
        html_path = item_dir / "source.html"
        files.append(html_path.name)
        write_text(html_path, response.text)
        title = meta_content(response.text, "og:title") or "X Post"
        excerpt = meta_content(response.text, "og:description", attr="property") or meta_content(response.text, "description", attr="name")
        if excerpt:
            assessment = assessment_for_result(
                kind="x",
                url=url,
                final_url=final_url,
                method="direct-html-meta",
                title=title,
                text=excerpt,
            )
            note = append_note(note, str(assessment["blocked_reason"]))
            result = ArchiveResult(
                "x",
                url,
                final_url,
                str(assessment["status"]),
                "direct-html-meta",
                title,
                str(assessment["text"])[:280],
                note,
                files,
                platform_id=str(assessment["platform_id"]),
                text_chars=int(assessment["text_chars"]),
                blocked_reason=str(assessment["blocked_reason"]),
                usable_for_scoring=bool(assessment["usable_for_scoring"]),
                discovery_only=bool(assessment["discovery_only"]),
                duplicate_key=str(assessment["duplicate_key"]),
                content_hash=str(assessment["content_hash"]),
                content_simhash=str(assessment["content_simhash"]),
                extraction_confidence=float(assessment["extraction_confidence"]),
            )
            md_path = item_dir / "content.md"
            files.append(md_path.name)
            lines = render_markdown_header(title, url, final_url, "direct-html-meta", note)
            lines.extend(render_quality_lines(result))
            lines.extend(["## Text", "", str(assessment["text"]), ""])
            write_text(md_path, "\n".join(lines))
            return result
    except Exception as exc:  # noqa: BLE001
        if note:
            note = f"{note}; direct fallback failed: {exc}"
        else:
            note = f"direct fallback failed: {exc}"

    assessment = assessment_for_result(
        kind="x",
        url=url,
        final_url=final_url,
        method=method,
        title=title or "X Post",
        text=excerpt,
    )
    note = append_note(note, str(assessment["blocked_reason"]))
    return ArchiveResult(
        "x",
        url,
        final_url,
        "failed",
        method,
        title or "X Post",
        str(assessment["text"])[:280],
        note,
        files,
        platform_id=str(assessment["platform_id"]),
        text_chars=int(assessment["text_chars"]),
        blocked_reason=str(assessment["blocked_reason"]),
        usable_for_scoring=False,
        discovery_only=True,
        duplicate_key=str(assessment["duplicate_key"]),
        content_hash=str(assessment["content_hash"]),
        content_simhash=str(assessment["content_simhash"]),
        extraction_confidence=float(assessment["extraction_confidence"]),
    )


def archive_wechat(session: requests.Session, url: str, item_dir: Path) -> ArchiveResult:
    return archive_html_like(session, url, item_dir, "wechat", os.environ.get("OPENCLAW_BROWSER_PROFILE", "openclaw"))


def archive_zhihu(session: requests.Session, url: str, item_dir: Path) -> ArchiveResult:
    return archive_html_like(session, url, item_dir, "zhihu", os.environ.get("OPENCLAW_BROWSER_PROFILE", "openclaw"))


def archive_xiaohongshu(session: requests.Session, url: str, item_dir: Path) -> ArchiveResult:
    return archive_html_like(session, url, item_dir, "xiaohongshu", os.environ.get("OPENCLAW_BROWSER_PROFILE", "openclaw"))


def archive_xueqiu(session: requests.Session, url: str, item_dir: Path) -> ArchiveResult:
    return archive_html_like(session, url, item_dir, "xueqiu", os.environ.get("OPENCLAW_BROWSER_PROFILE", "openclaw"))


def append_note(existing: str, extra: str) -> str:
    if not extra:
        return existing
    if not existing:
        return extra
    return f"{existing}; {extra}"


def openclaw_binary() -> str | None:
    return shutil.which("openclaw")


def run_openclaw_browser(browser_profile: str, args: list[str], timeout: int = 45) -> subprocess.CompletedProcess[str]:
    binary = openclaw_binary()
    if not binary:
        raise FileNotFoundError("openclaw CLI not found in PATH")
    return subprocess.run(
        [binary, "browser", "--browser-profile", browser_profile, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(workspace_root()),
    )


def parse_opened_target_id(output: str) -> str:
    for line in output.splitlines():
        if line.lower().startswith("id:"):
            return line.split(":", 1)[1].strip()
    return ""


def parse_media_output(output: str) -> Path | None:
    for line in output.splitlines():
        if line.startswith("MEDIA:"):
            return Path(line.split(":", 1)[1].strip()).expanduser()
    return None


def browser_capture_page(url: str, kind: str, item_dir: Path, browser_profile: str) -> BrowserCapture | None:
    target_id = ""
    files: list[str] = []

    try:
        opened = run_openclaw_browser(browser_profile, ["open", url], timeout=30)
        open_output = (opened.stdout or opened.stderr or "").strip()
        if opened.returncode != 0:
            raise RuntimeError(open_output or "browser open failed")
        target_id = parse_opened_target_id(open_output)
        if not target_id:
            raise RuntimeError("browser open returned no target id")

        run_openclaw_browser(browser_profile, ["wait", "--target-id", target_id, "--time", "2500"], timeout=10)

        selector_map = {
            "wechat": ["#js_content", "article", "main"],
            "zhihu": ["article", "main article", "main", ".RichContent", ".Post-RichTextContainer"],
            "xueqiu": ["article", "main article", "main"],
            "xiaohongshu": ["article", "main"],
        }
        selectors = selector_map.get(kind, ["article", "main", "body"])
        eval_fn = f"""
() => {{
  const selectors = {json.dumps(selectors, ensure_ascii=False)};
  const firstNode = (selectorList) => {{
    for (const selector of selectorList) {{
      const node = document.querySelector(selector);
      if (node) {{
        return {{ node, selector }};
      }}
    }}
    return {{ node: document.body, selector: 'body' }};
  }};
  const picked = firstNode(selectors);
  const node = picked.node;
  return {{
    title: document.title || '',
    url: location.href,
    author:
      (document.querySelector('#js_name') && document.querySelector('#js_name').innerText) ||
      (document.querySelector('[itemprop="author"]') && document.querySelector('[itemprop="author"]').innerText) ||
      (document.querySelector('meta[name="author"]') && document.querySelector('meta[name="author"]').content) ||
      '',
    publishedAt:
      (document.querySelector('meta[property="article:published_time"]') && document.querySelector('meta[property="article:published_time"]').content) ||
      (document.querySelector('meta[itemprop="datePublished"]') && document.querySelector('meta[itemprop="datePublished"]').content) ||
      (document.querySelector('time') && (document.querySelector('time').getAttribute('datetime') || document.querySelector('time').innerText)) ||
      '',
    text: ((node && node.innerText) || (document.body && document.body.innerText) || '').slice(0, 120000),
    html: ((node && node.innerHTML) || '').slice(0, 240000),
    sourceSelector: picked.selector,
    assets: [
      ...Array.from((node || document).querySelectorAll('img')).slice(0, 24).map((img) => {{
        const attrs = [img.currentSrc, img.getAttribute('data-original'), img.getAttribute('data-src'), img.getAttribute('src')].filter(Boolean);
        const src = attrs[0] || '';
        if (!src) return null;
        return {{
          url: src,
          asset_kind: 'image',
          alt: img.getAttribute('alt') || '',
          class_name: img.getAttribute('class') || '',
          width: img.naturalWidth || img.width || 0,
          height: img.naturalHeight || img.height || 0,
          source: 'img',
          label: img.getAttribute('title') || '',
          content_type: ''
        }};
      }}).filter(Boolean),
      ...Array.from((node || document).querySelectorAll('video')).slice(0, 8).flatMap((video) => {{
        const items = [];
        const poster = video.getAttribute('poster') || '';
        if (poster) {{
          items.push({{
            url: poster,
            asset_kind: 'image',
            alt: '',
            class_name: video.getAttribute('class') || '',
            width: video.videoWidth || video.clientWidth || 0,
            height: video.videoHeight || video.clientHeight || 0,
            source: 'video-poster',
            label: video.getAttribute('title') || '',
            content_type: ''
          }});
        }}
        const srcs = [
          video.currentSrc,
          video.getAttribute('src'),
          ...Array.from(video.querySelectorAll('source')).map((source) => source.getAttribute('src') || '')
        ].filter(Boolean);
        for (const src of srcs) {{
          items.push({{
            url: src,
            asset_kind: 'video',
            alt: '',
            class_name: video.getAttribute('class') || '',
            width: video.videoWidth || video.clientWidth || 0,
            height: video.videoHeight || video.clientHeight || 0,
            source: 'video',
            label: video.getAttribute('title') || '',
            content_type: ''
          }});
        }}
        return items;
      }}),
      ...Array.from((node || document).querySelectorAll('audio')).slice(0, 8).flatMap((audio) => {{
        const srcs = [
          audio.currentSrc,
          audio.getAttribute('src'),
          ...Array.from(audio.querySelectorAll('source')).map((source) => source.getAttribute('src') || '')
        ].filter(Boolean);
        return srcs.map((src) => ({{
          url: src,
          asset_kind: 'audio',
          alt: '',
          class_name: audio.getAttribute('class') || '',
          width: 0,
          height: 0,
          source: 'audio',
          label: audio.getAttribute('title') || '',
          content_type: ''
        }}));
      }}),
      ...Array.from((node || document).querySelectorAll('a[href]')).slice(0, 60).map((anchor) => ({{
        url: anchor.getAttribute('href') || '',
        asset_kind: '',
        alt: '',
        class_name: anchor.getAttribute('class') || '',
        width: 0,
        height: 0,
        source: 'anchor',
        label: (anchor.getAttribute('title') || anchor.getAttribute('download') || anchor.innerText || '').slice(0, 200),
        content_type: anchor.getAttribute('type') || ''
      }}))
    ],
    metaTitle:
      (document.querySelector('meta[property="og:title"]') && document.querySelector('meta[property="og:title"]').content) || '',
    metaDescription:
      (document.querySelector('meta[property="og:description"]') && document.querySelector('meta[property="og:description"]').content) ||
      (document.querySelector('meta[name="description"]') && document.querySelector('meta[name="description"]').content) ||
      '',
    metaImage:
      (document.querySelector('meta[property="og:image"]') && document.querySelector('meta[property="og:image"]').content) ||
      (document.querySelector('meta[name="twitter:image"]') && document.querySelector('meta[name="twitter:image"]').content) ||
      ''
  }};
}}
"""
        evaluated = run_openclaw_browser(
            browser_profile,
            ["evaluate", "--target-id", target_id, "--fn", eval_fn],
            timeout=30,
        )
        eval_output = (evaluated.stdout or evaluated.stderr or "").strip()
        if evaluated.returncode != 0:
            raise RuntimeError(eval_output or "browser evaluate failed")

        payload = json.loads(eval_output)
        asset_candidates = payload.get("assets") if isinstance(payload.get("assets"), list) else []
        meta_image = normalize_image_url(str(payload.get("metaImage") or ""), str(payload.get("url") or url))
        if meta_image:
            asset_candidates = [
                {
                    "url": meta_image,
                    "asset_kind": "image",
                    "alt": "",
                    "class_name": "",
                    "width": 0,
                    "height": 0,
                    "source": "meta",
                    "label": "meta-image",
                    "content_type": "",
                },
                *asset_candidates,
            ]
        browser_json_path = item_dir / "browser.json"
        write_json(browser_json_path, payload)
        files.append(browser_json_path.name)
        html_fragment = (payload.get("html") or "").strip()
        if html_fragment:
            html_fragment_path = item_dir / "content.html"
            write_text(html_fragment_path, html_fragment + "\n")
            files.append(html_fragment_path.name)

        screenshot = run_openclaw_browser(
            browser_profile,
            ["screenshot", target_id, "--full-page"],
            timeout=60,
        )
        shot_output = (screenshot.stdout or screenshot.stderr or "").strip()
        if screenshot.returncode == 0:
            media_path = parse_media_output(shot_output)
            if media_path and media_path.exists():
                suffix = media_path.suffix or ".jpg"
                local_shot = item_dir / f"browser{suffix}"
                shutil.copy2(media_path, local_shot)
                files.append(local_shot.name)

        title = (payload.get("title") or payload.get("metaTitle") or "").strip()
        text = (payload.get("text") or payload.get("metaDescription") or "").strip()
        final_url = (payload.get("url") or url).strip()
        author = (payload.get("author") or "").strip()
        published_at = (payload.get("publishedAt") or "").strip()
        return BrowserCapture(
            final_url=final_url,
            title=title or f"{kind.title()} Source",
            text=text,
            html=html_fragment,
            author=author,
            published_at=published_at,
            note=f"browser fallback via profile {browser_profile}",
            method=f"browser:{browser_profile}",
            files=files,
            source_selector=(payload.get("sourceSelector") or "").strip(),
            asset_candidates=normalize_asset_candidates(asset_candidates, str(payload.get("url") or url)),
        )
    except Exception as exc:  # noqa: BLE001
        error_path = item_dir / "browser-error.txt"
        write_text(error_path, f"{exc}\n")
        files.append(error_path.name)
        return BrowserCapture(
            final_url=url,
            title="",
            text="",
            html="",
            author="",
            published_at="",
            note=f"browser fallback failed: {exc}",
            method=f"browser:{browser_profile}",
            files=files,
            asset_candidates=[],
        )
    finally:
        if target_id:
            try:
                run_openclaw_browser(browser_profile, ["close", target_id], timeout=10)
            except Exception:  # noqa: BLE001
                pass


def archive_html_like(session: requests.Session, url: str, item_dir: Path, kind: str, browser_profile: str) -> ArchiveResult:
    files: list[str] = []
    title = ""
    excerpt = ""
    note = ""
    author = ""
    published_at = ""
    final_url = url
    text = ""
    html_fragment = ""
    method = "direct-html"
    asset_candidates: list[dict[str, object]] = []

    try:
        response = request_url(session, url)
        final_url = response.url or url
        html = response.text
        html_path = item_dir / "source.html"
        files.append(html_path.name)
        write_text(html_path, html)

        title = (
            meta_content(html, "og:title")
            or meta_content(html, "twitter:title", attr="name")
            or regex_capture(html, r"<title[^>]*>(.*?)</title>")
            or regex_capture(html, r"var msg_title = ['\"](.*?)['\"];")
            or f"{kind.title()} Source"
        )

        if kind == "wechat":
            html_fragment = extract_section_html_by_id(html, "js_content")
            if html_fragment:
                html_fragment_path = item_dir / "content.html"
                files.append(html_fragment_path.name)
                write_text(html_fragment_path, html_fragment + "\n")
                text = html_to_markdown(html_fragment)
                asset_candidates = extract_asset_candidates(html_fragment, final_url)
            if not text:
                text = extract_section_by_id(html, "js_content")
            if not text:
                text = regex_capture(html, r"var msg_desc = ['\"](.*?)['\"];")
            author = regex_capture(html, r"var nickname = htmlDecode\(['\"](.*?)['\"]\);")
            published_at = (
                meta_content(html, "article:published_time")
                or iso_from_epoch(regex_capture(html, r"var\s+ct\s*=\s*['\"]?(\d+)['\"]?;"))
                or iso_from_epoch(regex_capture(html, r"publish_time\s*=\s*['\"]?(\d+)['\"]?"))
            )
        else:
            published_at = (
                meta_content(html, "article:published_time")
                or meta_content(html, "og:published_time")
                or regex_capture(html, r'"datePublished":"(.*?)"')
                or regex_capture(html, r'<meta[^>]+itemprop=["\']datePublished["\'][^>]+content=["\']([^"\']+)')
            )
            text = (
                meta_content(html, "og:description")
                or meta_content(html, "description", attr="name")
                or regex_capture(html, r'"description":"(.*?)"')
                or ""
            )
            asset_candidates = extract_asset_candidates(html, final_url)
            if len(text) < 120:
                text = strip_html(html)

        text = normalize_body_text(text)
        excerpt = text[:280]
    except Exception as exc:  # noqa: BLE001
        note = f"direct fetch failed: {exc}"

    if non_whitespace_chars(text) < MIN_OK_TEXT_CHARS.get(kind, 120):
        mirror_url = "https://r.jina.ai/http://" + url.removeprefix("https://").removeprefix("http://")
        try:
            mirror = request_url(session, mirror_url)
            mirror_text = mirror.text.strip()
            if mirror_text:
                mirror_path = item_dir / "mirror.txt"
                files.append(mirror_path.name)
                write_text(mirror_path, mirror_text + "\n")
            if mirror_text and not mirror_text.lstrip().startswith("{\"data\":null"):
                text = normalize_body_text(mirror_text)
                excerpt = text[:280]
                method = "r.jina.ai"
            elif not note:
                note = "mirror returned no readable text"
        except Exception as exc:  # noqa: BLE001
            if note:
                note = f"{note}; mirror failed: {exc}"
            else:
                note = f"mirror failed: {exc}"

    blocked_reason = detect_blocked_reason(kind, final_url, title, text, original_url=url)
    should_try_browser = kind in {"wechat", "zhihu", "xueqiu"} and (
        bool(blocked_reason) or non_whitespace_chars(text) < MIN_OK_TEXT_CHARS.get(kind, 120)
    )
    if should_try_browser:
        browser = browser_capture_page(url, kind, item_dir, browser_profile)
        if browser:
            for browser_file in browser.files:
                if browser_file not in files:
                    files.append(browser_file)
            if browser.note:
                note = append_note(note, browser.note)
            if browser.author and not author:
                author = browser.author
            if browser.published_at and not published_at:
                published_at = browser.published_at
            browser_text = html_to_markdown(browser.html) if browser.html else normalize_body_text(browser.text)
            browser_assets = normalize_asset_candidates(browser.asset_candidates, browser.final_url or final_url)
            browser_blocked = detect_blocked_reason(kind, browser.final_url, browser.title, browser_text, original_url=url)
            if browser.source_selector:
                note = append_note(note, f"browser selector {browser.source_selector}")
            if browser_text and (not browser_blocked) and (
                bool(blocked_reason) or non_whitespace_chars(browser_text) > non_whitespace_chars(text)
            ):
                final_url = browser.final_url or final_url
                title = browser.title or title
                text = browser_text
                excerpt = browser_text[:280]
                method = browser.method
                blocked_reason = ""
                if browser_assets:
                    asset_candidates = browser_assets
            elif browser_blocked:
                blocked_reason = browser_blocked

    assessment = assessment_for_result(
        kind=kind,
        url=url,
        final_url=final_url,
        method=method,
        title=title,
        text=text,
        author=author,
        published_at=published_at,
    )
    note = append_note(note, str(assessment["blocked_reason"]))
    asset_manifest, asset_urls, asset_files, hero_image_url, hero_image_file = download_asset_candidates(
        session,
        asset_candidates,
        item_dir,
        final_url,
    )
    image_manifest, image_urls, image_files = image_manifest_subset(asset_manifest)
    if asset_manifest:
        asset_manifest_path = item_dir / "assets.json"
        files.append(asset_manifest_path.name)
        write_json(asset_manifest_path, {"assets": asset_manifest})
    if image_manifest:
        image_manifest_path = item_dir / "images.json"
        files.append(image_manifest_path.name)
        write_json(image_manifest_path, {"images": image_manifest})
    for asset_file in asset_files:
        if asset_file not in files:
            files.append(asset_file)
    result = ArchiveResult(
        kind,
        url,
        final_url,
        str(assessment["status"]),
        method,
        title,
        str(assessment["text"])[:280],
        note,
        files,
        source_author=author,
        published_at=published_at,
        platform_id=str(assessment["platform_id"]),
        text_chars=int(assessment["text_chars"]),
        blocked_reason=str(assessment["blocked_reason"]),
        usable_for_scoring=bool(assessment["usable_for_scoring"]),
        discovery_only=bool(assessment["discovery_only"]),
        duplicate_key=str(assessment["duplicate_key"]),
        content_hash=str(assessment["content_hash"]),
        content_simhash=str(assessment["content_simhash"]),
        extraction_confidence=float(assessment["extraction_confidence"]),
        asset_count=len(asset_urls),
        asset_urls=asset_urls,
        asset_files=asset_files,
        asset_type_counts=asset_type_counts(asset_manifest),
        image_count=len(image_urls),
        image_urls=image_urls,
        image_files=image_files,
        hero_image_url=hero_image_url,
        hero_image_file=hero_image_file,
    )

    md_path = item_dir / "content.md"
    files.append(md_path.name)
    lines = render_markdown_header(title, url, final_url, method, note)
    lines.extend(render_quality_lines(result))
    lines.extend(["## Text", "", str(assessment["text"]) or excerpt or "", ""])
    lines.extend(render_asset_lines(asset_manifest, hero_image_url, hero_image_file))
    write_text(md_path, "\n".join(lines))
    return result


def looks_blocked_or_generic(kind: str, final_url: str, title: str, text: str, original_url: str = "") -> bool:
    return bool(detect_blocked_reason(kind, final_url, title, text, original_url=original_url))


def collect_urls(report: Path | None, urls_file: Path | None, extra_urls: Iterable[str], max_per_kind: dict[str, int] | None = None) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    kind_counts: defaultdict[str, int] = defaultdict(int)

    def add(url: str) -> None:
        clean = canonicalize_url(trim_url_token(url))
        kind = detect_kind(clean)
        if not kind or clean in seen:
            return
        limit = (max_per_kind or {}).get(kind)
        if limit is not None and kind_counts[kind] >= limit:
            return
        seen.add(clean)
        kind_counts[kind] += 1
        ordered.append(clean)

    if report and report.exists():
        for url in extract_urls(report.read_text(encoding="utf-8", errors="ignore")):
            add(url)

    if urls_file and urls_file.exists():
        for raw_line in urls_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            for url in extract_urls(line):
                add(url)

    for url in extra_urls:
        add(url)

    return ordered


def _prefetch_x_batch(x_urls: list[str], out_dir: Path) -> dict[str, dict]:
    """Pre-read all X URLs in a single browser session via x-reader batch mode.

    Returns a dict mapping each URL to its x-reader result JSON.
    This avoids launching a separate browser per URL (slow + riskier for ban).
    """
    reader = x_reader_path()
    if not reader.exists() or not x_urls:
        return {}

    batch_file = out_dir / "_x_batch_urls.txt"
    results_file = out_dir / "_x_batch_results.json"
    batch_file.write_text("\n".join(x_urls) + "\n", encoding="utf-8")

    try:
        proc = subprocess.run(
            [
                sys.executable, str(reader),
                "--batch", str(batch_file),
                "--out", str(results_file),
                # Source-pack archiving only hits the final shortlist URLs, so
                # we can use a tighter delay window than exploratory browsing.
                "--min-delay", "3",
                "--max-delay", "6",
            ],
            capture_output=True,
            text=True,
            timeout=600,  # leave room for login walls / slow thread loads
            cwd=str(workspace_root()),
        )
        if proc.returncode != 0:
            print(f"[archive] x-reader batch returned code {proc.returncode}: {(proc.stderr or '')[:200]}", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("[archive] x-reader batch timed out", file=sys.stderr)
    except Exception as exc:
        print(f"[archive] x-reader batch failed: {exc}", file=sys.stderr)

    results: dict[str, dict] = {}
    if results_file.exists():
        try:
            raw = json.loads(results_file.read_text(encoding="utf-8"))
            items = raw if isinstance(raw, list) else [raw]
            for item in items:
                u = item.get("url", "")
                if u:
                    results[u] = item
        except (json.JSONDecodeError, KeyError):
            pass

    # Cleanup temp files
    batch_file.unlink(missing_ok=True)
    results_file.unlink(missing_ok=True)
    return results


def archive_sources(
    report: Path | None,
    urls_file: Path | None,
    out_dir: Path,
    extra_urls: list[str],
    max_per_kind: dict[str, int] | None = None,
    inter_request_delay_s: float = 0.0,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    urls = collect_urls(report, urls_file, extra_urls, max_per_kind=max_per_kind)

    # --- Batch pre-fetch all X URLs in one browser session ---
    x_urls = [u for u in urls if detect_kind(u) == "x"]
    x_prefetch = _prefetch_x_batch(x_urls, out_dir) if x_urls else {}

    sources: list[dict] = []
    all_text_parts: list[str] = []

    for idx, url in enumerate(urls, start=1):
        kind = detect_kind(url)
        label = slugify(urlparse(url).path or urlparse(url).netloc)
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
        item_dir = out_dir / f"{idx:03d}-{kind}-{label}-{digest}"
        item_dir.mkdir(parents=True, exist_ok=True)

        if kind == "x":
            result = archive_x(session, url, item_dir, prefetch=x_prefetch)
        elif kind == "wechat":
            result = archive_html_like(session, url, item_dir, "wechat", os.environ.get("OPENCLAW_BROWSER_PROFILE", "openclaw"))
        elif kind == "zhihu":
            result = archive_html_like(session, url, item_dir, "zhihu", os.environ.get("OPENCLAW_BROWSER_PROFILE", "openclaw"))
        elif kind == "xiaohongshu":
            result = archive_html_like(session, url, item_dir, "xiaohongshu", os.environ.get("OPENCLAW_BROWSER_PROFILE", "openclaw"))
        elif kind == "xueqiu":
            result = archive_html_like(session, url, item_dir, "xueqiu", os.environ.get("OPENCLAW_BROWSER_PROFILE", "openclaw"))
        else:
            continue

        meta = {
            "kind": result.kind,
            "url": result.url,
            "final_url": result.final_url,
            "status": result.status,
            "method": result.method,
            "title": result.title,
            "excerpt": result.excerpt,
            "note": result.note,
            "files": result.files,
            "source_author": result.source_author,
            "published_at": result.published_at,
            "platform_id": result.platform_id,
            "text_chars": result.text_chars,
            "blocked_reason": result.blocked_reason,
            "usable_for_scoring": result.usable_for_scoring,
            "discovery_only": result.discovery_only,
            "duplicate_key": result.duplicate_key,
            "content_hash": result.content_hash,
            "content_simhash": result.content_simhash,
            "extraction_confidence": result.extraction_confidence,
            "asset_count": result.asset_count,
            "asset_urls": result.asset_urls or [],
            "asset_files": result.asset_files or [],
            "asset_type_counts": result.asset_type_counts or {},
            "image_count": result.image_count,
            "image_urls": result.image_urls or [],
            "image_files": result.image_files or [],
            "hero_image_url": result.hero_image_url,
            "hero_image_file": result.hero_image_file,
            "archived_at": now_iso(),
        }
        if inter_request_delay_s > 0 and idx < len(urls):
            time.sleep(inter_request_delay_s)
        write_json(item_dir / "meta.json", meta)
        sources.append({**meta, "dir": item_dir.name})

        content_path = item_dir / "content.md"
        if content_path.exists():
            content = content_path.read_text(encoding="utf-8", errors="ignore").strip()
            if content:
                all_text_parts.append(content)

    ok_count = sum(1 for item in sources if item["status"] == "ok")
    partial_count = sum(1 for item in sources if item["status"] == "partial")
    failed_count = sum(1 for item in sources if item["status"] == "failed")
    usable_count = sum(1 for item in sources if item.get("usable_for_scoring"))
    discovery_only_count = sum(1 for item in sources if item.get("discovery_only"))
    asset_count = sum(int(item.get("asset_count", 0) or 0) for item in sources)
    image_count = sum(int(item.get("image_count", 0) or 0) for item in sources)

    summary = {
        "generated_at": now_iso(),
        "report": str(report) if report else None,
        "urls_file": str(urls_file) if urls_file else None,
        "source_count": len(sources),
        "ok_count": ok_count,
        "partial_count": partial_count,
        "failed_count": failed_count,
        "usable_for_scoring_count": usable_count,
        "discovery_only_count": discovery_only_count,
        "asset_count": asset_count,
        "image_count": image_count,
        "sources": sources,
    }
    write_json(out_dir / "index.json", summary)

    readme_lines = [
        "# Source Pack",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Report: {summary['report'] or '(none)'}",
        f"- URLs File: {summary['urls_file'] or '(none)'}",
        f"- Total Sources: {summary['source_count']}",
        f"- OK: {ok_count}",
        f"- Partial: {partial_count}",
        f"- Failed: {failed_count}",
        f"- Usable For Scoring: {usable_count}",
        f"- Discovery Only: {discovery_only_count}",
        f"- Assets: {asset_count}",
        f"- Images: {image_count}",
        "",
    ]
    for item in sources:
        readme_lines.extend(
            [
                f"## {item['title'] or item['dir']}",
                "",
                f"- Kind: {item['kind']}",
                f"- Status: {item['status']}",
                f"- Method: {item['method']}",
                f"- Usable For Scoring: {'yes' if item.get('usable_for_scoring') else 'no'}",
                f"- Discovery Only: {'yes' if item.get('discovery_only') else 'no'}",
                f"- Text Chars: {item.get('text_chars', 0)}",
                f"- Asset Count: {item.get('asset_count', 0)}",
                f"- Asset Types: {', '.join(f'{kind}:{count}' for kind, count in sorted((item.get('asset_type_counts') or {}).items()))}" if item.get("asset_type_counts") else "",
                f"- Image Count: {item.get('image_count', 0)}",
                f"- Hero Image URL: {item.get('hero_image_url')}" if item.get("hero_image_url") else "",
                f"- Hero Image File: {item.get('hero_image_file')}" if item.get("hero_image_file") else "",
                f"- URL: {item['url']}",
                f"- Final URL: {item['final_url']}",
                f"- Files: {', '.join(item['files'])}" if item["files"] else "- Files: (none)",
                f"- Directory: {item['dir']}",
            ]
        )
        if item.get("source_author"):
            readme_lines.append(f"- Author: {item['source_author']}")
        if item.get("published_at"):
            readme_lines.append(f"- Published At: {item['published_at']}")
        if item.get("duplicate_key"):
            readme_lines.append(f"- Duplicate Key: {item['duplicate_key']}")
        if item.get("blocked_reason"):
            readme_lines.append(f"- Blocked Reason: {item['blocked_reason']}")
        if item.get("note"):
            readme_lines.append(f"- Note: {item['note']}")
        if item.get("excerpt"):
            readme_lines.extend(["", "Excerpt:", "", item["excerpt"]])
        readme_lines.append("")
    write_text(out_dir / "README.md", "\n".join(readme_lines))

    if all_text_parts:
        write_text(out_dir / "all_text.md", "\n\n---\n\n".join(all_text_parts) + "\n")
    else:
        write_text(out_dir / "all_text.md", "")

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive social source text into a local source pack.")
    parser.add_argument("--report", help="Report markdown path to scan for social URLs.")
    parser.add_argument("--urls-file", help="Optional plain-text file with extra social URLs, one per line.")
    parser.add_argument("--out-dir", required=True, help="Directory to write the source pack into.")
    parser.add_argument("--url", action="append", default=[], help="Additional social URL to archive.")
    parser.add_argument(
        "--browser-profile",
        default=os.environ.get("OPENCLAW_BROWSER_PROFILE", "openclaw"),
        help="OpenClaw browser profile for browser fallback (default: OPENCLAW_BROWSER_PROFILE or openclaw).",
    )
    parser.add_argument(
        "--max-per-kind",
        type=int,
        default=int(os.environ.get("ARCHIVE_SOCIAL_MAX_PER_KIND", "3")),
        help="Hard cap per social source kind (default: ARCHIVE_SOCIAL_MAX_PER_KIND or 3).",
    )
    parser.add_argument(
        "--max-zhihu",
        type=int,
        default=int(os.environ.get("ARCHIVE_SOCIAL_MAX_ZHIHU", os.environ.get("ARCHIVE_SOCIAL_MAX_XIAOHONGSHU", "2"))),
        help="Hard cap for Zhihu URLs per run (default: ARCHIVE_SOCIAL_MAX_ZHIHU or 2).",
    )
    parser.add_argument(
        "--inter-request-delay",
        type=float,
        default=float(os.environ.get("ARCHIVE_SOCIAL_DELAY_SECONDS", "4.0")),
        help="Delay between archiving requests in seconds (default: ARCHIVE_SOCIAL_DELAY_SECONDS or 4.0).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.environ["OPENCLAW_BROWSER_PROFILE"] = args.browser_profile
    report = Path(args.report).resolve() if args.report else None
    urls_file = Path(args.urls_file).resolve() if args.urls_file else None
    out_dir = Path(args.out_dir).resolve()
    max_per_kind = {
        "x": args.max_per_kind,
        "wechat": args.max_per_kind,
        "zhihu": args.max_zhihu,
        "xueqiu": args.max_per_kind,
        "xiaohongshu": 0,
    }
    summary = archive_sources(
        report,
        urls_file,
        out_dir,
        list(args.url),
        max_per_kind=max_per_kind,
        inter_request_delay_s=args.inter_request_delay,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
