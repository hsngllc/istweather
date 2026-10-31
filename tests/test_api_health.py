from collections.abc import Iterator
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from hava.api.app import create_app
from hava.db.session import get_session


class _Result:
    def scalars(self) -> list[Any]:
        return []


class _HealthySession:
    def execute(self, *_: Any, **__: Any) -> _Result:
        return _Result()


class _BrokenSession:
    def execute(self, *_: Any, **__: Any) -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))


def _client(session: object) -> TestClient:
    app = create_app()

    def override() -> Iterator[object]:
        yield session

    app.dependency_overrides[get_session] = override
    return TestClient(app)


def test_health_ok_when_database_reachable() -> None:
    resp = _client(_HealthySession()).get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == {"ok": True}
    assert body["time"]["local"].endswith("+03:00")


def test_health_503_when_database_down() -> None:
    resp = _client(_BrokenSession()).get("/api/v1/health")
    assert resp.status_code == 503
    assert resp.json()["status"] == "degraded"


def test_openapi_is_served_under_v1() -> None:
    resp = _client(_HealthySession()).get("/api/v1/openapi.json")
    assert resp.status_code == 200
    assert "/api/v1/health" in resp.json()["paths"]
