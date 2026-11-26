from concurrent.futures import ThreadPoolExecutor
import json
import logging
import time
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    AuditLog,
    Document,
    DocumentEntity,
    DocumentStatus,
    PipelineStep,
    PipelineStepName,
    PipelineStepStatus,
    User,
    UserRole,
    UserStatus,
)
from app.security import hash_password
from app.services.detection.base import Span
from app.services.detection.resolve import resolve_overlaps, run_detection
from app.services.pipeline import run_document_pipeline
from app.services.safety import run_safety_scan
from app.services.tokenizer import tokenize_text
from app.services.vault import vault
from scripts.make_sample_pdfs import (
    build_discharge_metadata_bytes,
    build_scanned_and_image_header_bytes,
    build_text_lab_report_bytes,
)
from tests.conftest import CSRF_HEADERS


def _login_doctor(app: FastAPI) -> tuple[TestClient, User]:
    email = f"m4doc-{uuid.uuid4().hex[:8]}@example.com"
    with SessionLocal() as db:
        user = User(
            email=email,
            password_hash=hash_password("StrongPass123"),
            full_name="Dr Synthetic M4",
            role=UserRole.doctor,
            status=UserStatus.active,
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


def _wait_for_pipeline(client: TestClient, doc_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        res = client.get(f"/api/documents/{doc_id}")
        assert res.status_code == 200
        last = res.json()
        if last["status"] not in {"UPLOADED", "PROCESSING"}:
            return last
        time.sleep(0.15)
    raise AssertionError(f"Timed out waiting for pipeline; last={last}")


def test_detection_and_tokenization_hipaa18_dates_stoplists_labs_and_overlaps() -> None:
    text = (
        "City Care Medical College\n"
        "Patient Name: Rahim Ahmed\n"
        "DOB: 14/05/1968\n"
        "MRN: MRN-884210\n"
        "NID: 1968472910482\n"
        "Policy No: POL-77412\n"
        "Serial: SN-998811\n"
        "Phone: +880 1712-345678\n"
        "Fax: +1 212-555-0199\n"
        "Email: rahim.ahmed.synth@example.test\n"
        "Address: House 14, Road 7, Dhanmondi, Dhaka\n"
        "Consultant: Dr. Nasrin Sultana\n"
        "Father's Name: Mr. Abdul Karim\n"
        "Date of Admission: 10/10/2026\n"
        "Prior Visit: 05/10/2026\n"
        "Follow-up: 17/10/2026\n"
        "Invalid Date: 32/13/2026\n"
        "Portal: https://portal.example.test/case/1\n"
        "Workstation IP: 192.168.10.42\n"
        "Country: Bangladesh\n"
        "Note: Rahim has Parkinson disease and takes Metformin 500 mg daily.\n"
        "Hemoglobin 13.4 g/dL, Glucose 142 mg/dL, HbA1c 7.4 %, BP 138/86 mmHg, HR 78 bpm.\n"
        "Old record from 2019 reviewed. Older relative is 94 years old.\n"
    )

    spans = run_detection(text, metadata_hints=["Abdul Karim"], date_order="DMY")
    tok = tokenize_text(text, spans)
    clean = tok.sanitized_text

    # HIPAA 18 values scrubbed
    for secret in (
        "Rahim Ahmed",
        "Rahim",
        "14/05/1968",
        "MRN-884210",
        "1968472910482",
        "POL-77412",
        "SN-998811",
        "1712-345678",
        "212-555-0199",
        "rahim.ahmed.synth@example.test",
        "Dhanmondi",
        "Nasrin Sultana",
        "Abdul Karim",
        "10/10/2026",
        "05/10/2026",
        "17/10/2026",
        "32/13/2026",
        "https://portal.example.test/case/1",
        "192.168.10.42",
        "City Care Medical College",
        "94 years",
    ):
        assert secret not in clean, f"Expected {secret!r} to be tokenized, got:\n{clean}"

    # Context-preserving tokens verified
    assert "[PATIENT_A]" in clean
    assert clean.count("[PATIENT_A]") >= 2  # Full name + swept first name share [PATIENT_A]
    assert "Age 58" in clean
    assert "[DAY_0]" in clean
    assert "[DAY_-5]" in clean
    assert "[DAY_7]" in clean
    assert "[DAY_?]" in clean
    assert "90+ years" in clean

    # Year-only, country, medical stoplist terms, and lab values preserved
    assert "2019" in clean
    assert "Bangladesh" in clean
    assert "Parkinson" in clean
    assert "Metformin 500 mg" in clean
    assert "13.4 g/dL" in clean
    assert "142 mg/dL" in clean
    assert "7.4 %" in clean
    assert "138/86 mmHg" in clean
    assert "78 bpm" in clean

    # DOB > 89 -> Age 90+
    elder_text = "Patient Name: Salma Begum\nDOB: 03/02/1932\nDate of Admission: 01/10/2026\n"
    elder_tok = tokenize_text(elder_text, run_detection(elder_text, date_order="DMY"))
    assert "Age 90+" in elder_tok.sanitized_text

    # Deterministic overlap resolution: higher priority wins over lower priority
    s_low = Span(0, 10, "OTHER", 0.99, "d", "r1", "low")
    s_high = Span(2, 8, "MRN", 0.70, "d", "r2", "high")
    resolved = resolve_overlaps([s_low, s_high])
    assert resolved == [s_high]


def test_full_pipeline_on_three_sample_pdfs_and_p1_t5_privacy_check(
    app: FastAPI,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    c, _user = _login_doctor(app)
    try:
        samples = [
            ("lab_report.pdf", build_text_lab_report_bytes(), "discharge_summary"),
            ("discharge_meta.pdf", build_discharge_metadata_bytes(), "discharge_summary"),
            ("scanned_header.pdf", build_scanned_and_image_header_bytes(), "case_summary"),
        ]
        doc_ids: list[str] = []
        for fname, pdf_bytes, task in samples:
            up = c.post(
                "/api/documents",
                files={"file": (fname, pdf_bytes, "application/pdf")},
                data={"task_type": task},
                headers=CSRF_HEADERS,
            )
            assert up.status_code == 202
            doc_id = up.json()["id"]
            detail = _wait_for_pipeline(c, doc_id)
            assert detail["status"] == "REVIEW_REQUIRED", f"{fname} ended in {detail['status']}: {detail['safety_report']}"
            assert detail["safety_report"]["status"] == "PASS"
            assert detail["sanitized_sha256"] is not None
            doc_ids.append(doc_id)

        # Verify review endpoints work on sample 1
        d1 = doc_ids[0]
        assert c.get("/api/documents").json()["total"] >= 3
        assert len(c.get(f"/api/documents/{d1}/steps").json()["steps"]) == 6
        orig = c.get(f"/api/documents/{d1}/original-text")
        assert orig.status_code == 200
        assert "Rahim Ahmed" in orig.json()["original_text"]
        assert len(orig.json()["highlights"]) > 0

        pdf_res = c.get(f"/api/documents/{d1}/original-pdf")
        assert pdf_res.status_code == 200
        assert pdf_res.content.startswith(b"%PDF-")

        san = c.get(f"/api/documents/{d1}/sanitized")
        assert san.status_code == 200
        assert "Rahim Ahmed" not in san.json()["sanitized_text"]
        assert "[PATIENT_A]" in san.json()["sanitized_text"]

        # Sample 2 metadata author hint "Tariqul Karim" must be scrubbed from sanitized text
        san2 = c.get(f"/api/documents/{doc_ids[1]}/sanitized").json()["sanitized_text"]
        assert "Tariqul Karim" not in san2
        assert "Salma Begum" not in san2

        # P1 / T5 privacy check: NO real values in DB tables or captured logs
        forbidden_values = [
            "Rahim Ahmed",
            "1968472910482",
            "1712-345678",
            "rahim.ahmed.synth@example.test",
            "MRN-884210",
            "Dhanmondi",
            "Nasrin Sultana",
            "Salma Begum",
            "Tariqul Karim",
            "HSP-550192",
            "01819-654321",
            "Nadia Chowdhury",
            "01911223344",
        ]

        with SessionLocal() as db:
            db_blob_parts: list[str] = []
            for did in doc_ids:
                doc_row = db.get(Document, uuid.UUID(did))
                assert doc_row is not None
                db_blob_parts.append(doc_row.sanitized_text or "")
                db_blob_parts.append(json.dumps(doc_row.entity_summary or {}))
                db_blob_parts.append(json.dumps(doc_row.safety_report or {}))
                for ent in db.execute(select(DocumentEntity).where(DocumentEntity.document_id == doc_row.id)).scalars():
                    db_blob_parts.append(f"{ent.token} {ent.entity_type} {ent.rule_id} {ent.reason}")
                for st in db.execute(select(PipelineStep).where(PipelineStep.document_id == doc_row.id)).scalars():
                    db_blob_parts.append(f"{st.error_code or ''} {st.error_message or ''}")

            for alog in db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(50)).scalars():
                db_blob_parts.append(json.dumps(alog.metadata_ or {}))

            combined_db = "\n".join(db_blob_parts)
            combined_logs = "\n".join(r.getMessage() for r in caplog.records)

            for secret in forbidden_values:
                assert secret not in combined_db, f"PHI leak in DB: {secret!r}"
                assert secret not in combined_logs, f"PHI leak in logs: {secret!r}"

        # Delete document wipes vault and removes DB record
        del_res = c.delete(f"/api/documents/{d1}", headers=CSRF_HEADERS)
        assert del_res.status_code == 200
        assert c.get(f"/api/documents/{d1}").status_code == 404
    finally:
        c.__exit__(None, None, None)


def test_seeded_leak_blocks_manual_mark_clears_approval_reset_stale_and_version_conflict(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Seed a leak: make initial run_detection skip a synthetic identifier "Xylar Zephron"
    # while leaving a detectable pattern (e.g., an email) OR name component so safety scan BLOCKs!
    from app.services.detection import resolve as resolve_mod

    orig_run_detection = resolve_mod.run_detection
    skip_once = {"active": True}

    def leaky_detection(text: str, **kwargs):
        spans = orig_run_detection(text, **kwargs)
        if skip_once["active"]:
            # Drop the email span on first pass so safety scan catches the residual email and BLOCKs!
            skip_once["active"] = False
            return [s for s in spans if s.entity_type != "EMAIL"]
        return spans

    monkeypatch.setattr("app.services.pipeline.run_detection", leaky_detection)

    c, _user = _login_doctor(app)
    try:
        up = c.post(
            "/api/documents",
            files={"file": ("leaky.pdf", build_text_lab_report_bytes(), "application/pdf")},
            data={"task_type": "discharge_summary"},
            headers=CSRF_HEADERS,
        )
        assert up.status_code == 202
        doc_id = up.json()["id"]

        detail = _wait_for_pipeline(c, doc_id)
        assert detail["status"] == "BLOCKED"
        assert detail["safety_report"]["status"] == "BLOCK"
        assert len(detail["safety_report"]["findings"]) >= 1

        # P4: sanitized_text MUST be NULL in PostgreSQL while BLOCKED
        with SessionLocal() as db:
            row = db.get(Document, uuid.UUID(doc_id))
            assert row is not None
            assert row.sanitized_text is None
            assert "rahim.ahmed.synth@example.test" not in json.dumps(row.safety_report or {})

        # Approval while BLOCKED is rejected
        bad_approve = c.post(
            f"/api/documents/{doc_id}/approve",
            json={"sanitized_sha256": "0" * 64},
            headers=CSRF_HEADERS,
        )
        assert bad_approve.status_code == 409

        # Owner can read sanitized text from Vault (with snippet)
        san_blocked = c.get(f"/api/documents/{doc_id}/sanitized")
        assert san_blocked.status_code == 200
        assert "rahim.ahmed.synth@example.test" in san_blocked.json()["sanitized_text"]
        version = san_blocked.json()["version"]

        # Overlapping token rejected with 422 MARK_OVERLAPS_TOKEN
        overlap_res = c.post(
            f"/api/documents/{doc_id}/manual-marks",
            json={"text": "[PATIENT_A]", "entity_type": "PATIENT"},
            headers={**CSRF_HEADERS, "If-Match": str(version)},
        )
        assert overlap_res.status_code == 422
        assert overlap_res.json()["error"]["code"] == "MARK_OVERLAPS_TOKEN"

        # Missing text rejected with 422 MARK_NOT_FOUND
        missing_res = c.post(
            f"/api/documents/{doc_id}/manual-marks",
            json={"text": "NonexistentTokenString", "entity_type": "OTHER"},
            headers={**CSRF_HEADERS, "If-Match": str(version)},
        )
        assert missing_res.status_code == 422
        assert missing_res.json()["error"]["code"] == "MARK_NOT_FOUND"

        # Wrong If-Match version rejected with 409 VERSION_CONFLICT
        conflict_res = c.post(
            f"/api/documents/{doc_id}/manual-marks",
            json={"text": "rahim.ahmed.synth@example.test", "entity_type": "EMAIL"},
            headers={**CSRF_HEADERS, "If-Match": str(version + 99)},
        )
        assert conflict_res.status_code == 409
        assert conflict_res.json()["error"]["code"] == "VERSION_CONFLICT"

        # Valid manual mark clears BLOCK -> REVIEW_REQUIRED and persists sanitized_text
        mark_res = c.post(
            f"/api/documents/{doc_id}/manual-marks",
            json={"text": "rahim.ahmed.synth@example.test", "entity_type": "EMAIL"},
            headers={**CSRF_HEADERS, "If-Match": str(version)},
        )
        assert mark_res.status_code == 200
        assert mark_res.json()["occurrences"] == 1
        updated_doc = mark_res.json()["document"]
        assert updated_doc["status"] == "REVIEW_REQUIRED"
        assert updated_doc["safety_report"]["status"] == "PASS"
        assert updated_doc["version"] == version + 1

        # Stale sanitized_sha256 rejected with 409 STALE_REVIEW
        stale = c.post(
            f"/api/documents/{doc_id}/approve",
            json={"sanitized_sha256": "a" * 64},
            headers=CSRF_HEADERS,
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "STALE_REVIEW"

        # Valid approve succeeds
        good_sha = updated_doc["sanitized_sha256"]
        approved = c.post(
            f"/api/documents/{doc_id}/approve",
            json={"sanitized_sha256": good_sha},
            headers=CSRF_HEADERS,
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "APPROVED"
        assert approved.json()["approved_at"] is not None
        approved_version = approved.json()["version"]

        # P8: Manual mark after approval resets approved_at and returns status to REVIEW_REQUIRED
        mark_after = c.post(
            f"/api/documents/{doc_id}/manual-marks",
            json={"text": "routine diabetes", "entity_type": "OTHER"},
            headers={**CSRF_HEADERS, "If-Match": str(approved_version)},
        )
        assert mark_after.status_code == 200
        assert mark_after.json()["document"]["status"] == "REVIEW_REQUIRED"
        assert mark_after.json()["document"]["approved_at"] is None

        # Concurrent simultaneous manual marks with same If-Match -> 1 succeeds (200), 1 gets VERSION_CONFLICT (409)
        v_race = mark_after.json()["document"]["version"]
        cookies = dict(c.cookies)

        def race_mark(text_val: str) -> int:
            with TestClient(app, raise_server_exceptions=False, cookies=cookies) as tc:
                r = tc.post(
                    f"/api/documents/{doc_id}/manual-marks",
                    json={"text": text_val, "entity_type": "OTHER"},
                    headers={**CSRF_HEADERS, "If-Match": str(v_race)},
                )
                return r.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(race_mark, "Hematology")
            f2 = pool.submit(race_mark, "Biochemistry")
            codes = sorted([f1.result(), f2.result()])
        assert codes == [200, 409]
    finally:
        c.__exit__(None, None, None)


def test_pipeline_failure_injection_and_resume_skips_succeeded_steps(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Inject failure at TOKENIZE step, then clear failure and resume -> EXTRACT & DETECT skipped!
    import app.services.pipeline as pipeline_mod

    orig_tokenize = pipeline_mod.tokenize_text
    boom = {"fail": True}

    def flaky_tokenize(text: str, spans):
        if boom["fail"]:
            boom["fail"] = False
            raise RuntimeError("Injected tokenize failure")
        return orig_tokenize(text, spans)

    monkeypatch.setattr(pipeline_mod, "tokenize_text", flaky_tokenize)

    c, _user = _login_doctor(app)
    try:
        up = c.post(
            "/api/documents",
            files={"file": ("resume_test.pdf", build_text_lab_report_bytes(), "application/pdf")},
            data={"task_type": "case_summary"},
            headers=CSRF_HEADERS,
        )
        assert up.status_code == 202
        doc_id = up.json()["id"]

        failed_detail = _wait_for_pipeline(c, doc_id)
        assert failed_detail["status"] == "FAILED"
        assert failed_detail["failure_code"] == "DETECTION_FAILED"

        steps_before = {s["step"]: s for s in failed_detail["steps"]}
        assert steps_before["EXTRACT"]["status"] == "succeeded"
        assert steps_before["EXTRACT"]["attempts"] == 1
        assert steps_before["DETECT"]["status"] == "succeeded"
        assert steps_before["DETECT"]["attempts"] == 1
        assert steps_before["TOKENIZE"]["status"] == "failed"
        assert steps_before["TOKENIZE"]["attempts"] == 1

        # Find session family id from vault and run resume
        matching_sids = [sid for sid, did in vault._entries.keys() if did == doc_id]
        assert len(matching_sids) == 1
        run_document_pipeline(uuid.UUID(doc_id), uuid.UUID(matching_sids[0]))

        resumed_detail = c.get(f"/api/documents/{doc_id}").json()
        assert resumed_detail["status"] == "REVIEW_REQUIRED"
        steps_after = {s["step"]: s for s in resumed_detail["steps"]}
        # Succeeded steps were skipped on resume (attempts unchanged!)
        assert steps_after["EXTRACT"]["attempts"] == 1
        assert steps_after["DETECT"]["attempts"] == 1
        assert steps_after["TOKENIZE"]["status"] == "succeeded"
        assert steps_after["TOKENIZE"]["attempts"] == 2
        assert steps_after["SAFETY_CHECK"]["status"] == "succeeded"
    finally:
        c.__exit__(None, None, None)
