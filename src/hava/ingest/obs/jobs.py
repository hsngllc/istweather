"""Worker işleri: canlı METAR toplama (AWC) ve ardından QC."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import structlog

from hava.db.session import session_scope
from hava.ingest.obs.awc import fetch_awc
from hava.ingest.obs.store import metar_station_ids, store_reports
from hava.ops.health import record_error, record_success
from hava.qc.observations import run_qc
from hava.settings import get_settings

log = structlog.get_logger()
SOURCE = "metar_awc"


def collect_metar() -> dict[str, int]:
    """AWC'den son saatlerin METAR'larını alır, yazar (COR düzeltmeleri dahil), QC uygular."""
    settings = get_settings()
    now = datetime.now(UTC)
    with session_scope() as session:
        station_ids = metar_station_ids(session)
    try:
        with httpx.Client(timeout=30.0, headers={"User-Agent": settings.http_user_agent}) as client:
            reports = fetch_awc(
                client, settings.metar_awc_url, sorted(station_ids), settings.metar_awc_hours
            )
    except Exception as exc:
        with session_scope() as session:
            record_error(session, SOURCE, now, exc)
            session.commit()
        raise
    with session_scope() as session:
        res = store_reports(session, reports, station_ids, overwrite=True)
        qc = run_qc(session, now - timedelta(hours=settings.metar_awc_hours + 1), now)
        record_success(session, SOURCE, now)
        session.commit()
    summary = {
        "received": res.received,
        "written": res.written,
        "parse_errors": res.parse_errors,
        "unknown_station": res.unknown_station,
        "qc_updated": qc["updated"],
    }
    log.info("metar_collected", **summary)
    return summary
