import time
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditLog, Document, DocumentStatus, TaskType, User, UserRole, UserStatus
from app.security import hash_password
from scripts.make_sample_pdfs import build_text_lab_report_bytes
from tests.conftest import CSRF_HEADERS


def _create_and_login(
    app: FastAPI,
    *,
    role: UserRole = UserRole.doctor,
    status: UserStatus = UserStatus.active,
    portal: str | None = None,
) -> tuple[TestClient, User]:
    email = f"m9-{role.value}-{uuid.uuid4().hex[:8]}@example.com"
    with SessionLocal() as db:
        user = User(
            email=email,
            password_hash=hash_password("StrongPass123"),
            full_name=f"Synthetic {role.value.title()}",
            role=role,
            status=status,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    client = TestClient(app, raise_server_exceptions=False)
    client.__enter__()
    body: dict[str, str] = {"email": email, "password": "StrongPass123"}
    if portal is not None:
        body["portal"] = portal
    res = client.post("/api/auth/login", json=body, headers=CSRF_HEADERS)
    assert res.status_code == 200
    return client, user


def _wait_for_review(client: TestClient, doc_id: str, timeout: float = 25.0) -> dict:
    deadline = time.monotonic() + timeout
    detail: dict = {}
    while time.monotonic() < deadline:
        detail = client.get(f"/api/documents/{doc_id}").json()
        if detail["status"] not in {"UPLOADED", "PROCESSING"}:
            return detail
        time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for pipeline; last={detail}")


def test_external_handoff_requires_approval_hash_safety_rbac_and_audits(app: FastAPI) -> None:
    doc_owner_client, owner = _create_and_login(app, role=UserRole.doctor)
    other_doc_client, _other = _create_and_login(app, role=UserRole.doctor)
    admin_client, _admin = _create_and_login(app, role=UserRole.admin)
    auditor_client, _auditor = _create_and_login(app, role=UserRole.auditor)
    restricted_client, restricted_user = _create_and_login(app, role=UserRole.doctor)

    try:
        # Upload synthetic text lab report as owner
        up = doc_owner_client.post(
            "/api/documents",
            files={"file": ("synthetic_lab_handoff.pdf", build_text_lab_report_bytes(), "application/pdf")},
            data={"task_type": "discharge_summary"},
            headers=CSRF_HEADERS,
        )
        assert up.status_code == 202
        doc_id = up.json()["id"]
        detail = _wait_for_review(doc_owner_client, doc_id)
        assert detail["status"] == "REVIEW_REQUIRED"
        valid_sha = detail["sanitized_sha256"]
        assert valid_sha

        # 1. Owner success -> 200, prompt_text returned, status unchanged, DOC_EXTERNAL_HANDOFF audit with provider only
        ok = doc_owner_client.post(
            f"/api/documents/{doc_id}/handoff",
            json={"provider": "claude", "sanitized_sha256": valid_sha},
            headers=CSRF_HEADERS,
        )
        assert ok.status_code == 200
        prompt_text = ok.json()["prompt_text"]
        assert "## Diagnosis" in prompt_text
        assert "## Follow-up" in prompt_text

        # Privacy check: zero real patient values or filename in prompt_text
        for forbidden in (
            "Rahim Ahmed",
            "1968472910482",
            "1712-345678",
            "rahim.ahmed.synth@example.test",
            "MRN-884210",
            "Dhanmondi",
            "synthetic_lab_handoff.pdf",
        ):
            assert forbidden not in prompt_text

        after_detail = doc_owner_client.get(f"/api/documents/{doc_id}").json()
        assert after_detail["status"] == "REVIEW_REQUIRED"

        with SessionLocal() as db:
            audit_row = db.execute(
                select(AuditLog)
                .where(
                    AuditLog.action == "DOC_EXTERNAL_HANDOFF",
                    AuditLog.resource_id == doc_id,
                )
                .order_by(AuditLog.id.desc())
                .limit(1)
            ).scalar_one_or_none()
            assert audit_row is not None
            assert audit_row.actor_id == owner.id
            assert audit_row.metadata_ == {"provider": "claude"}
            assert "Rahim" not in str(audit_row.metadata_)

        # 2. Stale hash -> 409 STALE_REVIEW
        stale = doc_owner_client.post(
            f"/api/documents/{doc_id}/handoff",
            json={"provider": "gemini", "sanitized_sha256": "0" * 64},
            headers=CSRF_HEADERS,
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "STALE_REVIEW"

        # 3. Admin & Auditor -> 403 ADMIN_NO_DOCUMENT_ACCESS + audit
        adm_res = admin_client.post(
            f"/api/documents/{doc_id}/handoff",
            json={"provider": "chatgpt", "sanitized_sha256": valid_sha},
            headers=CSRF_HEADERS,
        )
        assert adm_res.status_code == 403
        assert adm_res.json()["error"]["code"] == "ADMIN_NO_DOCUMENT_ACCESS"

        aud_res = auditor_client.post(
            f"/api/documents/{doc_id}/handoff",
            json={"provider": "chatgpt", "sanitized_sha256": valid_sha},
            headers=CSRF_HEADERS,
        )
        assert aud_res.status_code == 403
        assert aud_res.json()["error"]["code"] == "ADMIN_NO_DOCUMENT_ACCESS"

        # 4. Other doctor -> 404 NOT_FOUND + audit
        other_res = other_doc_client.post(
            f"/api/documents/{doc_id}/handoff",
            json={"provider": "gemini", "sanitized_sha256": valid_sha},
            headers=CSRF_HEADERS,
        )
        assert other_res.status_code == 404
        assert other_res.json()["error"]["code"] == "NOT_FOUND"

        # 5. BLOCKED document -> 409 INVALID_STATE
        with SessionLocal() as db:
            blocked_doc = Document(
                owner_id=owner.id,
                original_filename="blocked_handoff.pdf",
                file_sha256=uuid.uuid4().hex * 2,
                size_bytes=512,
                page_count=1,
                task_type=TaskType.case_summary,
                status=DocumentStatus.BLOCKED,
                safety_report={"status": "BLOCK", "findings": [{"type": "PERSON", "reason": "leak", "start": 0, "end": 5}]},
            )
            db.add(blocked_doc)
            db.commit()
            blocked_id = str(blocked_doc.id)

        blk_res = doc_owner_client.post(
            f"/api/documents/{blocked_id}/handoff",
            json={"provider": "gemini", "sanitized_sha256": valid_sha},
            headers=CSRF_HEADERS,
        )
        assert blk_res.status_code == 409
        assert blk_res.json()["error"]["code"] == "INVALID_STATE"

        # 6. Restricted user owning a READY document -> 403 ACCOUNT_RESTRICTED
        up_r = restricted_client.post(
            "/api/documents",
            files={"file": ("restricted_doc.pdf", build_text_lab_report_bytes(), "application/pdf")},
            data={"task_type": "case_summary"},
            headers=CSRF_HEADERS,
        )
        assert up_r.status_code == 202
        r_doc_id = up_r.json()["id"]
        r_detail = _wait_for_review(restricted_client, r_doc_id)
        r_sha = r_detail["sanitized_sha256"]

        with SessionLocal() as db:
            u = db.get(User, restricted_user.id)
            assert u is not None
            u.status = UserStatus.restricted
            db.commit()

        res_restricted = restricted_client.post(
            f"/api/documents/{r_doc_id}/handoff",
            json={"provider": "claude", "sanitized_sha256": r_sha},
            headers=CSRF_HEADERS,
        )
        assert res_restricted.status_code == 403
        assert res_restricted.json()["error"]["code"] == "ACCOUNT_RESTRICTED"
    finally:
        for c in (doc_owner_client, other_doc_client, admin_client, auditor_client, restricted_client):
            c.__exit__(None, None, None)
