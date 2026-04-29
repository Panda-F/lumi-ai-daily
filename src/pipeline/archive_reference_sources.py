#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from ai_daily_paths import (
    tech_daily_latest_report,
    tech_daily_reference_pack_dir,
    tech_daily_report_json_path,
)
from archive_social_sources import (
    ArchiveResult,
    append_note,
    assessment_for_result,
    canonicalize_url,
    classify_asset_kind,
    detect_kind as detect_social_kind,
    download_asset_candidates,
    extract_asset_candidates,
    image_manifest_subset,
    meta_content,
    non_whitespace_chars,
    normalize_body_text,
    now_iso,
    regex_capture,
    render_asset_lines,
    render_markdown_header,
    render_quality_lines,
    request_url,
    slugify,
    strip_html,
    write_json,
    write_text,
)


URL_RE = re.compile(r"https?://[^\s<>()\"']+")
READABLE_HTML_PATTERNS: list[tuple[str, str]] = [
    ("article", r"(?is)<article[^>]*>(.*?)</article>"),
    ("main", r"(?is)<main[^>]*>(.*?)</main>"),
    ("markdown-body", r'(?is)<(?:div|article|section)[^>]+class=["\'][^"\']*markdown-body[^"\']*["\'][^>]*>(.*?)</(?:div|article|section)>'),
    ("article-body", r'(?is)<(?:div|section)[^>]+(?:id|class)=["\'][^"\']*(?:article-body|article-content|post-content|entry-content|content-body|doc-content|docs-content|theme-doc-markdown|main-content|content-main)[^"\']*["\'][^>]*>(.*?)</(?:div|section)>'),
    ("paper-abstract", r'(?is)<blockquote[^>]+class=["\'][^"\']*abstract[^"\']*["\'][^>]*>(.*?)</blockquote>'),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive non-social reference sources from the final tech-daily report into a local reference pack.")
    parser.add_argument("--report", help="Path to the final tech-daily Markdown report.")
    parser.add_argument("--report-json", help="Optional report JSON path. Defaults to the sidecar for --report.")
    parser.add_argument("--out-dir", help="Output directory. Defaults to the report day's reference-pack path.")
    parser.add_argument("--urls-file", help="Optional extra plain-text URLs file.")
    parser.add_argument("--url", action="append", default=[], help="Additional reference URL to archive.")
    parser.add_argument("--include-social", action="store_true", help="Include social URLs too. Off by default because social goes through source-pack.")
    parser.add_argument("--max-urls", type=int, default=24, help="Maximum URLs to archive.")
    parser.add_argument("--inter-request-delay-s", type=float, default=0.0, help="Optional delay between requests.")
    return parser.parse_args()


def resolve_report_path(report_arg: str | None) -> Path:
    if report_arg:
        path = Path(report_arg).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Report not found: {path}")
        return path
    latest = tech_daily_latest_report()
    if not latest:
        raise FileNotFoundError("No tech-daily report found.")
    return latest


def report_json_for_report(report_path: Path, report_json_arg: str | None) -> Path:
    if report_json_arg:
        return Path(report_json_arg).expanduser().resolve()
    report_date_match = re.search(r"(20\d{2}-\d{2}-\d{2})", report_path.name)
    if report_date_match:
        return tech_daily_report_json_path(report_date_match.group(1))
    return report_path.with_suffix(".report.json")


def output_dir_for_report(report_path: Path, out_dir_arg: str | None) -> Path:
    if out_dir_arg:
        return Path(out_dir_arg).expanduser().resolve()
    report_date_match = re.search(r"(20\d{2}-\d{2}-\d{2})", report_path.name)
    if report_date_match:
        return tech_daily_reference_pack_dir(report_date_match.group(1))
    return report_path.parent / "reference-pack"


def extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    for match in URL_RE.findall(text or ""):
        url = canonicalize_url(match)
        if url:
            urls.append(url)
    return urls


def load_report_json_urls(report_json_path: Path) -> list[str]:
    if not report_json_path.exists():
        return []
    raw = json.loads(report_json_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return []
    urls: list[str] = []
    for item in raw.get("items", []):
        if not isinstance(item, dict):
            continue
        source_refs = item.get("source_refs")
        if isinstance(source_refs, list):
            urls.extend(str(ref).strip() for ref in source_refs if str(ref).strip())
        source_url = str(item.get("source_url", "")).strip()
        if source_url:
            urls.append(source_url)
    return [canonicalize_url(url) for url in urls if url]


def load_urls(report_path: Path, report_json_path: Path, urls_file: Path | None, extra_urls: list[str], include_social: bool, max_urls: int) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        canonical = canonicalize_url(url)
        if not canonical or canonical in seen:
            return
        if not include_social and detect_social_kind(canonical):
            return
        seen.add(canonical)
        ordered.append(canonical)

    for url in load_report_json_urls(report_json_path):
        add(url)

    for url in extract_urls(report_path.read_text(encoding="utf-8", errors="ignore")):
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

    return ordered[:max_urls]


def infer_reference_kind(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if host in {"arxiv.org", "www.arxiv.org"}:
        return "arxiv"
    if host in {"github.com", "raw.githubusercontent.com", "gist.github.com"}:
        return "github"
    if host.startswith("docs.") or "/docs/" in path or path.startswith("/docs"):
        return "docs"
    if host.endswith("substack.com"):
        return "blog"
    if any(segment in path for segment in ["/blog", "/blogs", "/news", "/release", "/releases", "/announcements"]):
        return "blog"
    if path.endswith(".pdf"):
        return "document"
    return "web"


def github_raw_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.lower() != "github.com":
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 5 and parts[2] == "blob":
        owner, repo, _, branch, *rest = parts
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{'/'.join(rest)}"
    return ""


def arxiv_pdf_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.lower() not in {"arxiv.org", "www.arxiv.org"}:
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "abs":
        return f"https://arxiv.org/pdf/{parts[1]}.pdf"
    if len(parts) >= 2 and parts[0] == "pdf":
        return f"https://{parsed.netloc}/{'/'.join(parts)}"
    return ""


def extract_best_html_fragment(html: str) -> tuple[str, str]:
    best_fragment = ""
    best_label = ""
    best_chars = 0
    for label, pattern in READABLE_HTML_PATTERNS:
        for match in re.finditer(pattern, html):
            fragment = match.group(1).strip()
            text = normalize_body_text(strip_html(fragment))
            chars = non_whitespace_chars(text)
            if chars > best_chars:
                best_fragment = fragment
                best_label = label
                best_chars = chars
    return best_fragment, best_label


def fetch_mirror_text(session: requests.Session, url: str, item_dir: Path) -> tuple[str, str]:
    mirror_url = "https://r.jina.ai/http://" + url.removeprefix("https://").removeprefix("http://")
    try:
        response = request_url(session, mirror_url, timeout=35)
        mirror_text = normalize_body_text(response.text)
        if mirror_text and not mirror_text.lstrip().startswith("{\"data\":null"):
            write_text(item_dir / "mirror.txt", mirror_text + "\n")
            return mirror_text, ""
        return "", "mirror returned no readable text"
    except Exception as exc:  # noqa: BLE001
        return "", f"mirror failed: {exc}"


def title_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path:
        return Path(path).name or parsed.netloc
    return parsed.netloc or url


def archive_reference_url(session: requests.Session, url: str, item_dir: Path) -> ArchiveResult:
    files: list[str] = []
    kind = infer_reference_kind(url)
    final_url = url
    method = "direct-html"
    title = title_from_url(url)
    note = ""
    excerpt = ""
    author = ""
    published_at = ""
    text = ""
    asset_candidates: list[dict[str, object]] = []

    raw_text_candidate = ""
    raw_url = github_raw_url(url)
    if raw_url:
        try:
            raw_response = request_url(session, raw_url, timeout=25)
            raw_text_candidate = normalize_body_text(raw_response.text)
            if raw_text_candidate:
                raw_path = item_dir / "raw-source.txt"
                write_text(raw_path, raw_text_candidate + "\n")
                files.append(raw_path.name)
                method = "github-raw"
                note = append_note(note, "github raw fallback")
        except Exception as exc:  # noqa: BLE001
            note = append_note(note, f"github raw failed: {exc}")

    try:
        response = request_url(session, url, timeout=25)
        final_url = response.url or url
        content_type = response.headers.get("Content-Type", "").strip()
        response_kind = classify_asset_kind(final_url, content_type=content_type)
        if response_kind and response_kind != "image" and not content_type.lower().startswith(("text/html", "application/xhtml+xml", "text/plain", "application/xml", "text/xml")):
            asset_candidates = [
                {
                    "url": final_url,
                    "asset_kind": response_kind,
                    "alt": "",
                    "label": "primary-source",
                    "class_name": "",
                    "width": 0,
                    "height": 0,
                    "source": "direct",
                    "content_type": content_type,
                }
            ]
            binary_path = item_dir / "source.bin"
            binary_path.write_bytes(response.content)
            files.append(binary_path.name)
            mirror_text, mirror_note = fetch_mirror_text(session, url, item_dir)
            if mirror_text:
                text = mirror_text
                method = "r.jina.ai"
                files.append("mirror.txt")
            else:
                note = append_note(note, mirror_note)
                text = ""
        else:
            html = response.text
            html_path = item_dir / "source.html"
            write_text(html_path, html)
            files.append(html_path.name)

            title = (
                meta_content(html, "og:title")
                or meta_content(html, "twitter:title", attr="name")
                or regex_capture(html, r"<title[^>]*>(.*?)</title>")
                or title
            )
            author = (
                meta_content(html, "author", attr="name")
                or regex_capture(html, r'<meta[^>]+itemprop=["\']author["\'][^>]+content=["\']([^"\']+)')
                or ""
            )
            published_at = (
                meta_content(html, "article:published_time")
                or meta_content(html, "og:published_time")
                or regex_capture(html, r'"datePublished":"(.*?)"')
                or regex_capture(html, r'<meta[^>]+itemprop=["\']datePublished["\'][^>]+content=["\']([^"\']+)')
            )
            asset_candidates = extract_asset_candidates(html, final_url)
            if kind == "arxiv":
                pdf_url = arxiv_pdf_url(final_url)
                if pdf_url:
                    asset_candidates = [
                        {
                            "url": pdf_url,
                            "asset_kind": "document",
                            "alt": "",
                            "label": "paper-pdf",
                            "class_name": "",
                            "width": 0,
                            "height": 0,
                            "source": "arxiv-pdf",
                            "content_type": "application/pdf",
                        },
                        *asset_candidates,
                    ]

            fragment, fragment_label = extract_best_html_fragment(html)
            if fragment:
                fragment_path = item_dir / "content.html"
                write_text(fragment_path, fragment + "\n")
                files.append(fragment_path.name)
                text = normalize_body_text(strip_html(fragment))
                note = append_note(note, f"html fragment {fragment_label}")

            if kind == "arxiv":
                abstract_html = regex_capture(html, r'(?is)<blockquote[^>]+class=["\'][^"\']*abstract[^"\']*["\'][^>]*>(.*?)</blockquote>')
                abstract_text = normalize_body_text(strip_html(abstract_html))
                if non_whitespace_chars(abstract_text) > non_whitespace_chars(text):
                    text = abstract_text
                    note = append_note(note, "arxiv abstract block")

            if raw_text_candidate and non_whitespace_chars(raw_text_candidate) > non_whitespace_chars(text):
                text = raw_text_candidate

            if non_whitespace_chars(text) < 280:
                desc_text = normalize_body_text(
                    meta_content(html, "og:description")
                    or meta_content(html, "description", attr="name")
                    or regex_capture(html, r'"description":"(.*?)"')
                    or ""
                )
                if non_whitespace_chars(desc_text) > non_whitespace_chars(text):
                    text = desc_text

            if non_whitespace_chars(text) < 420 or kind in {"docs", "github", "arxiv"}:
                mirror_text, mirror_note = fetch_mirror_text(session, final_url, item_dir)
                if mirror_text:
                    if "mirror.txt" not in files:
                        files.append("mirror.txt")
                    if non_whitespace_chars(mirror_text) > non_whitespace_chars(text):
                        text = mirror_text
                        method = "r.jina.ai"
                else:
                    note = append_note(note, mirror_note)

            if not text:
                text = normalize_body_text(strip_html(html))
    except Exception as exc:  # noqa: BLE001
        note = append_note(note, f"direct fetch failed: {exc}")

    if raw_text_candidate and not text:
        text = raw_text_candidate

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
    excerpt = str(assessment["text"])[:280]
    asset_manifest, asset_urls, asset_files, hero_image_url, hero_image_file = download_asset_candidates(
        session,
        asset_candidates,
        item_dir,
        final_url,
    )
    image_manifest, image_urls, image_files = image_manifest_subset(asset_manifest)
    if asset_manifest:
        asset_manifest_path = item_dir / "assets.json"
        write_json(asset_manifest_path, {"assets": asset_manifest})
        files.append(asset_manifest_path.name)
    if image_manifest:
        image_manifest_path = item_dir / "images.json"
        write_json(image_manifest_path, {"images": image_manifest})
        files.append(image_manifest_path.name)
    for asset_file in asset_files:
        if asset_file not in files:
            files.append(asset_file)

    result = ArchiveResult(
        kind=kind,
        url=url,
        final_url=final_url,
        status=str(assessment["status"]),
        method=method,
        title=title,
        excerpt=excerpt,
        note=note,
        files=files,
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
        asset_type_counts={kind_name: sum(1 for entry in asset_manifest if str(entry.get("asset_kind") or "") == kind_name) for kind_name in sorted({str(entry.get("asset_kind") or "") for entry in asset_manifest if str(entry.get("asset_kind") or "")})},
        image_count=len(image_urls),
        image_urls=image_urls,
        image_files=image_files,
        hero_image_url=hero_image_url,
        hero_image_file=hero_image_file,
    )

    content_lines = render_markdown_header(title, url, final_url, method, note)
    content_lines.extend(render_quality_lines(result))
    content_lines.extend(["## Text", "", str(assessment["text"]) or excerpt or "", ""])
    content_lines.extend(render_asset_lines(asset_manifest, hero_image_url, hero_image_file))
    md_path = item_dir / "content.md"
    write_text(md_path, "\n".join(line for line in content_lines if line != "") + "\n")
    if md_path.name not in files:
        files.append(md_path.name)
    result.files = files
    return result


def archive_reference_sources(
    report_path: Path,
    report_json_path: Path,
    out_dir: Path,
    urls_file: Path | None,
    extra_urls: list[str],
    *,
    include_social: bool,
    max_urls: int,
    inter_request_delay_s: float,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    urls = load_urls(report_path, report_json_path, urls_file, extra_urls, include_social, max_urls)

    sources: list[dict[str, Any]] = []
    all_text_parts: list[str] = []

    for index, url in enumerate(urls, start=1):
        kind = infer_reference_kind(url)
        label = slugify(urlparse(url).path or urlparse(url).netloc)
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
        item_dir = out_dir / f"{index:03d}-{kind}-{label}-{digest}"
        item_dir.mkdir(parents=True, exist_ok=True)

        result = archive_reference_url(session, url, item_dir)
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
        write_json(item_dir / "meta.json", meta)
        sources.append({**meta, "dir": item_dir.name})

        content_path = item_dir / "content.md"
        if content_path.exists():
            content = content_path.read_text(encoding="utf-8", errors="ignore").strip()
            if content:
                all_text_parts.append(content)

        if inter_request_delay_s > 0 and index < len(urls):
            time.sleep(inter_request_delay_s)

    ok_count = sum(1 for item in sources if item["status"] == "ok")
    partial_count = sum(1 for item in sources if item["status"] == "partial")
    failed_count = sum(1 for item in sources if item["status"] == "failed")
    usable_count = sum(1 for item in sources if item.get("usable_for_scoring"))
    discovery_only_count = sum(1 for item in sources if item.get("discovery_only"))
    asset_count = sum(int(item.get("asset_count", 0) or 0) for item in sources)
    image_count = sum(int(item.get("image_count", 0) or 0) for item in sources)

    summary = {
        "generated_at": now_iso(),
        "report": str(report_path),
        "report_json": str(report_json_path) if report_json_path.exists() else None,
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
        "# Reference Pack",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Report: {summary['report']}",
        f"- Report JSON: {summary['report_json'] or '(none)'}",
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
                f"- Text Chars: {item.get('text_chars', 0)}",
                f"- Asset Count: {item.get('asset_count', 0)}",
                f"- Asset Types: {', '.join(f'{kind_name}:{count}' for kind_name, count in sorted((item.get('asset_type_counts') or {}).items()))}" if item.get("asset_type_counts") else "",
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


def main() -> int:
    args = parse_args()
    report_path = resolve_report_path(args.report)
    report_json_path = report_json_for_report(report_path, args.report_json)
    out_dir = output_dir_for_report(report_path, args.out_dir)
    urls_file = Path(args.urls_file).expanduser().resolve() if args.urls_file else None
    summary = archive_reference_sources(
        report_path,
        report_json_path,
        out_dir,
        urls_file,
        args.url,
        include_social=args.include_social,
        max_urls=args.max_urls,
        inter_request_delay_s=args.inter_request_delay_s,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
