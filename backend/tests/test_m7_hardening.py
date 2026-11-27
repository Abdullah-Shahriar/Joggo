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
from app.services.llm.gemini import DEFAULT_GEMINI_MODEL, GeminiProvider
from app.services.llm.groq import DEFAULT_GROQ_MODEL, GroqProvider
from app.services.llm.validate import validate_llm_output
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

    # Default model fallback when env model is empty or placeholder, plus Gemini thought-part filtering
    monkeypatch.setattr("app.services.llm.gemini.get_settings", lambda: type("S", (), {"GEMINI_API_KEY": "k1", "GEMINI_MODEL": ""})())
    monkeypatch.setattr("app.services.llm.groq.get_settings", lambda: type("S", (), {"GROQ_API_KEY": "k2", "GROQ_MODEL": "<placeholder>"})())
    gem_default = GeminiProvider()
    groq_default = GroqProvider()
    assert gem_default._model == DEFAULT_GEMINI_MODEL
    assert groq_default._model == DEFAULT_GROQ_MODEL

    monkeypatch.setattr(
        httpx.Client,
        "post",
        make_fake_post(
            _DummyHTTPResponse(
                200,
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": "internal reasoning", "thought": True},
                                    {"text": "### Summary:\nClean clinical summary.\n\n## **Key findings**\nStable.\n\n## 3. Concerns:\nNone."},
                                ]
                            }
                        }
                    ]
                },
            )
        ),
    )
    res_thought = gem_default.generate("sys", "usr")
    assert "internal reasoning" not in res_thought.text
    valid, reason = validate_llm_output(res_thought.text, TaskType.case_summary)
    assert valid is True, reason

    # Auto-model discovery fallback when configured model returns 404 (Gemini & Groq)
    gem_404 = GeminiProvider(api_key="test-gem-key", model="gemini-retired-model")
    gem_post_calls = {"n": 0}

    def fake_gem_post(self, url, *, json=None, headers=None, **kwargs):
        gem_post_calls["n"] += 1
        if "gemini-retired-model" in url:
            return _DummyHTTPResponse(404, {"error": {"status": "NOT_FOUND", "message": "model not found"}})
        assert "gemini-2.5-flash" in url
        return _DummyHTTPResponse(200, {"candidates": [{"content": {"parts": [{"text": "## Summary\nAuto-switched"}]}}]})

    def fake_gem_get(self, url, *, headers=None, **kwargs):
        return _DummyHTTPResponse(
            200,
            {
                "models": [
                    {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
                ]
            },
        )

    monkeypatch.setattr(httpx.Client, "post", fake_gem_post)
    monkeypatch.setattr(httpx.Client, "get", fake_gem_get)
    res_auto_gem = gem_404.generate("sys", "usr")
    assert res_auto_gem.model == "gemini-2.5-flash"
    assert res_auto_gem.text == "## Summary\nAuto-switched"
    assert gem_post_calls["n"] == 2

    groq_400 = GroqProvider(api_key="test-groq-key", model="llama3-retired")
    groq_post_calls = {"n": 0}

    def fake_groq_post(self, url, *, json=None, headers=None, **kwargs):
        groq_post_calls["n"] += 1
        if json and json.get("model") == "llama3-retired":
            return _DummyHTTPResponse(400, {"error": {"code": "model_decommissioned", "message": "Model decommissioned"}})
        assert json and json.get("model") == "openai/gpt-oss-120b"
        return _DummyHTTPResponse(200, {"choices": [{"message": {"content": "## Summary\nGroq auto-switched"}}]})

    def fake_groq_get(self, url, *, headers=None, **kwargs):
        return _DummyHTTPResponse(
            200,
            {
                "data": [
                    {"id": "whisper-large-v3", "active": True},
                    {"id": "openai/gpt-oss-120b", "active": True},
                ]
            },
        )

    monkeypatch.setattr(httpx.Client, "post", fake_groq_post)
    monkeypatch.setattr(httpx.Client, "get", fake_groq_get)
    res_auto_groq = groq_400.generate("sys", "usr")
    assert res_auto_groq.model == "openai/gpt-oss-120b"
    assert res_auto_groq.text == "## Summary\nGroq auto-switched"
    assert groq_post_calls["n"] == 2


def test_gemini_model_validation_discovery_thinking_config_and_startup_log(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging
    from app.services.llm.gemini import _pick_best_gemini_model, _resolve_model
    from app.services.llm.router import log_llm_startup_config

    # Invalid / blank / models/-prefixed GEMINI_MODEL falls back or normalizes cleanly
    assert _resolve_model(None, "", DEFAULT_GEMINI_MODEL, require_prefix="gemini-") == DEFAULT_GEMINI_MODEL
    assert _resolve_model(None, "invalid-model", DEFAULT_GEMINI_MODEL, require_prefix="gemini-") == DEFAULT_GEMINI_MODEL
    assert _resolve_model(None, "models/gemini-2.5-flash", DEFAULT_GEMINI_MODEL, require_prefix="gemini-") == "gemini-2.5-flash"
    assert _resolve_model(None, '"gemini-2.5-flash"', DEFAULT_GEMINI_MODEL, require_prefix="gemini-") == "gemini-2.5-flash"

    # Auto-model discovery skips image/live/latest/embedding models and picks gemini-2.5-flash
    payload = {
        "models": [
            {"name": "models/gemini-flash-latest", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-2.5-flash-image", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-2.0-flash-live-001", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
        ]
    }
    assert _pick_best_gemini_model(payload, exclude=set()) == "gemini-2.5-flash"
    # When gemini-2.5-flash is absent, avoids -image and -live and selects gemini-2.0-flash
    assert (
        _pick_best_gemini_model(
            {
                "models": [
                    {"name": "models/gemini-2.5-flash-image", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-2.0-flash-live-001", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-2.0-flash", "supportedGenerationMethods": ["generateContent"]},
                ]
            },
            exclude=set(),
        )
        == "gemini-2.0-flash"
    )

    # Request payload sets thinkingBudget=0 for gemini-2.5-flash and omits it for gemini-2.0-flash
    captured_payloads: list[dict] = []

    def fake_post(self, url, *, json=None, headers=None, **kwargs):
        captured_payloads.append({"url": url, "json": json})
        return _DummyHTTPResponse(200, {"candidates": [{"content": {"parts": [{"text": "## Summary\nOK"}]}}]})

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    GeminiProvider(api_key="test-key", model="gemini-2.5-flash").generate("sys", "usr")
    assert captured_payloads[-1]["json"]["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}

    GeminiProvider(api_key="test-key", model="gemini-2.0-flash").generate("sys", "usr")
    assert "thinkingConfig" not in captured_payloads[-1]["json"]["generationConfig"]

    # PHI-free / secret-free startup log line reports order, models, and key present yes/no (never key)
    secret_sentinel = "AIzaSySyntheticSecretValue12345"
    monkeypatch.setattr(
        "app.services.llm.router.get_settings",
        lambda: type(
            "S",
            (),
            {
                "llm_providers": ["gemini", "groq"],
                "GEMINI_MODEL": "",
                "GEMINI_API_KEY": secret_sentinel,
                "GROQ_MODEL": "llama-3.3-70b-versatile",
                "GROQ_API_KEY": "",
            },
        )(),
    )
    caplog.set_level(logging.INFO, logger="app.llm.router")
    caplog.clear()
    log_llm_startup_config()
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert "order=[gemini,groq]" in log_text
    assert "gemini(model=gemini-2.5-flash, key present: yes)" in log_text
    assert "groq(model=llama-3.3-70b-versatile, key present: no)" in log_text
    assert secret_sentinel not in log_text


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
