from collections.abc import Callable
from dataclasses import dataclass
import logging
import random
import threading
import time

from app.config import get_settings
from app.errors import ErrorCode
from app.models.document import TaskType
from app.services.llm.base import LLMProvider, LLMProviderError, LLMResult
from app.services.llm.breaker import CircuitBreaker
from app.services.llm.gemini import GeminiProvider
from app.services.llm.groq import GroqProvider
from app.services.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from app.services.llm.validate import validate_llm_output

logger = logging.getLogger("app.llm.router")

MAX_ATTEMPTS_PER_PROVIDER = 3
BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0, 4.0)
MAX_RETRY_AFTER_SECONDS = 10.0

LLM_SEMAPHORE = threading.Semaphore(4)

_breaker_lock = threading.Lock()
_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(provider_name: str) -> CircuitBreaker:
    with _breaker_lock:
        if provider_name not in _breakers:
            _breakers[provider_name] = CircuitBreaker()
        return _breakers[provider_name]


def reset_breakers() -> None:
    with _breaker_lock:
        for breaker in _breakers.values():
            breaker.reset()
        _breakers.clear()


@dataclass(frozen=True)
class ProviderAttemptSummary:
    provider: str
    model: str | None
    attempts: int
    latency_ms: int
    error_code: str | None
    succeeded: bool


@dataclass(frozen=True)
class RouterSuccess:
    result: LLMResult
    attempts_total: int
    used_fallback: bool
    history: list[ProviderAttemptSummary]


class LLMRouterError(Exception):
    def __init__(self, failure_code: ErrorCode, history: list[ProviderAttemptSummary]) -> None:
        super().__init__(failure_code.value)
        self.failure_code = failure_code
        self.history = history


def build_default_providers() -> list[LLMProvider]:
    settings = get_settings()
    factory = {
        "gemini": GeminiProvider,
        "groq": GroqProvider,
    }
    providers: list[LLMProvider] = []
    for name in settings.llm_providers:
        cls = factory.get(name.lower())
        if cls is not None:
            providers.append(cls())
    return providers


def _compute_sleep(attempt_idx: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return min(retry_after, MAX_RETRY_AFTER_SECONDS)
    base = BACKOFF_SECONDS[min(attempt_idx, len(BACKOFF_SECONDS) - 1)]
    return base + random.uniform(0.0, 0.3)


def route_generate(
    task_type: TaskType,
    sanitized_text: str,
    *,
    providers: list[LLMProvider] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> RouterSuccess:
    """A06 fault-tolerant LLM router: retries, backoff, Retry-After, circuit breaker, validation+repair, fallback."""
    active_providers = providers if providers is not None else build_default_providers()
    if not active_providers:
        raise LLMRouterError(ErrorCode.LLM_UNAVAILABLE, [])

    user_prompt = build_user_prompt(task_type, sanitized_text, repair=False)
    repair_prompt = build_user_prompt(task_type, sanitized_text, repair=True)

    history: list[ProviderAttemptSummary] = []
    last_error_code = ErrorCode.LLM_UNAVAILABLE
    total_attempts = 0

    for idx, provider in enumerate(active_providers):
        breaker = get_breaker(provider.name)
        if not breaker.allow_request():
            logger.warning(
                "Skipping provider with open circuit breaker",
                extra={"event": "llm_breaker_open", "provider": provider.name},
            )
            history.append(
                ProviderAttemptSummary(
                    provider=provider.name,
                    model=None,
                    attempts=0,
                    latency_ms=0,
                    error_code=ErrorCode.LLM_UNAVAILABLE.value,
                    succeeded=False,
                )
            )
            continue

        provider_attempts = 0
        provider_latency = 0
        provider_model: str | None = None
        provider_error: ErrorCode | None = None
        succeeded_result: LLMResult | None = None

        for attempt in range(MAX_ATTEMPTS_PER_PROVIDER):
            provider_attempts += 1
            total_attempts += 1
            try:
                with LLM_SEMAPHORE:
                    res = provider.generate(SYSTEM_PROMPT, user_prompt)
                provider_latency += res.latency_ms
                provider_model = res.model
            except LLMProviderError as exc:
                provider_error = exc.code
                last_error_code = exc.code
                breaker.record_failure()
                logger.warning(
                    "LLM provider attempt failed",
                    extra={
                        "event": "llm_attempt_failed",
                        "provider": provider.name,
                        "attempts": provider_attempts,
                        "error_code": exc.code.value,
                    },
                )
                if not exc.retryable or attempt >= (MAX_ATTEMPTS_PER_PROVIDER - 1):
                    break
                sleep_fn(_compute_sleep(attempt, exc.retry_after))
                continue

            # Output validation + single repair retry on same provider (architecture.md §16)
            valid, validation_reason = validate_llm_output(res.text, task_type)
            if valid:
                breaker.record_success()
                succeeded_result = LLMResult(
                    text=res.text.strip(),
                    model=res.model,
                    latency_ms=provider_latency,
                    provider=provider.name,
                )
                break

            logger.warning(
                "LLM output failed validation; attempting repair",
                extra={
                    "event": "llm_output_invalid",
                    "provider": provider.name,
                    "reason": validation_reason,
                },
            )

            # Repair retry once on the same provider
            provider_attempts += 1
            total_attempts += 1
            try:
                with LLM_SEMAPHORE:
                    repaired = provider.generate(SYSTEM_PROMPT, repair_prompt)
                provider_latency += repaired.latency_ms
                provider_model = repaired.model
                valid_repair, repair_reason = validate_llm_output(repaired.text, task_type)
                if valid_repair:
                    breaker.record_success()
                    succeeded_result = LLMResult(
                        text=repaired.text.strip(),
                        model=repaired.model,
                        latency_ms=provider_latency,
                        provider=provider.name,
                    )
                    break
                logger.warning(
                    "LLM repair output failed validation",
                    extra={
                        "event": "llm_repair_invalid",
                        "provider": provider.name,
                        "reason": repair_reason,
                    },
                )
                provider_error = ErrorCode.LLM_MALFORMED_RESPONSE
                last_error_code = ErrorCode.LLM_MALFORMED_RESPONSE
                breaker.record_failure()
                break
            except LLMProviderError as exc:
                provider_error = exc.code
                last_error_code = exc.code
                breaker.record_failure()
                break

        if succeeded_result is not None:
            history.append(
                ProviderAttemptSummary(
                    provider=provider.name,
                    model=provider_model,
                    attempts=provider_attempts,
                    latency_ms=provider_latency,
                    error_code=None,
                    succeeded=True,
                )
            )
            return RouterSuccess(
                result=succeeded_result,
                attempts_total=total_attempts,
                used_fallback=(idx > 0),
                history=history,
            )

        history.append(
            ProviderAttemptSummary(
                provider=provider.name,
                model=provider_model,
                attempts=provider_attempts,
                latency_ms=provider_latency,
                error_code=provider_error.value if provider_error else ErrorCode.LLM_UNAVAILABLE.value,
                succeeded=False,
            )
        )

    final_code = (
        last_error_code
        if last_error_code
        in {
            ErrorCode.LLM_TIMEOUT,
            ErrorCode.LLM_MALFORMED_RESPONSE,
            ErrorCode.LLM_AUTH_ERROR,
        }
        else ErrorCode.LLM_UNAVAILABLE
    )
    raise LLMRouterError(final_code, history)
