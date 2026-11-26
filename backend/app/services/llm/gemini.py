import logging
import re
import time

import httpx

from app.config import get_settings
from app.errors import ErrorCode
from app.services.llm.base import DEFAULT_LLM_TIMEOUT, LLMProvider, LLMProviderError, LLMResult

logger = logging.getLogger("app.llm.gemini")

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

PREFERRED_GEMINI_MODELS: tuple[str, ...] = (
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
)

_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_GEMINI_VERSION_RE = re.compile(r"gemini-(\d+)(?:\.(\d+))?")
_GEMINI_SKIP_SUBSTRINGS: tuple[str, ...] = (
    "embedding",
    "aqa",
    "imagen",
    "image",
    "veo",
    "tts",
    "audio",
    "robotics",
    "computer-use",
    "live",
    "vision",
    "learnlm",
    "gemma",
    "native",
    "dialog",
    "customtools",
)


def _resolve_model(
    explicit_model: str | None,
    configured_model: str,
    default_model: str,
    *,
    require_prefix: str | None = None,
) -> str:
    if explicit_model is not None:
        cleaned_explicit = explicit_model.strip().strip("\"'").removeprefix("models/").strip()
        return cleaned_explicit or default_model
    cleaned = (configured_model or "").strip().strip("\"'").removeprefix("models/").strip()
    if not cleaned or cleaned.startswith("<") or not _MODEL_ID_RE.match(cleaned):
        return default_model
    if require_prefix and not cleaned.lower().startswith(require_prefix.lower()):
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
        if not low.startswith("gemini-"):
            continue
        if any(skip in low for skip in _GEMINI_SKIP_SUBSTRINGS):
            continue
        candidates.append(model_id)

    if not candidates:
        return None

    # Prefer known stable text-generation Gemini Flash models first
    for preferred in PREFERRED_GEMINI_MODELS:
        if preferred in candidates:
            return preferred

    def _score(mid: str) -> tuple[int, int, int, int, int]:
        low = mid.lower()
        is_flash = 1 if "flash" in low else 0
        is_stable = 0 if any(t in low for t in ("exp", "preview", "thinking", "latest")) else 1
        is_not_lite = 0 if "lite" in low else 1
        vm = _GEMINI_VERSION_RE.search(low)
        major = int(vm.group(1)) if vm else 0
        minor = int(vm.group(2) or 0) if vm else 0
        return (is_flash, is_stable, major, minor, is_not_lite)

    return max(candidates, key=_score)


def _build_gemini_payload(system: str, user: str, model_id: str) -> dict:
    gen_config: dict = {
        "temperature": 0.2,
        "maxOutputTokens": 4096,
    }
    # Gemini 2.5 Flash enables dynamic thinking by default, which can consume maxOutputTokens
    # or extend latency on clinical drafts. Disable thinking budget on 2.5 Flash models per v1beta docs.
    low_model = model_id.lower()
    if "2.5" in low_model and "flash" in low_model:
        gen_config["thinkingConfig"] = {"thinkingBudget": 0}

    return {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": gen_config,
    }


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._api_key = (api_key if api_key is not None else settings.GEMINI_API_KEY).strip()
        self._model = _resolve_model(
            model,
            settings.GEMINI_MODEL,
            DEFAULT_GEMINI_MODEL,
            require_prefix="gemini-",
        )

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

        start = time.perf_counter()
        tried_models: set[str] = set()
        active_model = self._model

        try:
            with httpx.Client(timeout=timeout or DEFAULT_LLM_TIMEOUT) as client:
                while True:
                    tried_models.add(active_model)
                    payload = _build_gemini_payload(system, user, active_model)
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
            if not candidates:
                raise ValueError("No candidates in Gemini response")
            content = candidates[0].get("content") or {}
            parts = content.get("parts") or []
            text = "".join(str(p.get("text", "")) for p in parts if not p.get("thought"))
            if not text.strip():
                raise ValueError("Empty non-thought text in Gemini response")
        except Exception as exc:
            raise LLMProviderError(
                ErrorCode.LLM_MALFORMED_RESPONSE,
                "Malformed response payload from Gemini.",
                retryable=False,
            ) from exc

        return LLMResult(text=text, model=active_model, latency_ms=latency_ms, provider=self.name)
