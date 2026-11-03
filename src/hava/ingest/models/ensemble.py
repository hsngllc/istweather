"""Ensemble çalıştırması: üye alanları, nokta çıkarımı, istatistikler, ham üye Parquet'i (ADR-0006).

Üyeler deterministik hatla aynı kırpma ve kara-deniz maskeli ağırlıklarla noktaya çevrilir
(``pipeline.RunCollector`` + ``points.PointWeights.interpolate_many``). Kanonik giriş adları
``pipeline`` ile aynı: ``t2m`` (K), ``u10``/``v10``/``gust`` (m/s), ``precip_acc``/``snow_acc``
(başlangıçtan beri, mm).

Çıktılar:
- Ham üye nokta değerleri Parquet: ``<parquet_dir>/ensemble/<model>/<init>.parquet`` (nokta × adım ×
  üye). Spec §7: ham üyeler veritabanına yazılmaz; kalibrasyon için yeniden işlenebilir.
- ``ensemble_stats``: değişken başına üye sayısı, ortalama, std (n−1), p10/p25/p50/p75/p90 ve
  ``exceed_probs`` (ham üye oranı, kalibre değil). Yağış aralığı ve hamle tanımı ``extra``'da.
"""

from __future__ import annotations

import os
import warnings
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import h5netcdf
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session

from hava.db.bulk import upsert
from hava.db.models import EnsembleStat
from hava.db.models import Point as PointRow
from hava.ingest.models.grib import GribField
from hava.ingest.models.pipeline import K0, ModelSpec, RunCollector, extraction_label
from hava.processing.grid import BBox, CellCrop, Crop, FloatArray, UnstructuredGrid
from hava.processing.points import build_weights, lapse_correction
from hava.region import Point

INSTANT = ("t2m", "u10", "v10", "gust")
ACCUM = ("precip_acc", "snow_acc")
# Parquet sütunları (üye değerleri) ve istatistik değişkenleri
MEMBER_COLUMNS = (
    "temp_c",
    "precip_mm",
    "wind_u_ms",
    "wind_v_ms",
    "wind_speed_ms",
    "wind_gust_ms",
    "snow_mm",
)
STAT_VARIABLES = ("temp_c", "precip_mm", "wind_speed_ms", "wind_gust_ms", "snow_mm")
PERCENTILES = (10, 25, 50, 75, 90)
# Adım planı (ADR-0006 B): 0–72 sa 3 saatlik, sonra 6 saatlik; her model yayımladığıyla kesişir.
STEPS = (*range(0, 73, 3), *range(78, 385, 6))
# exceed_probs başlangıç eşikleri (ADR-0006); anahtar "<ge|le>_<değer>"
THRESHOLDS: dict[str, tuple[tuple[str, float], ...]] = {
    "precip_mm": (("ge", 0.1), ("ge", 1.0), ("ge", 5.0), ("ge", 10.0), ("ge", 20.0)),
    "wind_gust_ms": (("ge", 15.0), ("ge", 20.0), ("ge", 25.0)),
    "temp_c": (("le", 0.0),),
    "snow_mm": (("ge", 0.5),),
}


class EnsembleCollector:
    """Bir ensemble çalıştırmasının kırpılmış üye alanları: ``fields[var][step]`` → (M, *ızgara)."""

    def __init__(self, bbox: BBox, members: Sequence[int]) -> None:
        self.base = RunCollector(bbox)  # kırpma, ızgara denetimi ve sabit alanlar
        self.members = list(members)
        self._index = {m: i for i, m in enumerate(self.members)}
        self.fields: dict[str, dict[float, FloatArray]] = defaultdict(dict)

    @property
    def crop(self) -> Crop | CellCrop | None:
        return self.base.crop

    @property
    def static(self) -> dict[str, FloatArray]:
        return self.base.static

    def set_cells(self, lat: FloatArray, lon: FloatArray, grid_id: str) -> None:
        self.base.set_cells(lat, lon, grid_id)

    def add_static(self, var: str, f: GribField, scale: float = 1.0) -> None:
        self.base.add_static(var, f, scale)

    def crop_field(self, f: GribField) -> FloatArray:
        return self.base.crop_field(f)

    def add_cropped(self, var: str, step: float, member: int, values: FloatArray) -> None:
        by_step = self.fields[var]
        if step not in by_step:
            by_step[step] = np.full((len(self.members), *values.shape), np.nan)
        by_step[step][self._index[member]] = values

    def add(self, var: str, step: float, member: int, f: GribField, scale: float = 1.0) -> None:
        self.add_cropped(var, step, member, self.crop_field(f) * scale)

    @property
    def steps(self) -> list[float]:
        return sorted({s for by_step in self.fields.values() for s in by_step})


