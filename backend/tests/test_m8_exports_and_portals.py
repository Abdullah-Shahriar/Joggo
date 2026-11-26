import io
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pymupdf

from app.db import SessionLocal
from app.models import User, UserRole, UserStatus
from app.security import hash_password
from app.services.exporter import export_jpg, export_pdf, export_png
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
        extracted = doc.load_page(0).get_text("text")
        assert "Discharge Summary" in extracted
        assert "Rahim Ahmed" in extracted
    finally:
        doc.close()

    png_bytes = export_png(sample)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(io.BytesIO(png_bytes)) as im_png:
        assert im_png.format == "PNG"
        assert im_png.width > 400 and im_png.height > 400

    jpg_bytes = export_jpg(sample)
    assert jpg_bytes.startswith(b"\xff\xd8\xff")
    with Image.open(io.BytesIO(jpg_bytes)) as im_jpg:
        assert im_jpg.format == "JPEG"
        assert im_jpg.width > 400 and im_jpg.height > 400
