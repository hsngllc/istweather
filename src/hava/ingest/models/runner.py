"""Bir model çalıştırmasını uçtan uca işler (tüm adaptörler için ortak).

``model_runs`` durumu: downloading → extracted → loaded | failed (spec §4). Adaptör yalnız
kaynağından alanları toplayan bir işlev verir; kırpılmış dosya, nokta satırları ve durum burada.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from hava.db.session import session_scope
from hava.ingest.archive.http_range import RemoteFileGone
from hava.ingest.models import runs
from hava.ingest.models.ensemble import (
    EnsembleCollector,
    extract_members,
    member_stats,
    store_stats,
    write_members,
)
from hava.ingest.models.ensemble import write_crop as write_ensemble_crop
from hava.ingest.models.pipeline import (
    ModelSpec,
    RunCollector,
    extract_rows,
    store_rows,
    write_netcdf,
)
from hava.region import Region
from hava.settings import Settings

log = structlog.get_logger()

Collect = Callable[[], tuple[RunCollector, dict[str, Any]]]
# Bu kadar yeni bir çalıştırmada eksik dosya "henüz yayımlanmadı" sayılır, hata değil.
NOT_YET_PUBLISHED = timedelta(hours=12)
EnsembleCollect = Callable[[], tuple[EnsembleCollector, dict[str, Any]]]


@dataclass(frozen=True)
class Source:
    spec: ModelSpec
    extractor: str  # çıkarıcı sürümü (izlenebilirlik)
    source: str  # kaynak adresi
    resolution: str
    license: str


def candidate_runs(now: datetime, lookback_hours: int, cycle_h: int = 6) -> list[datetime]:
    """Bakış penceresindeki çalıştırmalar (her ``cycle_h`` saatte bir), eskiden yeniye."""
    last = now.replace(minute=0, second=0, microsecond=0)
    last -= timedelta(hours=last.hour % cycle_h)
    n = lookback_hours // cycle_h + 1
    return [last - timedelta(hours=cycle_h * k) for k in range(n)][::-1]


def pending(code: str, init: datetime) -> bool:
    with session_scope() as session:
        return runs.should_process(runs.get_run(session, runs.model_id(session, code), init))


def _start(src: Source, init: datetime) -> int:
    """Durumu ``downloading`` yapar, deneme sayısını artırır; model kimliğini döndürür."""
    with session_scope() as session:
        mid = runs.model_id(session, src.spec.code)
        run = runs.get_run(session, mid, init)
        attempts = int(((run.files if run else None) or {}).get("attempts", 0)) + 1
        files = {"attempts": attempts, "source": src.source, "resolution": src.resolution}
        runs.set_status(session, mid, init, "downloading", files=files)
        session.commit()
    return mid


def _fail(mid: int, init: datetime, exc: BaseException) -> bool:
    """Hatayı kaydeder. Yeni bir çalıştırmada dosya henüz yoksa (kaynaklar sırasız yayımlayabilir)
    çalıştırma deneme hakkı yakılmadan bekleyen duruma döner ve ``True`` döner."""
    error = f"{type(exc).__name__}: {exc}"[:500]
    with session_scope() as session:
        if isinstance(exc, RemoteFileGone) and datetime.now(UTC) - init < NOT_YET_PUBLISHED:
            run = runs.get_run(session, mid, init)
            attempts = int(((run.files if run else None) or {}).get("attempts", 1)) - 1
            runs.set_status(
                session, mid, init, "pending", files={"attempts": attempts}, error=error
            )
            session.commit()
            log.info("model_run_deferred", init=init.isoformat(), error=error)
            return True
        runs.set_status(session, mid, init, "failed", error=error)
        session.commit()
    return False


def _summary(
    code: str, init: datetime, rows: int, stats: dict[str, Any], started: float
) -> dict[str, Any]:
    summary = {
        "run": init.isoformat(),
        "rows": rows,
        **stats,
        "seconds": round(time.monotonic() - started, 1),
    }
    log.info("model_run_loaded", model=code, **summary)
    return summary


def process_run(
    src: Source, settings: Settings, region: Region, init: datetime, collect: Collect
) -> dict[str, Any]:
    code = src.spec.code
    started = time.monotonic()
    mid = _start(src, init)
    try:
        col, stats = collect()
        rows = extract_rows(col, src.spec, region.points, init)
        path = Path(settings.grib_dir) / code / f"{init:%Y%m%dT%H}Z.nc"
        write_netcdf(
            col,
            path,
            {
                "model": code,
                "init_time": init.isoformat(),
                "source": src.source,
                "resolution": src.resolution,
                "license": src.license,
            },
        )
        with session_scope() as session:
            runs.set_status(session, mid, init, "extracted", files={"crop_file": str(path)})
            n = store_rows(session, mid, init, rows)
            runs.set_status(
                session,
                mid,
                init,
                "loaded",
                files={
                    "extractor": src.extractor,
                    "steps": len(col.steps),
                    "rows": n,
                    **stats,
                    "seconds": round(time.monotonic() - started, 1),
                },
            )
            session.commit()
    except Exception as exc:
        if _fail(mid, init, exc):
            return {"run": init.isoformat(), "deferred": True}
        raise
    return _summary(code, init, n, stats, started)


def process_ensemble_run(
    src: Source, settings: Settings, region: Region, init: datetime, collect: EnsembleCollect
) -> dict[str, Any]:
    """Ensemble: ham üyeler Parquet'e, istatistikler ``ensemble_stats``'a (ADR-0006)."""
    code = src.spec.code
    started = time.monotonic()
    mid = _start(src, init)
    try:
        col, stats = collect()
        mv = extract_members(col, src.spec, region.points, init)
        attrs = {
            "model": code,
            "init_time": init.isoformat(),
            "source": src.source,
            "resolution": src.resolution,
            "license": src.license,
            "extractor": src.extractor,
        }
        crop = Path(settings.grib_dir) / code / f"{init:%Y%m%dT%H}Z.nc"
        write_ensemble_crop(col, crop, attrs)
        members = Path(settings.parquet_dir) / "ensemble" / code / f"{init:%Y%m%dT%H}Z.parquet"
        member_rows = write_members(mv, members, attrs)
        rows = member_stats(mv)
        with session_scope() as session:
            runs.set_status(
                session,
                mid,
                init,
                "extracted",
                files={"crop_file": str(crop), "members_file": str(members)},
            )
            n = store_stats(session, mid, init, rows)
            runs.set_status(
                session,
                mid,
                init,
                "loaded",
                files={
                    "extractor": src.extractor,
                    "extraction": mv.extraction,
                    "members": len(col.members),
                    "steps": len(col.steps),
                    "member_rows": member_rows,
                    "rows": n,
                    **stats,
                    "seconds": round(time.monotonic() - started, 1),
                },
            )
            session.commit()
    except Exception as exc:
        if _fail(mid, init, exc):
            return {"run": init.isoformat(), "deferred": True}
        raise
    return _summary(code, init, n, stats, started)
