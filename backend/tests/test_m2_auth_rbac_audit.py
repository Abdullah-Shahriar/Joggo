from typing import Any
import uuid

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, text

from app.config import get_settings
from app.db import SessionLocal
from app.deps import register_session_wipe_hook, require_active
from app.models import AuditLog, SessionRecord, User, UserRole, UserStatus
from app.security import REFRESH_COOKIE_NAME, hash_password
from tests.conftest import CSRF_HEADERS


def _new_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


def _create_user_in_db(
    *,
    role: UserRole = UserRole.doctor,
    status: UserStatus = UserStatus.active,
    password: str | None = "StrongPass123",
    google_sub: str | None = None,
) -> tuple[User, str]:
    email = _new_email(role.value)
    with SessionLocal() as db:
        user = User(
            email=email,
            password_hash=hash_password(password) if password else None,
            google_sub=google_sub,
            full_name=f"Synthetic {role.value.title()}",
            role=role,
            status=status,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user, email


def test_signup_login_duplicate_weak_password_and_role_escalation_ignored(client: TestClient) -> None:
    email = _new_email("signup")

    # Weak password rejected
    weak = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "short", "full_name": "Dr Test"},
        headers=CSRF_HEADERS,
    )
    assert weak.status_code == 422
    assert weak.json()["error"]["code"] == "WEAK_PASSWORD"

    # Signup with extra role="admin" is ignored; created as doctor
    created = client.post(
        "/api/auth/signup",
        json={
            "email": email.upper(),
            "password": "ValidPassword123",
            "full_name": "Dr Synthetic",
            "role": "admin",
        },
        headers=CSRF_HEADERS,
    )
    assert created.status_code == 201
    user_data = created.json()["user"]
    assert user_data["email"] == email
    assert user_data["role"] == "doctor"
    assert user_data["status"] == "active"

    # Duplicate email returns 409 EMAIL_TAKEN
    dup = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "ValidPassword123", "full_name": "Dr Dup"},
        headers=CSRF_HEADERS,
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "EMAIL_TAKEN"

    # Login succeeds
    logged = client.post(
        "/api/auth/login",
        json={"email": email, "password": "ValidPassword123"},
        headers=CSRF_HEADERS,
    )
    assert logged.status_code == 200
    assert logged.json()["user"]["email"] == email

    # Wrong password gives generic message
    bad = client.post(
        "/api/auth/login",
        json={"email": email, "password": "WrongPassword123"},
        headers=CSRF_HEADERS,
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert bad.json()["error"]["message"] == "Invalid email or password."


def test_lockout_after_five_failed_logins(client: TestClient) -> None:
    _user, email = _create_user_in_db(password="CorrectPass123")

    for attempt in range(4):
        res = client.post(
            "/api/auth/login",
            json={"email": email, "password": f"WrongPass{attempt}99"},
            headers=CSRF_HEADERS,
        )
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "INVALID_CREDENTIALS"

    fifth = client.post(
        "/api/auth/login",
        json={"email": email, "password": "WrongPass999"},
        headers=CSRF_HEADERS,
    )
    assert fifth.status_code == 423
    assert fifth.json()["error"]["code"] == "ACCOUNT_LOCKED"

    # Even the correct password is rejected while locked
    locked_correct = client.post(
        "/api/auth/login",
        json={"email": email, "password": "CorrectPass123"},
        headers=CSRF_HEADERS,
    )
    assert locked_correct.status_code == 423
    assert locked_correct.json()["error"]["code"] == "ACCOUNT_LOCKED"


def test_csrf_required_on_state_changing_requests(client: TestClient) -> None:
    res_no_headers = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "Password123"},
    )
    assert res_no_headers.status_code == 403
    assert res_no_headers.json()["error"]["code"] == "CSRF_REJECTED"

    res_bad_origin = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "Password123"},
        headers={"X-Requested-With": "fetch", "Origin": "https://evil.example"},
    )
    assert res_bad_origin.status_code == 403
    assert res_bad_origin.json()["error"]["code"] == "CSRF_REJECTED"


