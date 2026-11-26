import logging
import time

import httpx

from app.config import get_settings
from app.errors import ErrorCode
from app.services.llm.base import DEFAULT_LLM_TIMEOUT, LLMProvider, LLMProviderError, LLMResult

logger = logging.getLogger("app.llm.gemini")

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def _resolve_model(explicit_model: str | None, configured_model: str, default_model: str) -> str:
    if explicit_model is not None:
        return explicit_model.strip()
    cleaned = (configured_model or "").strip()
    if not cleaned or cleaned.startswith("<"):
        return default_model
    return cleaned


def _parse_retry_after(header_val: str | None) -> float | None:
    if not header_val:
        return None
    try:
        parsed = float(header_val.strip())
        return max(0.0, min(parsed, 10.0))
    except ValueError:
        return None


def _extract_provider_error_hint(resp: httpx.Response) -> str:
    """Extract only safe provider API error code/message (never document text or keys)."""
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            status = str(err.get("status") or err.get("code") or "").strip()
            msg = str(err.get("message") or "").strip()
            combined = f"{status}: {msg}" if status and msg else (msg or status)
            if combined:
                return combined[:160]
    except Exception:
        pass
    return f"HTTP {resp.status_code}"


def _is_model_unavailable_error(status_code: int, hint: str) -> bool:
    if status_code == 404:
        return True
    if status_code == 400:
        low = hint.lower()
        return any(
            kw in low
            for kw in (
                "not found",
                "not supported",
                "decommissioned",
                "deprecated",
                "unknown model",
                "invalid model",
                "does not exist",
            )
        )
    return False


def _pick_best_gemini_model(models_payload: dict, exclude: set[str]) -> str | None:
    models = models_payload.get("models") if isinstance(models_payload, dict) else None
    if not isinstance(models, list):
        return None
    candidates: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        methods = item.get("supportedGenerationMethods") or []
        if "generateContent" not in methods:
            continue
        raw_name = str(item.get("name") or "")
        model_id = raw_name.removeprefix("models/").strip()
        if not model_id or model_id in exclude:
            continue
        low = model_id.lower()
        if not low.startswith("gemini"):
            continue
        if any(skip in low for skip in ("embedding", "aqa", "imagen", "veo", "tts", "audio", "robotics", "computer-use")):
            continue
        candidates.append(model_id)

    if not candidates:
        return None

    def _rank(mid: str) -> tuple[int, int, str]:
        low = mid.lower()
        is_flash = 0 if "flash" in low else 1
        is_preview = 1 if any(tag in low for tag in ("exp", "preview", "thinking")) else 0
        # Prefer newer version numbers by sorting descending on version string inside same tier
        return (is_flash, is_preview, mid)

    # Prefer stable flash models (newest first), then preview flash, then other gemini text models
    stable_flash = [c for c in candidates if "flash" in c.lower() and not any(t in c.lower() for t in ("exp", "preview", "lite"))]
    if stable_flash:
        return sorted(stable_flash, reverse=True)[0]
    any_flash = [c for c in candidates if "flash" in c.lower()]
    if any_flash:
        return sorted(any_flash, reverse=True)[0]
    return sorted(candidates, key=_rank)[0]


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._api_key = (api_key if api_key is not None else settings.GEMINI_API_KEY).strip()
        self._model = _resolve_model(model, settings.GEMINI_MODEL, DEFAULT_GEMINI_MODEL)

    def _discover_fallback_model(
        self,
        client: httpx.Client,
        *,
        exclude: set[str],
    ) -> str | None:
        try:
            resp = client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": self._api_key},
            )
            if resp.status_code != 200:
                return None
            return _pick_best_gemini_model(resp.json(), exclude)
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
                "Gemini provider is not configured.",
                retryable=False,
            )

        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 4096,
            },
        }
        start = time.perf_counter()
        tried_models: set[str] = set()
        active_model = self._model

        try:
            with httpx.Client(timeout=timeout or DEFAULT_LLM_TIMEOUT) as client:
                while True:
                    tried_models.add(active_model)
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{active_model}:generateContent"
                    resp = client.post(
                        url,
                        json=payload,
                        headers={"x-goog-api-key": self._api_key},
                    )
                    if resp.status_code < 400:
                        self._model = active_model
                        break

                    hint = _extract_provider_error_hint(resp)
                    if len(tried_models) == 1 and _is_model_unavailable_error(resp.status_code, hint):
                        discovered = self._discover_fallback_model(client, exclude=tried_models)
                        if discovered:
                            logger.warning(
                                "Gemini model unavailable; auto-switching to discovered model",
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

        if resp.status_code >= 400:
            hint = _extract_provider_error_hint(resp)
            logger.warning(
                "Gemini API returned error status",
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
                    f"Gemini ({active_model}) HTTP {resp.status_code}: {hint}",
                    retryable=False,
                )
            if resp.status_code == 429:
                raise LLMProviderError(
                    ErrorCode.LLM_UNAVAILABLE,
                    f"Gemini ({active_model}) rate limited (HTTP 429): {hint}",
                    retryable=True,
                    retry_after=_parse_retry_after(resp.headers.get("retry-after")),
                )
            if resp.status_code >= 500:
                raise LLMProviderError(
                    ErrorCode.LLM_UNAVAILABLE,
                    f"Gemini ({active_model}) server error (HTTP {resp.status_code}).",
                    retryable=True,
                )
            raise LLMProviderError(
                ErrorCode.LLM_UNAVAILABLE,
                f"Gemini ({active_model}) HTTP {resp.status_code}: {hint}",
                retryable=False,
            )

        try:
            data = resp.json()
            candidates = data.get("candidates") or []
            parts = candidates[0]["content"]["parts"]
            text = "".join(str(p.get("text", "")) for p in parts if not p.get("thought"))
        except Exception as exc:
            raise LLMProviderError(
                ErrorCode.LLM_MALFORMED_RESPONSE,
                "Malformed response payload from Gemini.",
                retryable=False,
            ) from exc

        return LLMResult(text=text, model=active_model, latency_ms=latency_ms, provider=self.name)
