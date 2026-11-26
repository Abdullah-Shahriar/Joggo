from concurrent.futures import ThreadPoolExecutor
import io
import time
import uuid

from docx import Document as DocxDocument
from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.errors import ErrorCode
from app.models import AuditLog, Document, TaskType, User, UserRole, UserStatus
from app.security import hash_password
from app.services.llm.base import LLMProvider, LLMProviderError, LLMResult
from app.services.llm.breaker import CircuitBreaker
from app.services.llm.prompts import (
    AI_DISCLAIMER,
    SYSTEM_PROMPT,
    TASK_HEADINGS,
    build_external_handoff_prompt,
    build_user_prompt,
)
from app.services.llm.router import LLMRouterError, get_breaker, route_generate
from app.services.rehydrate import rehydrate_text
from app.services.vault import vault
from scripts.make_sample_pdfs import build_text_lab_report_bytes
from tests.conftest import CSRF_HEADERS

VALID_DISCHARGE_MD = """## Diagnosis
Type 2 diabetes mellitus.

## Clinical course
[PATIENT_A] presented on [DAY_0] for follow-up with [DOCTOR_1].

## Key findings
Hemoglobin 13.4 g/dL, Fasting Glucose 142 mg/dL, HbA1c 7.4 %.

## Medications at discharge
Metformin 500 mg twice daily.

## Follow-up
Return on [DAY_14] at [FACILITY_1].
"""


