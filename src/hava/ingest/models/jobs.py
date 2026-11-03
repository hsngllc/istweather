"""Worker işleri: canlı model toplama ve kırpılmış dosya temizliği."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from hava.db.session import session_scope
from hava.ingest.models import ecmwf
from hava.ingest.models.pipeline import prune_files
from hava.ops.health import record_error, record_success
from hava.settings import get_settings

log = structlog.get_logger()

# Model kodu → toplayıcı. Faz 3'te adaptör eklendikçe genişler.
ADAPTERS: dict[str, Callable[[], list[dict[str, Any]]]] = {
    ecmwf.MODEL_CODE: ecmwf.collect,
}


class ModelCollectionError(RuntimeError):
    """Bir veya daha fazla modelin toplanması başarısız oldu."""


def collect_models() -> dict[str, int]:
    """Her adaptörü ayrı çalıştırır; biri hata verirse diğerleri yine denenir."""
    failed: list[str] = []
    loaded: dict[str, int] = {}
    for code, collect in ADAPTERS.items():
        source = f"collector:{code}"
        try:
            done = collect()
        except Exception as exc:
            log.error("model_collect_failed", model=code, error=f"{type(exc).__name__}: {exc}")
            with session_scope() as session:
                record_error(session, source, datetime.now(UTC), exc)
                session.commit()
            failed.append(code)
            continue
        loaded[code] = len(done)
        with session_scope() as session:
            record_success(session, source, datetime.now(UTC))
            session.commit()
    if failed:
        raise ModelCollectionError(", ".join(failed))
    return loaded


def prune_grib() -> int:
    settings = get_settings()
    removed = prune_files(Path(settings.grib_dir), settings.grib_retention_days)
    log.info("grib_pruned", removed=removed, days=settings.grib_retention_days)
    return removed
