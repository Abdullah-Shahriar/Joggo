import io
import uuid
import zipfile

from docx import Document as DocxDocument
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pymupdf

from app.db import SessionLocal
from app.models import User, UserRole, UserStatus
from app.security import hash_password
from app.services.exporter import export_docx, export_jpg, export_pdf, export_png, export_txt
from tests.conftest import CSRF_HEADERS


def _make_user(role: UserRole) -> str:
    email = f"portal-{role.value}-{uuid.uuid4().hex[:8]}@example.com"
    with SessionLocal() as db:
        db.add(
            User(
                email=email,
                password_hash=hash_password("StrongPass123"),
                full_name=f"Synthetic {role.value.title()}",
                role=role,
                status=UserStatus.active,
            )
        )
        db.commit()
    return email


def test_role_portal_login_isolation_and_auth_config(app: FastAPI) -> None:
    doctor_email = _make_user(UserRole.doctor)
    admin_email = _make_user(UserRole.admin)
    auditor_email = _make_user(UserRole.auditor)

    with TestClient(app, raise_server_exceptions=False) as c:
        cfg = c.get("/api/auth/config")
        assert cfg.status_code == 200
        assert "google_client_id" in cfg.json()

        # Admin & Auditor BLOCKED on public doctor login portal even with correct password
        for blocked_email in (admin_email, auditor_email):
            r = c.post(
                "/api/auth/login",
                json={"email": blocked_email, "password": "StrongPass123", "portal": "doctor"},
                headers=CSRF_HEADERS,
            )
            assert r.status_code == 403
            assert "access_token" not in r.cookies

        # Doctor & Auditor BLOCKED on /00admin/00admin portal even with correct password
        for blocked_email in (doctor_email, auditor_email):
            r = c.post(
                "/api/auth/login",
                json={"email": blocked_email, "password": "StrongPass123", "portal": "admin"},
                headers=CSRF_HEADERS,
            )
            assert r.status_code == 403
            assert "access_token" not in r.cookies

        # Doctor & Admin BLOCKED on /00auditor portal even with correct password
        for blocked_email in (doctor_email, admin_email):
            r = c.post(
                "/api/auth/login",
                json={"email": blocked_email, "password": "StrongPass123", "portal": "auditor"},
                headers=CSRF_HEADERS,
            )
            assert r.status_code == 403
            assert "access_token" not in r.cookies

        # Matching role succeeds on its dedicated portal
        for email, portal in (
            (doctor_email, "doctor"),
            (admin_email, "admin"),
            (auditor_email, "auditor"),
        ):
            r = c.post(
                "/api/auth/login",
                json={"email": email, "password": "StrongPass123", "portal": portal},
                headers=CSRF_HEADERS,
            )
            assert r.status_code == 200
            assert r.json()["user"]["role"] == portal


def test_export_pdf_png_and_jpg_outputs_are_valid() -> None:
    sample = (
        "# Discharge Summary\n\n"
        "**Patient:** Rahim Ahmed (Age 58)\n\n"
        "## Clinical Course\n"
        "- Admitted with mild chest discomfort.\n"
        "- Stabilized on daily medication and cleared for home follow-up.\n"
    )

    pdf_bytes = export_pdf(sample)
    assert pdf_bytes.startswith(b"%PDF-")
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        assert doc.page_count >= 1
        page0 = doc.load_page(0)
        extracted = page0.get_text("text")
        assert "Discharge Summary" in extracted
        assert "Rahim Ahmed" in extracted
        assert "JOGGO" in extracted
        # Centered JOGGO logo image watermark embedded on page
        assert len(page0.get_images()) >= 1
    finally:
        doc.close()

    png_bytes = export_png(sample)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(io.BytesIO(png_bytes)) as im_png:
        assert im_png.format == "PNG"
        assert im_png.width > 400 and im_png.height > 400
        # Center watermark region contains non-white pixels from the JOGGO logo
        cx, cy = im_png.width // 2, im_png.height // 2
        center_crop = im_png.crop((cx - 120, cy - 120, cx + 120, cy + 120))
        assert any(px != (255, 255, 255) for px in center_crop.getdata())

    jpg_bytes = export_jpg(sample)
    assert jpg_bytes.startswith(b"\xff\xd8\xff")
    with Image.open(io.BytesIO(jpg_bytes)) as im_jpg:
        assert im_jpg.format == "JPEG"
        assert im_jpg.width > 400 and im_jpg.height > 400

    # DOCX contains behind-text JOGGO logo watermark in header media while header/footer text remains empty
    docx_bytes = export_docx(sample)
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        names = zf.namelist()
        assert any(n.startswith("word/media/") and n.endswith(".png") for n in names), names
        header_xml = "".join(zf.read(n).decode("utf-8", errors="ignore") for n in names if "header" in n)
        assert 'behindDoc="1"' in header_xml
    parsed_docx = DocxDocument(io.BytesIO(docx_bytes))
    for sec in parsed_docx.sections:
        assert "".join(p.text for p in sec.header.paragraphs).strip() == ""
        assert "".join(p.text for p in sec.footer.paragraphs).strip() == ""

    # TXT includes subtle JOGGO watermark footer
    txt_out = export_txt(sample).decode("utf-8")
    assert "Rahim Ahmed" in txt_out
    assert "[JOGGO] Watermark" in txt_out


