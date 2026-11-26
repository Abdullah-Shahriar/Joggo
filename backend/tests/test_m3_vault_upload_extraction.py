from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import io
import time
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pymupdf
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.errors import ErrorCode
from app.models import AuditLog, Document, DocumentStatus, PipelineStep, PipelineStepName, PipelineStepStatus, TaskType, User, UserRole, UserStatus
from app.security import hash_password
from app.services.extraction import ExtractionError, extract_pdf
from app.services.vault import VaultService, run_startup_recovery, vault
from scripts.make_sample_pdfs import (
    build_annotated_and_widget_pdf_bytes,
    build_discharge_metadata_bytes,
    build_scanned_and_image_header_bytes,
    build_text_lab_report_bytes,
)
from tests.conftest import CSRF_HEADERS


def _create_and_login(
    app: FastAPI,
    *,
    role: UserRole = UserRole.doctor,
    status: UserStatus = UserStatus.active,
) -> tuple[TestClient, User]:
    email = f"{role.value}-{uuid.uuid4().hex[:8]}@example.com"
    with SessionLocal() as db:
        user = User(
            email=email,
            password_hash=hash_password("StrongPass123"),
            full_name=f"Synthetic {role.value}",
            role=role,
            status=status,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    c = TestClient(app, raise_server_exceptions=False)
    c.__enter__()
    res = c.post(
        "/api/auth/login",
        json={"email": email, "password": "StrongPass123"},
        headers=CSRF_HEADERS,
    )
    assert res.status_code == 200
    return c, user


def _make_blank_pdf(pages: int = 1, encrypt: bool = False) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page()
    if encrypt:
        raw = doc.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw="secret",
            owner_pw="owner",
        )
    else:
        raw = doc.tobytes()
    doc.close()
    return raw


def _wait_for_extract_done(client: TestClient, doc_id: str, timeout: float = 25.0) -> dict:
    deadline = time.monotonic() + timeout
    last_body: dict = {}
    while time.monotonic() < deadline:
        res = client.get(f"/api/documents/{doc_id}")
        assert res.status_code == 200
        last_body = res.json()
        if last_body["status"] not in {"UPLOADED", "PROCESSING"}:
            return last_body
        time.sleep(0.15)
    raise AssertionError(f"Timed out waiting for pipeline completion; last={last_body}")


def test_vault_encryption_lru_caps_idle_expiration_and_startup_recovery() -> None:
    local_vault = VaultService()
    sid = uuid.uuid4()
    doc_id = uuid.uuid4()
    uid = uuid.uuid4()
    t0 = datetime(2026, 11, 26, 10, 0, 0, tzinfo=timezone.utc)

    local_vault.put(
        sid,
        doc_id,
        {"original_text": "Patient Rahim Ahmed 01712345678"},
        user_id=uid,
        now=t0,
    )
    # Raw stored ciphertext must not contain plaintext
    entry = local_vault._entries[(str(sid), str(doc_id))]
    assert b"Rahim Ahmed" not in entry.ciphertext
    assert b"01712345678" not in entry.ciphertext

    fetched = local_vault.get(sid, doc_id, now=t0 + timedelta(minutes=5))
    assert fetched is not None
    assert fetched["original_text"] == "Patient Rahim Ahmed 01712345678"

    # Idle > VAULT_IDLE_MINUTES expires entry
    expired = local_vault.get(sid, doc_id, now=t0 + timedelta(minutes=40))
    assert expired is None
    assert local_vault.stats()["entries"] == 0

    # Per-session cap (20 entries) evicts oldest
    for i in range(22):
        local_vault.put(sid, uuid.uuid4(), {"idx": i}, user_id=uid, now=t0)
    assert local_vault.stats()["entries"] == 20

    # wipe_user removes all entries for user
    local_vault.wipe_user(uid, mark_db=False)
    assert local_vault.stats()["entries"] == 0

    # Startup recovery marks PROCESSING->FAILED and SENDING->LLM_FAILED and vault_expired=True
    with SessionLocal() as db:
        owner = User(
            email=f"startup-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("StrongPass123"),
            full_name="Dr Startup",
            role=UserRole.doctor,
            status=UserStatus.active,
        )
        db.add(owner)
        db.flush()
        d_proc = Document(
            owner_id=owner.id,
            original_filename="proc.pdf",
            file_sha256=uuid.uuid4().hex * 2,
            size_bytes=100,
            page_count=1,
            task_type=TaskType.case_summary,
            status=DocumentStatus.PROCESSING,
            vault_expired=False,
        )
        d_send = Document(
            owner_id=owner.id,
            original_filename="send.pdf",
            file_sha256=uuid.uuid4().hex * 2,
            size_bytes=100,
            page_count=1,
            task_type=TaskType.case_summary,
            status=DocumentStatus.SENDING,
            vault_expired=False,
        )
        db.add_all([d_proc, d_send])
        db.commit()
        proc_id, send_id = d_proc.id, d_send.id

        run_startup_recovery(db)
        db.expire_all()
        d_proc_after = db.get(Document, proc_id)
        d_send_after = db.get(Document, send_id)
        assert d_proc_after is not None and d_proc_after.status == DocumentStatus.FAILED
        assert d_proc_after.failure_code == "SERVER_RESTART"
        assert d_proc_after.vault_expired is True
        assert d_send_after is not None and d_send_after.status == DocumentStatus.LLM_FAILED
        assert d_send_after.failure_code == "SERVER_RESTART"
        assert d_send_after.vault_expired is True


