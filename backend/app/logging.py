from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import re
from typing import Any

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

ALLOWED_EXTRA_KEYS: frozenset[str] = frozenset(
    {
        "event",
        "method",
        "path",
        "status_code",
        "duration_ms",
        "error_code",
        "count",
        "actor_id",
        "actor_role",
        "resource_type",
        "resource_id",
        "document_id",
        "step",
        "provider",
        "attempts",
        "latency_ms",
        "stage",
        "rss_mb",
    }
)

FORBIDDEN_KEY_SUBSTRINGS: tuple[str, ...] = (
    "password",
    "secret",
    "token",
    "cookie",
    "authorization",
    "api_key",
    "apikey",
    "credential",
    "document_text",
    "original_text",
    "sanitized_text",
    "filename",
    "entity_value",
    "patient",
    "email",
    "phone",
    "request_body",
    "body",
    "avatar",
)

SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(
        r"\b(?:password|passwd|secret|api[_-]?key|cookie|authorization|token)\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(r"(?<!\d)(?:\+?\d[\s-]?){10,17}(?!\d)"),
)


def scrub_sensitive_text(text: str) -> str:
    cleaned = text
    for pattern in SENSITIVE_PATTERNS:
        cleaned = pattern.sub("[REDACTED]", cleaned)
    return cleaned


STANDARD_LOGRECORD_ATTRS: frozenset[str] = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
)


def _is_forbidden_key(key: str) -> bool:
    if key in STANDARD_LOGRECORD_ATTRS:
        return False
    lowered = key.lower()
    return any(part in lowered for part in FORBIDDEN_KEY_SUBSTRINGS)


class PHISafeFilter(logging.Filter):
    """Strips sensitive fields and scrubs PHI/secrets from log records (rules.md P6)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()

        # Render message safely and clear args so formatted output is always scrubbed.
        try:
            rendered = record.getMessage()
        except Exception:
            rendered = str(record.msg)
        record.msg = scrub_sensitive_text(rendered)
        record.args = ()

        # Remove any forbidden custom attributes attached to the record.
        for key in list(record.__dict__.keys()):
            if _is_forbidden_key(key):
                delattr(record, key)

        # Suppress raw exception tracebacks in structured log text to avoid leaking values.
        if record.exc_info:
            exc_type = record.exc_info[0]
            record.error_type = exc_type.__name__ if exc_type else "Exception"
            record.exc_info = None
            record.exc_text = None

        return True


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line UTC ISO-8601 JSON with whitelisted fields only."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", request_id_var.get()),
            "message": scrub_sensitive_text(str(record.msg)),
        }

        error_type = getattr(record, "error_type", None)
        if error_type:
            payload["error_type"] = str(error_type)

        for key in ALLOWED_EXTRA_KEYS:
            value = getattr(record, key, None)
            if value is not None:
                if isinstance(value, str):
                    payload[key] = scrub_sensitive_text(value)
                elif isinstance(value, (int, float, bool)):
                    payload[key] = value
                else:
                    payload[key] = scrub_sensitive_text(str(value))

        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.addFilter(PHISafeFilter())
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(handler)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(logger_name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True
