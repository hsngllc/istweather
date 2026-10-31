"""UK Met Office Global 10 km arşivinden (AWS) nokta çıkarımı — yalnız iç doğrulama.

Kaynak: ``s3://met-office-atmospheric-model-data/global-deterministic-10km/`` (eu-west-2),
lisans CC BY-SA 4.0 ("British Crown copyright, the Met Office"). Arşiv 2 yıllık kayan penceredir;
her gün en eski gün silinir. Bu yüzden en eski çalıştırmadan başlanır (spec §5.2.5).

Her dosya (parametre × adım) için tüm noktaların 4×4 komşuluğunu kapsayan en küçük ızgara kutusu
HTTP Range ile okunur. Nokta başına 16 hücre (stencil), en yakın hücre ve maskesiz bilineer değer
saklanır. UKMO deterministik ürünü kara-deniz maskesi vermediği için maskeli seçim ve lapse-rate
düzeltmesi sonradan (processing) stencil üzerinden yapılır (spec §6).

Çıktı dizini:
  stencils/<parmak_izi>.parquet  nokta → ızgara hücreleri, koordinatlar ve bilineer ağırlıklar
  runs/<YYYYMMDDTHHMMZ>.parquet  çalıştırma başına nokta değerleri
  manifest/<YYYYMMDDTHHMMZ>.json durum (complete | partial | lost | empty), sayımlar, hatalar

İş kaldığı yerden devam eder: manifest'i ``complete``/``lost``/``empty`` olan çalıştırmalar atlanır,
``partial`` olanlar en fazla ``MAX_ATTEMPTS`` kez yeniden denenir.

Kullanım:
  python -m hava.ingest.archive.ukmo --out .data/ukmo_global --workers 32 --follow
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import h5py
import httpx
import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pyarrow.parquet as pq

from hava import __version__
from hava.ingest.archive.http_range import HttpRangeFile, RemoteFileGone, get_with_retry
from hava.region import Point, load_region

log = logging.getLogger("hava.ukmo")

BUCKET_URL = "https://met-office-atmospheric-model-data.s3.eu-west-2.amazonaws.com"
PREFIX = "global-deterministic-10km/"
MODEL_CODE = "ukmo_global_10km"
EXTRACTOR_VERSION = "ukmo-points-1"
LICENSE = "CC BY-SA 4.0 — British Crown copyright, the Met Office (yalnız iç doğrulama)"
MAX_ATTEMPTS = 3
S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"

# Spec §5.1 değişkenlerine karşılık gelen UKMO parametreleri (dosya adındaki son kısım).
_WINDOWS = ("PT01H", "PT03H", "PT06H")
WANTED_PARAMS: frozenset[str] = frozenset(
    {
        "temperature_at_screen_level",
        "temperature_of_dew_point_at_screen_level",
        "relative_humidity_at_screen_level",
        "snowfall_rate",
        "snowfall_rate_from_convection",
        "wind_speed_at_10m",
        "wind_direction_at_10m",
        "wind_gust_at_10m",
        "pressure_at_mean_sea_level",
        "cloud_amount_of_total_cloud",
        "cloud_amount_of_low_cloud",
        "visibility_at_screen_level",
        "fog_fraction_at_screen_level",
        "temperature_on_pressure_levels",
        "temperature_at_surface",
        "height_of_orography",
    }
    | {f"precipitation_accumulation-{w}" for w in _WINDOWS}
    | {f"rainfall_accumulation-{w}" for w in _WINDOWS}
    | {f"wind_gust_at_10m_max-{w}" for w in _WINDOWS}
    | {f"temperature_at_screen_level_max-{w}" for w in _WINDOWS}
    | {f"temperature_at_screen_level_min-{w}" for w in _WINDOWS}
)
# Basınç seviyeli parametrelerden yalnız istenen seviye okunur (Pa).
PRESSURE_LEVEL_PA: dict[str, int] = {"temperature_on_pressure_levels": 85000}
# Açısal parametrelerde bilineer ortalama anlamsızdır (spec §8: açı ortalaması alınmaz);
# bu parametrelerde ``bilinear`` boş (NaN) yazılır, ``nearest`` ve ``stencil`` saklanır.
ANGULAR_PARAMS: frozenset[str] = frozenset({"wind_direction_at_10m"})

KEY_RE = re.compile(
    r"^global-deterministic-10km/(?P<run>\d{8}T\d{4}Z)/"
    r"(?P<valid>\d{8}T\d{4}Z)-PT(?P<h>\d{4})H(?P<m>\d{2})M-(?P<param>.+)\.nc$"
)
RUN_RE = re.compile(r"^\d{8}T\d{4}Z$")
_NON_DATA = {"latitude", "longitude", "pressure", "height", "time", "forecast_period"}


class GridMismatch(Exception):
    """Dosyanın ızgarası çalıştırmanın ızgarasıyla aynı değil."""


@dataclass(frozen=True)
class FileRef:
    key: str
    run: datetime
    valid: datetime
    lead_min: int
    param: str


def parse_time(s: str) -> datetime:
    return datetime.strptime(s, "%Y%m%dT%H%MZ").replace(tzinfo=UTC)


def parse_key(key: str) -> FileRef | None:
    """S3 anahtarını çözer. Kalıba uymayan anahtar için None döner."""
    m = KEY_RE.match(key)
    if m is None:
        return None
    run = parse_time(m["run"])
    valid = parse_time(m["valid"])
    lead_min = int(m["h"]) * 60 + int(m["m"])
    if run + timedelta(minutes=lead_min) != valid:
        raise ValueError(f"run + lead != valid in key {key}")
    return FileRef(key=key, run=run, valid=valid, lead_min=lead_min, param=m["param"])


# --------------------------------------------------------------------------- S3 listeleme


def _list(client: httpx.Client, prefix: str, delimiter: str | None) -> tuple[list[str], list[str]]:
    keys: list[str] = []
    prefixes: list[str] = []
    token: str | None = None
    while True:
        url = f"{BUCKET_URL}/?list-type=2&prefix={quote(prefix)}&max-keys=1000"
        if delimiter:
            url += f"&delimiter={quote(delimiter)}"
        if token:
            url += f"&continuation-token={quote(token, safe='')}"
        root = ET.fromstring(get_with_retry(client, url).content)
        keys += [e.text or "" for e in root.iter(f"{S3_NS}Key")]
        prefixes += [e.text or "" for e in root.iter(f"{S3_NS}Prefix") if e.text != prefix]
        token_el = root.find(f"{S3_NS}NextContinuationToken")
        if token_el is None or not token_el.text:
            return keys, prefixes
        token = token_el.text


def list_runs(client: httpx.Client) -> list[str]:
    """Bucket'taki çalıştırma kimliklerini (YYYYMMDDTHHMMZ) eskiden yeniye döndürür."""
    _, prefixes = _list(client, PREFIX, "/")
    runs = [p[len(PREFIX) :].rstrip("/") for p in prefixes]
    return sorted(r for r in runs if RUN_RE.match(r))