def test_manual_mark_handles_mixed_token_text_punctuation_and_re_marking(app: FastAPI) -> None:
    import time
    from scripts.make_sample_pdfs import build_text_lab_report_bytes

    email = _make_user(UserRole.doctor)
    with TestClient(app, raise_server_exceptions=False) as c:
        r_login = c.post(
            "/api/auth/login",
            json={"email": email, "password": "StrongPass123", "portal": "doctor"},
            headers=CSRF_HEADERS,
        )
        assert r_login.status_code == 200

        up = c.post(
            "/api/documents",
            files={"file": ("mark_edge.pdf", build_text_lab_report_bytes(), "application/pdf")},
            data={"task_type": "discharge_summary"},
            headers=CSRF_HEADERS,
        )
        assert up.status_code == 202
        doc_id = up.json()["id"]

        detail = {}
        for _ in range(100):
            detail = c.get(f"/api/documents/{doc_id}").json()
            if detail["status"] not in {"UPLOADED", "PROCESSING"}:
                break
            time.sleep(0.15)
        assert detail["status"] in {"REVIEW_REQUIRED", "BLOCKED"}

        san = c.get(f"/api/documents/{doc_id}/sanitized").json()
        version = san["version"]

        # 1. Mixed selection containing an already-replaced token + unmasked word must NOT fail
        #    with MARK_OVERLAPS_TOKEN; it strips the token and hides the unmasked word cleanly.
        r_mixed = c.post(
            f"/api/documents/{doc_id}/manual-marks",
            json={"text": "[PATIENT_A] Hematology", "entity_type": "OTHER"},
            headers={**CSRF_HEADERS, "If-Match": str(version)},
        )
        assert r_mixed.status_code == 200
        assert r_mixed.json()["occurrences"] >= 1
        version = r_mixed.json()["document"]["version"]

        # 2. Pure token-only selection still returns 422 MARK_OVERLAPS_TOKEN
        r_pure_tok = c.post(
            f"/api/documents/{doc_id}/manual-marks",
            json={"text": "[PATIENT_A]", "entity_type": "PATIENT"},
            headers={**CSRF_HEADERS, "If-Match": str(version)},
        )
        assert r_pure_tok.status_code == 422
        assert r_pure_tok.json()["error"]["code"] == "MARK_OVERLAPS_TOKEN"

        # 3. Word with punctuation (e.g. "Biochemistry" or "g/dL") resolves cleanly
        r_punct = c.post(
            f"/api/documents/{doc_id}/manual-marks",
            json={"text": "Biochemistry", "entity_type": "OTHER"},
            headers={**CSRF_HEADERS, "If-Match": str(version)},
        )
        assert r_punct.status_code == 200
        updated_doc = r_punct.json()["document"]
        assert updated_doc["status"] == "REVIEW_REQUIRED"
        assert updated_doc["safety_report"]["status"] == "PASS"

        # 4. Proceeding to Approve succeeds cleanly after resolution
        r_approve = c.post(
            f"/api/documents/{doc_id}/approve",
            json={"sanitized_sha256": updated_doc["sanitized_sha256"]},
            headers=CSRF_HEADERS,
        )
        assert r_approve.status_code == 200
        assert r_approve.json()["status"] == "APPROVED"
