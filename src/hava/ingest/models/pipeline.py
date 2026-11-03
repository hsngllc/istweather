"""Model çalıştırması işleme hattı (tüm modeller için ortak).

Adaptör, GRIB alanlarını kanonik adlarla ``RunCollector``'a ekler; birimleri burada beklenen
birime çevirerek verir:

=============  ==========================================  =========
Ad             Anlam                                        Birim
=============  ==========================================  =========
t2m, d2m       2 m sıcaklık / çiy noktası                   K
t850           850 hPa sıcaklık                             K
u10, v10       10 m rüzgâr bileşenleri                      m/s
gust           10 m hamle (tanımı ``ModelSpec``'te)         m/s
msl            ortalama deniz seviyesi basıncı              Pa
tcc, lcc       toplam / alçak bulut                         0–1
precip_acc     toplam yağış, başlangıçtan beri              mm
conv_acc       konvektif yağış, başlangıçtan beri           mm
snow_acc       kar yağışı (su eşdeğeri), başlangıçtan beri  mm
ptype          yağış tipi kodu (kategorik)                  —
lsm, orog      kara oranı (0–1) / model arazi yüksekliği     —, m
=============  ==========================================  =========

Sonra noktalara çevirir (kara-deniz maskeli, sıcaklıkta yükseklik düzeltmeli), birikimli
değişkenleri adım aralığına böler, kırpılmış alanları NetCDF olarak saklar ve
``point_forecasts``'a yazar.
"""

from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import h5netcdf
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from hava.db.bulk import upsert
from hava.db.models import Point as PointRow
from hava.db.models import PointForecast
from hava.ingest.models.grib import GribField
from hava.processing.grid import BBox, Crop, FloatArray, crop_grid
from hava.processing.points import build_weights, lapse_correction
from hava.processing.thermo import relative_humidity
from hava.region import Point

INSTANT = ("t2m", "d2m", "t850", "u10", "v10", "gust", "msl", "tcc", "lcc")
ACCUM = ("precip_acc", "conv_acc", "snow_acc")
CATEGORICAL = ("ptype",)
STATIC = ("lsm", "orog")
K0 = 273.15


class GridChanged(ValueError):
    """Çalıştırma içinde farklı ızgaralı bir alan geldi."""


@dataclass(frozen=True)
class ModelSpec:
    code: str
    gust_definition: Callable[[float], str | None]
    ptype_names: dict[int, str] = field(default_factory=dict)


class RunCollector:
    """Bir çalıştırmanın kırpılmış alanlarını adım × değişken olarak toplar."""

    def __init__(self, bbox: BBox) -> None:
        self.bbox = bbox
        self.crop: Crop | None = None
        self._native: tuple[int, int, float, float, float, float] | None = None
        self.fields: dict[str, dict[float, FloatArray]] = defaultdict(dict)
        self.static: dict[str, FloatArray] = {}

    def _cropped(self, f: GribField) -> FloatArray:
        sig = (len(f.lat), len(f.lon), f.lat[0], f.lat[-1], f.lon[0], f.lon[-1])
        if self.crop is None:
            self.crop = crop_grid(f.lat, f.lon, self.bbox)
            self._native = sig
        elif sig != self._native:
            raise GridChanged(f"{f.short_name}: ızgara {sig} != {self._native}")
        return self.crop.apply(f.values)

    def add(self, var: str, step_h: float, f: GribField, scale: float = 1.0) -> None:
        self.fields[var][step_h] = self._cropped(f) * scale

    def add_static(self, var: str, f: GribField, scale: float = 1.0) -> None:
        self.static[var] = self._cropped(f) * scale

    @property
    def steps(self) -> list[float]:
        return sorted({s for by_step in self.fields.values() for s in by_step})


def _num(x: float) -> float | None:
    return None if x is None or not np.isfinite(x) else float(x)


def extraction_label(col: RunCollector) -> str:
    parts = ["bilinear"]
    if "lsm" in col.static:
        parts.append("lsm")
    if "orog" in col.static:
        parts.append("lapse")
    return "_".join(parts) if len(parts) > 1 else "bilinear_unmasked"


