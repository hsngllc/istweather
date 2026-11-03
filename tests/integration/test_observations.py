"""Gözlem zinciri: METAR yazma (AWC/IEM), QC ve kaynak tazeliği — gerçek TimescaleDB'de."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from hava.db.models import Observation, SourceHealth
from hava.db.session import session_scope
from hava.ingest.obs.store import RawReport, metar_station_ids, store_reports
from hava.ops.health import evaluate, record_error, record_success
from hava.qc.observations import QC_VERSION, run_qc
from hava.settings import Settings, get_settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("HAVA_DATABASE_URL"), reason="HAVA_DATABASE_URL tanımlı değil"
    ),
]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "metar"


@pytest.fixture
def clean(seeded: str) -> None:
    with session_scope() as session:
        session.execute(delete(Observation))
        session.execute(delete(SourceHealth).where(SourceHealth.source.like("metar%")))
        session.commit()


def _awc_reports() -> list[RawReport]:
    records = json.loads((FIXTURES / "awc_metar_2026-11-02.json").read_text(encoding="utf-8"))
    return [
        RawReport(r["icaoId"], datetime.fromtimestamp(r["obsTime"], UTC), r["rawOb"], "awc")
        for r in records
    ]


def _synthetic(icao: str, at: datetime, temp: str = "15/10") -> RawReport:
    """Sentetik METAR (zaman grubu ``at`` ile tutarlı)."""
    return RawReport(icao, at, f"{icao} {at:%d%H%M}Z 18005KT 9999 FEW030 {temp} Q1015", "awc")


def test_store_awc_then_iem_keeps_existing_rows(clean: None) -> None:
    reports = _awc_reports()
    with session_scope() as session:
        ids = metar_station_ids(session)
        first = store_reports(session, reports, ids, overwrite=True)
        again = store_reports(session, reports, ids, overwrite=True)
        iem_copy = [RawReport(r.station, r.observed_at, r.text, "iem") for r in reports]
        iem = store_reports(session, iem_copy, ids, overwrite=False)
        session.commit()
        rows = session.execute(select(Observation)).scalars().all()
    assert (first.written, again.written, iem.written) == (33, 33, 0)
    assert first.parse_errors == 0 and first.unknown_station == 0
    assert len(rows) == 33 and {r.raw["source"] for r in rows if r.raw} == {"awc"}
    ltfj = next(r for r in rows if r.raw and r.raw["metar"].startswith("METAR LTFJ 020520Z"))
    assert (ltfj.temp_c, ltfj.dewpoint_c, ltfj.visibility_m) == (15, 14, 4100)
    assert ltfj.wind_dir_deg is None and ltfj.raw["wind_variable"] is True


def test_qc_marks_every_row_and_flags_errors(clean: None) -> None:
    t0 = datetime(2026, 1, 10, 0, 20, tzinfo=UTC)
    reports = [_synthetic("LTFM", t0 + i * timedelta(minutes=30)) for i in range(5)]
    reports[2] = _synthetic("LTFM", t0 + 2 * timedelta(minutes=30), temp="15/18")  # Td > T
    with session_scope() as session:
        store_reports(session, reports, metar_station_ids(session), overwrite=True)
        stats = run_qc(session, t0, t0 + timedelta(hours=3))
        again = run_qc(session, t0, t0 + timedelta(hours=3))
        session.commit()
        flags = dict(session.execute(select(Observation.observed_at, Observation.qc_flags)).all())
    assert stats == {"checked": 5, "updated": 5, "flagged": 1}
    assert again["updated"] == 0  # değişmeyen bayrak yeniden yazılmaz
    assert all(f["version"] == QC_VERSION for f in flags.values())
    assert flags[t0 + timedelta(hours=1)]["dewpoint_c"] == ["dewpoint_gt_temp"]


def _metar_transitions(session: Session, now: datetime, settings: Settings) -> dict[str, bool]:
    """Yalnız gözlem kaynakları (model tazeliği ``test_model_runs``'ta)."""
    return {
        t.source: t.stale for t in evaluate(session, now, settings) if t.source.startswith("metar")
    }


def test_freshness_transitions(clean: None) -> None:
    settings = get_settings()
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    recent = now - timedelta(minutes=10)
    with session_scope() as session:
        ids = metar_station_ids(session)
        store_reports(session, [_synthetic("LTFM", recent)], ids, overwrite=True)
        record_success(session, "metar_awc", now)
        first = _metar_transitions(session, now, settings)
        session.commit()
    # LTFM taze; diğer iki istasyonda veri yok → bozuk olarak bildirilir.
    assert first == {"metar:LTFJ": True, "metar:LTBA": True}

    later = now + timedelta(minutes=settings.metar_stale_minutes + 5)
    with session_scope() as session:
        record_error(session, "metar_awc", later, "ConnectError: test")
        second = _metar_transitions(session, later, settings)
        session.commit()
        awc = session.get(SourceHealth, "metar_awc")
        assert awc is not None and awc.stale and awc.last_error == "ConnectError: test"
    assert second == {"metar:LTFM": True, "metar_awc": True}  # tekrar bildirim yok

    with session_scope() as session:
        store_reports(session, [_synthetic("LTFM", later)], ids, overwrite=True)
        record_success(session, "metar_awc", later)
        third = _metar_transitions(session, later, settings)
        session.commit()
    assert third == {"metar:LTFM": False, "metar_awc": False}
