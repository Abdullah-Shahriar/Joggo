from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.errors import ErrorCode

DEFAULT_LLM_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    latency_ms: int
    provider: str = ""


class LLMProviderError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.retry_after = retry_after


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def generate(
        self,
        system: str,
        user: str,
        *,
        timeout: httpx.Timeout | None = None,
    ) -> LLMResult:
        raise NotImplementedError
