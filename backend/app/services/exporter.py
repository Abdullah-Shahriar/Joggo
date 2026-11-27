from functools import lru_cache
import io
from pathlib import Path
import re
from xml.sax.saxutils import escape as xml_escape

from docx import Document as DocxDocument
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches
from PIL import Image
import pymupdf
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

LOGO_ASSET_PATH = Path(__file__).resolve().parent.parent / "assets" / "joggo_logo.png"
TXT_WATERMARK_FOOTER = (
    "\n\n------------------------------------------------------------\n"
    "[JOGGO] Watermark — Generated via JOGGO Clinical AI Gateway\n"
)


@lru_cache(maxsize=4)
def _build_faded_logo_png(opacity: float = 0.12) -> tuple[bytes, int, int] | None:
    """Load the JOGGO logo PNG and pre-fade its alpha channel for clean document watermarks."""
    if not LOGO_ASSET_PATH.is_file():
        return None
    with Image.open(LOGO_ASSET_PATH) as raw_img:
        rgba = raw_img.convert("RGBA")
        # Resize smoothly if oversized while preserving aspect ratio
        if max(rgba.size) > 512:
            rgba.thumbnail((512, 512), Image.Resampling.LANCZOS)
        r, g, b, alpha = rgba.split()
        faded_alpha = alpha.point(lambda px: int(round(px * opacity)))
        faded = Image.merge("RGBA", (r, g, b, faded_alpha))
        w, h = faded.size
        out = io.BytesIO()
        faded.save(out, format="PNG", optimize=True)
        return out.getvalue(), w, h


def _draw_pdf_watermark(canvas, doc) -> None:
    """Draw a subtle centered JOGGO logo watermark behind every PDF page."""
    canvas.saveState()
    page_w, page_h = doc.pagesize

    logo_data = _build_faded_logo_png(opacity=0.11)
    if logo_data is not None:
        png_bytes, img_w, img_h = logo_data
        target_w = 3.2 * inch
        target_h = target_w * (img_h / max(1, img_w))
        x = (page_w - target_w) / 2.0
        y = (page_h - target_h) / 2.0
        canvas.drawImage(
            ImageReader(io.BytesIO(png_bytes)),
            x,
            y,
            width=target_w,
            height=target_h,
            mask="auto",
            preserveAspectRatio=True,
        )

    # Subtle branded text mark below the center logo
    try:
        canvas.setFillAlpha(0.14)
    except Exception:
        pass
    canvas.setFillColorRGB(15 / 255.0, 118 / 255.0, 110 / 255.0)
    canvas.setFont("Helvetica-Bold", 18)
    canvas.drawCentredString(page_w / 2.0, (page_h / 2.0) - (1.85 * inch), "JOGGO")
    canvas.restoreState()


def _attach_docx_logo_watermark(section) -> None:
    """Embed a centered behind-text JOGGO logo watermark in a DOCX section header (header text stays empty)."""
    logo_data = _build_faded_logo_png(opacity=0.12)
    if logo_data is None:
        return
    png_bytes, _w, _h = logo_data

    header = section.header
    p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    p.text = ""
    run = p.add_run()
    run.add_picture(io.BytesIO(png_bytes), width=Inches(3.2))

    drawing = run._r.find(qn("w:drawing"))
    if drawing is None:
        return
    inline = drawing.find(qn("wp:inline"))
    if inline is None:
        return

    extent = inline.find(qn("wp:extent"))
    doc_pr = inline.find(qn("wp:docPr"))
    c_nv_pr = inline.find(qn("wp:cNvGraphicFramePr"))
    graphic = inline.find(qn("a:graphic"))
    if extent is None or doc_pr is None or graphic is None:
        return

    cx = extent.get("cx", "2926080")
    cy = extent.get("cy", "2926080")

    anchor = parse_xml(
        f'<wp:anchor {nsdecls("wp")} distT="0" distB="0" distL="0" distR="0" '
        f'simplePos="0" relativeHeight="0" behindDoc="1" locked="0" layoutInCell="1" allowOverlap="1">'
        f'<wp:simplePos x="0" y="0"/>'
        f'<wp:positionH relativeFrom="page"><wp:align>center</wp:align></wp:positionH>'
        f'<wp:positionV relativeFrom="page"><wp:align>center</wp:align></wp:positionV>'
        f'<wp:extent cx="{cx}" cy="{cy}"/>'
        f'<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        f"<wp:wrapNone/>"
        f"</wp:anchor>"
    )
    anchor.append(doc_pr)
    if c_nv_pr is not None:
        anchor.append(c_nv_pr)
    anchor.append(graphic)

    drawing.remove(inline)
    drawing.append(anchor)


def export_txt(text: str) -> bytes:
    """Export clinical summary as UTF-8 text with a subtle JOGGO watermark footer."""
    body = text.rstrip()
    if "[JOGGO] Watermark" not in body:
        body = f"{body}{TXT_WATERMARK_FOOTER}"
    else:
        body = f"{body}\n"
    return body.encode("utf-8")