def list_run_files(client: httpx.Client, run_id: str) -> list[str]:
    keys, _ = _list(client, f"{PREFIX}{run_id}/", None)
    return keys


# --------------------------------------------------------------------------- ızgara ve stencil


@dataclass(frozen=True)
class GridStencil:
    """Noktaların ızgaradaki 4×4 komşuluğu ve bunları kapsayan okuma kutusu."""

    fingerprint: str
    shape: tuple[int, int]
    box: tuple[int, int, int, int]  # j0, j1, i0, i1 (tam ızgarada, yarı açık)
    point_ids: tuple[str, ...]
    rows: npt.NDArray[np.intp]  # (P, 4) kutu içi satır indisleri
    cols: npt.NDArray[np.intp]  # (P, 4) kutu içi sütun indisleri
    weights: npt.NDArray[np.float64]  # (P, 2, 2) iç 2×2 hücre için bilineer ağırlıklar
    nearest: npt.NDArray[np.intp]  # (P, 2) iç 2×2 içinde en yakın hücre (stencil indisi 1..2)
    cell_table: pa.Table


def grid_fingerprint(lat: npt.NDArray[Any], lon: npt.NDArray[Any]) -> str:
    desc = f"{len(lat)}:{lat[0]:.6f}:{lat[-1]:.6f}:{len(lon)}:{lon[0]:.6f}:{lon[-1]:.6f}"
    return hashlib.sha1(desc.encode()).hexdigest()[:12]