def test_refresh_rotation_and_reuse_detection_revokes_family_and_wipes_vault(app: FastAPI) -> None:
    from app.services.vault import vault

    wiped_families: list[uuid.UUID] = []

    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            register_session_wipe_hook(lambda sid: wiped_families.append(sid))
            email = _new_email("refresh")
            signup_res = c.post(
                "/api/auth/signup",
                json={"email": email, "password": "ValidPassword123", "full_name": "Dr Refresh"},
                headers=CSRF_HEADERS,
            )
            assert signup_res.status_code == 201
            old_refresh = c.cookies.get(REFRESH_COOKIE_NAME)
            assert old_refresh is not None

            # First refresh rotates token
            ref1 = c.post("/api/auth/refresh", headers=CSRF_HEADERS)
            assert ref1.status_code == 200
            new_refresh = c.cookies.get(REFRESH_COOKIE_NAME)
            assert new_refresh is not None
            assert new_refresh != old_refresh

            # Reuse old refresh token → revokes entire family + wipes vault + audit log
            c.cookies.set(REFRESH_COOKIE_NAME, old_refresh, path="/api/auth")
            reuse_res = c.post("/api/auth/refresh", headers=CSRF_HEADERS)
            assert reuse_res.status_code == 401
            assert reuse_res.json()["error"]["code"] == "SESSION_REVOKED"
            assert len(wiped_families) == 1

            # Subsequent use of the newer rotated token also fails because entire family was revoked
            c.cookies.set(REFRESH_COOKIE_NAME, new_refresh, path="/api/auth")
            after_reuse = c.post("/api/auth/refresh", headers=CSRF_HEADERS)
            assert after_reuse.status_code == 401
            assert after_reuse.json()["error"]["code"] == "SESSION_REVOKED"

            with SessionLocal() as db:
                audit_row = db.execute(
                    select(AuditLog)
                    .where(AuditLog.action == "AUTH_REFRESH_REUSE_DETECTED")
                    .order_by(AuditLog.id.desc())
                    .limit(1)
                ).scalar_one_or_none()
                assert audit_row is not None
                assert audit_row.resource_id == str(wiped_families[0])
    finally:
        register_session_wipe_hook(vault.wipe_session)


def test_logout_wipes_vault_and_revokes_session(app: FastAPI) -> None:
    from app.services.vault import vault

    wiped_families: list[uuid.UUID] = []

    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            register_session_wipe_hook(lambda sid: wiped_families.append(sid))
            email = _new_email("logout")
            res = c.post(
                "/api/auth/signup",
                json={"email": email, "password": "ValidPassword123", "full_name": "Dr Logout"},
                headers=CSRF_HEADERS,
            )
            assert res.status_code == 201
            saved_access = c.cookies.get("access_token")
            assert saved_access is not None

            out = c.post("/api/auth/logout", headers=CSRF_HEADERS)
            assert out.status_code == 200
            assert len(wiped_families) == 1

            # Replaying the old access token fails because session family is revoked in DB
            c.cookies.set("access_token", saved_access, path="/")
            me_res = c.get("/api/me")
            assert me_res.status_code == 401
            assert me_res.json()["error"]["code"] == "SESSION_REVOKED"
    finally:
        register_session_wipe_hook(vault.wipe_session)


