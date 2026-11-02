"""UKMO arşiv Parquet'lerini ``point_forecasts`` tablosuna yükler — yalnız iç doğrulama.

Değerler maskesiz bilineerdir (``extraction="bilinear_unmasked"``). Kara-deniz maskeli seçim ve
lapse-rate düzeltmesi (spec §6) Faz 3 processing'de saklanan stencil'den yeniden hesaplanıp
üzerine yazılacak. Rüzgâr u/v bileşenleri hücre başına hız/yönden hesaplanıp sonra bilineer
ağırlıklarla birleştirilir; açı ortalaması alınmaz (spec §8).

Kullanım: ``python -m hava.ingest.archive.load_ukmo --dir /data/parquet/ukmo_global``
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pyarrow.parquet as pq
import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from hava.db.models import Model, ModelRun, Point, PointForecast
from hava.db.session import session_scope
from hava.ingest.archive.ukmo import EXTRACTOR_VERSION, MODEL_CODE
from hava.ops.logging import configure_logging
from hava.settings import get_settings

log = structlog.get_logger()

K0 = 273.15
EXTRACTION = "bilinear_unmasked"
GUST_DEFINITION = "max_3s_mean_prev_10min"
_WINDOW_RE = re.compile(r"^(?P<base>.+)-PT(?P<h>\d+)H$")


def inner_weights(stencil_table: pa.Table) -> dict[str, npt.NDArray[np.float64]]:
    """Nokta başına 16 elemanlı bilineer ağırlık vektörü (dış halka sıfır)."""
    out: dict[str, npt.NDArray[np.float64]] = defaultdict(lambda: np.zeros(16))
    for row in stencil_table.select(["point_id", "k", "bilinear_weight"]).to_pylist():
        out[row["point_id"]][row["k"]] = row["bilinear_weight"]
    return dict(out)


def _f(x: float | None) -> float | None:
    if x is None or not math.isfinite(x):
        return None
    return float(x)


def _windowed(group: dict[str, dict[str, Any]], base: str) -> tuple[dict[str, Any], float] | None:
    """``<base>-PTnnH`` parametrelerinden en kısa pencereliyi döndürür."""
    best: tuple[dict[str, Any], float] | None = None
    for param, row in group.items():
        m = _WINDOW_RE.match(param)
        if m and m["base"] == base:
            h = float(m["h"])
            if best is None or h < best[1]:
                best = (row, h)
    return best


def _wind_uv(
    speed: Sequence[float], direction: Sequence[float], weights: npt.NDArray[np.float64]
) -> tuple[float | None, float | None]:
    s = np.asarray(speed, dtype=np.float64)
    d = np.deg2rad(np.asarray(direction, dtype=np.float64))
    used = weights > 0
    if not np.all(np.isfinite(s[used]) & np.isfinite(d[used])):
        return None, None
    # Meteorolojik yön: rüzgârın geldiği yön.
    u = -s * np.sin(d)
    v = -s * np.cos(d)
    return _f(float(np.sum(weights[used] * u[used]))), _f(float(np.sum(weights[used] * v[used])))


def transform_run(
    table: pa.Table, weights: dict[str, npt.NDArray[np.float64]]
) -> list[dict[str, Any]]:
    """Bir çalıştırmanın uzun formatlı satırlarını ``point_forecasts`` kayıtlarına çevirir."""
    groups: dict[tuple[datetime, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    meta: dict[tuple[datetime, str], tuple[datetime, int]] = {}
    for row in table.to_pylist():
        key = (row["valid_time"], row["point_id"])
        groups[key][row["param"]] = row
        meta[key] = (row["init_time"], row["lead_min"])

    def bil(g: dict[str, dict[str, Any]], param: str) -> float | None:
        row = g.get(param)
        return None if row is None else _f(row["bilinear"])

    records: list[dict[str, Any]] = []
    for (valid, point_key), g in groups.items():
        init_time, lead_min = meta[(valid, point_key)]
        t = bil(g, "temperature_at_screen_level")
        td = bil(g, "temperature_of_dew_point_at_screen_level")
        rh = bil(g, "relative_humidity_at_screen_level")
        mslp = bil(g, "pressure_at_mean_sea_level")
        tcc = bil(g, "cloud_amount_of_total_cloud")
        lcc = bil(g, "cloud_amount_of_low_cloud")
        t850 = bil(g, "temperature_on_pressure_levels")
        rec: dict[str, Any] = {
            "point_key": point_key,
            "init_time": init_time,
            "valid_time": valid,
            "lead_h": lead_min / 60.0,
            "temp_c": None if t is None else t - K0,
            "dewpoint_c": None if td is None else td - K0,
            "rh_pct": None if rh is None else rh * 100.0,
            "precip_mm": None,
            "precip_period_h": None,
            "snow_mm": None,
            "precip_type": None,
            "wind_u_ms": None,
            "wind_v_ms": None,
            "wind_gust_ms": bil(g, "wind_gust_at_10m"),
            "mslp_hpa": None if mslp is None else mslp / 100.0,
            "cloud_cover_pct": None if tcc is None else tcc * 100.0,
            "low_cloud_pct": None if lcc is None else lcc * 100.0,
            "visibility_m": bil(g, "visibility_at_screen_level"),
            "t850_c": None if t850 is None else t850 - K0,
            "extraction": EXTRACTION,
        }
        extra: dict[str, Any] = {"gust_definition": GUST_DEFINITION}
        precip = _windowed(g, "precipitation_accumulation")
        if precip:
            value = _f(precip[0]["bilinear"])
            rec["precip_mm"] = None if value is None else value * 1000.0
            rec["precip_period_h"] = precip[1]
        if "wind_speed_at_10m" in g and "wind_direction_at_10m" in g:
            w = weights.get(point_key)
            if w is not None:
                rec["wind_u_ms"], rec["wind_v_ms"] = _wind_uv(
                    g["wind_speed_at_10m"]["stencil"], g["wind_direction_at_10m"]["stencil"], w
                )
        gust_max = _windowed(g, "wind_gust_at_10m_max")
        if gust_max:
            extra["gust_max_ms"] = _f(gust_max[0]["bilinear"])
            extra["gust_max_period_h"] = gust_max[1]
        for base, name in (
            ("temperature_at_screen_level_max", "tmax_c"),
            ("temperature_at_screen_level_min", "tmin_c"),
        ):
            hit = _windowed(g, base)
            if hit:
                value = _f(hit[0]["bilinear"])
                extra[name] = None if value is None else value - K0
                extra[f"{name}_period_h"] = hit[1]
        rain = _windowed(g, "rainfall_accumulation")
        if rain:
            value = _f(rain[0]["bilinear"])
            extra["rain_mm"] = None if value is None else value * 1000.0
            extra["rain_period_h"] = rain[1]
        for param, name in (
            ("snowfall_rate", "snowfall_rate_mm_h"),
            ("snowfall_rate_from_convection", "snowfall_rate_conv_mm_h"),
        ):
            value = bil(g, param)
            if value is not None:
                extra[name] = value * 3.6e6  # m s-1 → mm h-1
        fog = bil(g, "fog_fraction_at_screen_level")
        if fog is not None:
            extra["fog_fraction"] = fog
        tsurf = bil(g, "temperature_at_surface")
        if tsurf is not None:
            extra["surface_temp_c"] = tsurf - K0
        orog = bil(g, "height_of_orography")
        if orog is not None:
            extra["model_orography_m"] = orog
        rec["extra"] = extra
        records.append(rec)
    return records


_UPDATE_COLS = [
    c.name
    for c in PointForecast.__table__.columns
    if c.name not in ("model_id", "init_time", "point_id", "valid_time")
]
# PostgreSQL protokolü bir sorguda en fazla 65535 bağlı parametreye izin verir.
_MAX_PARAMS = 65535


def batches(rows: list[dict[str, Any]], batch: int) -> list[list[dict[str, Any]]]:
    """Satırları, çok satırlı INSERT'in parametre sınırını aşmayacak paketlere böler."""
    if not rows:
        return []
    size = max(1, min(batch, _MAX_PARAMS // len(rows[0])))
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def load_run(
    session: Session,
    model_id: int,
    point_ids: dict[str, int],
    run_path: Path,
    stencil_dir: Path,
    batch: int = 2500,
) -> int:
    table = pq.read_table(run_path)
    fp = (table.schema.metadata or {}).get(b"stencil_fingerprint", b"").decode()
    weights = inner_weights(pq.read_table(stencil_dir / f"{fp}.parquet"))
    records = transform_run(table, weights)
    rows = []
    for rec in records:
        pid = point_ids.get(rec.pop("point_key"))
        if pid is not None:
            rows.append({"model_id": model_id, "point_id": pid, **rec})
    for chunk in batches(rows, batch):
        stmt = insert(PointForecast).values(chunk)
        session.execute(
            stmt.on_conflict_do_update(
                constraint="pk_point_forecasts",
                set_={c: stmt.excluded[c] for c in _UPDATE_COLS},
            )
        )
    init_time = datetime.strptime(run_path.stem, "%Y%m%dT%H%MZ").replace(tzinfo=UTC)
    now = datetime.now(UTC)
    files = {"parquet": run_path.name, "extractor": EXTRACTOR_VERSION, "rows": len(rows)}
    stmt_run = insert(ModelRun).values(
        model_id=model_id, init_time=init_time, status="loaded", completed_at=now, files=files
    )
    session.execute(
        stmt_run.on_conflict_do_update(
            constraint="pk_model_runs",
            set_={"status": "loaded", "completed_at": now, "files": files, "error": None},
        )
    )
    return len(rows)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=None, help="varsayılan: <HAVA_PARQUET_DIR>/ukmo_global")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument(
        "--reload", action="store_true", help="yüklenmiş çalıştırmaları da yeniden yükle"
    )
    args = ap.parse_args(argv)
    configure_logging()
    base = Path(args.dir or Path(get_settings().parquet_dir) / "ukmo_global")
    runs = sorted((base / "runs").glob("*.parquet"))
    with session_scope() as session:
        model_id = session.execute(select(Model.id).where(Model.code == MODEL_CODE)).scalar_one()
        point_ids = {key: pid for key, pid in session.execute(select(Point.point_key, Point.id))}
        loaded = set(
            session.execute(
                select(ModelRun.init_time).where(
                    ModelRun.model_id == model_id, ModelRun.status == "loaded"
                )
            ).scalars()
        )
        done = 0
        for path in runs:
            manifest = base / "manifest" / f"{path.stem}.json"
            status = json.loads(manifest.read_text(encoding="utf-8"))["status"]
            init_time = datetime.strptime(path.stem, "%Y%m%dT%H%MZ").replace(tzinfo=UTC)
            if status != "complete" or (init_time in loaded and not args.reload):
                continue
            n = load_run(session, model_id, point_ids, path, base / "stencils")
            session.commit()
            done += 1
            log.info("ukmo_run_loaded", run=path.stem, rows=n)
            if args.limit is not None and done >= args.limit:
                break
    log.info("ukmo_load_done", runs=done)
    return 0


if __name__ == "__main__":
    sys.exit(main())
