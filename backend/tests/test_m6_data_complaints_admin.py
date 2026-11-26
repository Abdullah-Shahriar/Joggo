from datetime import datetime, timedelta, timezone
import json
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    AuditLog,
    Document,
    DocumentStatus,
    TaskType,
    User,
    UserRole,
    UserStatus,
)
from app.security import hash_password
from app.services.vault import vault
from tests.conftest import CSRF_HEADERS


def _create_and_login(
    app: FastAPI,
    *,
    role: UserRole = UserRole.doctor,
    status: UserStatus = UserStatus.active,
) -> tuple[TestClient, User]:
    email = f"m6-{role.value}-{uuid.uuid4().hex[:8]}@example.com"
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

    c = TestClient(app, raise_server_exceptions=False)
    c.__enter__()
    assert (
        c.post(
            "/api/auth/login",
            json={"email": email, "password": "StrongPass123"},
            headers=CSRF_HEADERS,
        ).status_code
        == 200
    )
    return c, user


def test_documents_query_filters_sorting_pagination_and_dashboard(app: FastAPI) -> None:
    c_doc, doc_user = _create_and_login(app, role=UserRole.doctor)
    try:
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            d1 = Document(
                owner_id=doc_user.id,
                original_filename="alpha_cardiology.pdf",
                file_sha256=uuid.uuid4().hex * 2,
                size_bytes=1000,
                page_count=1,
                task_type=TaskType.discharge_summary,
                status=DocumentStatus.REVIEW_REQUIRED,
                entity_summary={"PATIENT": 2, "DATE": 3},
                created_at=now - timedelta(days=2),
            )
            d2 = Document(
                owner_id=doc_user.id,
                original_filename="beta_oncology.pdf",
                file_sha256=uuid.uuid4().hex * 2,
                size_bytes=1200,
                page_count=2,
                task_type=TaskType.case_summary,
                status=DocumentStatus.BLOCKED,
                entity_summary={"PATIENT": 1},
                created_at=now - timedelta(days=1),
            )
            d3 = Document(
                owner_id=doc_user.id,
                original_filename="gamma_neurology.pdf",
                file_sha256=uuid.uuid4().hex * 2,
                size_bytes=1500,
                page_count=3,
                task_type=TaskType.treatment_plan,
                status=DocumentStatus.COMPLETED,
                entity_summary={"PATIENT": 4, "DOCTOR": 4, "PHONE": 2},
                created_at=now - timedelta(hours=2),
            )
            db.add_all([d1, d2, d3])
            db.commit()
            d1_id = str(d1.id)

        # Filter by q (filename)
        r_q = c_doc.get("/api/documents?q=beta")
        assert r_q.status_code == 200
        assert r_q.json()["total"] == 1
        assert r_q.json()["items"][0]["original_filename"] == "beta_oncology.pdf"

        # Filter by q (UUID prefix)
        r_id = c_doc.get(f"/api/documents?q={d1_id[:8]}")
        assert r_id.status_code == 200
        assert r_id.json()["total"] == 1
        assert r_id.json()["items"][0]["id"] == d1_id

        # Filter by status & task_type
        r_st = c_doc.get("/api/documents?status=BLOCKED&task_type=case_summary")
        assert r_st.status_code == 200
        assert r_st.json()["total"] == 1

        # Sort by entity_count desc
        r_ent = c_doc.get("/api/documents?sort=entity_count&order=desc")
        assert r_ent.status_code == 200
        counts = [item["entity_count"] for item in r_ent.json()["items"]]
        assert counts == [10, 5, 1]

        # Sort by original_filename asc
        r_fn = c_doc.get("/api/documents?sort=original_filename&order=asc")
        assert [i["original_filename"] for i in r_fn.json()["items"]] == [
            "alpha_cardiology.pdf",
            "beta_oncology.pdf",
            "gamma_neurology.pdf",
        ]

        # Pagination beyond range returns empty items
        r_beyond = c_doc.get("/api/documents?page=99&page_size=10")
        assert r_beyond.status_code == 200
        assert r_beyond.json()["items"] == []
        assert r_beyond.json()["total"] == 3

        # page_size > 50 rejected with 422
        r_cap = c_doc.get("/api/documents?page_size=51")
        assert r_cap.status_code == 422

        # Dashboard metrics match fixtures
        dash = c_doc.get("/api/dashboard")
        assert dash.status_code == 200
        dbody = dash.json()
        assert dbody["waiting_for_review"] == 1
        assert dbody["blocked_count"] == 1
        assert dbody["processed_last_7_days"] == 2
        assert len(dbody["recent_documents"]) == 3
    finally:
        c_doc.__exit__(None, None, None)