def test_google_login_valid_invalid_unverified(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-google-client-id")

    google_email = _new_email("google")
    google_sub = f"sub-{uuid.uuid4().hex}"

    def fake_verify(token: str, _req: Any, _aud: str) -> dict[str, Any]:
        if token == "valid-token-12345":
            return {
                "sub": google_sub,
                "email": google_email,
                "email_verified": True,
                "name": "Dr Google User",
            }
        if token == "unverified-token-12345":
            return {
                "sub": "sub-unverified",
                "email": _new_email("unverified"),
                "email_verified": False,
                "name": "Unverified",
            }
        raise ValueError("Invalid token")

    monkeypatch.setattr("app.security.google_id_token.verify_oauth2_token", fake_verify)

    bad = client.post(
        "/api/auth/google",
        json={"credential": "invalid-token-12345"},
        headers=CSRF_HEADERS,
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "GOOGLE_TOKEN_INVALID"

    unverified = client.post(
        "/api/auth/google",
        json={"credential": "unverified-token-12345"},
        headers=CSRF_HEADERS,
    )
    assert unverified.status_code == 401
    assert unverified.json()["error"]["code"] == "GOOGLE_TOKEN_INVALID"

    ok = client.post(
        "/api/auth/google",
        json={"credential": "valid-token-12345"},
        headers=CSRF_HEADERS,
    )
    assert ok.status_code == 200
    assert ok.json()["user"]["email"] == google_email
    assert ok.json()["user"]["has_password"] is False
    assert ok.json()["user"]["has_google"] is True

    # Google-only account cannot change password → 400 NO_PASSWORD_SET
    pwd_res = client.post(
        "/api/me/password",
        json={"current": "Anything1234", "new": "NewPassword123"},
        headers=CSRF_HEADERS,
    )
    assert pwd_res.status_code == 400
    assert pwd_res.json()["error"]["code"] == "NO_PASSWORD_SET"


def test_me_profile_sessions_and_password_change(client: TestClient) -> None:
    email = _new_email("me")
    res = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "InitialPass123", "full_name": "Dr Initial"},
        headers=CSRF_HEADERS,
    )
    assert res.status_code == 201

    me_res = client.get("/api/me")
    assert me_res.status_code == 200
    assert me_res.json()["full_name"] == "Dr Initial"

    patch_res = client.patch(
        "/api/me",
        json={
            "full_name": "Dr Updated",
            "age": 38,
            "designation": "Senior Registrar",
            "hospital_name": "City Care Medical College",
            "avatar_data_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
        },
        headers=CSRF_HEADERS,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["full_name"] == "Dr Updated"
    assert patch_res.json()["age"] == 38
    assert patch_res.json()["designation"] == "Senior Registrar"
    assert patch_res.json()["hospital_name"] == "City Care Medical College"
    assert patch_res.json()["avatar_data_url"].startswith("data:image/png;base64,")

    bad_avatar = client.patch(
        "/api/me",
        json={"avatar_data_url": "javascript:alert(1)"},
        headers=CSRF_HEADERS,
    )
    assert bad_avatar.status_code == 422

    sess_res = client.get("/api/me/sessions")
    assert sess_res.status_code == 200
    assert len(sess_res.json()["items"]) == 1
    assert sess_res.json()["items"][0]["is_current"] is True

    old_access = client.cookies.get("access_token")
    assert old_access is not None

    pwd_res = client.post(
        "/api/me/password",
        json={"current": "InitialPass123", "new": "UpdatedPass456"},
        headers=CSRF_HEADERS,
    )
    assert pwd_res.status_code == 200

    # Old access token rejected (token_version bumped + sessions revoked)
    client.cookies.set("access_token", old_access, path="/")
    assert client.get("/api/me").status_code == 401

    # Can log in with new password
    login_res = client.post(
        "/api/auth/login",
        json={"email": email, "password": "UpdatedPass456"},
        headers=CSRF_HEADERS,
    )
    assert login_res.status_code == 200


def test_restricted_user_allowed_me_but_blocked_by_require_active(app: FastAPI) -> None:
    @app.get("/api/_test/active-only")
    def active_only(_user: User = Depends(require_active)) -> dict[str, str]:
        return {"ok": "yes"}

    _user, email = _create_user_in_db(role=UserRole.doctor, status=UserStatus.restricted)

    with TestClient(app, raise_server_exceptions=False) as c:
        login_res = c.post(
            "/api/auth/login",
            json={"email": email, "password": "StrongPass123"},
            headers=CSRF_HEADERS,
        )
        assert login_res.status_code == 200
        assert login_res.json()["user"]["status"] == "restricted"

        # Profile allowed
        assert c.get("/api/me").status_code == 200

        # Active-only endpoint blocked with 403 ACCOUNT_RESTRICTED
        blocked = c.get("/api/_test/active-only")
        assert blocked.status_code == 403
        assert blocked.json()["error"]["code"] == "ACCOUNT_RESTRICTED"


def test_audit_rbac_and_hash_chain_tamper_detection(app: FastAPI) -> None:
    _doc, doc_email = _create_user_in_db(role=UserRole.doctor)
    _aud, aud_email = _create_user_in_db(role=UserRole.auditor)
    _adm, adm_email = _create_user_in_db(role=UserRole.admin)

    # Doctor denied access to /api/audit and /api/audit/verify
    with TestClient(app, raise_server_exceptions=False) as c_doc:
        assert (
            c_doc.post(
                "/api/auth/login",
                json={"email": doc_email, "password": "StrongPass123"},
                headers=CSRF_HEADERS,
            ).status_code
            == 200
        )
        assert c_doc.get("/api/audit").status_code == 403
        assert c_doc.get("/api/audit/verify").status_code == 403

    # Auditor allowed read-only access
    with TestClient(app, raise_server_exceptions=False) as c_aud:
        assert (
            c_aud.post(
                "/api/auth/login",
                json={"email": aud_email, "password": "StrongPass123"},
                headers=CSRF_HEADERS,
            ).status_code
            == 200
        )
        aud_list = c_aud.get("/api/audit?page=1&page_size=5")
        assert aud_list.status_code == 200
        assert aud_list.json()["total"] >= 1

    # Admin can list and verify hash chain; tamper detection works
    with TestClient(app, raise_server_exceptions=False) as c_adm:
        assert (
            c_adm.post(
                "/api/auth/login",
                json={"email": adm_email, "password": "StrongPass123"},
                headers=CSRF_HEADERS,
            ).status_code
            == 200
        )

        verify_ok = c_adm.get("/api/audit/verify")
        assert verify_ok.status_code == 200
        assert verify_ok.json()["ok"] is True
        assert verify_ok.json()["checked"] >= 1
        assert verify_ok.json()["first_broken_id"] is None

        with SessionLocal() as db:
            last_row = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).scalar_one()
            original_hash = last_row.hash
            target_id = last_row.id

        try:
            with SessionLocal() as db:
                db.execute(text("ALTER TABLE audit_logs DISABLE TRIGGER trg_audit_logs_immutable"))
                db.execute(
                    text("UPDATE audit_logs SET hash = :tampered WHERE id = :id"),
                    {"tampered": "f" * 64, "id": target_id},
                )
                db.execute(text("ALTER TABLE audit_logs ENABLE TRIGGER trg_audit_logs_immutable"))
                db.commit()

            verify_bad = c_adm.get("/api/audit/verify")
            assert verify_bad.status_code == 200
            body = verify_bad.json()
            assert body["ok"] is False
            assert body["first_broken_id"] == target_id
        finally:
            with SessionLocal() as db:
                db.execute(text("ALTER TABLE audit_logs DISABLE TRIGGER trg_audit_logs_immutable"))
                db.execute(
                    text("UPDATE audit_logs SET hash = :orig WHERE id = :id"),
                    {"orig": original_hash, "id": target_id},
                )
                db.execute(text("ALTER TABLE audit_logs ENABLE TRIGGER trg_audit_logs_immutable"))
                db.commit()

        verify_restored = c_adm.get("/api/audit/verify")
        assert verify_restored.status_code == 200
        assert verify_restored.json()["ok"] is True


def test_auth_rate_limit_returns_429_with_retry_after(client: TestClient) -> None:
    got_429 = False
    for i in range(12):
        res = client.post(
            "/api/auth/login",
            json={"email": f"ratelimit-{i}@example.com", "password": "WrongPassword123"},
            headers=CSRF_HEADERS,
        )
        if res.status_code == 429:
            got_429 = True
            assert res.json()["error"]["code"] == "RATE_LIMITED"
            assert "retry-after" in {k.lower() for k in res.headers.keys()}
            break
    assert got_429 is True
