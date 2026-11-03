"""Model hattının veritabanı tarafı: ``model_runs`` durumu, nokta tahmini yazma, model tazeliği."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select

from hava.db.models import ModelRun, PointForecast, SourceHealth
from hava.db.models import Point as PointRow
from hava.db.session import session_scope
from hava.ingest.models.pipeline import store_rows
from hava.ingest.models.runs import get_run, model_id, set_status, should_process
from hava.ops.health import evaluate, record_success
from hava.settings import get_settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("HAVA_DATABASE_URL"), reason="HAVA_DATABASE_URL tanımlı değil"
    ),
]
MODEL = "ecmwf_ifs"  # config/models.yaml'da stale_hours: 18


@pytest.fixture
def mid(seeded: str) -> int:
    with session_scope() as session:
        session.execute(delete(PointForecast))
        session.execute(delete(ModelRun))
        session.execute(delete(SourceHealth).where(SourceHealth.source.like("model:%")))
        session.execute(delete(SourceHealth).where(SourceHealth.source.like("collector:%")))
        session.commit()
        return model_id(session, MODEL)


def _rows(keys: list[str], init: datetime, temp: float) -> list[dict[str, object]]:
    """Sentetik nokta satırları (``extract_rows`` çıktısıyla aynı biçim)."""
    return [
        {
            "point_id": key,
            "valid_time": init + timedelta(hours=h),
            "lead_h": float(h),
            "temp_c": temp,
            "extraction": "bilinear_lsm_lapse",
            "extra": {"point_method": "lsm_bilinear"},
        }
        for key in keys
        for h in (0, 3)
    ]


def test_run_status_and_idempotent_store(mid: int) -> None:
    init = datetime(2026, 11, 2, 6, tzinfo=UTC)
    with session_scope() as session:
        keys = list(session.execute(select(PointRow.point_key).limit(2)).scalars())
        set_status(session, mid, init, "downloading", files={"attempts": 1})
        first = store_rows(session, mid, init, _rows([*keys, "district:yok:0"], init, 10.0))
        again = store_rows(session, mid, init, _rows(keys, init, 11.0))
        set_status(session, mid, init, "loaded", files={"rows": again})
        session.commit()
        run = get_run(session, mid, init)
        temps = set(session.execute(select(PointForecast.temp_c)).scalars())
        count = session.execute(select(func.count()).select_from(PointForecast)).scalar_one()
    assert (first, again, count) == (4, 4, 4)  # bilinmeyen nokta atlanır, tekrar yazım günceller
    assert temps == {11.0}
    assert run is not None and run.status == "loaded" and run.completed_at is not None
    assert run.files == {"attempts": 1, "rows": 4}
    assert not should_process(run)


def test_failed_run_retried_until_limit(mid: int) -> None:
    init = datetime(2026, 11, 2, 12, tzinfo=UTC)
    with session_scope() as session:
        for attempt in (1, 2, 3):
            assert should_process(get_run(session, mid, init))
            set_status(session, mid, init, "failed", files={"attempts": attempt}, error="503")
            session.flush()
        session.commit()
        assert not should_process(get_run(session, mid, init))


def test_model_freshness(mid: int) -> None:
    settings = get_settings()
    now = datetime.now(UTC).replace(second=0, microsecond=0)

    def model_transitions(at: datetime) -> dict[str, bool]:
        with session_scope() as session:
            out = {t.source: t.stale for t in evaluate(session, at, settings)}
            session.commit()
        return {k: v for k, v in out.items() if k == f"model:{MODEL}"}

    # Yeni model: toplayıcı ilk turunu bitirmeden bildirim yok.
    assert model_transitions(now) == {}
    # Toplayıcı turunu bitirdi ama hiç yüklenmiş çalıştırma yok → bayat (METAR'daki "veri yok").
    with session_scope() as session:
        record_success(session, f"collector:{MODEL}", now)
        session.commit()
    assert model_transitions(now) == {f"model:{MODEL}": True}
    with session_scope() as session:
        set_status(session, mid, now - timedelta(hours=8), "loaded")
        session.commit()
    assert model_transitions(now) == {f"model:{MODEL}": False}
    assert model_transitions(now + timedelta(hours=5)) == {}  # değişiklik yok, tekrar bildirim yok
    assert model_transitions(now + timedelta(hours=11)) == {f"model:{MODEL}": True}