def test_complaints_workflow_permissions_transitions_and_foreign_doc_rejected(app: FastAPI) -> None:
    c_doc_a, doc_a = _create_and_login(app, role=UserRole.doctor)
    c_doc_b, doc_b = _create_and_login(app, role=UserRole.doctor)
    c_restricted, _rest = _create_and_login(app, role=UserRole.doctor, status=UserStatus.restricted)
    c_admin, _admin = _create_and_login(app, role=UserRole.admin)

    try:
        # Seed a document belonging to doc_b
        with SessionLocal() as db:
            b_doc = Document(
                owner_id=doc_b.id,
                original_filename="secret_doc_b_filename.pdf",
                file_sha256=uuid.uuid4().hex * 2,
                size_bytes=500,
                page_count=1,
                task_type=TaskType.case_summary,
                status=DocumentStatus.REVIEW_REQUIRED,
            )
            db.add(b_doc)
            db.commit()
            b_doc_id = str(b_doc.id)

        # Foreign document_id rejected with 404
        bad_doc = c_doc_a.post(
            "/api/complaints",
            json={
                "subject": "Cannot open report",
                "category": "bug",
                "message": "Trying to attach someone else's document id.",
                "document_id": b_doc_id,
            },
            headers=CSRF_HEADERS,
        )
        assert bad_doc.status_code == 404

        # Restricted user CAN create a complaint
        r_rest = c_restricted.post(
            "/api/complaints",
            json={
                "subject": "Account restriction inquiry",
                "category": "account",
                "message": "Please review why my account was restricted today.",
            },
            headers=CSRF_HEADERS,
        )
        assert r_rest.status_code == 201
        comp_id = r_rest.json()["id"]
        assert r_rest.json()["status"] == "open"

        # Another doctor cannot view/reply to restricted user's complaint
        assert c_doc_a.get(f"/api/complaints/{comp_id}").status_code == 404

        # Admin lists & views complaint
        adm_list = c_admin.get("/api/admin/complaints?status=open&category=account")
        assert adm_list.status_code == 200
        assert any(item["id"] == comp_id for item in adm_list.json()["items"])

        # First admin reply auto-moves open -> in_progress
        adm_reply = c_admin.post(
            f"/api/admin/complaints/{comp_id}/messages",
            json={"body": "We are reviewing your account now."},
            headers=CSRF_HEADERS,
        )
        assert adm_reply.status_code == 201
        assert adm_reply.json()["status"] == "in_progress"
        assert len(adm_reply.json()["messages"]) == 1

        # User can reply while in_progress
        usr_reply = c_restricted.post(
            f"/api/complaints/{comp_id}/messages",
            json={"body": "Thank you for checking."},
            headers=CSRF_HEADERS,
        )
        assert usr_reply.status_code == 201
        assert len(usr_reply.json()["messages"]) == 2

        # Invalid transition: in_progress -> open -> 409 INVALID_COMPLAINT_TRANSITION
        bad_tr = c_admin.patch(
            f"/api/admin/complaints/{comp_id}/status",
            json={"status": "open"},
            headers=CSRF_HEADERS,
        )
        assert bad_tr.status_code == 409
        assert bad_tr.json()["error"]["code"] == "INVALID_COMPLAINT_TRANSITION"

        # Valid transition: in_progress -> resolved
        resolved = c_admin.patch(
            f"/api/admin/complaints/{comp_id}/status",
            json={"status": "resolved"},
            headers=CSRF_HEADERS,
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "resolved"
        assert resolved.json()["resolved_at"] is not None

        # User reply while resolved -> 409 COMPLAINT_CLOSED
        closed_reply = c_restricted.post(
            f"/api/complaints/{comp_id}/messages",
            json={"body": "One more thing"},
            headers=CSRF_HEADERS,
        )
        assert closed_reply.status_code == 409
        assert closed_reply.json()["error"]["code"] == "COMPLAINT_CLOSED"

        # Admin can reopen: resolved -> in_progress
        reopened = c_admin.patch(
            f"/api/admin/complaints/{comp_id}/status",
            json={"status": "in_progress"},
            headers=CSRF_HEADERS,
        )
        assert reopened.status_code == 200
        assert reopened.json()["status"] == "in_progress"
        assert reopened.json()["resolved_at"] is None
    finally:
        for c in (c_doc_a, c_doc_b, c_restricted, c_admin):
            c.__exit__(None, None, None)


def test_admin_user_management_guards_restrict_effects_and_zero_phi_exposure(app: FastAPI) -> None:
    c_admin1, admin1 = _create_and_login(app, role=UserRole.admin)
    c_admin2, admin2 = _create_and_login(app, role=UserRole.admin)
    c_doc, doc_user = _create_and_login(app, role=UserRole.doctor)
    c_aud, _aud = _create_and_login(app, role=UserRole.auditor)

    try:
        # Non-admins denied on /api/admin/*
        assert c_doc.get("/api/admin/users").status_code == 403
        assert c_aud.get("/api/admin/users").status_code == 403
        assert c_aud.get("/api/admin/analytics").status_code == 403

        # Self modification -> 400 CANNOT_MODIFY_SELF
        self_mod = c_admin1.patch(
            f"/api/admin/users/{admin1.id}",
            json={"status": "restricted"},
            headers=CSRF_HEADERS,
        )
        assert self_mod.status_code == 400
        assert self_mod.json()["error"]["code"] == "CANNOT_MODIFY_SELF"

        # Modifying another admin -> 403 CANNOT_MODIFY_ADMIN
        other_admin = c_admin1.patch(
            f"/api/admin/users/{admin2.id}",
            json={"status": "restricted"},
            headers=CSRF_HEADERS,
        )
        assert other_admin.status_code == 403
        assert other_admin.json()["error"]["code"] == "CANNOT_MODIFY_ADMIN"

        # Promoting doctor to admin -> 400 INVALID_ROLE_CHANGE
        bad_role = c_admin1.patch(
            f"/api/admin/users/{doc_user.id}",
            json={"role": "admin"},
            headers=CSRF_HEADERS,
        )
        assert bad_role.status_code == 400
        assert bad_role.json()["error"]["code"] == "INVALID_ROLE_CHANGE"

        # Create a non-terminal document + vault entry for doc_user with distinctive filename & sanitized text
        secret_filename = "ULTRA_PRIVATE_PATIENT_FILENAME_999.pdf"
        secret_text = "ULTRA_PRIVATE_SANITIZED_BODY_MARKER_888"
        with SessionLocal() as db:
            d = Document(
                owner_id=doc_user.id,
                original_filename=secret_filename,
                file_sha256=uuid.uuid4().hex * 2,
                size_bytes=512,
                page_count=1,
                task_type=TaskType.discharge_summary,
                status=DocumentStatus.REVIEW_REQUIRED,
                sanitized_text=secret_text,
            )
            db.add(d)
            db.commit()
            doc_id = d.id

        sid = uuid.uuid4()
        vault.put(sid, doc_id, {"original_text": "Private text"}, user_id=doc_user.id)

        # Restrict doctor -> wipes vault, fails non-terminal document with ACCOUNT_RESTRICTED
        restrict_res = c_admin1.patch(
            f"/api/admin/users/{doc_user.id}",
            json={"status": "restricted", "restricted_reason": "Policy review"},
            headers=CSRF_HEADERS,
        )
        assert restrict_res.status_code == 200
        assert restrict_res.json()["status"] == "restricted"
        assert restrict_res.json()["restricted_reason"] == "Policy review"
        assert vault.get(sid, doc_id) is None

        with SessionLocal() as db:
            d_after = db.get(Document, doc_id)
            assert d_after is not None
            assert d_after.status == DocumentStatus.FAILED
            assert d_after.failure_code == "ACCOUNT_RESTRICTED"
            assert d_after.vault_expired is True

        # Restore doctor
        restore_res = c_admin1.patch(
            f"/api/admin/users/{doc_user.id}",
            json={"status": "active"},
            headers=CSRF_HEADERS,
        )
        assert restore_res.status_code == 200
        assert restore_res.json()["status"] == "active"
        assert restore_res.json()["restricted_reason"] is None

        # Role change doctor -> auditor bumps token_version and revokes active sessions
        role_res = c_admin1.patch(
            f"/api/admin/users/{doc_user.id}",
            json={"role": "auditor"},
            headers=CSRF_HEADERS,
        )
        assert role_res.status_code == 200
        assert role_res.json()["role"] == "auditor"
        assert c_doc.get("/api/me").status_code == 401

        # P7: Admin endpoints NEVER expose document filenames or text
        users_body = json.dumps(c_admin1.get("/api/admin/users?page_size=50").json())
        overview_body = json.dumps(c_admin1.get("/api/admin/overview").json())
        analytics_res = c_admin1.get("/api/admin/analytics")
        assert analytics_res.status_code == 200
        analytics_data = analytics_res.json()
        assert len(analytics_data["documents_per_day"]) == 14
        analytics_body = json.dumps(analytics_data)

        for blob in (users_body, overview_body, analytics_body):
            assert secret_filename not in blob
            assert secret_text not in blob
    finally:
        for c in (c_admin1, c_admin2, c_doc, c_aud):
            c.__exit__(None, None, None)
