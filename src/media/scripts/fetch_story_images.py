#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)
URL_RE = re.compile(r'https?://[^\s<>\"]+')
PRIORITY_HINTS = ("原文链接", "[主信号链接", "[核验链接")
SOCIAL_LINE_HINTS = ("x出处", "x 来源", "x链接", "tweet", "status")
META_KEYS = {
    "og:image",
    "og:image:secure_url",
    "twitter:image",
    "twitter:image:src",
}
BAD_IMAGE_HINTS = ("logo", "avatar", "icon", "sprite", "badge")
SOCIAL_HOST_HINTS = (
    "x.com",
    "twitter.com",
    "t.co",
    "mobile.x.com",
    "mobile.twitter.com",
)
RICH_IMAGE_HINTS = (
    "hero",
    "cover",
    "featured",
    "header",
    "opengraph",
    "og-image",
    "lead",
    "thumbnail",
    "preview",
    "original_images",
)
LOW_VALUE_IMAGE_HINTS = (
    "chart",
    "graph",
    "table",
    "benchmark",
    "eval",
    "result",
    "results",
    "matrix",
    "dashboard",
    "paper",
    "system-card",
    "screenshot",
    "slide",
    "keyword_meta",
)
DIRECT_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
}


class ImageCandidateParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta_candidates: list[str] = []
        self.img_candidates: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() == "meta":
            key = (attr_map.get("property") or attr_map.get("name") or "").lower()
            content = attr_map.get("content", "").strip()
            if key in META_KEYS and content:
                self.meta_candidates.append(content)
            return
        if tag.lower() != "img":
            return
        for key in ("src", "data-src", "data-lazy-src", "data-original"):
            value = attr_map.get(key, "").strip()
            if value:
                self.img_candidates.append(value)
                break


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch story images from a report Markdown or explicit URLs, "
            "preferring source-page hero assets over social links and falling back "
            "to arXiv PDF previews when needed."
        )
    )
    parser.add_argument("--report", help="Markdown report path to scan for URLs")
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        default=[],
        help="Explicit source URL",
    )
    parser.add_argument("--out-dir", required=True, help="Directory to save images into")
    parser.add_argument("--limit", type=int, default=6, help="Max number of images to fetch")
    parser.add_argument(
        "--per-url-limit",
        type=int,
        default=4,
        help="Max number of image candidates to keep for each source URL",
    )
    return parser.parse_args()


def unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def is_social_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == hint or host.endswith(f".{hint}") for hint in SOCIAL_HOST_HINTS)


def extract_urls_from_report(report_path: Path) -> list[str]:
    text = report_path.read_text(encoding="utf-8")
    priority_regular: list[str] = []
    priority_social: list[str] = []
    secondary_regular: list[str] = []
    secondary_social: list[str] = []
    for line in text.splitlines():
        urls = URL_RE.findall(line)
        if not urls:
            continue
        lowered = line.lower()
        for url in urls:
            social = is_social_url(url)
            if any(hint in line for hint in PRIORITY_HINTS):
                (priority_social if social else priority_regular).append(url)
            elif any(hint in lowered for hint in SOCIAL_LINE_HINTS):
                secondary_social.append(url)
            else:
                (secondary_social if social else secondary_regular).append(url)
    return unique(priority_regular + secondary_regular + priority_social + secondary_social)


def open_url(url: str, accept: str) -> tuple[bytes, str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
        },
    )
    with urlopen(request, timeout=20) as response:
        payload = response.read()
        content_type = response.headers.get_content_type()
        return payload, content_type, response.geturl()


def normalize_candidate(base_url: str, candidate: str) -> str | None:
    if not candidate or candidate.startswith("data:"):
        return None
    normalized = urljoin(base_url, candidate)
    lower = normalized.lower()
    if any(hint in lower for hint in BAD_IMAGE_HINTS):
        return None
    return normalized


def score_candidate(source_kind: str, candidate: str) -> int:
    lower = candidate.lower()
    score = 0
    if source_kind == "meta":
        score += 10
    if any(hint in lower for hint in RICH_IMAGE_HINTS):
        score += 7
    if "original_images" in lower:
        score += 4
    if any(hint in lower for hint in LOW_VALUE_IMAGE_HINTS):
        score -= 8
    if "keyword_meta" in lower:
        score -= 3
    return score


def choose_candidates(page_url: str, html: str) -> list[tuple[str, str]]:
    parser = ImageCandidateParser()
    parser.feed(html)
    chosen: list[tuple[str, str]] = []
    for source_kind, raw_values in (
        ("meta", parser.meta_candidates),
        ("img", parser.img_candidates),
    ):
        for raw in raw_values:
            normalized = normalize_candidate(page_url, raw)
            if normalized:
                chosen.append((source_kind, normalized))
    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for source_kind, candidate in chosen:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append((source_kind, candidate))
    return sorted(
        deduped,
        key=lambda item: (score_candidate(item[0], item[1]), 1 if item[0] == "meta" else 0),
        reverse=True,
    )


