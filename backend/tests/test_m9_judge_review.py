import time
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditLog, Document, DocumentStatus, TaskType, User, UserRole, UserStatus
from app.security import GoogleIdentity, SESSION_HINT_COOKIE_NAME, hash_password
from app.services.detection.resolve import run_detection
from app.services.safety import run_safety_scan
from app.services.tokenizer import tokenize_text
from app.services.vault import vault
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


def test_bangla_detection_sweep_safety_and_manual_mark(app: FastAPI) -> None:
    synthetic_bangla = (
        "ভর্তির তারিখ: ১০/০৩/২০২৬\n"
        "রোগীর নামঃ তানভীর রহমান\n"
        "পিতার নাম: আব্দুল করিম\n"
        "জন্ম তারিখ: ১৫/০৮/১৯৬৮\n"
        "মোবাইল: ০১৭১২-৩৪৫৬৭৮\n"
        "এনআইডি: ১৯৮৫২৬৯১২৩৪৫৬৭৮৯০\n"
        "রেজি নং: ২০২৬-৮৮৪২\n"
        "ঠিকানা: বাড়ি ১২, রোড ৪, ধানমন্ডি, ঢাকা\n"
        "ডাক্তার: ডাঃ ফারিহা ইসলাম\n"
        "অভিভাবক: জনাব সেলিম উদ্দিন\n"
        "রোগী তানভীর রহমান গতরাতে জ্বর নিয়ে আসেন। তানভীর এর সাথে সাবিনা এসেছেন এবং "
        "মোঃ রফিকুল ইসলাম পরীক্ষা সম্পন্ন করেছেন। রোগীর বয়স ৯২ বছর নয়, স্থিতিশীল আছেন।\n"
    )

    spans = run_detection(synthetic_bangla, date_order="DMY", use_presidio=False)
    tok = tokenize_text(synthetic_bangla, spans)
    sanitized = tok.sanitized_text

    # 1. All synthetic Bangla identifiers removed & DOB/Admission/Age90 converted
    assert "[PATIENT_A]" in sanitized
    assert "Age 57" in sanitized
    assert "[DAY_0]" in sanitized
    assert "90+ years" in sanitized
    for secret in (
        "তানভীর রহমান",
        "তানভীর",
        "আব্দুল করিম",
        "০১৭১২-৩৪৫৬৭৮",
        "১৯৮৫২৬৯১২৩৪৫৬৭৮৯০",
        "২০২৬-৮৮৪২",
        "ধানমন্ডি",
        "ফারিহা ইসলাম",
        "সেলিম উদ্দিন",
        "রফিকুল ইসলাম",
        "১৫/০৮/১৯৬৮",
        "১০/০৩/২০২৬",
    ):
        assert secret not in sanitized, f"Expected {secret!r} to be redacted in: {sanitized}"

    # Original Bangla text preserved verbatim in mapping values (not ASCII-mutated)
    assert any("০১৭১২-৩৪৫৬৭৮" in v for v in tok.mapping.values())
    assert any("তানভীর রহমান" in v for v in tok.mapping.values())

    # 2. Clean Bangla text passes safety scan
    clean_report = run_safety_scan(
        sanitized_text=sanitized,
        mapping=tok.mapping,
        name_components=tok.name_components,
        entity_count=sum(tok.entity_summary.values()),
        date_order="DMY",
        use_presidio=False,
    )
    assert clean_report["status"] == "PASS", clean_report

    # 3. Seeded Bangla leak (both Bangla name component and Bangla-digit phone) causes BLOCK
    leaked_name_report = run_safety_scan(
        sanitized_text=sanitized + "\nফলোআপ নোট: তানভীর আজ স্থিতিশীল।",
        mapping=tok.mapping,
        name_components=tok.name_components,
        entity_count=sum(tok.entity_summary.values()),
        date_order="DMY",
        use_presidio=False,
    )
    assert leaked_name_report["status"] == "BLOCK"
    assert any(f["type"] in {"LEAK_LITERAL", "LEAK_NAME_COMPONENT"} for f in leaked_name_report["findings"])

    leaked_phone_report = run_safety_scan(
        sanitized_text=sanitized + "\nযোগাযোগ ০১৭৯৯-৮৮৭৭৬৬",
        mapping=tok.mapping,
        name_components=tok.name_components,
        entity_count=sum(tok.entity_summary.values()),
        date_order="DMY",
        use_presidio=False,
    )
    assert leaked_phone_report["status"] == "BLOCK"
    assert any(f["type"] == "PHONE" for f in leaked_phone_report["findings"])

    # 4. Line-start bare 'নাম:' works
    bare_spans = run_detection("নাম: নাসরিন আক্তার\nরিপোর্ট স্বাভাবিক আছে।", use_presidio=False)
    bare_tok = tokenize_text("নাম: নাসরিন আক্তার\nরিপোর্ট স্বাভাবিক আছে।", bare_spans)
    assert "নাসরিন আক্তার" not in bare_tok.sanitized_text
    assert "[PATIENT_A]" in bare_tok.sanitized_text

    # 5. End-to-end manual mark of an unlabelled Bangla word ("সাবিনা") via API
    doc_client, _owner = _create_and_login(app, role=UserRole.doctor)
    try:
        up = doc_client.post(
            "/api/documents",
            files={"file": ("bangla_manual_mark.pdf", build_text_lab_report_bytes(), "application/pdf")},
            data={"task_type": "case_summary"},
            headers=CSRF_HEADERS,
        )
        assert up.status_code == 202
        doc_id = up.json()["id"]
        detail = _wait_for_review(doc_client, doc_id)
        doc_uuid = uuid.UUID(doc_id)

        # Find the active session family in the vault and replace with synthetic Bangla record
        sessions_body = doc_client.get("/api/me/sessions").json()
        me_sessions = sessions_body["items"] if isinstance(sessions_body, dict) else sessions_body
        family_id = uuid.UUID(me_sessions[0]["family_id"])
        updated = vault.update(
            family_id,
            doc_uuid,
            {
                "original_text": synthetic_bangla,
                "sanitized_text": sanitized,
                "mapping": tok.mapping,
                "name_components": tok.name_components,
                "detected_spans": [],
                "manual_spans": [],
            },
        )
        assert updated is True

        mark_res = doc_client.post(
            f"/api/documents/{doc_id}/manual-marks",
            json={"text": "সাবিনা", "entity_type": "PERSON"},
            headers={**CSRF_HEADERS, "If-Match": str(detail["version"])},
        )
        assert mark_res.status_code == 200, mark_res.text
        assert mark_res.json()["occurrences"] == 1
        san_after = doc_client.get(f"/api/documents/{doc_id}/sanitized").json()["sanitized_text"]
        assert "সাবিনা" not in san_after
        assert "তানভীর" not in san_after
        assert "Age 57" in san_after
    finally:
        doc_client.__exit__(None, None, None)


