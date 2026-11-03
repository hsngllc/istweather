"""UK Met Office Global 10 km — canlı, yalnız iç doğrulama (CLAUDE.md, ``models.internal_only``).

Arşiv çıkarıcısı ve yükleyicisi (``hava.ingest.archive.ukmo`` / ``load_ukmo``) yeni çalıştırmalar
için yeniden kullanılır: nokta başına 4×4 hücre HTTP Range ile okunur, Parquet + manifest'e yazılır,
sonra ``point_forecasts``'a maskesiz bilineer (``bilinear_unmasked``) yüklenir. UKMO kara-deniz
maskesi vermediği için maskeli seçim ve yükseklik düzeltmesi saklanan stencil'den sonradan yapılır
(spec §6). Lisans CC BY-SA 4.0 → sitede ve blend'de kullanılmaz.

Tamlık (2026-11-03 S3 listelerinden): 00/12z 0–168 sa (1.810 istenen dosya), 06/18z 0–69 sa (1.217).
Dosyalar S3'e kademeli yüklendiğinden çalıştırma, en uzun adım bu ufka ulaştığında ve istenen dosya
sayısı 12 saat önceki aynı tip çalıştırmanınkinden az olmadığında tamam sayılır.
"""

from __future__ import annotations

import multiprocessing
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import structlog
from sqlalchemy import select

from hava.db.models import Point as PointRow
from hava.db.session import session_scope
from hava.ingest.archive import load_ukmo
from hava.ingest.archive import ukmo as archive
from hava.ingest.models import runs
from hava.region import load_region
from hava.settings import get_settings

log = structlog.get_logger()

MODEL_CODE = archive.MODEL_CODE
HORIZON_H = {0: 168, 12: 168, 6: 69, 18: 69}
WORKERS = 6  # h5py iş parçacıklarında seri çalışır → ayrı süreçler


def wanted(client: httpx.Client, run_id: str) -> list[archive.FileRef]:
    refs = (archive.parse_key(k) for k in archive.list_run_files(client, run_id))
    return [r for r in refs if r is not None and r.param in archive.WANTED_PARAMS]


def run_complete(refs: list[archive.FileRef], init: datetime, previous: int | None) -> bool:
    """En uzun adım ufka ulaştı mı ve dosya sayısı önceki aynı tip çalıştırmadan az değil mi."""
    if not refs:
        return False
    if max(r.lead_min for r in refs) // 60 < HORIZON_H.get(init.hour, 168):
        return False
    return previous is None or len(refs) >= previous


def _pool(user_agent: str) -> ProcessPoolExecutor:
    # Worker çok iş parçacıklı; fork yerine forkserver (Windows'ta spawn).
    method = "spawn" if sys.platform == "win32" else "forkserver"
    return ProcessPoolExecutor(
        WORKERS,
        mp_context=multiprocessing.get_context(method),
        initializer=archive._init_worker,
        initargs=(user_agent,),
    )


def process(client: httpx.Client, out: Path, run_id: str, user_agent: str) -> dict[str, Any]:
    """Çıkarır (gerekirse) ve yükler; ``model_runs`` durumunu yönetir."""
    init = archive.parse_time(run_id)
    with session_scope() as session:
        mid = runs.model_id(session, MODEL_CODE)
        run = runs.get_run(session, mid, init)
        attempts = int(((run.files if run else None) or {}).get("attempts", 0)) + 1
        files = {"attempts": attempts, "source": archive.BUCKET_URL, "resolution": "10 km"}
        runs.set_status(session, mid, init, "downloading", files=files)
        session.commit()
    try:
        if archive.needs_processing(out, run_id):
            points = load_region(get_settings().region_config).points
            with _pool(user_agent) as pool:
                manifest = archive.process_run(client, pool, out, run_id, points, {})
        else:
            manifest = archive.read_manifest(out, run_id) or {}
        if manifest.get("status") != "complete":
            raise RuntimeError(
                f"çıkarım {manifest.get('status')}: ok={manifest.get('files_ok')} "
                f"başarısız={manifest.get('files_failed')} kayıp={manifest.get('files_gone')}"
            )
        with session_scope() as session:
            keys = session.execute(select(PointRow.point_key, PointRow.id))
            point_ids = {k: pid for k, pid in keys}
            path = out / "runs" / f"{run_id}.parquet"
            n = load_ukmo.load_run(session, mid, point_ids, path, out / "stencils")
            stats = {k: manifest.get(k) for k in ("files_ok", "requests", "bytes", "seconds")}
            runs.set_status(session, mid, init, "loaded", files={"attempts": attempts, **stats})
            session.commit()
    except Exception as exc:
        with session_scope() as session:
            runs.set_status(
                session, mid, init, "failed", error=f"{type(exc).__name__}: {exc}"[:500]
            )
            session.commit()
        raise
    summary = {"run": init.isoformat(), "rows": n, **stats}
    log.info("model_run_loaded", model=MODEL_CODE, **summary)
    return summary


def collect(max_runs: int = 2) -> list[dict[str, Any]]:
    """Worker işi: tamamlanmış ve yüklenmemiş çalıştırmaları (yeniden eskiye) işler."""
    settings = get_settings()
    out = Path(settings.parquet_dir) / "ukmo_global"
    cutoff = datetime.now(UTC) - timedelta(hours=settings.model_lookback_hours)
    done: list[dict[str, Any]] = []
    with httpx.Client(timeout=60.0, headers={"User-Agent": settings.http_user_agent}) as client:
        listed = [r for r in archive.list_runs(client) if archive.parse_time(r) >= cutoff]
        counts: dict[str, int] = {}
        for run_id in reversed(listed):  # önce en yeni çalıştırma
            init = archive.parse_time(run_id)
            with session_scope() as session:
                run = runs.get_run(session, runs.model_id(session, MODEL_CODE), init)
                if not runs.should_process(run):
                    continue
            refs = wanted(client, run_id)
            counts[run_id] = len(refs)
            prev_id = f"{init - timedelta(hours=12):%Y%m%dT%H%MZ}"
            if prev_id in listed and prev_id not in counts:
                counts[prev_id] = len(wanted(client, prev_id))
            if not run_complete(refs, init, counts.get(prev_id)):
                continue
            done.append(process(client, out, run_id, settings.http_user_agent))
            if len(done) >= max_runs:
                break
    return done
