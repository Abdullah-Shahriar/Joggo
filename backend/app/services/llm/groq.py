import logging
import time

import httpx

from app.config import get_settings
from app.errors import ErrorCode
from app.services.llm.base import DEFAULT_LLM_TIMEOUT, LLMProvider, LLMProviderError, LLMResult
from app.services.llm.gemini import (
    _extract_provider_error_hint,
    _is_model_unavailable_error,
    _parse_retry_after,
    _resolve_model,
)

logger = logging.getLogger("app.llm.groq")

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
PREFERRED_GROQ_MODELS: tuple[str, ...] = (
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-20b",
)


def _pick_best_groq_model(models_payload: dict, exclude: set[str]) -> str | None:
    items = models_payload.get("data") if isinstance(models_payload, dict) else None
    if not isinstance(items, list):
        return None
    available: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("active") is False:
            continue
        mid = str(item.get("id") or "").strip()
        if not mid or mid in exclude:
            continue
        low = mid.lower()
        if any(skip in low for skip in ("whisper", "guard", "tts", "safeguard", "embedding", "orpheus")):
            continue
        available.append(mid)

    if not available:
        return None
    for preferred in PREFERRED_GROQ_MODELS:
        if preferred in available:
            return preferred
    return available[0]


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._api_key = (api_key if api_key is not None else settings.GROQ_API_KEY).strip()
        self._model = _resolve_model(model, settings.GROQ_MODEL, DEFAULT_GROQ_MODEL)

    def _discover_fallback_model(
        self,
        client: httpx.Client,
        *,
        exclude: set[str],
    ) -> str | None:
        try:
            resp = client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            if resp.status_code != 200:
                return None
            return _pick_best_groq_model(resp.json(), exclude)
        except Exception:
            return None

    def generate(
        self,
        system: str,
        user: str,
        *,
        timeout: httpx.Timeout | None = None,
    ) -> LLMResult:
        if not self._api_key or not self._model:
            raise LLMProviderError(
                ErrorCode.LLM_AUTH_ERROR,
                "Groq provider is not configured.",
                retryable=False,
            )

        url = "https://api.groq.com/openai/v1/chat/completions"
        start = time.perf_counter()
        tried_models: set[str] = set()
        active_model = self._model

        try:
            with httpx.Client(timeout=timeout or DEFAULT_LLM_TIMEOUT) as client:
                while True:
                    tried_models.add(active_model)
                    payload = {
                        "model": active_model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "temperature": 0.2,
                        "max_tokens": 3000,
                    }
                    resp = client.post(
                        url,
                        json=payload,
                        headers={"Authorization": f"Bearer {self._api_key}"},
                    )
                    if resp.status_code < 400:
                        self._model = active_model
                        break

                    hint = _extract_provider_error_hint(resp)
                    if len(tried_models) == 1 and _is_model_unavailable_error(resp.status_code, hint):
                        discovered = self._discover_fallback_model(client, exclude=tried_models)
                        if discovered:
                            logger.warning(
                                "Groq model unavailable; auto-switching to discovered model",
                                extra={
                                    "event": "llm_model_autofallback",
                                    "provider": self.name,
                                    "failed_model": active_model,
                                    "fallback_model": discovered,
                                },
                            )
                            active_model = discovered
                            continue
                    break
        except httpx.TimeoutException as exc:
            raise LLMProviderError(
                ErrorCode.LLM_TIMEOUT,
                "Groq request timed out.",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise LLMProviderError(
                ErrorCode.LLM_UNAVAILABLE,
                "Groq connection failed.",
                retryable=True,
            ) from exc

        latency_ms = int((time.perf_counter() - start) * 1000)

        if resp.status_code >= 400:
            hint = _extract_provider_error_hint(resp)
            logger.warning(
                "Groq API returned error status",
                extra={
                    "event": "llm_provider_http_error",
                    "provider": self.name,
                    "model": active_model,
                    "status_code": resp.status_code,
                    "detail": hint,
                },
            )
            if resp.status_code in {400, 401, 403}:
                raise LLMProviderError(
                    ErrorCode.LLM_AUTH_ERROR,
                    f"Groq ({active_model}) HTTP {resp.status_code}: {hint}",
                    retryable=False,
                )
            if resp.status_code == 429:
                raise LLMProviderError(
                    ErrorCode.LLM_UNAVAILABLE,
                    f"Groq ({active_model}) rate limited (HTTP 429): {hint}",
                    retryable=True,
                    retry_after=_parse_retry_after(resp.headers.get("retry-after")),
                )
            if resp.status_code >= 500:
                raise LLMProviderError(
                    ErrorCode.LLM_UNAVAILABLE,
                    f"Groq ({active_model}) server error (HTTP {resp.status_code}).",
                    retryable=True,
                )
            raise LLMProviderError(
                ErrorCode.LLM_UNAVAILABLE,
                f"Groq ({active_model}) HTTP {resp.status_code}: {hint}",
                retryable=False,
            )

        try:
            data = resp.json()
            text = str(data["choices"][0]["message"]["content"])
        except Exception as exc:
            raise LLMProviderError(
                ErrorCode.LLM_MALFORMED_RESPONSE,
                "Malformed response payload from Groq.",
                retryable=False,
            ) from exc

        return LLMResult(text=text, model=active_model, latency_ms=latency_ms, provider=self.name)