def test_session_hint_cookie_lifecycle_and_multifield_validation(app: FastAPI, monkeypatch) -> None:
    client = TestClient(app, raise_server_exceptions=False)
    client.__enter__()
    try:
        # 1. Multi-field VALIDATION_ERROR lists ALL invalid field names and zero raw values
        bad_signup = client.post(
            "/api/auth/signup",
            json={"email": "not-an-email-secret", "password": "short", "full_name": "x"},
            headers=CSRF_HEADERS,
        )
        assert bad_signup.status_code == 422
        err = bad_signup.json()["error"]
        assert err["code"] == "VALIDATION_ERROR"
        assert err["message"] == "Invalid request input (email, password, full_name)."
        assert "not-an-email-secret" not in err["message"]
        assert "short" not in err["message"]

        # 2. Signup sets non-HttpOnly joggo_session=1 hint cookie (Path=/)
        email = f"hint-{uuid.uuid4().hex[:8]}@example.com"
        su = client.post(
            "/api/auth/signup",
            json={"email": email, "password": "ValidPassword123", "full_name": "Dr Hint Test"},
            headers=CSRF_HEADERS,
        )
        assert su.status_code == 201
        set_cookies = su.headers.get_list("set-cookie")
        hint_headers = [h for h in set_cookies if h.startswith(f"{SESSION_HINT_COOKIE_NAME}=")]
        assert hint_headers, f"Missing {SESSION_HINT_COOKIE_NAME} cookie in {set_cookies}"
        assert "joggo_session=1" in hint_headers[0]
        assert "httponly" not in hint_headers[0].lower()
        assert "path=/" in hint_headers[0].lower()

        # 3. Refresh rotates and keeps joggo_session=1; reuse clears joggo_session
        old_refresh = client.cookies.get("refresh_token")
        assert old_refresh
        ref = client.post("/api/auth/refresh", headers=CSRF_HEADERS)
        assert ref.status_code == 200
        assert any("joggo_session=1" in h for h in ref.headers.get_list("set-cookie"))

        # Replay revoked refresh token -> 401 SESSION_REVOKED and clears joggo_session
        client.cookies.set("refresh_token", old_refresh, path="/api/auth")
        reused = client.post("/api/auth/refresh", headers=CSRF_HEADERS)
        assert reused.status_code == 401
        assert reused.json()["error"]["code"] == "SESSION_REVOKED"
        cleared_reuse = [h for h in reused.headers.get_list("set-cookie") if h.startswith(f"{SESSION_HINT_COOKIE_NAME}=")]
        assert cleared_reuse and "max-age=0" in cleared_reuse[0].lower()

        # 4. Login sets joggo_session=1; Logout clears it
        lg = client.post(
            "/api/auth/login",
            json={"email": email, "password": "ValidPassword123"},
            headers=CSRF_HEADERS,
        )
        assert lg.status_code == 200
        assert any("joggo_session=1" in h for h in lg.headers.get_list("set-cookie"))

        lo = client.post("/api/auth/logout", headers=CSRF_HEADERS)
        assert lo.status_code == 200
        cleared_logout = [h for h in lo.headers.get_list("set-cookie") if h.startswith(f"{SESSION_HINT_COOKIE_NAME}=")]
        assert cleared_logout and "max-age=0" in cleared_logout[0].lower()

        # 5. Refresh without cookie clears joggo_session
        bad_ref = client.post("/api/auth/refresh", headers=CSRF_HEADERS)
        assert bad_ref.status_code == 401
        cleared_fail = [h for h in bad_ref.headers.get_list("set-cookie") if h.startswith(f"{SESSION_HINT_COOKIE_NAME}=")]
        assert cleared_fail and "max-age=0" in cleared_fail[0].lower()

        # 6. Google login sets joggo_session=1
        monkeypatch.setattr(
            "app.routers.auth.verify_google_credential",
            lambda _cred: GoogleIdentity(
                sub=f"gsub-{uuid.uuid4().hex[:8]}",
                email=f"google-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Dr Google Hint",
            ),
        )
        gl = client.post(
            "/api/auth/google",
            json={"credential": "synthetic-google-id-token-123456"},
            headers=CSRF_HEADERS,
        )
        assert gl.status_code == 200
        assert any("joggo_session=1" in h for h in gl.headers.get_list("set-cookie"))
    finally:
        client.__exit__(None, None, None)


