"""IEM ASOS/METAR arşivinden geçmiş METAR (spec §5.3).

Kamu malı; atıf rica ediliyor. IP başına saniyede 1 istek. ``data=metar`` ile yalnız ham METAR ve
gözlem zamanı alınır (IEM'in çözdüğü değerler °F/mil ve eksik grupları dolduruyor; kullanılmaz).

Geçmiş yükleme: ``python -m hava.ingest.obs.iem --since 2024-01-01``
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from hava.db.session import session_scope
from hava.ingest.archive.http_range import get_with_retry
from hava.ingest.obs.store import RawReport, metar_station_ids, store_reports
from hava.ops.health import record_error, record_success
from hava.ops.logging import configure_logging
from hava.qc.observations import run_qc
from hava.settings import get_settings

log = structlog.get_logger()
SOURCE = "metar_iem"
MIN_INTERVAL_S = 1.1  # IEM: IP başına 1 istek/sn


def fetch_iem(
    client: httpx.Client, url: str, station: str, start: datetime, end: datetime
) -> list[RawReport]:
    """[start, end) aralığındaki rutin METAR'lar ve SPECI'ler."""
    params: dict[str, str | list[str]] = {
        "station": station,
        "data": "metar",
        "sts": start.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "ets": end.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "tz": "Etc/UTC",
        "format": "onlycomma",
        "latlon": "no",
        "elev": "no",
        "missing": "empty",
        "trace": "T",
        "direct": "no",
        "report_type": ["3", "4"],
    }
    resp = get_with_retry(client, url, attempts=4, params=params)
    reports = []
    for row in csv.DictReader(io.StringIO(resp.text)):
        if not row.get("metar"):
            continue
        observed = datetime.strptime(row["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
        reports.append(RawReport(row["station"], observed, row["metar"], "iem"))
    return reports


def month_windows(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    windows = []
    cur = start
    while cur < end:
        nxt = (cur.replace(day=1) + timedelta(days=32)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        windows.append((cur, min(nxt, end)))
        cur = nxt
    return windows


def backfill(
    client: httpx.Client,
    stations: Sequence[str],
    start: datetime,
    end: datetime,
    sleep: float = MIN_INTERVAL_S,
) -> dict[str, int]:
    """Aylık parçalarla yükler, var olan kayıtlara dokunmaz, sonra aralığa QC uygular."""
    settings = get_settings()
    totals = {"received": 0, "written": 0, "parse_errors": 0}
    with session_scope() as session:
        station_ids = metar_station_ids(session)
    for station in stations:
        for lo, hi in month_windows(start, end):
            reports = fetch_iem(client, settings.metar_iem_url, station, lo, hi)
            with session_scope() as session:
                res = store_reports(session, reports, station_ids, overwrite=False)
                session.commit()
            totals["received"] += res.received
            totals["written"] += res.written
            totals["parse_errors"] += res.parse_errors
            log.info(
                "iem_month_loaded",
                station=station,
                month=lo.strftime("%Y-%m"),
                received=res.received,
                written=res.written,
                parse_errors=res.parse_errors,
            )
            time.sleep(sleep)
    with session_scope() as session:
        qc = run_qc(session, start, end)
        session.commit()
    log.info("iem_backfill_qc", **qc)
    return totals


def fill_recent(days: int = 3) -> dict[str, int]:
    """Worker işi: son günlerdeki boşlukları IEM'den doldurur (AWC kesintilerine karşı)."""
    settings = get_settings()
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    try:
        with session_scope() as session:
            stations = sorted(metar_station_ids(session))
        with httpx.Client(timeout=60.0, headers={"User-Agent": settings.http_user_agent}) as c:
            totals = backfill(c, stations, start, end)
    except Exception as exc:
        with session_scope() as session:
            record_error(session, SOURCE, datetime.now(UTC), exc)
            session.commit()
        raise
    with session_scope() as session:
        record_success(session, SOURCE, datetime.now(UTC))
        session.commit()
    return totals


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="IEM'den geçmiş METAR yükler.")
    ap.add_argument("--since", required=True, help="YYYY-MM-DD (UTC, dahil)")
    ap.add_argument("--until", default=None, help="YYYY-MM-DD (UTC, hariç); varsayılan şimdi")
    ap.add_argument("--stations", default=None, help="ör. LTFM,LTFJ; varsayılan tüm METAR")
    args = ap.parse_args(argv)
    configure_logging()
    settings = get_settings()
    start = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=UTC)
    end = (
        datetime.strptime(args.until, "%Y-%m-%d").replace(tzinfo=UTC)
        if args.until
        else datetime.now(UTC)
    )
    with session_scope() as session:
        known = sorted(metar_station_ids(session))
    stations = args.stations.split(",") if args.stations else known
    with httpx.Client(timeout=120.0, headers={"User-Agent": settings.http_user_agent}) as client:
        totals = backfill(client, stations, start, end)
    log.info("iem_backfill_done", stations=stations, **totals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
