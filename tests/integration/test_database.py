"""Veritabanı entegrasyon testleri: TimescaleDB gerektirir (CI'da servis konteyneri).

``HAVA_DATABASE_URL`` tanımlı değilse atlanır. Testler boş bir veritabanı varsayar.
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("HAVA_DATABASE_URL"), reason="HAVA_DATABASE_URL tanımlı değil"
    ),
]

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def migrated() -> str:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")
    command.check(cfg)  # modeller ile migration arasında fark yok
    return os.environ["HAVA_DATABASE_URL"]


def test_hypertables_and_compression(migrated: str) -> None:
    engine = create_engine(migrated)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT hypertable_name, compression_enabled"
                " FROM timescaledb_information.hypertables ORDER BY 1"
            )
        ).all()
    assert [(r[0], r[1]) for r in rows] == [
        ("ensemble_stats", True),
        ("observations", True),
        ("point_forecasts", True),
        ("published_forecasts", True),
    ]


def test_seed_is_idempotent(migrated: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from hava.db.seed import seed_models, seed_region
    from hava.db.session import session_scope

    monkeypatch.chdir(ROOT)
    for _ in range(2):
        with session_scope() as session:
            counts = seed_region(session, "config/region.istanbul.yaml")
            n_models = seed_models(session, "config/models.yaml")
            session.commit()
    engine = create_engine(migrated)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM districts")).scalar_one() == 39
        assert conn.execute(text("SELECT count(*) FROM points")).scalar_one() == counts["points"]
        assert conn.execute(text("SELECT count(*) FROM models")).scalar_one() == n_models
        internal = conn.execute(
            text("SELECT internal_only FROM models WHERE code = 'ukmo_global_10km'")
        ).scalar_one()
        assert internal is True


def test_heartbeat_and_health(migrated: str) -> None:
    from hava.api.app import create_app
    from hava.scheduler.__main__ import heartbeat

    heartbeat()
    resp = TestClient(create_app()).get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["database"]["ok"] is True
    assert [s["source"] for s in body["sources"]] == ["worker"]
