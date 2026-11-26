from enum import Enum
import logging
from typing import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging import request_id_var
from app.schemas.common import ErrorBody, ErrorResponse

logger = logging.getLogger("app.errors")


class ErrorCode(str, Enum):
    # Auth
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    EMAIL_TAKEN = "EMAIL_TAKEN"
    WEAK_PASSWORD = "WEAK_PASSWORD"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    SESSION_REVOKED = "SESSION_REVOKED"
    GOOGLE_TOKEN_INVALID = "GOOGLE_TOKEN_INVALID"
    NO_PASSWORD_SET = "NO_PASSWORD_SET"
    CSRF_REJECTED = "CSRF_REJECTED"

    # Access
    FORBIDDEN = "FORBIDDEN"
    ACCOUNT_RESTRICTED = "ACCOUNT_RESTRICTED"
    ADMIN_NO_DOCUMENT_ACCESS = "ADMIN_NO_DOCUMENT_ACCESS"
    NOT_FOUND = "NOT_FOUND"

    # Validation
    VALIDATION_ERROR = "VALIDATION_ERROR"
    IDEMPOTENCY_KEY_REQUIRED = "IDEMPOTENCY_KEY_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"

    # Upload
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    NOT_A_PDF = "NOT_A_PDF"
    PDF_CORRUPT = "PDF_CORRUPT"
    PDF_ENCRYPTED = "PDF_ENCRYPTED"
    TOO_MANY_PAGES = "TOO_MANY_PAGES"
    EMPTY_DOCUMENT = "EMPTY_DOCUMENT"
    DUPLICATE_DOCUMENT = "DUPLICATE_DOCUMENT"

    # Pipeline
    EXTRACTION_TIMEOUT = "EXTRACTION_TIMEOUT"
    OCR_FAILED = "OCR_FAILED"
    DETECTION_FAILED = "DETECTION_FAILED"
    SAFETY_BLOCKED = "SAFETY_BLOCKED"
    SERVER_RESTART = "SERVER_RESTART"
    INVALID_STATE = "INVALID_STATE"
    VAULT_EXPIRED = "VAULT_EXPIRED"
    STALE_REVIEW = "STALE_REVIEW"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    MARK_NOT_FOUND = "MARK_NOT_FOUND"
    MARK_OVERLAPS_TOKEN = "MARK_OVERLAPS_TOKEN"

    # LLM
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_MALFORMED_RESPONSE = "LLM_MALFORMED_RESPONSE"
    LLM_AUTH_ERROR = "LLM_AUTH_ERROR"

    # Admin
    CANNOT_MODIFY_SELF = "CANNOT_MODIFY_SELF"
    CANNOT_MODIFY_ADMIN = "CANNOT_MODIFY_ADMIN"
    INVALID_ROLE_CHANGE = "INVALID_ROLE_CHANGE"

    # Complaints
    COMPLAINT_CLOSED = "COMPLAINT_CLOSED"
    INVALID_COMPLAINT_TRANSITION = "INVALID_COMPLAINT_TRANSITION"

    # Fallback
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        http_status: int,
        message: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.message = message
        self.headers = dict(headers) if headers else None


def build_error_response(
    code: ErrorCode,
    http_status: int,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    req_id = request_id_var.get()
    body = ErrorResponse(
        error=ErrorBody(
            code=code.value,
            message=message,
            request_id=req_id,
        )
    )
    response_headers = dict(headers) if headers else {}
    response_headers["X-Request-ID"] = req_id
    return JSONResponse(
        status_code=http_status,
        content=body.model_dump(),
        headers=response_headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "Handled application error",
            extra={"event": "app_error", "error_code": exc.code.value, "status_code": exc.http_status},
        )
        return build_error_response(exc.code, exc.http_status, exc.message, exc.headers)

    @app.exception_handler(RequestValidationError)
    def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Summarize field locations only; never echo raw input values (rules.md P1/P6).
        fields: list[str] = []
        for err in exc.errors():
            loc = [str(part) for part in err.get("loc", ()) if part != "body"]
            if loc:
                fields.append(".".join(loc))
        summary = f"Invalid request input ({', '.join(dict.fromkeys(fields))})." if fields else "Invalid request input."
        logger.warning(
            "Request validation failed",
            extra={"event": "validation_error", "error_code": ErrorCode.VALIDATION_ERROR.value, "status_code": 422},
        )
        return build_error_response(ErrorCode.VALIDATION_ERROR, 422, summary)

    @app.exception_handler(StarletteHTTPException)
    def handle_http_exception(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        status_map: dict[int, tuple[ErrorCode, str]] = {
            401: (ErrorCode.UNAUTHENTICATED, "Authentication required."),
            403: (ErrorCode.FORBIDDEN, "Access denied."),
            404: (ErrorCode.NOT_FOUND, "Resource not found."),
            405: (ErrorCode.VALIDATION_ERROR, "Method not allowed."),
            429: (ErrorCode.RATE_LIMITED, "Too many requests. Please try again later."),
        }
        code, message = status_map.get(
            exc.status_code,
            (ErrorCode.INTERNAL_ERROR, "An internal error occurred."),
        )
        logger.warning(
            "HTTP exception",
            extra={"event": "http_error", "error_code": code.value, "status_code": exc.status_code},
        )
        return build_error_response(code, exc.status_code, message, exc.headers)

    @app.exception_handler(Exception)
    def handle_unexpected_exception(_request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled server exception",
            exc_info=(type(exc), exc, exc.__traceback__),
            extra={"event": "internal_error", "error_code": ErrorCode.INTERNAL_ERROR.value, "status_code": 500},
        )
        return build_error_response(ErrorCode.INTERNAL_ERROR, 500, "An internal error occurred.")