def infer_extension(image_url: str, content_type: str) -> str:
    if content_type in DIRECT_IMAGE_TYPES:
        return DIRECT_IMAGE_TYPES[content_type]
    parsed = urlparse(image_url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix:
        return suffix
    return mimetypes.guess_extension(content_type) or ".bin"


def sanitize_stem(value: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
    return stem or "image"


def extract_citation_pdf_url(page_url: str, html: str) -> str | None:
    match = re.search(
        r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )
    if match:
        return urljoin(page_url, match.group(1).strip())
    parsed = urlparse(page_url)
    if parsed.netloc.lower().endswith("arxiv.org") and "/abs/" in parsed.path:
        return urljoin(page_url, parsed.path.replace("/abs/", "/pdf/") + ".pdf")
    return None


def download_pdf_preview(pdf_url: str, out_dir: Path, index: int) -> tuple[Path, int, str]:
    payload, content_type, final_url = open_url(
        pdf_url,
        "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
    )
    if "pdf" not in content_type and not final_url.lower().endswith(".pdf"):
        raise ValueError(f"Not a PDF: {content_type}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        pdf_path = tmpdir_path / "source.pdf"
        pdf_path.write_bytes(payload)
        subprocess.run(
            ["/usr/bin/qlmanage", "-t", "-s", "1600", "-o", str(tmpdir_path), str(pdf_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        preview_path = pdf_path.with_suffix(".pdf.png")
        if not preview_path.exists():
            png_files = sorted(tmpdir_path.glob("*.png"))
            if not png_files:
                raise FileNotFoundError("qlmanage produced no PNG thumbnail")
            preview_path = png_files[0]

        host = sanitize_stem(urlparse(final_url).netloc or "asset")
        name = sanitize_stem(Path(urlparse(final_url).path).stem or f"paper-{index:02d}")
        destination = out_dir / f"{index:02d}-{host}-{name}-preview.png"
        shutil.copyfile(preview_path, destination)
        return destination, destination.stat().st_size, "image/png"


def download_image(image_url: str, out_dir: Path, index: int) -> tuple[Path, int, str]:
    payload, content_type, final_url = open_url(
        image_url,
        "image/avif,image/webp,image/*,*/*;q=0.8",
    )
    if not content_type.startswith("image/"):
        raise ValueError(f"Not an image: {content_type}")
    extension = infer_extension(final_url, content_type)
    host = sanitize_stem(urlparse(final_url).netloc or "asset")
    name = sanitize_stem(Path(urlparse(final_url).path).stem or f"image-{index:02d}")
    destination = out_dir / f"{index:02d}-{host}-{name}{extension}"
    destination.write_bytes(payload)
    return destination, len(payload), content_type


def fetch_many(page_url: str, out_dir: Path, start_index: int, per_url_limit: int) -> list[dict[str, object]]:
    payload, content_type, final_url = open_url(
        page_url,
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    )
    if content_type.startswith("image/"):
        path, size, image_type = download_image(final_url, out_dir, start_index)
        return [
            {
                "source_page": page_url,
                "page_final_url": final_url,
                "image_url": final_url,
                "selector": "direct-image",
                "image_rank": 1,
                "file": str(path),
                "size_bytes": size,
                "content_type": image_type,
            }
        ]

    html = payload.decode("utf-8", errors="replace")
    candidates = choose_candidates(final_url, html)
    assets: list[dict[str, object]] = []
    errors: list[str] = []
    next_index = start_index
    for selector, image_url in candidates:
        try:
            path, size, image_type = download_image(image_url, out_dir, next_index)
            if size < 15_000:
                path.unlink(missing_ok=True)
                errors.append(f"too-small:{image_url}")
                continue
            assets.append(
                {
                    "source_page": page_url,
                    "page_final_url": final_url,
                    "image_url": image_url,
                    "selector": selector,
                    "image_rank": len(assets) + 1,
                    "file": str(path),
                    "size_bytes": size,
                    "content_type": image_type,
                }
            )
            next_index += 1
            if len(assets) >= max(1, per_url_limit):
                break
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{image_url}: {exc}")
    if assets:
        return assets
    pdf_url = extract_citation_pdf_url(final_url, html)
    if pdf_url:
        try:
            path, size, image_type = download_pdf_preview(pdf_url, out_dir, next_index)
            return [
                {
                    "source_page": page_url,
                    "page_final_url": final_url,
                    "image_url": pdf_url,
                    "selector": "pdf-preview",
                    "image_rank": 1,
                    "file": str(path),
                    "size_bytes": size,
                    "content_type": image_type,
                }
            ]
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{pdf_url}: {exc}")
    raise RuntimeError("; ".join(errors) or "no image candidate found")


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    urls = list(args.urls)
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        urls = extract_urls_from_report(report_path) + urls
    urls = unique(urls)[: args.limit]
    if not urls:
        print(json.dumps({"error": "no_urls_found"}, ensure_ascii=False))
        return 1

    assets: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    next_index = 1
    for index, url in enumerate(urls, start=1):
        try:
            fetched = fetch_many(url, out_dir, next_index, args.per_url_limit)
            assets.extend(fetched)
            next_index += len(fetched)
        except Exception as exc:  # noqa: BLE001
            failures.append({"source_page": url, "error": str(exc)})

    manifest_path = out_dir / "manifest.json"
    manifest = {
        "report": args.report,
        "out_dir": str(out_dir),
        "assets": assets,
        "failures": failures,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "asset_count": len(assets),
                "failure_count": len(failures),
                "manifest": str(manifest_path),
                "assets": assets,
                "failures": failures,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if assets else 1


if __name__ == "__main__":
    sys.exit(main())
