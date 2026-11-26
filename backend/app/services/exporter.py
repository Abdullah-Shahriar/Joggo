import io
import re
from xml.sax.saxutils import escape as xml_escape

from docx import Document as DocxDocument
from PIL import Image
import pymupdf
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def export_txt(text: str) -> bytes:
    return text.encode("utf-8")


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
    """Render clinical summary Markdown into a clean DOCX with empty headers/footers (architecture.md §18)."""
    doc = DocxDocument()

    # Ensure headers and footers are empty
    for section in doc.sections:
        section.header.is_linked_to_previous = False
        section.footer.is_linked_to_previous = False
        for p in section.header.paragraphs:
            p.text = ""
        for p in section.footer.paragraphs:
            p.text = ""

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
    """Render generated clinical summary into a clean PDF document in memory."""
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

    doc.build(story)
    return buf.getvalue()


def _render_pdf_to_image(pdf_bytes: bytes, dpi: int = 150) -> Image.Image:
    """Rasterize PDF pages into a single stitched RGB Pillow image on a white canvas."""
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
    """Render generated clinical summary as a crisp PNG image."""
    img = _render_pdf_to_image(export_pdf(text))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def export_jpg(text: str) -> bytes:
    """Render generated clinical summary as a crisp JPEG image."""
    img = _render_pdf_to_image(export_pdf(text))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()
