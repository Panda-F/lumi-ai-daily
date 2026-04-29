#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import mimetypes
import re
import subprocess
import sys
from typing import Any, Mapping
from zipfile import ZIP_DEFLATED, ZipFile

try:
    from lxml import etree
except ModuleNotFoundError:
    subprocess.run([sys.executable, "-m", "pip", "install", "lxml"], check=True, capture_output=True, text=True)
    from lxml import etree
from PIL import Image


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_NS = "http://purl.org/dc/elements/1.1/"
DCTERMS_NS = "http://purl.org/dc/terms/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
APP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"

NSMAP = {
    "w": WORD_NS,
    "r": REL_NS,
    "a": DRAWING_NS,
    "pic": PIC_NS,
    "wp": WP_NS,
}

EMU_PER_INCH = 914400
DEFAULT_DPI = 96
PAGE_WIDTH_TWIPS = 11906
PAGE_HEIGHT_TWIPS = 16838
PAGE_MARGIN_TWIPS = 1440
AVAILABLE_WIDTH_EMU = (PAGE_WIDTH_TWIPS - 2 * PAGE_MARGIN_TWIPS) * 635
INLINE_MARKDOWN_RE = re.compile(r"(\*\*([^*]+)\*\*|\[([^\]]+)\]\((https?://[^)]+)\))")


def _qn(prefix: str, name: str) -> str:
    return f"{{{NSMAP[prefix]}}}{name}"


def _w_attr(name: str) -> str:
    return f"{{{WORD_NS}}}{name}"


def _xml_bytes(element: etree._Element) -> bytes:
    return etree.tostring(element, xml_declaration=True, encoding="UTF-8", standalone="yes")


def _content_type_for_suffix(suffix: str) -> str:
    normalized = suffix.lower()
    if normalized in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if normalized == ".gif":
        return "image/gif"
    if normalized == ".webp":
        return "image/webp"
    guessed, _ = mimetypes.guess_type(f"file{normalized}")
    if guessed and guessed.startswith("image/"):
        return guessed
    return "image/png"


def _rasterize_if_needed(path: Path, alt_text: str = "") -> tuple[Path, bytes, str]:
    suffix = path.suffix.lower()
    if suffix != ".svg":
        return path, path.read_bytes(), _content_type_for_suffix(suffix)
    raster_path = path.with_suffix(".png")
    try:
        import cairosvg  # type: ignore
        png_bytes = cairosvg.svg2png(url=str(path))
        raster_path.write_bytes(png_bytes)
        return raster_path, png_bytes, "image/png"
    except Exception:
        canvas = Image.new("RGB", (1200, 675), color=(248, 245, 255))
        try:
            from PIL import ImageDraw, ImageFont
            draw = ImageDraw.Draw(canvas)
            title = (alt_text or path.stem or "AI Daily").strip()[:80]
            subtitle = "Lumi AI Daily"
            try:
                font_big = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 64)
                font_small = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 32)
            except Exception:
                font_big = ImageFont.load_default()
                font_small = ImageFont.load_default()
            draw.rounded_rectangle((60, 60, 1140, 615), radius=36, fill=(255, 255, 255), outline=(213, 195, 255), width=6)
            draw.text((120, 220), title, fill=(77, 52, 135), font=font_big)
            draw.text((120, 340), subtitle, fill=(140, 120, 190), font=font_small)
        except Exception:
            pass
        canvas.save(raster_path, format="PNG")
        png_bytes = raster_path.read_bytes()
        return raster_path, png_bytes, "image/png"


def _image_extents(path: Path, max_width_emu: int) -> tuple[int, int]:
    with Image.open(path) as image:
        width_px, height_px = image.size
        dpi = image.info.get("dpi", (DEFAULT_DPI, DEFAULT_DPI))
        x_dpi = int(dpi[0] or DEFAULT_DPI) if isinstance(dpi, tuple) else DEFAULT_DPI
        y_dpi = int(dpi[1] or DEFAULT_DPI) if isinstance(dpi, tuple) else DEFAULT_DPI
    x_dpi = x_dpi if x_dpi > 0 else DEFAULT_DPI
    y_dpi = y_dpi if y_dpi > 0 else DEFAULT_DPI
    width_emu = int(width_px * EMU_PER_INCH / x_dpi)
    height_emu = int(height_px * EMU_PER_INCH / y_dpi)
    if width_emu <= max_width_emu:
        return width_emu, height_emu
    scale = max_width_emu / float(width_emu)
    return max_width_emu, max(1, int(height_emu * scale))


