import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.errors import AppError, ErrorCode
from app.logging import JsonFormatter, PHISafeFilter, request_id_var


def test_health_endpoint_and_security_headers(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["app_name"] == "ClinicShield"
    assert body["env"] in {"dev", "prod", "test"}
    assert "timestamp" in body

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert len(response.headers["x-request-id"]) >= 8


def test_request_id_echoed_when_valid_and_replaced_when_invalid(client: TestClient) -> None:
    custom_id = "req-12345678-test"
    ok_res = client.get("/api/health", headers={"X-Request-ID": custom_id})
    assert ok_res.status_code == 200
    assert ok_res.headers["x-request-id"] == custom_id

    bad_res = client.get("/api/health", headers={"X-Request-ID": "bad\nheader value"})
    assert bad_res.status_code == 200
    assert bad_res.headers["x-request-id"] != "bad\nheader value"
    assert len(bad_res.headers["x-request-id"]) >= 8


def test_standard_error_shape_across_status_codes(app: FastAPI, client: TestClient) -> None:
    class SamplePayload(BaseModel):
        count: int

    @app.get("/api/_test/unauth")
    def trigger_401() -> None:
        raise AppError(ErrorCode.UNAUTHENTICATED, 401, "Authentication required.")

    @app.get("/api/_test/forbidden")
    def trigger_403() -> None:
        raise AppError(ErrorCode.FORBIDDEN, 403, "Access denied.")

    @app.post("/api/_test/validate")
    def trigger_422(payload: SamplePayload) -> dict[str, int]:
        return {"count": payload.count}

    @app.get("/api/_test/ratelimit")
    def trigger_429() -> None:
        raise AppError(
            ErrorCode.RATE_LIMITED,
            429,
            "Too many requests.",
            headers={"Retry-After": "60"},
        )

    @app.get("/api/_test/crash")
    def trigger_500() -> None:
        raise RuntimeError("SELECT * FROM users WHERE email='leak@example.com'")

    cases = [
        ("GET", "/api/_test/unauth", None, 401, "UNAUTHENTICATED"),
        ("GET", "/api/_test/forbidden", None, 403, "FORBIDDEN"),
        ("GET", "/api/does-not-exist", None, 404, "NOT_FOUND"),
        ("POST", "/api/_test/validate", {"count": "Rahim Ahmed secret"}, 422, "VALIDATION_ERROR"),
        ("GET", "/api/_test/ratelimit", None, 429, "RATE_LIMITED"),
        ("GET", "/api/_test/crash", None, 500, "INTERNAL_ERROR"),
    ]

    for method, path, payload, expected_status, expected_code in cases:
        res = client.request(method, path, json=payload)
        assert res.status_code == expected_status
        body = res.json()
        assert set(body.keys()) == {"error"}
        assert set(body["error"].keys()) == {"code", "message", "request_id"}
        assert body["error"]["code"] == expected_code
        assert body["error"]["request_id"] == res.headers["x-request-id"]
        assert "Rahim Ahmed" not in body["error"]["message"]
        assert "SELECT" not in body["error"]["message"]
        assert "leak@example.com" not in body["error"]["message"]
        assert res.headers["cache-control"] == "no-store"
        assert res.headers["x-content-type-options"] == "nosniff"


def test_json_logging_and_phi_safe_filter() -> None:
    token = request_id_var.set("req-log-check-01")
    try:
        phi_filter = PHISafeFilter()
        formatter = JsonFormatter()

        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="Failed for user@example.com phone +8801712345678 password=SuperSecret123",
            args=(),
            exc_info=None,
        )
        record.event = "test_event"
        record.status_code = 400
        record.duration_ms = 12.4
        record.document_text = "Patient Rahim Ahmed DOB 01/01/1970"
        record.original_filename = "rahim_ahmed_report.pdf"
        record.password = "SuperSecret123"
        record.unlisted_field = "should_not_appear"

        assert phi_filter.filter(record) is True
        assert not hasattr(record, "original_filename")
        assert not hasattr(record, "document_text")
        assert not hasattr(record, "password")
        formatted = formatter.format(record)
        parsed = json.loads(formatted)

        assert parsed["request_id"] == "req-log-check-01"
        assert parsed["level"] == "INFO"
        assert parsed["event"] == "test_event"
        assert parsed["status_code"] == 400
        assert parsed["duration_ms"] == 12.4
        assert parsed["timestamp"].endswith("Z")

        assert "user@example.com" not in formatted
        assert "01712345678" not in formatted
        assert "SuperSecret123" not in formatted
        assert "Rahim Ahmed" not in formatted
        assert "rahim_ahmed_report.pdf" not in formatted
        assert "should_not_appear" not in formatted
    finally:
        request_id_var.reset(token)