@dataclass
class MemberValues:
    """Noktaya çevrilmiş üye değerleri: ``values[sütun]`` → (S, M, P)."""

    point_keys: tuple[str, ...]
    members: list[int]
    steps: list[float]
    valid_times: list[datetime]
    period_h: list[float | None]  # birikimli değişkenlerin aralığı (adım başına)
    gust_definition: list[str | None]
    values: dict[str, FloatArray]
    extraction: str
    point_method: tuple[str, ...]
    lapse_correction_c: FloatArray | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def extract_members(
    col: EnsembleCollector, spec: ModelSpec, points: Sequence[Point], init_time: datetime
) -> MemberValues:
    if col.crop is None:
        raise ValueError("ensemble çalıştırmasında alan yok")
    pw = build_weights(col.crop.grid, points, col.static.get("lsm"))
    n_m, n_p = len(col.members), len(points)
    corr = None
    if "orog" in col.static:
        corr = lapse_correction(pw.interpolate(col.static["orog"]), pw.elevation_m)
    steps = col.steps
    out = {c: np.full((len(steps), n_m, n_p), np.nan) for c in MEMBER_COLUMNS}
    # Birikim başlangıçtan beri: 0. adımda mesajı olmayan modelde başlangıç değeri 0.
    zero_based = {v for v in ACCUM if col.fields.get(v) and 0 not in col.fields[v]}
    prev_acc: dict[str, FloatArray] = {}
    prev_step: float | None = None
    period: list[float | None] = []
    gust_def: list[str | None] = []
    for s, step in enumerate(steps):
        inst = {
            v: pw.interpolate_many(col.fields[v][step])
            for v in INSTANT
            if step in col.fields.get(v, {})
        }
        if "t2m" in inst:
            out["temp_c"][s] = inst["t2m"] - K0 + (0.0 if corr is None else corr)
        if "u10" in inst and "v10" in inst:
            out["wind_u_ms"][s], out["wind_v_ms"][s] = inst["u10"], inst["v10"]
            out["wind_speed_ms"][s] = np.hypot(inst["u10"], inst["v10"])
        if "gust" in inst:
            out["wind_gust_ms"][s] = inst["gust"]
        gust_def.append(spec.gust_definition(step) if "gust" in inst else None)
        if step == 0:
            prev_acc.update({v: np.zeros((n_m, n_p)) for v in zero_based})
        acc_now = {
            v: pw.interpolate_many(col.fields[v][step])
            for v in ACCUM
            if step in col.fields.get(v, {})
        }
        has_interval = False
        for v, now in acc_now.items():
            if prev_step is not None and v in prev_acc:
                target = "precip_mm" if v == "precip_acc" else "snow_mm"
                out[target][s] = np.maximum(now - prev_acc[v], 0.0)
                has_interval = True
        period.append(None if prev_step is None or not has_interval else step - prev_step)
        prev_acc.update(acc_now)
        prev_step = step
    return MemberValues(
        point_keys=tuple(p.point_id for p in points),
        members=col.members,
        steps=steps,
        valid_times=[init_time + timedelta(hours=s) for s in steps],
        period_h=period,
        gust_definition=gust_def,
        values=out,
        extraction=extraction_label(col.base),
        point_method=pw.method,
        lapse_correction_c=corr,
    )


def member_stats(mv: MemberValues) -> list[dict[str, Any]]:
    """``ensemble_stats`` satırları (``point_id`` burada nokta anahtarıdır, DB kimliği değil)."""
    rows: list[dict[str, Any]] = []
    for var in STAT_VARIABLES:
        data = mv.values[var]  # (S, M, P)
        for s in range(len(mv.steps)):
            arr = data[s]
            valid = np.isfinite(arr)
            n = valid.sum(axis=0)
            if not n.any():
                continue
            with warnings.catch_warnings():
                # Tüm üyeleri eksik noktalar için "boş dilim" uyarısı (n=0 zaten atlanır).
                warnings.simplefilter("ignore", RuntimeWarning)
                mean = np.nanmean(arr, axis=0)
                std = np.nanstd(arr, axis=0, ddof=1)
                pct = np.nanpercentile(arr, PERCENTILES, axis=0)
            extra: dict[str, Any] = {}
            if var in ("precip_mm", "snow_mm") and mv.period_h[s] is not None:
                extra["period_h"] = mv.period_h[s]
            if var == "wind_gust_ms" and mv.gust_definition[s]:
                extra["gust_definition"] = mv.gust_definition[s]
            for k, key in enumerate(mv.point_keys):
                if n[k] == 0:
                    continue
                probs = {}
                for op, thr in THRESHOLDS.get(var, ()):
                    hit = (arr[:, k] >= thr) if op == "ge" else (arr[:, k] <= thr)
                    probs[f"{op}_{thr:g}"] = round(float((hit & valid[:, k]).sum() / n[k]), 4)
                rows.append(
                    {
                        "point_id": key,
                        "valid_time": mv.valid_times[s],
                        "variable": var,
                        "n_members": int(n[k]),
                        "mean": float(mean[k]),
                        "std": float(std[k]) if n[k] > 1 else None,
                        **{f"p{q}": float(pct[i, k]) for i, q in enumerate(PERCENTILES)},
                        "exceed_probs": probs,
                        "extraction": mv.extraction,
                        "extra": extra,
                    }
                )
    return rows