def build_stencil(
    lat: npt.NDArray[Any], lon: npt.NDArray[Any], points: Sequence[Point]
) -> GridStencil:
    lat = np.asarray(lat, dtype=np.float64)
    lon = np.asarray(lon, dtype=np.float64)
    if not (np.all(np.diff(lat) > 0) and np.all(np.diff(lon) > 0)):
        raise ValueError("latitude/longitude must be strictly increasing")
    js: list[int] = []
    is_: list[int] = []
    weights = np.zeros((len(points), 2, 2))
    nearest = np.zeros((len(points), 2), dtype=np.intp)
    for n, p in enumerate(points):
        j = int(np.searchsorted(lat, p.lat, side="right")) - 1
        i = int(np.searchsorted(lon, p.lon, side="right")) - 1
        if j < 1 or i < 1 or j + 2 >= len(lat) or i + 2 >= len(lon):
            raise ValueError(f"point {p.point_id} too close to the grid edge")
        ty = (p.lat - lat[j]) / (lat[j + 1] - lat[j])
        tx = (p.lon - lon[i]) / (lon[i + 1] - lon[i])
        weights[n] = [[(1 - ty) * (1 - tx), (1 - ty) * tx], [ty * (1 - tx), ty * tx]]
        nearest[n] = (1 + int(ty >= 0.5), 1 + int(tx >= 0.5))
        js.append(j)
        is_.append(i)
    j0, j1 = min(js) - 1, max(js) + 3
    i0, i1 = min(is_) - 1, max(is_) + 3
    offs = np.arange(-1, 3)
    rows = np.array([[j - j0 + o for o in offs] for j in js], dtype=np.intp)
    cols = np.array([[i - i0 + o for o in offs] for i in is_], dtype=np.intp)

    recs: dict[str, list[Any]] = {
        k: []
        for k in (
            "point_id", "kind", "lat", "lon", "elevation_m", "coastal", "k",
            "grid_j", "grid_i", "cell_lat", "cell_lon", "bilinear_weight", "is_nearest",
        )
    }  # fmt: skip
    for n, p in enumerate(points):
        for a in range(4):
            for b in range(4):
                gj, gi = j0 + rows[n, a], i0 + cols[n, b]
                inner = 1 <= a <= 2 and 1 <= b <= 2
                recs["point_id"].append(p.point_id)
                recs["kind"].append(p.kind)
                recs["lat"].append(p.lat)
                recs["lon"].append(p.lon)
                recs["elevation_m"].append(p.elevation_m)
                recs["coastal"].append(p.coastal)
                recs["k"].append(a * 4 + b)
                recs["grid_j"].append(int(gj))
                recs["grid_i"].append(int(gi))
                recs["cell_lat"].append(float(lat[gj]))
                recs["cell_lon"].append(float(lon[gi]))
                recs["bilinear_weight"].append(float(weights[n, a - 1, b - 1]) if inner else 0.0)
                recs["is_nearest"].append(bool((a, b) == tuple(nearest[n])))
    return GridStencil(
        fingerprint=grid_fingerprint(lat, lon),
        shape=(len(lat), len(lon)),
        box=(j0, j1, i0, i1),
        point_ids=tuple(p.point_id for p in points),
        rows=rows,
        cols=cols,
        weights=weights,
        nearest=nearest,
        cell_table=pa.table(recs),
    )


def point_values(
    stencil: GridStencil, box_values: npt.NDArray[Any]
) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.float32], npt.NDArray[np.float32]]:
    """Kutu değerlerinden nokta başına (stencil[16], en yakın, bilineer) üretir.

    Bilineer değer maskesizdir; iç 2×2 hücreden biri eksikse (NaN) sonuç NaN olur.
    """
    v = np.asarray(box_values, dtype=np.float64)
    st = v[stencil.rows[:, :, None], stencil.cols[:, None, :]]  # (P, 4, 4)
    bil = np.sum(st[:, 1:3, 1:3] * stencil.weights, axis=(1, 2))
    idx = np.arange(len(stencil.point_ids))
    near = st[idx, stencil.nearest[:, 0], stencil.nearest[:, 1]]
    return (
        st.reshape(len(idx), 16).astype(np.float32),
        near.astype(np.float32),
        bil.astype(np.float32),
    )


# --------------------------------------------------------------------------- dosya okuma


