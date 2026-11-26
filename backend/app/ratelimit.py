import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.errors import ErrorCode, build_error_response

logger = logging.getLogger("app.ratelimit")


def user_or_ip_key(request: Request) -> str:
    user_id = getattr(request.state, "rate_limit_user_id", None)
    if user_id:
        return f"user:{user_id}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute"],
    headers_enabled=False,
)


def reset_rate_limits() -> None:
    """Clear in-memory rate-limit counters (used between tests)."""
    limiter._storage.reset()


def register_rate_limiter(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.exception_handler(RateLimitExceeded)
    def handle_rate_limit(_request: Request, exc: RateLimitExceeded) -> JSONResponse:
        retry_after = "60"
        if getattr(exc, "detail", None):
            detail = str(exc.detail)
            if "hour" in detail:
                retry_after = "3600"
            elif "second" in detail:
                retry_after = "1"
        logger.warning(
            "Rate limit exceeded",
            extra={"event": "rate_limited", "error_code": ErrorCode.RATE_LIMITED.value, "status_code": 429},
        )
        return build_error_response(
            ErrorCode.RATE_LIMITED,
            429,
            "Too many requests. Please try again later.",
            headers={"Retry-After": retry_after},
        )