def write_members(mv: MemberValues, path: Path, meta: dict[str, Any]) -> int:
    """Ham üye nokta değerlerini atomik olarak Parquet'e yazar; satır sayısını döndürür."""
    n_s, n_m, n_p = len(mv.steps), len(mv.members), len(mv.point_keys)
    grids = np.meshgrid(np.arange(n_s), np.arange(n_m), np.arange(n_p), indexing="ij")
    s_idx, m_idx, p_idx = (g.ravel() for g in grids)
    table = pa.table(
        {
            "valid_time": pa.array([mv.valid_times[i] for i in s_idx], pa.timestamp("s", "UTC")),
            "lead_h": pa.array(np.asarray(mv.steps, dtype=np.float32)[s_idx]),
            "point_key": pa.array(
                [mv.point_keys[i] for i in p_idx], pa.string()
            ).dictionary_encode(),
            "member": pa.array(np.asarray(mv.members, dtype=np.int16)[m_idx]),
            **{
                c: pa.array(mv.values[c].astype(np.float32).ravel(), from_pandas=True)
                for c in MEMBER_COLUMNS
            },
            "precip_period_h": pa.array([mv.period_h[i] for i in s_idx], pa.float32()),
            # Tür açıkça string: hamlesiz modelde (AIFS ENS) sütun tamamen boş olabilir.
            "gust_definition": pa.array(
                [mv.gust_definition[i] for i in s_idx], pa.string()
            ).dictionary_encode(),
        }
    )
    table = table.replace_schema_metadata(
        {**{k: str(v) for k, v in meta.items()}, "extraction": mv.extraction}
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, path)
    return int(table.num_rows)


def write_crop(col: EnsembleCollector, path: Path, attrs: dict[str, Any]) -> None:
    """Kırpılmış üye alanlarını atomik olarak NetCDF-4'e yazar (30 gün saklanır)."""
    if col.crop is None:
        return
    grid = col.crop.grid
    steps = col.steps
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with h5netcdf.File(tmp, "w") as f:
        space: tuple[str, ...]
        dims: dict[str, int] = {"step": len(steps), "member": len(col.members)}
        if isinstance(col.crop, CellCrop) and isinstance(grid, UnstructuredGrid):
            space = ("cell",)
            f.dimensions = {**dims, "cell": len(grid.lat)}
            f.create_variable("lat", ("cell",), "f8", data=grid.lat)
            f.create_variable("lon", ("cell",), "f8", data=grid.lon)
            f.attrs["grid_id"] = grid.grid_id
        else:
            space = ("lat", "lon")
            f.dimensions = {**dims, "lat": len(grid.lat), "lon": len(grid.lon)}
            f.create_variable("lat", ("lat",), "f8", data=grid.lat)
            f.create_variable("lon", ("lon",), "f8", data=grid.lon)
        f.create_variable("step", ("step",), "f4", data=np.array(steps, dtype=np.float32))
        f.variables["step"].attrs["units"] = "hours since init_time"
        f.create_variable("member", ("member",), "i2", data=np.array(col.members, dtype=np.int16))
        for var, by_step in sorted(col.fields.items()):
            arr = np.full((len(steps), len(col.members), *grid.shape), np.nan, dtype=np.float32)
            for n, s in enumerate(steps):
                if s in by_step:
                    arr[n] = by_step[s]
            dims_v = ("step", "member", *space)
            f.create_variable(var, dims_v, "f4", data=arr, compression="gzip")
        for var, arr2 in sorted(col.static.items()):
            f.create_variable(var, space, "f4", data=arr2.astype(np.float32))
        f.attrs.update({k: str(v) for k, v in attrs.items()})
    os.replace(tmp, path)


def store_stats(
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
        EnsembleStat,
        out,
        constraint="pk_ensemble_stats",
        key_cols=("model_id", "init_time", "point_id", "valid_time", "variable"),
    )
