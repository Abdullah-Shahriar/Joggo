from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
import re
import time
from typing import MutableMapping
from uuid import uuid4

from fastapi import Depends, FastAPI
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.db import SessionLocal
from app.deps import register_session_wipe_hook, verify_csrf
from app.errors import ErrorCode, build_error_response, register_exception_handlers
from app.logging import configure_logging, request_id_var
from app.ratelimit import register_rate_limiter
from app.routers import admin, audit, auth, complaints, dashboard, documents, health, me
from app.services.llm.router import log_llm_startup_config
from app.services.memory import log_process_rss
from app.services.vault import run_startup_recovery, vault

logger = logging.getLogger("app.http")

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestContextAndSecurityMiddleware:
    """Assigns X-Request-ID, logs safe request metrics, and sets S11 security headers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming_id = ""
        for key, value in scope.get("headers", []):
            if key == b"x-request-id":
                candidate = value.decode("latin-1").strip()
                if REQUEST_ID_PATTERN.match(candidate):
                    incoming_id = candidate
                break

        req_id = incoming_id or str(uuid4())
        token = request_id_var.set(req_id)
        start = time.perf_counter()
        status_code = 500
        path: str = scope.get("path", "")
        method: str = scope.get("method", "")
        response_started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = int(message["status"])
                raw_headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                header_map: MutableMapping[bytes, bytes] = {k.lower(): v for k, v in raw_headers}

                def set_header(name: bytes, value: bytes) -> None:
                    header_map[name.lower()] = value

                set_header(b"x-request-id", req_id.encode("ascii"))
                set_header(b"x-content-type-options", b"nosniff")
                set_header(b"x-frame-options", b"SAMEORIGIN")
                set_header(b"referrer-policy", b"no-referrer")
                if path.startswith("/api"):
                    set_header(b"cache-control", b"no-store")

                managed = {
                    b"x-request-id",
                    b"x-content-type-options",
                    b"x-frame-options",
                    b"referrer-policy",
                }
                if path.startswith("/api"):
                    managed.add(b"cache-control")

                filtered = [(k, v) for k, v in raw_headers if k.lower() not in managed]
                for key in managed:
                    filtered.append((key, header_map[key]))
                message["headers"] = filtered

            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception as exc:
            logger.error(
                "Unhandled server exception",
                exc_info=(type(exc), exc, exc.__traceback__),
                extra={
                    "event": "internal_error",
                    "error_code": ErrorCode.INTERNAL_ERROR.value,
                    "status_code": 500,
                },
            )
            if not response_started:
                response = build_error_response(
                    ErrorCode.INTERNAL_ERROR,
                    500,
                    "An internal error occurred.",
                )
                await response(scope, receive, send_with_headers)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "HTTP request completed",
                extra={
                    "event": "http_request",
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
            request_id_var.reset(token)


@asynccontextmanager
async def _lifespan(_application: FastAPI) -> AsyncIterator[None]:
    register_session_wipe_hook(vault.wipe_session)
    if get_settings().ENV != "test":
        try:
            with SessionLocal() as db:
                run_startup_recovery(db)
        except Exception:
            logger.warning("Startup recovery skipped", extra={"event": "startup_recovery_skipped"})
    vault.start_sweeper()
    log_process_rss("startup")
    log_llm_startup_config()
    try:
        yield
    finally:
        vault.stop_sweeper()


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    application = FastAPI(
        title=settings.APP_NAME,
        docs_url="/api/docs" if settings.ENV == "dev" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.ENV == "dev" else None,
        dependencies=[Depends(verify_csrf)],
        lifespan=_lifespan,
    )

    register_exception_handlers(application)
    register_rate_limiter(application)
    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(me.router)
    application.include_router(audit.router)
    application.include_router(documents.router)
    application.include_router(dashboard.router)
    application.include_router(complaints.router)
    application.include_router(admin.router)
    application.add_middleware(RequestContextAndSecurityMiddleware)

    return application


app = create_app()
