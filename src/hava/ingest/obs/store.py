"""Ham METAR raporlarını ayrıştırıp ``observations`` tablosuna yazar (AWC ve IEM ortak)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from hava.db.models import Observation, Station
from hava.ingest.obs.metar import MetarParseError, observation_values, parse_metar

log = structlog.get_logger()

_VALUE_COLS = [
    c.name
    for c in Observation.__table__.columns
    if c.name not in ("station_id", "observed_at", "qc_flags")
]
_MAX_PARAMS = 65535  # PostgreSQL'in sorgu başına bağlı parametre sınırı


@dataclass(frozen=True)
class RawReport:
    station: str  # ICAO
    observed_at: datetime  # kaynağın verdiği gerçek gözlem zamanı (UTC)
    text: str  # ham METAR
    source: str  # "awc" | "iem"


@dataclass
class StoreResult:
    received: int = 0
    written: int = 0
    unknown_station: int = 0
    parse_errors: int = 0


def metar_station_ids(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(Station.external_id, Station.id).where(
            Station.source == "metar", Station.active.is_(True)
        )
    )
    return {icao: sid for icao, sid in rows}


def store_reports(
    session: Session,
    reports: Iterable[RawReport],
    station_ids: dict[str, int],
    overwrite: bool,
) -> StoreResult:
    """Raporları yazar; QC bayrakları ayrı QC adımında hesaplanır.

    ``overwrite=True`` (AWC canlı): aynı zamanlı kayıt güncellenir (ör. COR düzeltmesi).
    ``overwrite=False`` (IEM geçmiş): var olan kayda dokunulmaz; boşluklar doldurulur.
    """
    result = StoreResult()
    rows: dict[tuple[int, datetime], dict[str, Any]] = {}
    for rep in reports:
        result.received += 1
        sid = station_ids.get(rep.station)
        if sid is None:
            result.unknown_station += 1
            continue
        try:
            metar = parse_metar(rep.text)
        except MetarParseError as exc:
            result.parse_errors += 1
            log.warning("metar_parse_error", station=rep.station, error=str(exc))
            continue
        values = observation_values(metar, rep.observed_at, rep.source)
        rows[(sid, rep.observed_at)] = {"station_id": sid, **values}  # aynı anahtarda son gelen
    batch = list(rows.values())
    size = _MAX_PARAMS // (len(_VALUE_COLS) + 2)
    for i in range(0, len(batch), size):
        stmt = insert(Observation).values(batch[i : i + size])
        if overwrite:
            stmt = stmt.on_conflict_do_update(
                constraint="pk_observations", set_={c: stmt.excluded[c] for c in _VALUE_COLS}
            )
        else:
            stmt = stmt.on_conflict_do_nothing(constraint="pk_observations")
        result.written += len(session.execute(stmt.returning(Observation.station_id)).all())
    return result
