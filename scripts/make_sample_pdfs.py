"""Generate three synthetic clinical sample PDFs for testing and demo (rules.md T4)."""

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import pymupdf
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def _load_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def build_text_lab_report_bytes() -> bytes:
    """Sample 1: Text-based lab report with synthetic HIPAA identifiers + normal lab values."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Synthetic Clinical Laboratory Report")
    c.setAuthor("ReportLab")

    lines = [
        "Green Valley Diagnostic Center",
        "Clinical Laboratory Report",
        "------------------------------------------------------------",
        "Patient Name: Rahim Ahmed",
        "DOB: 14/05/1968",
        "MRN: MRN-884210",
        "NID: 1968472910482",
        "Phone: +880 1712-345678",
        "Email: rahim.ahmed.synth@example.test",
        "Address: House 14, Road 7, Dhanmondi, Dhaka",
        "Consultant: Dr. Nasrin Sultana",
        "Date of Collection: 10/10/2026",
        "Date of Report: 12/10/2026",
        "",
        "Hematology & Biochemistry:",
        "Hemoglobin: 13.4 g/dL (Ref: 13.0-17.0 g/dL)",
        "Fasting Glucose: 142 mg/dL",
        "HbA1c: 7.4 %",
        "Serum Creatinine: 1.1 mg/dL",
        "Blood Pressure: 138/86 mmHg, Heart Rate: 78 bpm",
        "",
        "Clinical Note:",
        "Rahim presented for routine diabetes follow-up. Continue Metformin 500 mg twice daily.",
        "Next follow-up scheduled on 24/10/2026 at Green Valley Diagnostic Center.",
        "Portal: https://portal.greenvalley-synth.example/reports/884210",
    ]
    y = 800
    c.setFont("Helvetica", 11)
    for line in lines:
        c.drawString(50, y, line)
        y -= 20

    c.showPage()
    c.save()
    return buf.getvalue()


def build_discharge_metadata_bytes() -> bytes:
    """Sample 2: Discharge summary with PDF author metadata set to a synthetic name."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Synthetic Discharge Summary")
    # Hidden author metadata hint that must be caught and scrubbed
    c.setAuthor("Tariqul Karim")

    lines = [
        "City Care Medical College",
        "Discharge Summary",
        "------------------------------------------------------------",
        "Patient Name: Salma Begum",
        "Father's Name: Abdul Karim",
        "DOB: 03/02/1932",
        "Hospital No: HSP-550192",
        "Mobile: 01819-654321",
        "Date of Admission: 01/10/2026",
        "Discharge Date: 06/10/2026",
        "Attending: Dr. Kamrul Hasan",
        "Address: 22 Station Road, Sylhet",
        "",
        "Diagnosis:",
        "Community-acquired pneumonia, resolved. Type 2 diabetes mellitus.",
        "",
        "Clinical Course:",
        "Salma was admitted on 01/10/2026 with fever and productive cough (age 94 years).",
        "Treated with Ceftriaxone 1000 mg IV daily and supportive oxygen therapy.",
        "By 05/10/2026 patient was afebrile with SpO2 97 % on room air.",
        "Family contact Tariqul Karim was counseled on discharge medications.",
        "Also reviewed prior chest X-ray from 2019 showing clear lung fields.",
        "",
        "Follow-up:",
        "Review with Dr. Kamrul Hasan on 15/10/2026.",
    ]
    y = 800
    c.setFont("Helvetica", 11)
    for line in lines:
        c.drawString(50, y, line)
        y -= 20

    c.showPage()
    c.save()
    return buf.getvalue()


def build_scanned_and_image_header_bytes() -> bytes:
    """Sample 3: Page 1 is a scanned raster image (OCR); Page 2 has text + embedded image header."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Synthetic Scanned Clinical Report")
    c.setAuthor("Scanner")

    # Page 1: Full rasterized scanned image (no native text)
    scan_img = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(scan_img)
    title_font = _load_font(34)
    body_font = _load_font(28)

    scan_lines = [
        "SUNRISE HEALTH CENTER",
        "OUTPATIENT CONSULTATION NOTE",
        "Patient Name: Nadia Chowdhury",
        "MRN: UHID-441902",
        "DOB: 20/08/1984",
        "Phone: 01911223344",
        "Date of Visit: 11/10/2026",
        "Doctor: Dr. Mahmudul Haque",
        "Assessment: Mild iron deficiency anemia.",
        "Hemoglobin 10.8 g/dL. Ferrous sulfate 200 mg daily.",
    ]
    y = 80
    for idx, line in enumerate(scan_lines):
        draw.text((70, y), line, fill="black", font=title_font if idx < 2 else body_font)
        y += 65

    scan_buf = io.BytesIO()
    scan_img.save(scan_buf, format="PNG")
    scan_buf.seek(0)
    c.drawImage(ImageReader(scan_buf), 20, 40, width=555, height=740)
    c.showPage()

    # Page 2: Embedded clinic banner image (>= 100x100) + native clinical text
    header_img = Image.new("RGB", (900, 220), "white")
    h_draw = ImageDraw.Draw(header_img)
    h_draw.text((30, 30), "SUNRISE DIAGNOSTIC LAB", fill="black", font=title_font)
    h_draw.text((30, 90), "Patient: Nadia Chowdhury", fill="black", font=body_font)
    h_draw.text((30, 145), "Contact: 01911223344", fill="black", font=body_font)
    header_buf = io.BytesIO()
    header_img.save(header_buf, format="PNG")
    header_buf.seek(0)
    c.drawImage(ImageReader(header_buf), 50, 680, width=490, height=120)

    c.setFont("Helvetica", 11)
    c.drawString(50, 640, "Additional Notes:")
    c.drawString(50, 618, "Patient tolerated oral iron well without gastrointestinal symptoms.")
    c.drawString(50, 596, "Repeat CBC scheduled in 6 weeks to verify hemoglobin response.")
    c.showPage()
    c.save()
    return buf.getvalue()


def build_annotated_and_widget_pdf_bytes() -> bytes:
    """Helper PDF with native text, PDF annotation, and AcroForm widget field."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(
        (50, 80),
        "Patient Name: Karim Uddin\nVisit summary: Mild hypertension, continue Amlodipine 5 mg daily.",
        fontsize=12,
    )
    page.add_text_annot((50, 140), "Reviewed by Dr. Shahina Akter")

    widget = pymupdf.Widget()
    widget.field_name = "EmergencyContact"
    widget.field_label = "Emergency Contact"
    widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    widget.rect = pymupdf.Rect(50, 180, 300, 205)
    widget.field_value = "01755667788"
    page.add_widget(widget)

    raw = doc.tobytes()
    doc.close()
    return raw


def generate_fixtures(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "sample_text_lab_report.pdf": build_text_lab_report_bytes(),
        "sample_discharge_metadata.pdf": build_discharge_metadata_bytes(),
        "sample_scanned_image_header.pdf": build_scanned_and_image_header_bytes(),
    }
    written: list[Path] = []
    for name, content in files.items():
        path = output_dir / name
        path.write_bytes(content)
        written.append(path)
    return written


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    fixtures_dir = repo_root / "backend" / "tests" / "fixtures"
    if not (repo_root / "backend").is_dir():
        fixtures_dir = repo_root / "tests" / "fixtures"
    written = generate_fixtures(fixtures_dir)
    for path in written:
        print(f"Generated {path}")


if __name__ == "__main__":
    main()