@dataclass
class _MediaAsset:
    rel_id: str
    path_in_zip: str
    blob: bytes
    content_type: str


@dataclass
class _HyperlinkAsset:
    rel_id: str
    url: str


class _DocxBuilder:
    def __init__(self) -> None:
        self.body: list[etree._Element] = []
        self.media_assets: list[_MediaAsset] = []
        self.hyperlink_assets: list[_HyperlinkAsset] = []
        self.doc_rel_index = 1
        self.doc_pr_index = 1

    def _paragraph(
        self,
        *,
        align: str = "left",
        before: int = 0,
        after: int = 160,
        line: int = 420,
    ) -> etree._Element:
        paragraph = etree.Element(_qn("w", "p"), nsmap=NSMAP)
        ppr = etree.SubElement(paragraph, _qn("w", "pPr"))
        etree.SubElement(ppr, _qn("w", "jc"), {_w_attr("val"): align})
        etree.SubElement(
            ppr,
            _qn("w", "spacing"),
            {
                _w_attr("before"): str(before),
                _w_attr("after"): str(after),
                _w_attr("line"): str(line),
                _w_attr("lineRule"): "auto",
            },
        )
        return paragraph

    def _append_run(
        self,
        paragraph: etree._Element,
        text: str,
        *,
        font_size: int,
        bold: bool = False,
        color: str | None = None,
        italic: bool = False,
        underline: bool = False,
        parent: etree._Element | None = None,
    ) -> None:
        if not text:
            return
        container = parent if parent is not None else paragraph
        run = etree.SubElement(container, _qn("w", "r"))
        rpr = etree.SubElement(run, _qn("w", "rPr"))
        etree.SubElement(
            rpr,
            _qn("w", "rFonts"),
            {
                _w_attr("ascii"): "Arial",
                _w_attr("hAnsi"): "Arial",
                _w_attr("eastAsia"): "PingFang SC",
            },
        )
        etree.SubElement(rpr, _qn("w", "sz"), {_w_attr("val"): str(font_size)})
        etree.SubElement(rpr, _qn("w", "szCs"), {_w_attr("val"): str(font_size)})
        if bold:
            etree.SubElement(rpr, _qn("w", "b"))
        if italic:
            etree.SubElement(rpr, _qn("w", "i"))
        if underline:
            etree.SubElement(rpr, _qn("w", "u"), {_w_attr("val"): "single"})
        if color:
            etree.SubElement(rpr, _qn("w", "color"), {_w_attr("val"): color})
        lines = text.splitlines() or [text]
        for index, line_text in enumerate(lines):
            if index:
                etree.SubElement(run, _qn("w", "br"))
            text_node = etree.SubElement(run, _qn("w", "t"))
            if line_text[:1].isspace() or line_text[-1:].isspace():
                text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            text_node.text = line_text

    def add_paragraph(
        self,
        text: str,
        *,
        align: str = "left",
        font_size: int = 22,
        bold: bool = False,
        color: str | None = None,
        before: int = 0,
        after: int = 160,
        line: int = 420,
    ) -> None:
        if not text:
            return
        paragraph = self._paragraph(align=align, before=before, after=after, line=line)
        self._append_run(
            paragraph,
            text,
            font_size=font_size,
            bold=bold,
            color=color,
        )
        self.body.append(paragraph)

    def add_highlighted_paragraph(
        self,
        text: str,
        terms: list[str],
        *,
        font_size: int = 26,
        before: int = 0,
        after: int = 160,
        line: int = 520,
    ) -> None:
        if not text:
            return
        paragraph = self._paragraph(before=before, after=after, line=line)
        cleaned_terms = sorted({term.strip() for term in terms if term.strip()}, key=len, reverse=True)
        if not cleaned_terms:
            self._append_run(paragraph, text, font_size=font_size)
            self.body.append(paragraph)
            return
        pattern = re.compile("(" + "|".join(re.escape(term) for term in cleaned_terms) + ")", flags=re.I)
        cursor = 0
        for match in pattern.finditer(text):
            if match.start() > cursor:
                self._append_run(paragraph, text[cursor : match.start()], font_size=font_size)
            self._append_run(paragraph, match.group(0), font_size=font_size, bold=True, color="175CD3")
            cursor = match.end()
        if cursor < len(text):
            self._append_run(paragraph, text[cursor:], font_size=font_size)
        self.body.append(paragraph)

    def add_markdown_paragraph(
        self,
        text: str,
        terms: list[str],
        *,
        font_size: int = 26,
        before: int = 0,
        after: int = 160,
        line: int = 520,
    ) -> None:
        if not text:
            return
        if not INLINE_MARKDOWN_RE.search(text):
            self.add_highlighted_paragraph(text, terms, font_size=font_size, before=before, after=after, line=line)
            return
        paragraph = self._paragraph(before=before, after=after, line=line)
        cursor = 0
        for match in INLINE_MARKDOWN_RE.finditer(text):
            if match.start() > cursor:
                self._append_run(paragraph, text[cursor : match.start()], font_size=font_size)
            bold_text = match.group(2)
            link_label = match.group(3)
            link_url = match.group(4)
            if bold_text:
                self._append_run(paragraph, bold_text, font_size=font_size, bold=True, color="175CD3")
            elif link_label and link_url:
                rel_id = f"rId{self.doc_rel_index}"
                self.doc_rel_index += 1
                self.hyperlink_assets.append(_HyperlinkAsset(rel_id=rel_id, url=link_url))
                hyperlink = etree.SubElement(paragraph, _qn("w", "hyperlink"), {f"{{{REL_NS}}}id": rel_id})
                self._append_run(
                    paragraph,
                    link_label,
                    font_size=font_size,
                    color="175CD3",
                    underline=True,
                    parent=hyperlink,
                )
            cursor = match.end()
        if cursor < len(text):
            self._append_run(paragraph, text[cursor:], font_size=font_size)
        self.body.append(paragraph)

    def add_markdown_body(
        self,
        body: str,
        terms: list[str],
        *,
        font_size: int = 26,
        after: int = 160,
        line: int = 520,
    ) -> None:
        for raw_part in re.split(r"\n\s*\n", body or ""):
            part = re.sub(r"\s*\n\s*", " ", raw_part).strip()
            if not part:
                continue
            if part.startswith(">"):
                self.add_quote(part.lstrip("> ").strip(), font_size=max(20, font_size - 2))
                continue
            self.add_markdown_paragraph(part, terms, font_size=font_size, after=after, line=line)

    def add_quote(self, text: str, *, font_size: int = 22) -> None:
        if not text:
            return
        paragraph = self._paragraph(before=40, after=180, line=420)
        ppr = paragraph.find(_qn("w", "pPr"))
        if ppr is not None:
            etree.SubElement(ppr, _qn("w", "ind"), {_w_attr("left"): "360", _w_attr("right"): "240"})
            etree.SubElement(ppr, _qn("w", "shd"), {_w_attr("val"): "clear", _w_attr("color"): "auto", _w_attr("fill"): "F5F7FA"})
        self._append_run(paragraph, text, font_size=font_size, italic=True, color="4B5563")
        self.body.append(paragraph)

    def add_hyperlink_paragraph(
        self,
        prefix: str,
        label: str,
        url: str,
        *,
        font_size: int = 21,
        before: int = 0,
        after: int = 100,
        line: int = 380,
    ) -> None:
        if not url:
            return
        rel_id = f"rId{self.doc_rel_index}"
        self.doc_rel_index += 1
        self.hyperlink_assets.append(_HyperlinkAsset(rel_id=rel_id, url=url))
        paragraph = self._paragraph(before=before, after=after, line=line)
        if prefix:
            self._append_run(paragraph, prefix, font_size=font_size, color="4B5563")
        hyperlink = etree.SubElement(paragraph, _qn("w", "hyperlink"), {f"{{{REL_NS}}}id": rel_id})
        self._append_run(
            paragraph,
            label or url,
            font_size=font_size,
            color="175CD3",
            underline=True,
            parent=hyperlink,
        )
        if label and url and label != url:
            self._append_run(paragraph, f"  {url}", font_size=18, color="9CA3AF")
        self.body.append(paragraph)

    def add_image(self, image_path: str | Path, alt_text: str, *, max_width_emu: int = AVAILABLE_WIDTH_EMU) -> None:
        path = Path(image_path).expanduser().resolve()
        if not path.exists():
            return
        rel_id = f"rId{self.doc_rel_index}"
        self.doc_rel_index += 1
        raster_path, blob, content_type = _rasterize_if_needed(path, alt_text)
        extension = raster_path.suffix.lower() or ".png"
        zip_path = f"word/media/image{len(self.media_assets) + 1}{extension}"
        self.media_assets.append(
            _MediaAsset(
                rel_id=rel_id,
                path_in_zip=zip_path,
                blob=blob,
                content_type=content_type,
            )
        )

        cx, cy = _image_extents(raster_path, max_width_emu)
        paragraph = etree.Element(_qn("w", "p"), nsmap=NSMAP)
        ppr = etree.SubElement(paragraph, _qn("w", "pPr"))
        etree.SubElement(ppr, _qn("w", "jc"), {_w_attr("val"): "center"})
        etree.SubElement(
            ppr,
            _qn("w", "spacing"),
            {
                _w_attr("before"): "120",
                _w_attr("after"): "120",
            },
        )

        run = etree.SubElement(paragraph, _qn("w", "r"))
        drawing = etree.SubElement(run, _qn("w", "drawing"))
        inline = etree.SubElement(
            drawing,
            _qn("wp", "inline"),
            {"distT": "0", "distB": "0", "distL": "0", "distR": "0"},
        )
        etree.SubElement(inline, _qn("wp", "extent"), {"cx": str(cx), "cy": str(cy)})
        etree.SubElement(inline, _qn("wp", "effectExtent"), {"l": "0", "t": "0", "r": "0", "b": "0"})
        etree.SubElement(
            inline,
            _qn("wp", "docPr"),
            {"id": str(self.doc_pr_index), "name": f"Picture {self.doc_pr_index}", "descr": alt_text},
        )
        self.doc_pr_index += 1
        c_nv = etree.SubElement(inline, _qn("wp", "cNvGraphicFramePr"))
        etree.SubElement(c_nv, _qn("a", "graphicFrameLocks"), {"noChangeAspect": "1"})

        graphic = etree.SubElement(inline, _qn("a", "graphic"))
        graphic_data = etree.SubElement(
            graphic,
            _qn("a", "graphicData"),
            {"uri": "http://schemas.openxmlformats.org/drawingml/2006/picture"},
        )
        picture = etree.SubElement(graphic_data, _qn("pic", "pic"))
        nv_pic = etree.SubElement(picture, _qn("pic", "nvPicPr"))
        etree.SubElement(nv_pic, _qn("pic", "cNvPr"), {"id": "0", "name": raster_path.name})
        etree.SubElement(nv_pic, _qn("pic", "cNvPicPr"))
        blip_fill = etree.SubElement(picture, _qn("pic", "blipFill"))
        etree.SubElement(blip_fill, _qn("a", "blip"), {f"{{{REL_NS}}}embed": rel_id})
        stretch = etree.SubElement(blip_fill, _qn("a", "stretch"))
        etree.SubElement(stretch, _qn("a", "fillRect"))

        sp_pr = etree.SubElement(picture, _qn("pic", "spPr"))
        xfrm = etree.SubElement(sp_pr, _qn("a", "xfrm"))
        etree.SubElement(xfrm, _qn("a", "off"), {"x": "0", "y": "0"})
        etree.SubElement(xfrm, _qn("a", "ext"), {"cx": str(cx), "cy": str(cy)})
        preset = etree.SubElement(sp_pr, _qn("a", "prstGeom"), {"prst": "rect"})
        etree.SubElement(preset, _qn("a", "avLst"))
        self.body.append(paragraph)

    def _document_xml(self) -> bytes:
        document = etree.Element(_qn("w", "document"), nsmap=NSMAP)
        body = etree.SubElement(document, _qn("w", "body"))
        for entry in self.body:
            body.append(entry)
        section = etree.SubElement(body, _qn("w", "sectPr"))
        etree.SubElement(section, _qn("w", "pgSz"), {_w_attr("w"): str(PAGE_WIDTH_TWIPS), _w_attr("h"): str(PAGE_HEIGHT_TWIPS)})
        etree.SubElement(
            section,
            _qn("w", "pgMar"),
            {
                _w_attr("top"): str(PAGE_MARGIN_TWIPS),
                _w_attr("right"): str(PAGE_MARGIN_TWIPS),
                _w_attr("bottom"): str(PAGE_MARGIN_TWIPS),
                _w_attr("left"): str(PAGE_MARGIN_TWIPS),
                _w_attr("header"): "708",
                _w_attr("footer"): "708",
                _w_attr("gutter"): "0",
            },
        )
        etree.SubElement(section, _qn("w", "docGrid"), {_w_attr("linePitch"): "360"})
        return _xml_bytes(document)

    def _document_relationships_xml(self) -> bytes:
        root = etree.Element("Relationships", nsmap={None: PKG_REL_NS})
        for asset in self.media_assets:
            etree.SubElement(
                root,
                "Relationship",
                {
                    "Id": asset.rel_id,
                    "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                    "Target": asset.path_in_zip.removeprefix("word/"),
                },
            )
        for asset in self.hyperlink_assets:
            etree.SubElement(
                root,
                "Relationship",
                {
                    "Id": asset.rel_id,
                    "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
                    "Target": asset.url,
                    "TargetMode": "External",
                },
            )
        return _xml_bytes(root)