def _attr_str(ds: Any, name: str) -> str | None:
    val = ds.attrs.get(name)
    if val is None:
        return None
    if isinstance(val, bytes | np.bytes_):
        return val.decode()
    return str(val)


def _main_variable(h: Any) -> str:
    # Basınç seviyeli dosyalarda ana değişkenin yanında yüzey altı durumunu gösteren bir
    # ``flag`` (ancillary, flag_values/flag_meanings) değişkeni bulunur; o hariç tutulur.
    cands = [
        name
        for name, obj in h.items()
        if isinstance(obj, h5py.Dataset)
        and obj.ndim >= 2
        and min(obj.shape[-2:]) > 100
        and name not in _NON_DATA
        and "flag_values" not in obj.attrs
    ]
    if len(cands) != 1:
        raise ValueError(f"expected exactly one data variable, found {cands}")
    return str(cands[0])


def _level_index(h: Any, ds: Any, level_pa: int) -> int:
    if "pressure" not in h:
        raise ValueError("pressure coordinate not found")
    levels = np.asarray(h["pressure"][:], dtype=np.float64)
    units = (_attr_str(h["pressure"], "units") or "Pa").lower()
    if units in ("hpa", "mbar", "mb"):
        levels = levels * 100.0
    if len(levels) != ds.shape[0]:
        raise ValueError("pressure coordinate length mismatch")
    hits = np.flatnonzero(np.abs(levels - level_pa) < 1.0)
    if len(hits) != 1:
        raise ValueError(f"level {level_pa} Pa not found")
    return int(hits[0])


def _unpack(ds: Any, arr: npt.NDArray[Any]) -> npt.NDArray[np.float32]:
    out = arr.astype(np.float64)
    for name in ("_FillValue", "missing_value"):
        fill = ds.attrs.get(name)
        if fill is not None:
            out[arr == np.asarray(fill).item()] = np.nan
    scale = ds.attrs.get("scale_factor")
    offset = ds.attrs.get("add_offset")
    if scale is not None:
        out = out * float(np.asarray(scale).item())
    if offset is not None:
        out = out + float(np.asarray(offset).item())
    return out.astype(np.float32)


def read_grid(client: httpx.Client, key: str) -> tuple[npt.NDArray[Any], npt.NDArray[Any]]:
    f = HttpRangeFile.open(client, f"{BUCKET_URL}/{key}")
    with h5py.File(f, "r") as h:
        return np.asarray(h["latitude"][:]), np.asarray(h["longitude"][:])


_WORKER_CLIENT: httpx.Client | None = None


def _init_worker(user_agent: str) -> None:
    global _WORKER_CLIENT
    _WORKER_CLIENT = httpx.Client(timeout=60.0, headers={"User-Agent": user_agent})


def extract_box(
    key: str, param: str, box: tuple[int, int, int, int], shape: tuple[int, int]
) -> dict[str, Any]:
    """Süreç havuzu işçisi: tek dosyadan okuma kutusunu döndürür."""
    assert _WORKER_CLIENT is not None
    j0, j1, i0, i1 = box
    f = HttpRangeFile.open(_WORKER_CLIENT, f"{BUCKET_URL}/{key}")
    level_pa: int | None = None
    with h5py.File(f, "r") as h:
        name = _main_variable(h)
        ds = h[name]
        if tuple(ds.shape[-2:]) != shape:
            raise GridMismatch(f"{key}: {ds.shape} != {shape}")
        if ds.ndim == 3:
            level_pa = PRESSURE_LEVEL_PA.get(param)
            if level_pa is None:
                raise ValueError(f"unexpected 3-D parameter {param}")
            raw = ds[_level_index(h, ds, level_pa), j0:j1, i0:i1]
        elif ds.ndim == 2:
            raw = ds[j0:j1, i0:i1]
        else:
            raise ValueError(f"unexpected rank {ds.ndim}")
        values = _unpack(ds, np.asarray(raw))
        units = _attr_str(ds, "units")
        cell_methods = _attr_str(ds, "cell_methods")
    return {
        "key": key,
        "values": values,
        "units": units,
        "cell_methods": cell_methods,
        "variable": name,
        "level_pa": level_pa,
        "requests": f.requests,
        "bytes": f.bytes_read,
    }


# --------------------------------------------------------------------------- çalıştırma işleme


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def read_manifest(out: Path, run_id: str) -> dict[str, Any] | None:
    p = out / "manifest" / f"{run_id}.json"
    if not p.exists():
        return None
    data: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    return data


