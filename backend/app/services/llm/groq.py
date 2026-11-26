import logging
import time

import httpx

from app.config import get_settings
from app.errors import ErrorCode
from app.services.llm.base import DEFAULT_LLM_TIMEOUT, LLMProvider, LLMProviderError, LLMResult
from app.services.llm.gemini import _parse_retry_after, _resolve_model

logger = logging.getLogger("app.llm.groq")

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._api_key = (api_key if api_key is not None else settings.GROQ_API_KEY).strip()
        self._model = _resolve_model(model, settings.GROQ_MODEL, DEFAULT_GROQ_MODEL)

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
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": 3000,
        }
        start = time.perf_counter()

        try:
            with httpx.Client(timeout=timeout or DEFAULT_LLM_TIMEOUT) as client:
                resp = client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
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
            logger.warning(
                "Groq API returned error status",
                extra={
                    "event": "llm_provider_http_error",
                    "provider": self.name,
                    "model": self._model,
                    "status_code": resp.status_code,
                },
            )

        if resp.status_code in {400, 401, 403}:
            raise LLMProviderError(
                ErrorCode.LLM_AUTH_ERROR,
                "Groq authentication or request rejected.",
                retryable=False,
            )
        if resp.status_code == 429:
            raise LLMProviderError(
                ErrorCode.LLM_UNAVAILABLE,
                "Groq rate limited.",
                retryable=True,
                retry_after=_parse_retry_after(resp.headers.get("retry-after")),
            )
        if resp.status_code >= 500:
            raise LLMProviderError(
                ErrorCode.LLM_UNAVAILABLE,
                "Groq server error.",
                retryable=True,
            )
        if resp.status_code >= 400:
            raise LLMProviderError(
                ErrorCode.LLM_UNAVAILABLE,
                "Groq returned an error response.",
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

        return LLMResult(text=text, model=self._model, latency_ms=latency_ms, provider=self.name)
