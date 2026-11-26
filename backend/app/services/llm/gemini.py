import time

import httpx

from app.config import get_settings
from app.errors import ErrorCode
from app.services.llm.base import DEFAULT_LLM_TIMEOUT, LLMProvider, LLMProviderError, LLMResult


def _parse_retry_after(header_val: str | None) -> float | None:
    if not header_val:
        return None
    try:
        parsed = float(header_val.strip())
        return max(0.0, min(parsed, 10.0))
    except ValueError:
        return None


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self._model = model if model is not None else settings.GEMINI_MODEL

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
                "Gemini provider is not configured.",
                retryable=False,
            )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2000,
            },
        }
        start = time.perf_counter()

        try:
            with httpx.Client(timeout=timeout or DEFAULT_LLM_TIMEOUT) as client:
                resp = client.post(
                    url,
                    json=payload,
                    headers={"x-goog-api-key": self._api_key},
                )
        except httpx.TimeoutException as exc:
            raise LLMProviderError(
                ErrorCode.LLM_TIMEOUT,
                "Gemini request timed out.",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise LLMProviderError(
                ErrorCode.LLM_UNAVAILABLE,
                "Gemini connection failed.",
                retryable=True,
            ) from exc

        latency_ms = int((time.perf_counter() - start) * 1000)

        if resp.status_code in {400, 401, 403}:
            raise LLMProviderError(
                ErrorCode.LLM_AUTH_ERROR,
                "Gemini authentication or request rejected.",
                retryable=False,
            )
        if resp.status_code == 429:
            raise LLMProviderError(
                ErrorCode.LLM_UNAVAILABLE,
                "Gemini rate limited.",
                retryable=True,
                retry_after=_parse_retry_after(resp.headers.get("retry-after")),
            )
        if resp.status_code >= 500:
            raise LLMProviderError(
                ErrorCode.LLM_UNAVAILABLE,
                "Gemini server error.",
                retryable=True,
            )
        if resp.status_code >= 400:
            raise LLMProviderError(
                ErrorCode.LLM_UNAVAILABLE,
                "Gemini returned an error response.",
                retryable=False,
            )

        try:
            data = resp.json()
            candidates = data.get("candidates") or []
            parts = candidates[0]["content"]["parts"]
            text = "".join(str(p.get("text", "")) for p in parts)
        except Exception as exc:
            raise LLMProviderError(
                ErrorCode.LLM_MALFORMED_RESPONSE,
                "Malformed response payload from Gemini.",
                retryable=False,
            ) from exc

        return LLMResult(text=text, model=self._model, latency_ms=latency_ms, provider=self.name)