def needs_processing(out: Path, run_id: str) -> bool:
    m = read_manifest(out, run_id)
    if m is None:
        return True
    if m["status"] in ("complete", "lost", "empty"):
        return False
    return int(m.get("attempts", 1)) < MAX_ATTEMPTS


def _points_table(
    stencil: GridStencil, refs: dict[str, FileRef], results: Iterable[dict[str, Any]]
) -> pa.Table:
    cols: dict[str, list[Any]] = {
        k: []
        for k in (
            "init_time", "valid_time", "lead_min", "param", "level_pa", "units",
            "cell_methods", "point_id", "nearest", "bilinear", "stencil", "source_key",
        )
    }  # fmt: skip
    n_pts = len(stencil.point_ids)
    for res in results:
        ref = refs[res["key"]]
        st, near, bil = point_values(stencil, res["values"])
        if ref.param in ANGULAR_PARAMS:
            bil = np.full_like(bil, np.nan)
        cols["init_time"] += [ref.run] * n_pts
        cols["valid_time"] += [ref.valid] * n_pts
        cols["lead_min"] += [ref.lead_min] * n_pts
        cols["param"] += [ref.param] * n_pts
        cols["level_pa"] += [res["level_pa"]] * n_pts
        cols["units"] += [res["units"]] * n_pts
        cols["cell_methods"] += [res["cell_methods"]] * n_pts
        cols["point_id"] += list(stencil.point_ids)
        cols["nearest"] += near.tolist()
        cols["bilinear"] += bil.tolist()
        cols["stencil"] += [row.tolist() for row in st]
        cols["source_key"] += [ref.key] * n_pts
    ts = pa.timestamp("s", tz="UTC")
    schema = pa.schema(
        [
            ("init_time", ts),
            ("valid_time", ts),
            ("lead_min", pa.int32()),
            ("param", pa.dictionary(pa.int16(), pa.string())),
            ("level_pa", pa.int32()),
            ("units", pa.dictionary(pa.int16(), pa.string())),
            ("cell_methods", pa.dictionary(pa.int16(), pa.string())),
            ("point_id", pa.dictionary(pa.int16(), pa.string())),
            ("nearest", pa.float32()),
            ("bilinear", pa.float32()),
            ("stencil", pa.list_(pa.float32(), 16)),
            ("source_key", pa.string()),
        ],
        metadata={
            "model": MODEL_CODE,
            "source": f"{BUCKET_URL}/{PREFIX}",
            "license": LICENSE,
            "extractor": EXTRACTOR_VERSION,
            "hava_version": __version__,
            "stencil_fingerprint": stencil.fingerprint,
        },
    )
    return pa.table(cols, schema=schema)