def _package_relationships_xml() -> bytes:
    root = etree.Element("Relationships", nsmap={None: PKG_REL_NS})
    etree.SubElement(
        root,
        "Relationship",
        {
            "Id": "rId1",
            "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
            "Target": "word/document.xml",
        },
    )
    etree.SubElement(
        root,
        "Relationship",
        {
            "Id": "rId2",
            "Type": "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties",
            "Target": "docProps/core.xml",
        },
    )
    etree.SubElement(
        root,
        "Relationship",
        {
            "Id": "rId3",
            "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties",
            "Target": "docProps/app.xml",
        },
    )
    return _xml_bytes(root)


def _content_types_xml(media_assets: list[_MediaAsset]) -> bytes:
    root = etree.Element("Types", nsmap={None: "http://schemas.openxmlformats.org/package/2006/content-types"})
    etree.SubElement(root, "Default", {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"})
    etree.SubElement(root, "Default", {"Extension": "xml", "ContentType": "application/xml"})
    seen_extensions: set[str] = set()
    for asset in media_assets:
        extension = Path(asset.path_in_zip).suffix.lower().lstrip(".")
        if extension in seen_extensions:
            continue
        seen_extensions.add(extension)
        etree.SubElement(root, "Default", {"Extension": extension, "ContentType": asset.content_type})
    etree.SubElement(
        root,
        "Override",
        {
            "PartName": "/word/document.xml",
            "ContentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
        },
    )
    etree.SubElement(
        root,
        "Override",
        {
            "PartName": "/docProps/core.xml",
            "ContentType": "application/vnd.openxmlformats-package.core-properties+xml",
        },
    )
    etree.SubElement(
        root,
        "Override",
        {
            "PartName": "/docProps/app.xml",
            "ContentType": "application/vnd.openxmlformats-officedocument.extended-properties+xml",
        },
    )
    return _xml_bytes(root)


def _core_properties_xml(title: str) -> bytes:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    root = etree.Element(
        f"{{{CP_NS}}}coreProperties",
        nsmap={None: CP_NS, "dc": DC_NS, "dcterms": DCTERMS_NS, "xsi": XSI_NS},
    )
    etree.SubElement(root, f"{{{DC_NS}}}title").text = title
    etree.SubElement(root, f"{{{DC_NS}}}creator").text = "OpenClaw"
    etree.SubElement(root, f"{{{CP_NS}}}lastModifiedBy").text = "OpenClaw"
    created = etree.SubElement(root, f"{{{DCTERMS_NS}}}created")
    created.set(f"{{{XSI_NS}}}type", "dcterms:W3CDTF")
    created.text = now
    modified = etree.SubElement(root, f"{{{DCTERMS_NS}}}modified")
    modified.set(f"{{{XSI_NS}}}type", "dcterms:W3CDTF")
    modified.text = now
    return _xml_bytes(root)


def _app_properties_xml() -> bytes:
    root = etree.Element(f"{{{APP_NS}}}Properties", nsmap={None: APP_NS, "vt": VT_NS})
    etree.SubElement(root, f"{{{APP_NS}}}Application").text = "OpenClaw"
    etree.SubElement(root, f"{{{APP_NS}}}DocSecurity").text = "0"
    etree.SubElement(root, f"{{{APP_NS}}}ScaleCrop").text = "false"
    etree.SubElement(root, f"{{{APP_NS}}}Company").text = "OpenClaw"
    etree.SubElement(root, f"{{{APP_NS}}}LinksUpToDate").text = "false"
    etree.SubElement(root, f"{{{APP_NS}}}SharedDoc").text = "false"
    etree.SubElement(root, f"{{{APP_NS}}}HyperlinksChanged").text = "false"
    etree.SubElement(root, f"{{{APP_NS}}}AppVersion").text = "1.0"
    return _xml_bytes(root)


def build_wechat_docx(article: Mapping[str, Any], output_path: str | Path) -> Path:
    builder = _DocxBuilder()
    title = str(article.get("title") or "").strip()
    intro = str(article.get("intro") or "").strip()
    outro_heading = str(article.get("outro_heading") or "").strip()
    outro = str(article.get("outro") or "").strip()
    cover_image = str(article.get("cover_image") or "").strip()
    sections = article.get("sections") or []
    references = article.get("references") or []

    if cover_image:
        builder.add_image(cover_image, title or "cover image")
    builder.add_paragraph(title, align="center", font_size=44, bold=True, after=280, line=560)
    if intro:
        builder.add_markdown_body(intro, [], font_size=26, after=220, line=520)

    for section in sections:
        if not isinstance(section, Mapping):
            continue
        heading = str(section.get("title") or "").strip()
        body = str(section.get("body") or "").strip()
        facts = str(section.get("facts") or "").strip()
        analysis = str(section.get("analysis") or "").strip()
        image_path = str(section.get("image_path") or "").strip()
        caption = str(section.get("image_caption") or "").strip()
        highlight_terms = [str(term) for term in section.get("highlight_terms") or []]
        if heading:
            builder.add_paragraph(heading, font_size=32, bold=True, color="111827", after=140, before=260, line=460)
        if image_path:
            builder.add_image(image_path, heading or "section image")
        if caption:
            builder.add_paragraph(caption, align="center", font_size=20, color="666666", before=0, after=180, line=340)
        if body:
            builder.add_markdown_body(body, highlight_terms, font_size=26, after=160, line=520)
        elif facts:
            builder.add_highlighted_paragraph(facts, highlight_terms, font_size=26, after=160, line=520)
        if not body and analysis:
            builder.add_highlighted_paragraph(analysis, highlight_terms, font_size=26, after=180, line=520)

    if outro:
        if outro_heading:
            builder.add_paragraph(outro_heading, font_size=30, bold=True, before=260, after=120, line=440)
        builder.add_markdown_body(outro, [], font_size=26, after=220, line=520)

    if references:
        builder.add_paragraph("参考链接", font_size=30, bold=True, before=260, after=120, line=440)
        for entry in references:
            if not isinstance(entry, Mapping):
                continue
            index = str(entry.get("index") or "").strip()
            label = str(entry.get("label") or "").strip()
            url = str(entry.get("url") or "").strip()
            if url:
                prefix = " ".join(part for part in [f"{index}.", label] if part)
                builder.add_hyperlink_paragraph(f"{prefix}  " if prefix else "", url, url, font_size=21, after=100, line=380)

    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml(builder.media_assets))
        archive.writestr("_rels/.rels", _package_relationships_xml())
        archive.writestr("docProps/core.xml", _core_properties_xml(title))
        archive.writestr("docProps/app.xml", _app_properties_xml())
        archive.writestr("word/document.xml", builder._document_xml())
        archive.writestr("word/_rels/document.xml.rels", builder._document_relationships_xml())
        for asset in builder.media_assets:
            archive.writestr(asset.path_in_zip, asset.blob)
    return output