def test_memory_singleton_worker_cap_and_rss_logging() -> None:
    from app.config import Settings
    from app.services.detection import presidio_engine
    from app.services.extraction import MAX_OCR_DPI
    from app.services.memory import get_process_rss_mb, log_process_rss

    # Worker thread caps: default 2 in prod, 4 in dev, env override honored
    assert Settings(ENV="prod", PIPELINE_MAX_WORKERS=None).effective_pipeline_max_workers == 2
    assert Settings(ENV="dev", PIPELINE_MAX_WORKERS=None).effective_pipeline_max_workers == 4
    assert Settings(ENV="prod", PIPELINE_MAX_WORKERS=3).effective_pipeline_max_workers == 3
    assert Settings(ENV="prod", PIPELINE_MAX_WORKERS="").effective_pipeline_max_workers == 2  # type: ignore[arg-type]

    # OCR DPI capped at 200
    assert MAX_OCR_DPI <= 200

    # Presidio / spaCy loaded once (singleton)
    a1 = presidio_engine._get_analyzer()
    a2 = presidio_engine._get_analyzer()
    assert a1 is a2
    assert presidio_engine._load_count == 1

    # RSS helper returns positive MB
    rss = get_process_rss_mb()
    assert rss > 0
    logged_rss = log_process_rss("test_probe")
    assert logged_rss > 0
