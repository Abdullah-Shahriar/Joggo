from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.ratelimit import reset_rate_limits

CSRF_HEADERS: dict[str, str] = {
    "X-Requested-With": "fetch",
    "Origin": "http://localhost:3000",
}


@pytest.fixture(autouse=True)
def _reset_limiter() -> Iterator[None]:
    reset_rate_limits()
    yield
    reset_rate_limits()


@pytest.fixture()
def app() -> FastAPI:
    return create_app()


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