def test_extraction_on_text_metadata_scanned_image_annotations_and_empty() -> None:
    # 1. Text lab report
    res1 = extract_pdf(build_text_lab_report_bytes())
    assert res1.page_count == 1
    assert "Rahim Ahmed" in res1.text
    assert "MRN-884210" in res1.text
    assert "13.4 g/dL" in res1.text
    assert res1.metadata_hints == []  # ReportLab is in software ignore list

    # 2. Discharge summary with metadata author
    res2 = extract_pdf(build_discharge_metadata_bytes())
    assert res2.page_count == 1
    assert "Salma Begum" in res2.text
    assert "Tariqul Karim" in res2.metadata_hints

    # 3. Scanned page OCR + embedded image header OCR
    res3 = extract_pdf(build_scanned_and_image_header_bytes())
    assert res3.page_count == 2
    assert "Nadia" in res3.text
    assert "441902" in res3.text or "01911223344" in res3.text
    assert "[IMAGE_TEXT p2]" in res3.text

    # 4. Annotations and form widgets
    res4 = extract_pdf(build_annotated_and_widget_pdf_bytes())
    assert "Karim Uddin" in res4.text
    assert "Shahina Akter" in res4.text
    assert "01755667788" in res4.text

    # 5. Blank PDF fails with EMPTY_DOCUMENT
    with pytest.raises(ExtractionError) as exc_info:
        extract_pdf(_make_blank_pdf(pages=1))
    assert exc_info.value.code == ErrorCode.EMPTY_DOCUMENT


