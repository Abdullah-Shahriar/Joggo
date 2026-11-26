from collections import deque
from collections.abc import Callable
import threading
import time


class CircuitBreaker:
    """Per-provider circuit breaker: 5 consecutive failures in 60s -> open 30s -> half-open (1 trial)."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        failure_window_seconds: float = 60.0,
        recovery_timeout_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._failure_window = failure_window_seconds
        self._recovery_timeout = recovery_timeout_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._state: str = "closed"  # closed | open | half_open
        self._failure_times: deque[float] = deque()
        self._opened_at: float | None = None
        self._half_open_in_flight: bool = False

    @property
    def state(self) -> str:
        with self._lock:
            self._maybe_transition_to_half_open_locked(self._clock())
            return self._state

    def _maybe_transition_to_half_open_locked(self, now: float) -> None:
        if (
            self._state == "open"
            and self._opened_at is not None
            and (now - self._opened_at) >= self._recovery_timeout
        ):
            self._state = "half_open"
            self._half_open_in_flight = False

    def allow_request(self) -> bool:
        with self._lock:
            now = self._clock()
            self._maybe_transition_to_half_open_locked(now)
            if self._state == "closed":
                return True
            if self._state == "open":
                return False
            # half_open: allow a single trial call
            if not self._half_open_in_flight:
                self._half_open_in_flight = True
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._state = "closed"
            self._failure_times.clear()
            self._opened_at = None
            self._half_open_in_flight = False

    def record_failure(self) -> None:
        with self._lock:
            now = self._clock()
            if self._state == "half_open":
                self._state = "open"
                self._opened_at = now
                self._half_open_in_flight = False
                self._failure_times.clear()
                return

            cutoff = now - self._failure_window
            while self._failure_times and self._failure_times[0] < cutoff:
                self._failure_times.popleft()
            self._failure_times.append(now)

            if len(self._failure_times) >= self._failure_threshold:
                self._state = "open"
                self._opened_at = now
                self._half_open_in_flight = False

    def reset(self) -> None:
        with self._lock:
            self._state = "closed"
            self._failure_times.clear()
            self._opened_at = None
            self._half_open_in_flight = False
