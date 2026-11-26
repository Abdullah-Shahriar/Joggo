import io

from docx import Document as DocxDocument


def export_txt(text: str) -> bytes:
    return text.encode("utf-8")


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
        if not line:
            continue
        if line.startswith("## "):
            doc.add_heading(line[3:].strip(), level=2)
        elif line.startswith("# "):
            doc.add_heading(line[2:].strip(), level=1)
        elif line.startswith("- ") or line.startswith("* "):
            doc.add_paragraph(line[2:].strip(), style="List Bullet")
        else:
            doc.add_paragraph(line)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