def process_run(
    client: httpx.Client,
    pool: ProcessPoolExecutor,
    out: Path,
    run_id: str,
    points: Sequence[Point],
    stencils: dict[str, GridStencil],
) -> dict[str, Any]:
    started = time.time()
    prev = read_manifest(out, run_id)
    attempts = int(prev.get("attempts", 0)) + 1 if prev else 1
    manifest: dict[str, Any] = {
        "run": run_id,
        "model": MODEL_CODE,
        "extractor": EXTRACTOR_VERSION,
        "attempts": attempts,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    keys = list_run_files(client, run_id)
    refs: dict[str, FileRef] = {}
    for key in keys:
        ref = parse_key(key)
        if ref is not None and ref.param in WANTED_PARAMS:
            refs[key] = ref
    manifest["files_listed"] = len(keys)
    manifest["files_wanted"] = len(refs)
    manifest["params_missing"] = sorted(WANTED_PARAMS - {r.param for r in refs.values()})
    if not refs:
        manifest["status"] = "lost" if not keys else "empty"
        _finish(out, run_id, manifest, started)
        return manifest

    try:
        first = min(refs)
        lat, lon = read_grid(client, first)
    except RemoteFileGone:
        manifest["status"] = "lost"
        _finish(out, run_id, manifest, started)
        return manifest
    fp = grid_fingerprint(lat, lon)
    if fp not in stencils:
        stencils[fp] = build_stencil(lat, lon, points)
        path = out / "stencils" / f"{fp}.parquet"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(stencils[fp].cell_table, path)
    stencil = stencils[fp]
    manifest["stencil_fingerprint"] = fp

    futures: dict[Future[dict[str, Any]], str] = {
        pool.submit(extract_box, key, ref.param, stencil.box, stencil.shape): key
        for key, ref in refs.items()
    }
    results: list[dict[str, Any]] = []
    gone: list[str] = []
    failed: dict[str, str] = {}
    for fut in as_completed(futures):
        key = futures[fut]
        try:
            results.append(fut.result())
        except RemoteFileGone:
            gone.append(key)
        except Exception as exc:  # her hata kaydedilir, iş durmaz
            failed[key] = f"{type(exc).__name__}: {exc}"[:500]

    results.sort(key=lambda r: (refs[r["key"]].param, refs[r["key"]].lead_min))
    if results:
        table = _points_table(stencil, refs, results)
        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, compression="zstd", use_dictionary=True)
        _write_atomic(out / "runs" / f"{run_id}.parquet", sink.getvalue().to_pybytes())
        manifest["rows"] = table.num_rows
    manifest["files_ok"] = len(results)
    manifest["files_gone"] = len(gone)
    manifest["files_failed"] = len(failed)
    manifest["failures"] = dict(list(failed.items())[:50])
    manifest["requests"] = sum(r["requests"] for r in results)
    manifest["bytes"] = sum(r["bytes"] for r in results)
    if not failed and not gone:
        manifest["status"] = "complete"
    elif not results:
        manifest["status"] = "lost" if gone and not failed else "partial"
    else:
        manifest["status"] = "partial"
    _finish(out, run_id, manifest, started)
    return manifest


def _finish(out: Path, run_id: str, manifest: dict[str, Any], started: float) -> None:
    manifest["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    manifest["seconds"] = round(time.time() - started, 1)
    data = json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8")
    _write_atomic(out / "manifest" / f"{run_id}.json", data)
    log.info(
        "run %s status=%s ok=%s failed=%s gone=%s MB=%.1f req=%s s=%.0f",
        run_id,
        manifest["status"],
        manifest.get("files_ok", 0),
        manifest.get("files_failed", 0),
        manifest.get("files_gone", 0),
        manifest.get("bytes", 0) / 1e6,
        manifest.get("requests", 0),
        manifest["seconds"],
    )


# --------------------------------------------------------------------------- CLI


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--region", default="config/region.istanbul.yaml")
    ap.add_argument("--out", default=".data/ukmo_global")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--follow", action="store_true", help="bitince yeni çalıştırmaları bekle")
    ap.add_argument("--poll-minutes", type=float, default=30.0)
    ap.add_argument("--max-runs", type=int, default=None, help="bu geçişte en fazla N çalıştırma")
    ap.add_argument("--since", default=None, help="YYYYMMDDTHHMMZ (dahil)")
    ap.add_argument("--until", default=None, help="YYYYMMDDTHHMMZ (dahil)")
    ap.add_argument(
        "--user-agent",
        default=os.environ.get("HAVA_HTTP_USER_AGENT") or f"istweather/{__version__}",
    )
    return ap.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(out / "backfill.log", encoding="utf-8"),
        ],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    points = load_region(args.region).points
    stencils: dict[str, GridStencil] = {}
    log.info("start out=%s points=%d workers=%d", out, len(points), args.workers)
    with (
        httpx.Client(timeout=60.0, headers={"User-Agent": args.user_agent}) as client,
        ProcessPoolExecutor(
            args.workers, initializer=_init_worker, initargs=(args.user_agent,)
        ) as pool,
    ):
        while True:
            runs = list_runs(client)
            pending = [
                r
                for r in runs
                if (args.since is None or r >= args.since)
                and (args.until is None or r <= args.until)
                and needs_processing(out, r)
            ]
            if args.max_runs is not None:
                pending = pending[: args.max_runs]
            log.info(
                "runs listed=%d oldest=%s pending=%d",
                len(runs),
                runs[0] if runs else None,
                len(pending),
            )
            for run_id in pending:
                try:
                    process_run(client, pool, out, run_id, points, stencils)
                except Exception:
                    log.exception("run %s failed", run_id)
            if not args.follow:
                return 0
            time.sleep(args.poll_minutes * 60)


if __name__ == "__main__":
    sys.exit(main())