def _add_docx_inline_runs(paragraph, raw: str) -> None:
    """Populate a python-docx paragraph with clean **bold** and _italic_ runs."""
    tokens = re.split(r"(\*\*[^*]+\*\*|_[^_]+_)", raw)
    for tok in tokens:
        if not tok:
            continue
        if tok.startswith("**") and tok.endswith("**") and len(tok) > 4:
            run = paragraph.add_run(tok[2:-2])
            run.bold = True
        elif tok.startswith("_") and tok.endswith("_") and len(tok) > 2:
            run = paragraph.add_run(tok[1:-1])
            run.italic = True
        else:
            paragraph.add_run(tok)


def export_docx(text: str) -> bytes:
    """Render clinical summary Markdown into a clean DOCX with behind-text JOGGO logo watermark and empty header/footer text."""
    doc = DocxDocument()

    # Keep header/footer text empty and embed the behind-text JOGGO logo watermark
    for section in doc.sections:
        section.header.is_linked_to_previous = False
        section.footer.is_linked_to_previous = False
        for p in section.header.paragraphs:
            p.text = ""
        for p in section.footer.paragraphs:
            p.text = ""
        _attach_docx_logo_watermark(section)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or re.match(r"^[-_]{3,}$", line):
            continue
        h_match = re.match(r"^(#{1,4})\s+(.*)$", line)
        if h_match:
            level = min(len(h_match.group(1)), 3)
            heading_text = re.sub(r"\*\*([^*]+)\*\*", r"\1", h_match.group(2).strip())
            doc.add_heading(heading_text, level=level)
            continue
        b_match = re.match(r"^[-*•]\s+(.*)$", line)
        if b_match:
            p = doc.add_paragraph(style="List Bullet")
            _add_docx_inline_runs(p, b_match.group(1).strip())
            continue
        p = doc.add_paragraph()
        _add_docx_inline_runs(p, line)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _markdown_inline_to_reportlab(raw: str) -> str:
    """Safely escape XML and convert **bold** and _italic_ spans for ReportLab Paragraph."""
    escaped = xml_escape(raw)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"<i>\1</i>", escaped)
    return escaped


def export_pdf(text: str) -> bytes:
    """Render generated clinical summary into a clean PDF document in memory with a centered JOGGO logo watermark."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.8 * inch,
        title="Clinical Summary",
        author="",
    )

    styles = getSampleStyleSheet()
    h1_style = ParagraphStyle(
        "JoggoH1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=20,
        spaceBefore=12,
        spaceAfter=6,
    )
    h2_style = ParagraphStyle(
        "JoggoH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12.5,
        leading=17,
        spaceBefore=10,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "JoggoBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=15,
        spaceAfter=5,
    )
    bullet_style = ParagraphStyle(
        "JoggoBullet",
        parent=body_style,
        leftIndent=16,
        firstLineIndent=-10,
        spaceAfter=3,
    )

    story = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 5))
            continue
        if re.match(r"^[-_]{3,}$", line):
            story.append(Spacer(1, 8))
            continue

        h_match = re.match(r"^(#{1,4})\s+(.*)$", line)
        if h_match:
            level = len(h_match.group(1))
            content = _markdown_inline_to_reportlab(h_match.group(2).strip())
            story.append(Paragraph(content, h1_style if level == 1 else h2_style))
            continue

        b_match = re.match(r"^[-*•]\s+(.*)$", line)
        if b_match:
            content = _markdown_inline_to_reportlab(b_match.group(1).strip())
            story.append(Paragraph(f"&bull;&nbsp; {content}", bullet_style))
            continue

        story.append(Paragraph(_markdown_inline_to_reportlab(line), body_style))

    if not story:
        story.append(Paragraph("Clinical Summary", body_style))

    doc.build(story, onFirstPage=_draw_pdf_watermark, onLaterPages=_draw_pdf_watermark)
    return buf.getvalue()


def _render_pdf_to_image(pdf_bytes: bytes, dpi: int = 150) -> Image.Image:
    """Rasterize PDF pages (including the JOGGO logo watermark) into a stitched RGB Pillow image."""
    pdf = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        page_images: list[Image.Image] = []
        for idx in range(pdf.page_count):
            pix = pdf.load_page(idx).get_pixmap(dpi=dpi, alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            page_images.append(img)
    finally:
        pdf.close()

    if len(page_images) == 1:
        return page_images[0]

    gap = 16
    width = max(im.width for im in page_images)
    total_height = sum(im.height for im in page_images) + gap * (len(page_images) - 1)
    canvas = Image.new("RGB", (width, total_height), (255, 255, 255))
    y = 0
    for im in page_images:
        canvas.paste(im, (0, y))
        y += im.height + gap
    return canvas


def export_png(text: str) -> bytes:
    """Render generated clinical summary as a crisp PNG image with JOGGO logo watermark."""
    img = _render_pdf_to_image(export_pdf(text))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def export_jpg(text: str) -> bytes:
    """Render generated clinical summary as a crisp JPEG image with JOGGO logo watermark."""
    img = _render_pdf_to_image(export_pdf(text))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()
