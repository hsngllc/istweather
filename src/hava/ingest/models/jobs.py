"""Worker işleri: canlı model toplama ve kırpılmış dosya temizliği."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from hava.db.session import session_scope
from hava.ingest.models import arpege, ecmwf, gdps, gefs, gfs, icon, ukmo
from hava.ingest.models.pipeline import prune_files
from hava.ops.health import record_error, record_success
from hava.settings import get_settings

log = structlog.get_logger()

# Model kodu → toplayıcı. Faz 3'te adaptör eklendikçe genişler.
ADAPTERS: dict[str, Callable[[], list[dict[str, Any]]]] = {
    ecmwf.IFS.code: ecmwf.collect_ifs,
    ecmwf.AIFS_SINGLE.code: ecmwf.collect_aifs_single,
    gfs.MODEL_CODE: gfs.collect,
    icon.ICON.code: icon.collect_icon,
    icon.ICON_EU.code: icon.collect_icon_eu,
    arpege.MODEL_CODE: arpege.collect,
    gdps.MODEL_CODE: gdps.collect,  # duyurular AMQPS dinleyicisinden (ADR-0007)
    ukmo.MODEL_CODE: ukmo.collect,  # yalnız iç doğrulama (CC BY-SA)
    # Ensemble'lar (ADR-0006): 00/12z
    ecmwf.IFS_ENS.code: ecmwf.collect_ifs_ens,
    ecmwf.AIFS_ENS.code: ecmwf.collect_aifs_ens,
    gefs.MODEL_CODE: gefs.collect,
    icon.ICON_EU_EPS.code: icon.collect_eps,
}


def collect_model(code: str) -> int:
    """Tek modelin toplayıcısı. Her model ayrı zamanlanmış iştir; biri diğerini bekletmez."""
    source = f"collector:{code}"
    try:
        done = ADAPTERS[code]()
    except Exception as exc:
        log.error("model_collect_failed", model=code, error=f"{type(exc).__name__}: {exc}")
        with session_scope() as session:
            record_error(session, source, datetime.now(UTC), exc)
            session.commit()
        raise
    with session_scope() as session:
        record_success(session, source, datetime.now(UTC))
        session.commit()
    return len(done)


def prune_grib() -> int:
    settings = get_settings()
    removed = prune_files(Path(settings.grib_dir), settings.grib_retention_days)
    log.info("grib_pruned", removed=removed, days=settings.grib_retention_days)
    return removed
