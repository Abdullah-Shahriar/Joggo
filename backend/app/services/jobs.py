from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pipeline-worker")


def submit(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future[Any]:
    return _executor.submit(fn, *args, **kwargs)


def shutdown(wait: bool = False) -> None:
    _executor.shutdown(wait=wait)