class ScriptedProvider(LLMProvider):
    def __init__(self, name: str, outcomes: list[LLMResult | LLMProviderError]) -> None:
        self.name = name
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, str]] = []

    def generate(
        self,
        system: str,
        user: str,
        *,
        timeout: httpx.Timeout | None = None,
    ) -> LLMResult:
        self.calls.append((system, user))
        if not self._outcomes:
            raise LLMProviderError(ErrorCode.LLM_UNAVAILABLE, "No scripted outcome left", retryable=True)
        nxt = self._outcomes.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def _login_doctor(app: FastAPI) -> tuple[TestClient, User]:
    email = f"m5doc-{uuid.uuid4().hex[:8]}@example.com"
    with SessionLocal() as db:
        user = User(
            email=email,
            password_hash=hash_password("StrongPass123"),
            full_name="Dr Synthetic M5",
            role=UserRole.doctor,
            status=UserStatus.active,
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


def _upload_and_approve(client: TestClient) -> tuple[str, dict]:
    up = client.post(
        "/api/documents",
        files={"file": ("patient_rahim_secret_name.pdf", build_text_lab_report_bytes(), "application/pdf")},
        data={"task_type": "discharge_summary"},
        headers=CSRF_HEADERS,
    )
    assert up.status_code == 202
    doc_id = up.json()["id"]

    deadline = time.monotonic() + 25.0
    detail: dict = {}
    while time.monotonic() < deadline:
        detail = client.get(f"/api/documents/{doc_id}").json()
        if detail["status"] not in {"UPLOADED", "PROCESSING"}:
            break
        time.sleep(0.1)
    assert detail["status"] == "REVIEW_REQUIRED"

    app_res = client.post(
        f"/api/documents/{doc_id}/approve",
        json={"sanitized_sha256": detail["sanitized_sha256"]},
        headers=CSRF_HEADERS,
    )
    assert app_res.status_code == 200
    return doc_id, app_res.json()


def _wait_terminal(client: TestClient, doc_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        last = client.get(f"/api/documents/{doc_id}").json()
        if last["status"] not in {"SENDING", "PROCESSING", "UPLOADED"}:
            return last
        time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for terminal status; last={last}")


def test_llm_router_timeout_retry_429_retry_after_fallback_repair_and_both_fail() -> None:
    sleeps: list[float] = []

    # 1. Timeout -> retry -> success
    p_timeout = ScriptedProvider(
        "gemini",
        [
            LLMProviderError(ErrorCode.LLM_TIMEOUT, "timeout", retryable=True),
            LLMResult(text=VALID_DISCHARGE_MD, model="gemini-test", latency_ms=120, provider="gemini"),
        ],
    )
    ok = route_generate(TaskType.discharge_summary, "Sanitized text", providers=[p_timeout], sleep_fn=sleeps.append)
    assert ok.result.provider == "gemini"
    assert ok.used_fallback is False
    assert ok.attempts_total == 2
    assert len(sleeps) == 1

    # 2. 429 with Retry-After honored (and capped at 10s)
    sleeps.clear()
    p_429 = ScriptedProvider(
        "gemini",
        [
            LLMProviderError(ErrorCode.LLM_UNAVAILABLE, "429", retryable=True, retry_after=25.0),
            LLMResult(text=VALID_DISCHARGE_MD, model="gemini-test", latency_ms=100, provider="gemini"),
        ],
    )
    ok2 = route_generate(TaskType.discharge_summary, "Sanitized text", providers=[p_429], sleep_fn=sleeps.append)
    assert ok2.result.provider == "gemini"
    assert sleeps == [10.0]

    # 3. Primary fails all 3 attempts -> fallback provider used
    p_primary_down = ScriptedProvider(
        "gemini",
        [
            LLMProviderError(ErrorCode.LLM_UNAVAILABLE, "503", retryable=True),
            LLMProviderError(ErrorCode.LLM_UNAVAILABLE, "503", retryable=True),
            LLMProviderError(ErrorCode.LLM_UNAVAILABLE, "503", retryable=True),
        ],
    )
    p_fallback_ok = ScriptedProvider(
        "groq",
        [LLMResult(text=VALID_DISCHARGE_MD, model="groq-test", latency_ms=90, provider="groq")],
    )
    fb = route_generate(
        TaskType.discharge_summary,
        "Sanitized text",
        providers=[p_primary_down, p_fallback_ok],
        sleep_fn=lambda _s: None,
    )
    assert fb.result.provider == "groq"
    assert fb.used_fallback is True
    assert len(p_primary_down.calls) == 3
    assert len(p_fallback_ok.calls) == 1

    # 4. Malformed response -> single repair retry -> then fallback if repair still malformed
    p_malformed = ScriptedProvider(
        "gemini",
        [
            LLMResult(text="Missing headings completely", model="gemini-test", latency_ms=50, provider="gemini"),
            LLMResult(text="I cannot assist with that.", model="gemini-test", latency_ms=50, provider="gemini"),
        ],
    )
    p_groq_rescue = ScriptedProvider(
        "groq",
        [LLMResult(text=VALID_DISCHARGE_MD, model="groq-test", latency_ms=80, provider="groq")],
    )
    repaired_fb = route_generate(
        TaskType.discharge_summary,
        "Sanitized text",
        providers=[p_malformed, p_groq_rescue],
        sleep_fn=lambda _s: None,
    )
    assert repaired_fb.result.provider == "groq"
    assert repaired_fb.used_fallback is True
    assert len(p_malformed.calls) == 2
    assert "Return only the required Markdown headings" in p_malformed.calls[1][1]

    # 5. Both providers fail -> raises LLMRouterError
    p_bad1 = ScriptedProvider("gemini", [LLMProviderError(ErrorCode.LLM_AUTH_ERROR, "401", retryable=False)])
    p_bad2 = ScriptedProvider(
        "groq",
        [
            LLMProviderError(ErrorCode.LLM_TIMEOUT, "t1", retryable=True),
            LLMProviderError(ErrorCode.LLM_TIMEOUT, "t2", retryable=True),
            LLMProviderError(ErrorCode.LLM_TIMEOUT, "t3", retryable=True),
        ],
    )
    with pytest.raises(LLMRouterError) as exc_info:
        route_generate(
            TaskType.discharge_summary,
            "Sanitized text",
            providers=[p_bad1, p_bad2],
            sleep_fn=lambda _s: None,
        )
    assert exc_info.value.failure_code == ErrorCode.LLM_TIMEOUT


def test_circuit_breaker_opens_and_recovers() -> None:
    now = {"t": 100.0}
    breaker = CircuitBreaker(
        failure_threshold=5,
        failure_window_seconds=60.0,
        recovery_timeout_seconds=30.0,
        clock=lambda: now["t"],
    )

    for _ in range(4):
        assert breaker.allow_request() is True
        breaker.record_failure()
    assert breaker.state == "closed"

    # 5th failure opens breaker
    assert breaker.allow_request() is True
    breaker.record_failure()
    assert breaker.state == "open"
    assert breaker.allow_request() is False

    # After 30s transitions to half_open and allows exactly 1 trial
    now["t"] += 31.0
    assert breaker.state == "half_open"
    assert breaker.allow_request() is True
    assert breaker.allow_request() is False

    # Trial succeeds -> closes breaker
    breaker.record_success()
    assert breaker.state == "closed"
    assert breaker.allow_request() is True


def test_rehydration_unknown_token_bare_token_and_vault_expired() -> None:
    raw_llm = "## Summary\n[PATIENT_A] visited [DOCTOR_1]. Also PATIENT_A saw [DOCTOR_99].\n"
    mapping = {"[PATIENT_A]": "Rahim Ahmed", "[DOCTOR_1]": "Dr. Nasrin Sultana"}

    res = rehydrate_text(raw_llm, mapping)
    assert res.rehydrated is True
    assert res.vault_expired is False
    assert "Rahim Ahmed visited Dr. Nasrin Sultana. Also Rahim Ahmed saw [DOCTOR_99]." in res.text
    assert AI_DISCLAIMER in res.text
    assert res.warnings == [{"code": "UNKNOWN_TOKEN", "token": "[DOCTOR_99]"}]

    # Vault expired -> tokenized text + disclaimer, rehydrated=False
    expired = rehydrate_text(raw_llm, None)
    assert expired.rehydrated is False
    assert expired.vault_expired is True
    assert "[PATIENT_A]" in expired.text
    assert AI_DISCLAIMER in expired.text


def test_send_outbound_payload_privacy_fallback_rehydrate_export_and_retry(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_outbound: list[tuple[str, str]] = []

    p_down = ScriptedProvider("gemini", [LLMProviderError(ErrorCode.LLM_AUTH_ERROR, "401", retryable=False)])
    p_backup = ScriptedProvider(
        "groq",
        [LLMResult(text=VALID_DISCHARGE_MD, model="groq-mock", latency_ms=75, provider="groq")],
    )

    def fake_route(task_type: TaskType, sanitized_text: str):
        outcome = route_generate(task_type, sanitized_text, providers=[p_down, p_backup], sleep_fn=lambda _s: None)
        captured_outbound.extend(p_backup.calls)
        return outcome

    monkeypatch.setattr("app.services.pipeline.route_generate", fake_route)

    c, user = _login_doctor(app)
    try:
        doc_id, _approved = _upload_and_approve(c)

        # Missing Idempotency-Key -> 400 IDEMPOTENCY_KEY_REQUIRED
        no_key = c.post(f"/api/documents/{doc_id}/send", headers=CSRF_HEADERS)
        assert no_key.status_code == 400
        assert no_key.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"

        # Send with Idempotency-Key -> 202
        idem = str(uuid.uuid4())
        send_res = c.post(
            f"/api/documents/{doc_id}/send",
            headers={**CSRF_HEADERS, "Idempotency-Key": idem},
        )
        assert send_res.status_code == 202
        assert send_res.json()["replayed"] is False

        # Replay with same Idempotency-Key -> 200 replayed, no second provider call
        replay_res = c.post(
            f"/api/documents/{doc_id}/send",
            headers={**CSRF_HEADERS, "Idempotency-Key": idem},
        )
        assert replay_res.status_code == 200
        assert replay_res.json()["replayed"] is True

        done = _wait_terminal(c, doc_id)
        assert done["status"] == "COMPLETED"
        assert done["llm_provider_used"] == "groq"
        assert len(p_backup.calls) == 1

        # P3 / T5: Outbound LLM payload MUST contain ZERO real patient values, filename, user email, or ids
        outbound_blob = "\n".join(sys_p + "\n" + usr_p for sys_p, usr_p in captured_outbound)
        for forbidden in (
            "Rahim Ahmed",
            "1968472910482",
            "1712-345678",
            "rahim.ahmed.synth@example.test",
            "MRN-884210",
            "Dhanmondi",
            "patient_rahim_secret_name.pdf",
            user.email,
            str(user.id),
            doc_id,
        ):
            assert forbidden not in outbound_blob, f"Outbound LLM payload leaked: {forbidden!r}"

        # Result endpoint re-hydrates locally and reports fallback_used=True
        res = c.get(f"/api/documents/{doc_id}/result")
        assert res.status_code == 200
        body = res.json()
        assert body["rehydrated"] is True
        assert body["fallback_used"] is True
        assert "Rahim Ahmed" in body["text"]
        assert AI_DISCLAIMER in body["text"]

        # Verify re-hydrated text is NEVER stored in PostgreSQL (P1)
        with SessionLocal() as db:
            row = db.get(Document, uuid.UUID(doc_id))
            assert row is not None
            assert "Rahim Ahmed" not in (row.llm_response_tokenized or "")
            fb_audit = db.execute(
                select(AuditLog).where(AuditLog.action == "DOC_LLM_FALLBACK", AuditLog.resource_id == doc_id).limit(1)
            ).scalar_one_or_none()
            assert fb_audit is not None

        # Export TXT and DOCX (headers/footers empty)
        txt_res = c.get(f"/api/documents/{doc_id}/export?format=txt")
        assert txt_res.status_code == 200
        assert f"summary-{doc_id[:8]}.txt" in txt_res.headers["content-disposition"]
        assert "Rahim Ahmed" in txt_res.text

        docx_res = c.get(f"/api/documents/{doc_id}/export?format=docx")
        assert docx_res.status_code == 200
        assert f"summary-{doc_id[:8]}.docx" in docx_res.headers["content-disposition"]
        parsed_docx = DocxDocument(io.BytesIO(docx_res.content))
        all_paras = "\n".join(p.text for p in parsed_docx.paragraphs)
        assert "Rahim Ahmed" in all_paras
        for sec in parsed_docx.sections:
            assert "".join(p.text for p in sec.header.paragraphs).strip() == ""
            assert "".join(p.text for p in sec.footer.paragraphs).strip() == ""
    finally:
        c.__exit__(None, None, None)


def test_double_concurrent_send_calls_provider_once_and_llm_failed_retry_works(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = {"n": 0}
    should_fail = {"flag": True}

    def controlled_route(task_type: TaskType, sanitized_text: str):
        call_count["n"] += 1
        if should_fail["flag"]:
            raise LLMRouterError(ErrorCode.LLM_UNAVAILABLE, [])
        p = ScriptedProvider(
            "gemini",
            [LLMResult(text=VALID_DISCHARGE_MD, model="gemini-mock", latency_ms=40, provider="gemini")],
        )
        return route_generate(task_type, sanitized_text, providers=[p], sleep_fn=lambda _s: None)

    monkeypatch.setattr("app.services.pipeline.route_generate", controlled_route)

    c, _user = _login_doctor(app)
    try:
        doc_id, _approved = _upload_and_approve(c)
        cookies = dict(c.cookies)

        # Two simultaneous sends with different keys -> 1 gets 202, 1 gets 409 INVALID_STATE
        def do_send() -> int:
            with TestClient(app, raise_server_exceptions=False, cookies=cookies) as tc:
                r = tc.post(
                    f"/api/documents/{doc_id}/send",
                    headers={**CSRF_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
                )
                return r.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(do_send)
            f2 = pool.submit(do_send)
            statuses = sorted([f1.result(), f2.result()])

        assert statuses == [202, 409]
        failed_doc = _wait_terminal(c, doc_id)
        assert failed_doc["status"] == "LLM_FAILED"
        assert failed_doc["failure_code"] == "LLM_UNAVAILABLE"
        assert call_count["n"] == 1

        # Retry from LLM_FAILED succeeds once provider recovers
        should_fail["flag"] = False
        retry_res = c.post(f"/api/documents/{doc_id}/retry", headers=CSRF_HEADERS)
        assert retry_res.status_code == 202
        completed_doc = _wait_terminal(c, doc_id)
        assert completed_doc["status"] == "COMPLETED"
        assert call_count["n"] == 2
    finally:
        c.__exit__(None, None, None)


def test_prompts_include_per_heading_guidance_and_preserve_rules() -> None:
    assert "Copy placeholders exactly as written" in SYSTEM_PROMPT
    assert "Never guess or invent identities, dates or numbers" in SYSTEM_PROMPT
    assert "Not documented" in SYSTEM_PROMPT

    sample_sanitized = "[PATIENT_A] (Age 47) admitted on [DAY_0] with HbA1c 8.1 %, Creatinine 1.4 mg/dL, GCS 15."

    for task in (TaskType.discharge_summary, TaskType.case_summary, TaskType.treatment_plan):
        prompt = build_user_prompt(task, sample_sanitized, repair=False)
        for heading in TASK_HEADINGS[task]:
            assert f"## {heading}:" in prompt
        assert "Not documented" in prompt
        assert sample_sanitized in prompt

        handoff = build_external_handoff_prompt(task, sample_sanitized)
        for heading in TASK_HEADINGS[task]:
            assert f"## {heading}:" in handoff
        assert sample_sanitized in handoff

    tp_prompt = build_user_prompt(TaskType.treatment_plan, sample_sanitized)
    assert "working diagnosis" in tp_prompt.lower()
    assert "vitals" in tp_prompt.lower() and "lab" in tp_prompt.lower()

    repair_prompt = build_user_prompt(TaskType.treatment_plan, sample_sanitized, repair=True)
    assert "Return only the required Markdown headings" in repair_prompt
