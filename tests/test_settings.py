import pytest
from sqlalchemy.engine import URL

from hava.settings import Settings


def test_url_built_from_postgres_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAVA_DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_DB", "havadb")
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "örnek-şifre")
    monkeypatch.setenv("HAVA_DB_HOST", "db")
    url = Settings(_env_file=None).sqlalchemy_url  # type: ignore[call-arg]
    assert isinstance(url, URL)
    assert (url.drivername, url.host, url.database, url.username) == (
        "postgresql+psycopg",
        "db",
        "havadb",
        "u",
    )
    assert url.password == "örnek-şifre"


def test_database_url_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAVA_DATABASE_URL", "postgresql+psycopg://a:b@h:1/d")
    assert Settings(_env_file=None).sqlalchemy_url == "postgresql+psycopg://a:b@h:1/d"  # type: ignore[call-arg]


def test_cors_origins_split(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAVA_CORS_ORIGINS", "https://a.example, https://b.example")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.cors_origin_list == ["https://a.example", "https://b.example"]