def extract_rows(
    col: RunCollector, spec: ModelSpec, points: Sequence[Point], init_time: datetime
) -> list[dict[str, Any]]:
    """Nokta × adım satırları (``point_id`` burada nokta anahtarıdır, DB kimliği değil)."""
    if col.crop is None:
        return []
    pw = build_weights(col.crop.grid, points, col.static.get("lsm"))
    n = len(points)
    if "orog" in col.static:
        orog = pw.interpolate(col.static["orog"])
        corr = lapse_correction(orog, pw.elevation_m)
    else:
        orog = np.full(n, np.nan)
        corr = np.zeros(n)
    label = extraction_label(col)
    rows: list[dict[str, Any]] = []
    prev_step: float | None = None
    prev_acc: dict[str, FloatArray] = {}
    for step in col.steps:
        v: dict[str, FloatArray] = {}
        for var in INSTANT:
            if step in col.fields.get(var, {}):
                v[var] = pw.interpolate(col.fields[var][step])
        acc_now = {
            var: pw.interpolate(col.fields[var][step])
            for var in ACCUM
            if step in col.fields.get(var, {})
        }
        interval: dict[str, FloatArray] = {}
        for var, now in acc_now.items():
            if prev_step is not None and var in prev_acc:
                interval[var] = np.maximum(now - prev_acc[var], 0.0)
        period = None if prev_step is None else step - prev_step
        ptype = (
            pw.categorical(col.fields["ptype"][step])
            if step in col.fields.get("ptype", {})
            else None
        )
        gust_def = spec.gust_definition(step) if "gust" in v else None
        for k, p in enumerate(points):
            t_raw = v["t2m"][k] - K0 if "t2m" in v else np.nan
            td = v["d2m"][k] - K0 if "d2m" in v else np.nan
            temp = t_raw + corr[k]
            rh = relative_humidity(t_raw, td) if np.isfinite(t_raw + td) else np.nan
            extra: dict[str, Any] = {"point_method": pw.method[k]}
            if np.isfinite(orog[k]):
                extra["model_orography_m"] = round(float(orog[k]), 1)
                extra["lapse_correction_c"] = round(float(corr[k]), 3)
            if gust_def:
                extra["gust_definition"] = gust_def
            if "conv_acc" in interval:
                extra["conv_precip_mm"] = _num(interval["conv_acc"][k])
            code = None if ptype is None or not np.isfinite(ptype[k]) else round(float(ptype[k]))
            rows.append(
                {
                    "point_id": p.point_id,
                    "valid_time": init_time + timedelta(hours=step),
                    "lead_h": float(step),
                    "temp_c": _num(temp),
                    "dewpoint_c": _num(min(td, temp)) if np.isfinite(td) else None,
                    "rh_pct": _num(rh),
                    "precip_mm": _num(interval["precip_acc"][k])
                    if "precip_acc" in interval
                    else None,
                    "precip_period_h": period if "precip_acc" in interval else None,
                    "snow_mm": _num(interval["snow_acc"][k]) if "snow_acc" in interval else None,
                    "precip_type": None if code is None else spec.ptype_names.get(code, str(code)),
                    "wind_u_ms": _num(v["u10"][k]) if "u10" in v else None,
                    "wind_v_ms": _num(v["v10"][k]) if "v10" in v else None,
                    "wind_gust_ms": _num(v["gust"][k]) if "gust" in v else None,
                    "mslp_hpa": _num(v["msl"][k] / 100.0) if "msl" in v else None,
                    "cloud_cover_pct": _num(v["tcc"][k] * 100.0) if "tcc" in v else None,
                    "low_cloud_pct": _num(v["lcc"][k] * 100.0) if "lcc" in v else None,
                    "visibility_m": None,
                    "t850_c": _num(v["t850"][k] - K0) if "t850" in v else None,
                    "extraction": label,
                    "extra": extra,
                }
            )
        prev_step = step
        prev_acc.update(acc_now)
    return rows


def write_netcdf(col: RunCollector, path: Path, attrs: dict[str, Any]) -> None:
    """Kırpılmış alanları atomik olarak NetCDF-4'e yazar (spec §5.1: 30 gün saklanır)."""
    if col.crop is None:
        return
    grid = col.crop.grid
    steps = col.steps
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with h5netcdf.File(tmp, "w") as f:
        f.dimensions = {"step": len(steps), "lat": len(grid.lat), "lon": len(grid.lon)}
        f.create_variable("step", ("step",), "f4", data=np.array(steps, dtype=np.float32))
        f.variables["step"].attrs["units"] = "hours since init_time"
        f.create_variable("lat", ("lat",), "f8", data=grid.lat)
        f.create_variable("lon", ("lon",), "f8", data=grid.lon)
        for var, by_step in sorted(col.fields.items()):
            arr = np.full((len(steps), len(grid.lat), len(grid.lon)), np.nan, dtype=np.float32)
            for n, s in enumerate(steps):
                if s in by_step:
                    arr[n] = by_step[s]
            f.create_variable(var, ("step", "lat", "lon"), "f4", data=arr, compression="gzip")
        for var, arr2 in sorted(col.static.items()):
            f.create_variable(var, ("lat", "lon"), "f4", data=arr2.astype(np.float32))
        f.attrs.update({k: str(v) for k, v in attrs.items()})
    os.replace(tmp, path)


def store_rows(
    session: Session, mid: int, init_time: datetime, rows: Sequence[dict[str, Any]]
) -> int:
    ids = {key: pid for key, pid in session.execute(select(PointRow.point_key, PointRow.id))}
    out = []
    for r in rows:
        pid = ids.get(r["point_id"])
        if pid is not None:
            out.append({**r, "model_id": mid, "init_time": init_time, "point_id": pid})
    return upsert(
        session,
        PointForecast,
        out,
        constraint="pk_point_forecasts",
        key_cols=("model_id", "init_time", "point_id", "valid_time"),
    )


def prune_files(root: Path, days: int, now: datetime | None = None) -> int:
    """``root`` altında ``days`` günden eski kırpılmış dosyaları siler."""
    limit = (now or datetime.now(UTC)).timestamp() - days * 86400
    removed = 0
    for p in root.rglob("*.nc"):
        if p.stat().st_mtime < limit:
            p.unlink()
            removed += 1
    return removed