def test_upload_validations_duplicates_rbac_and_logout_vault_wipe(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c_doc_a, _doc_a = _create_and_login(app, role=UserRole.doctor)
    c_doc_b, _doc_b = _create_and_login(app, role=UserRole.doctor)
    c_admin, _admin = _create_and_login(app, role=UserRole.admin)
    c_auditor, _auditor = _create_and_login(app, role=UserRole.auditor)
    c_restricted, _restricted = _create_and_login(app, role=UserRole.doctor, status=UserStatus.restricted)

    try:
        sample_pdf = build_text_lab_report_bytes()

        # Admin & auditor blocked with 403 ADMIN_NO_DOCUMENT_ACCESS
        for c_priv in (c_admin, c_auditor):
            res = c_priv.post(
                "/api/documents",
                files={"file": ("lab.pdf", sample_pdf, "application/pdf")},
                data={"task_type": "discharge_summary"},
                headers=CSRF_HEADERS,
            )
            assert res.status_code == 403
            assert res.json()["error"]["code"] == "ADMIN_NO_DOCUMENT_ACCESS"

        # Restricted doctor blocked with 403 ACCOUNT_RESTRICTED
        res_rest = c_restricted.post(
            "/api/documents",
            files={"file": ("lab.pdf", sample_pdf, "application/pdf")},
            data={"task_type": "discharge_summary"},
            headers=CSRF_HEADERS,
        )
        assert res_rest.status_code == 403
        assert res_rest.json()["error"]["code"] == "ACCOUNT_RESTRICTED"

        # Non-PDF -> 415 NOT_A_PDF
        res_non = c_doc_a.post(
            "/api/documents",
            files={"file": ("notes.txt", b"not a pdf at all", "text/plain")},
            data={"task_type": "case_summary"},
            headers=CSRF_HEADERS,
        )
        assert res_non.status_code == 415
        assert res_non.json()["error"]["code"] == "NOT_A_PDF"

        # Corrupt PDF -> 422 PDF_CORRUPT
        res_corrupt = c_doc_a.post(
            "/api/documents",
            files={"file": ("bad.pdf", b"%PDF-1.7\ngarbage-corrupt-body", "application/pdf")},
            data={"task_type": "case_summary"},
            headers=CSRF_HEADERS,
        )
        assert res_corrupt.status_code == 422
        assert res_corrupt.json()["error"]["code"] == "PDF_CORRUPT"

        # Encrypted PDF -> 422 PDF_ENCRYPTED
        res_enc = c_doc_a.post(
            "/api/documents",
            files={"file": ("enc.pdf", _make_blank_pdf(encrypt=True), "application/pdf")},
            data={"task_type": "case_summary"},
            headers=CSRF_HEADERS,
        )
        assert res_enc.status_code == 422
        assert res_enc.json()["error"]["code"] == "PDF_ENCRYPTED"

        # Too many pages -> 422 TOO_MANY_PAGES
        res_pages = c_doc_a.post(
            "/api/documents",
            files={"file": ("big.pdf", _make_blank_pdf(pages=31), "application/pdf")},
            data={"task_type": "case_summary"},
            headers=CSRF_HEADERS,
        )
        assert res_pages.status_code == 422
        assert res_pages.json()["error"]["code"] == "TOO_MANY_PAGES"

        # Oversize file -> 413 FILE_TOO_LARGE
        monkeypatch.setattr(get_settings(), "MAX_UPLOAD_MB", 1)
        res_big = c_doc_a.post(
            "/api/documents",
            files={"file": ("huge.pdf", b"%PDF-1.4\n" + (b"0" * (1024 * 1024 + 10)), "application/pdf")},
            data={"task_type": "case_summary"},
            headers=CSRF_HEADERS,
        )
        assert res_big.status_code == 413
        assert res_big.json()["error"]["code"] == "FILE_TOO_LARGE"
        monkeypatch.setattr(get_settings(), "MAX_UPLOAD_MB", 10)

        # Valid upload -> 202 + background extraction succeeds
        up = c_doc_a.post(
            "/api/documents",
            files={"file": ("synthetic_lab.pdf", sample_pdf, "application/pdf")},
            data={"task_type": "discharge_summary"},
            headers=CSRF_HEADERS,
        )
        assert up.status_code == 202
        doc_id = up.json()["id"]

        detail = _wait_for_extract_done(c_doc_a, doc_id)
        extract_step = next(s for s in detail["steps"] if s["step"] == "EXTRACT")
        assert extract_step["status"] == "succeeded"

        # Duplicate upload -> 409 DUPLICATE_DOCUMENT with existing_document_id
        dup = c_doc_a.post(
            "/api/documents",
            files={"file": ("synthetic_lab_copy.pdf", sample_pdf, "application/pdf")},
            data={"task_type": "discharge_summary"},
            headers=CSRF_HEADERS,
        )
        assert dup.status_code == 409
        assert dup.json()["error"]["code"] == "DUPLICATE_DOCUMENT"
        assert dup.json()["error"]["existing_document_id"] == doc_id

        # Doctor B trying to read Doctor A's document -> 404 + audit DOC_ACCESS_DENIED
        denied = c_doc_b.get(f"/api/documents/{doc_id}")
        assert denied.status_code == 404
        assert denied.json()["error"]["code"] == "NOT_FOUND"
        with SessionLocal() as db:
            row = db.execute(
                select(AuditLog)
                .where(AuditLog.action == "DOC_ACCESS_DENIED", AuditLog.resource_id == doc_id)
                .limit(1)
            ).scalar_one_or_none()
            assert row is not None

        # Logout wipes vault for Doctor A's session and marks document vault_expired=True
        out = c_doc_a.post("/api/auth/logout", headers=CSRF_HEADERS)
        assert out.status_code == 200
        with SessionLocal() as db:
            refreshed = db.get(Document, uuid.UUID(doc_id))
            assert refreshed is not None
            assert refreshed.vault_expired is True

        # Empty PDF upload completes extraction step as FAILED with EMPTY_DOCUMENT
        up_empty = c_doc_b.post(
            "/api/documents",
            files={"file": ("empty.pdf", _make_blank_pdf(pages=1), "application/pdf")},
            data={"task_type": "case_summary"},
            headers=CSRF_HEADERS,
        )
        assert up_empty.status_code == 202
        empty_detail = _wait_for_extract_done(c_doc_b, up_empty.json()["id"])
        assert empty_detail["status"] == "FAILED"
        assert empty_detail["failure_code"] == "EMPTY_DOCUMENT"
    finally:
        for c in (c_doc_a, c_doc_b, c_admin, c_auditor, c_restricted):
            c.__exit__(None, None, None)


def test_concurrent_duplicate_upload_creates_exactly_one_document(app: FastAPI) -> None:
    c, _user = _create_and_login(app, role=UserRole.doctor)
    try:
        pdf = build_discharge_metadata_bytes()
        # Capture cookies to run two independent concurrent requests as the same user
        cookies = dict(c.cookies)

        def do_upload() -> tuple[int, dict]:
            with TestClient(app, raise_server_exceptions=False, cookies=cookies) as tc:
                r = tc.post(
                    "/api/documents",
                    files={"file": ("race.pdf", pdf, "application/pdf")},
                    data={"task_type": "discharge_summary"},
                    headers=CSRF_HEADERS,
                )
                return r.status_code, r.json()

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(do_upload)
            f2 = pool.submit(do_upload)
            results = [f1.result(), f2.result()]

        statuses = sorted(r[0] for r in results)
        assert statuses == [202, 409]
        dup_body = next(body for code, body in results if code == 409)
        assert dup_body["error"]["code"] == "DUPLICATE_DOCUMENT"
    finally:
        c.__exit__(None, None, None)


def test_png_jpg_svg_uploads_and_document_delete_including_referer_csrf(app: FastAPI) -> None:
    from PIL import Image, ImageDraw

    c, _user = _create_and_login(app, role=UserRole.doctor)
    try:
        # Build a clean synthetic clinical note image for PNG and JPEG OCR
        img = Image.new("RGB", (1100, 320), "white")
        draw = ImageDraw.Draw(img)
        draw.text((40, 40), "Patient Name: Nadia Islam", fill="black")
        draw.text((40, 100), "Phone: 01911223344", fill="black")
        draw.text((40, 160), "Assessment: Stable recovery, continue daily medication.", fill="black")

        png_buf = io.BytesIO()
        img.save(png_buf, format="PNG")
        png_bytes = png_buf.getvalue()

        jpg_buf = io.BytesIO()
        img.save(jpg_buf, format="JPEG", quality=95)
        jpg_bytes = jpg_buf.getvalue()

        svg_bytes = (
            b'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="200">'
            b'<text x="20" y="40">Patient Name: Karim Uddin</text>'
            b'<text x="20" y="80">Phone: 01755667788</text>'
            b'<text x="20" y="120">Follow-up visit planned in two weeks for blood pressure check.</text>'
            b"</svg>"
        )

        # 1. PNG upload succeeds & previews with image/png
        r_png = c.post(
            "/api/documents",
            files={"file": ("note.png", png_bytes, "image/png")},
            data={"task_type": "case_summary"},
            headers=CSRF_HEADERS,
        )
        assert r_png.status_code == 202
        png_id = r_png.json()["id"]
        png_detail = _wait_for_extract_done(c, png_id)
        assert png_detail["status"] in {"REVIEW_REQUIRED", "BLOCKED"}
        prev_png = c.get(f"/api/documents/{png_id}/original-pdf")
        assert prev_png.status_code == 200
        assert prev_png.headers["content-type"].startswith("image/png")

        # 2. JPG upload succeeds
        r_jpg = c.post(
            "/api/documents",
            files={"file": ("photo.jpg", jpg_bytes, "image/jpeg")},
            data={"task_type": "discharge_summary"},
            headers=CSRF_HEADERS,
        )
        assert r_jpg.status_code == 202
        jpg_id = r_jpg.json()["id"]
        jpg_detail = _wait_for_extract_done(c, jpg_id)
        assert jpg_detail["status"] in {"REVIEW_REQUIRED", "BLOCKED"}

        # 3. SVG upload succeeds & XXE DOCTYPE SVG is rejected
        r_svg = c.post(
            "/api/documents",
            files={"file": ("chart.svg", svg_bytes, "image/svg+xml")},
            data={"task_type": "treatment_plan"},
            headers=CSRF_HEADERS,
        )
        assert r_svg.status_code == 202
        svg_id = r_svg.json()["id"]
        svg_detail = _wait_for_extract_done(c, svg_id)
        assert svg_detail["status"] in {"REVIEW_REQUIRED", "BLOCKED"}
        prev_svg = c.get(f"/api/documents/{svg_id}/original-pdf")
        assert prev_svg.status_code == 200
        assert prev_svg.headers["content-type"].startswith("image/svg+xml")
        assert prev_svg.headers.get("content-security-policy") == "sandbox"

        xxe_svg = b'<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><svg><text>&xxe;</text></svg>'
        r_xxe = c.post(
            "/api/documents",
            files={"file": ("bad.svg", xxe_svg, "image/svg+xml")},
            data={"task_type": "case_summary"},
            headers=CSRF_HEADERS,
        )
        assert r_xxe.status_code in {415, 422}

        # 4. Delete document works with Origin AND with Referer-only (no Origin)
        r_del_origin = c.delete(f"/api/documents/{png_id}", headers=CSRF_HEADERS)
        assert r_del_origin.status_code == 200
        assert c.get(f"/api/documents/{png_id}").status_code == 404

        r_del_referer = c.delete(
            f"/api/documents/{svg_id}",
            headers={"X-Requested-With": "fetch", "Referer": "http://localhost:3000/documents"},
        )
        assert r_del_referer.status_code == 200
        assert c.get(f"/api/documents/{svg_id}").status_code == 404
    finally:
        c.__exit__(None, None, None)
