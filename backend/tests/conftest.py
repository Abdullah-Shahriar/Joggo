from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.config import get_settings
from app.main import create_app
from app.ratelimit import reset_rate_limits
from app.services.vault import vault

CSRF_HEADERS: dict[str, str] = {
    "X-Requested-With": "fetch",
    "Origin": "http://localhost:3000",
}


@pytest.fixture(autouse=True)
def _test_isolation(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(get_settings(), "ENV", "test")
    reset_rate_limits()
    yield
    reset_rate_limits()
    vault.clear_all_for_tests()


@pytest.fixture()
def app() -> FastAPI:
    return create_app()


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
