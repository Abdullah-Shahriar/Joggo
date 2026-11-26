from datetime import datetime, timedelta, timezone
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

from app.db import SessionLocal
from app.errors import ErrorCode
from app.models import Document, DocumentStatus, TaskType, User, UserRole, UserStatus
from app.security import hash_password
from app.services.llm.base import LLMProviderError
from app.services.llm.gemini import GeminiProvider
from app.services.llm.groq import GroqProvider
from app.services.vault import vault
from tests.conftest import CSRF_HEADERS


class _DummyHTTPResponse:
    def __init__(self, status_code: int, json_body: dict | None = None, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._json = json_body or {}
        self.headers = headers or {}

    def json(self) -> dict:
        return self._json


def test_gemini_and_groq_providers_http_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict] = []

    def make_fake_post(response_or_exc):
        def _post(self, url, *, json=None, headers=None, **kwargs):
            captured.append({"url": url, "json": json, "headers": headers})
            if isinstance(response_or_exc, Exception):
                raise response_or_exc
            return response_or_exc

        return _post

    # Gemini success
    gem = GeminiProvider(api_key="test-gem-key", model="gemini-test-model")
    monkeypatch.setattr(
        httpx.Client,
        "post",
        make_fake_post(
            _DummyHTTPResponse(
                200,
                {"candidates": [{"content": {"parts": [{"text": "## Summary\nOK"}]}}]},
            )
        ),
    )
    res_g = gem.generate("sys", "usr")
    assert res_g.text == "## Summary\nOK"
    assert res_g.model == "gemini-test-model"
    assert captured[-1]["headers"]["x-goog-api-key"] == "test-gem-key"
    assert "gemini-test-model:generateContent" in captured[-1]["url"]

    # Gemini 401 -> LLM_AUTH_ERROR (not retryable)
    monkeypatch.setattr(httpx.Client, "post", make_fake_post(_DummyHTTPResponse(401)))
    with pytest.raises(LLMProviderError) as e_auth:
        gem.generate("sys", "usr")
    assert e_auth.value.code == ErrorCode.LLM_AUTH_ERROR
    assert e_auth.value.retryable is False

    # Gemini 429 with Retry-After -> capped at 10s
    monkeypatch.setattr(httpx.Client, "post", make_fake_post(_DummyHTTPResponse(429, headers={"retry-after": "30"})))
    with pytest.raises(LLMProviderError) as e_429:
        gem.generate("sys", "usr")
    assert e_429.value.retryable is True
    assert e_429.value.retry_after == 10.0

    # Gemini timeout -> LLM_TIMEOUT
    monkeypatch.setattr(httpx.Client, "post", make_fake_post(httpx.ReadTimeout("timed out")))
    with pytest.raises(LLMProviderError) as e_to:
        gem.generate("sys", "usr")
    assert e_to.value.code == ErrorCode.LLM_TIMEOUT
    assert e_to.value.retryable is True

    # Groq success
    groq = GroqProvider(api_key="test-groq-key", model="groq-test-model")
    monkeypatch.setattr(
        httpx.Client,
        "post",
        make_fake_post(
            _DummyHTTPResponse(
                200,
                {"choices": [{"message": {"content": "## Summary\nGroq OK"}}]},
            )
        ),
    )
    res_q = groq.generate("sys", "usr")
    assert res_q.text == "## Summary\nGroq OK"
    assert captured[-1]["headers"]["Authorization"] == "Bearer test-groq-key"

    # Groq 503 -> retryable LLM_UNAVAILABLE
    monkeypatch.setattr(httpx.Client, "post", make_fake_post(_DummyHTTPResponse(503)))
    with pytest.raises(LLMProviderError) as e_503:
        groq.generate("sys", "usr")
    assert e_503.value.code == ErrorCode.LLM_UNAVAILABLE
    assert e_503.value.retryable is True


def test_session_revoke_audit_filters_and_failed_retry_vault_expired(app: FastAPI) -> None:
    email_doc = f"m7-doc-{uuid.uuid4().hex[:8]}@example.com"
    email_adm = f"m7-adm-{uuid.uuid4().hex[:8]}@example.com"
    with SessionLocal() as db:
        doc_user = User(
            email=email_doc,
            password_hash=hash_password("StrongPass123"),
            full_name="Dr M7",
            role=UserRole.doctor,
            status=UserStatus.active,
        )
        adm_user = User(
            email=email_adm,
            password_hash=hash_password("StrongPass123"),
            full_name="Admin M7",
            role=UserRole.admin,
            status=UserStatus.active,
        )
        db.add_all([doc_user, adm_user])
        db.commit()
        doc_user_id = doc_user.id

    with TestClient(app, raise_server_exceptions=False) as c1, TestClient(
        app, raise_server_exceptions=False
    ) as c2, TestClient(app, raise_server_exceptions=False) as c_adm:
        assert c1.post("/api/auth/login", json={"email": email_doc, "password": "StrongPass123"}, headers=CSRF_HEADERS).status_code == 200
        assert c2.post("/api/auth/login", json={"email": email_doc, "password": "StrongPass123"}, headers=CSRF_HEADERS).status_code == 200
        assert c_adm.post("/api/auth/login", json={"email": email_adm, "password": "StrongPass123"}, headers=CSRF_HEADERS).status_code == 200

        # List 2 active sessions and revoke the non-current session
        sessions = c1.get("/api/me/sessions").json()["items"]
        assert len(sessions) == 2
        other = next(s for s in sessions if not s["is_current"])
        rev = c1.delete(f"/api/me/sessions/{other['id']}", headers=CSRF_HEADERS)
        assert rev.status_code == 200

        # Revoked session c2 is immediately rejected
        assert c2.get("/api/me").status_code == 401
        assert c1.get("/api/me").status_code == 200

        # Retry FAILED document when Vault is expired -> 409 VAULT_EXPIRED
        with SessionLocal() as db:
            failed_doc = Document(
                owner_id=doc_user_id,
                original_filename="expired_failed.pdf",
                file_sha256=uuid.uuid4().hex * 2,
                size_bytes=200,
                page_count=1,
                task_type=TaskType.case_summary,
                status=DocumentStatus.FAILED,
                failure_code="SERVER_RESTART",
                vault_expired=True,
            )
            db.add(failed_doc)
            db.commit()
            failed_id = str(failed_doc.id)

        retry_exp = c1.post(f"/api/documents/{failed_id}/retry", headers=CSRF_HEADERS)
        assert retry_exp.status_code == 409
        assert retry_exp.json()["error"]["code"] == "VAULT_EXPIRED"

        # Audit filters (actor UUID, action, outcome, date_from, date_to, sort/order)
        now = datetime.now(timezone.utc)
        d_from = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        d_to = (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        filtered = c_adm.get(
            f"/api/audit?actor={doc_user_id}&action=AUTH_LOGIN_SUCCESS&outcome=allowed&date_from={d_from}&date_to={d_to}&sort=id&order=asc"
        )
        assert filtered.status_code == 200
        assert filtered.json()["total"] >= 2
        assert all(item["action"] == "AUTH_LOGIN_SUCCESS" for item in filtered.json()["items"])
