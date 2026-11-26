from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
import threading
from typing import Any

from app.config import get_settings

_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None


def get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is not None:
        return _executor
    with _lock:
        if _executor is not None:
            return _executor
        workers = get_settings().effective_pipeline_max_workers
        _executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pipeline-worker")
        return _executor


def submit(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future[Any]:
    return get_executor().submit(fn, *args, **kwargs)
