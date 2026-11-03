"""Model ızgaraları ve bölge kırpma.

- Düzenli enlem-boylam: içeride her zaman güneyden kuzeye (enlem artan) ve batıdan doğuya (boylam
  artan) tutulur; kaynak dosyanın tarama yönü ``Crop.apply`` içinde düzeltilir.
- Yapısal olmayan (ör. ICON üçgen ızgarası): hücre merkezleri ``CLAT/CLON``'dan; kutudaki hücreler
  indisleriyle seçilir (``CellCrop``).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class BBox:
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    def expanded(self, margin: float) -> BBox:
        return BBox(
            self.lat_min - margin,
            self.lat_max + margin,
            self.lon_min - margin,
            self.lon_max + margin,
        )


@dataclass(frozen=True)
class RegularGrid:
    lat: FloatArray  # artan
    lon: FloatArray  # artan

    @property
    def shape(self) -> tuple[int, int]:
        return (len(self.lat), len(self.lon))

    def fingerprint(self) -> str:
        lat, lon = self.lat, self.lon
        desc = f"{len(lat)}:{lat[0]:.5f}:{lat[-1]:.5f}:{len(lon)}:{lon[0]:.5f}:{lon[-1]:.5f}"
        return hashlib.sha1(desc.encode()).hexdigest()[:12]


@dataclass(frozen=True)
class Crop:
    """Kaynak ızgaradan bir kutunun alınması (tarama yönü düzeltmesiyle)."""

    source_shape: tuple[int, int]  # (Nj, Ni) dosyadaki satır × sütun
    lat_reversed: bool  # dosyada satırlar kuzeyden güneye mi
    rows: slice  # yönü düzeltilmiş tam ızgarada
    cols: slice
    grid: RegularGrid  # kırpılmış ızgara

    def apply(self, values: npt.NDArray[Any]) -> FloatArray:
        v = np.asarray(values, dtype=np.float64).reshape(self.source_shape)
        if self.lat_reversed:
            v = v[::-1, :]
        return np.ascontiguousarray(v[self.rows, self.cols])


def crop_grid(lat_native: FloatArray, lon_native: FloatArray, bbox: BBox) -> Crop:
    """Dosyadaki eksenlerden (``lat_native`` dosya sırasıyla) kutuyu kapsayan kırpmayı kurar."""
    lat_native = np.asarray(lat_native, dtype=np.float64)
    lon_native = np.asarray(lon_native, dtype=np.float64)
    reversed_ = bool(lat_native[0] > lat_native[-1])
    lat = lat_native[::-1] if reversed_ else lat_native
    if np.any(np.diff(lon_native) <= 0):
        raise ValueError("boylam ekseni artan olmalı")
    lon_min, lon_max = bbox.lon_min, bbox.lon_max
    if lon_native.min() >= 0 and lon_min < 0:  # 0..360 ızgarası
        lon_min, lon_max = lon_min % 360, lon_max % 360
    j0 = int(np.searchsorted(lat, bbox.lat_min, side="right")) - 1
    j1 = int(np.searchsorted(lat, bbox.lat_max, side="left")) + 1
    i0 = int(np.searchsorted(lon_native, lon_min, side="right")) - 1
    i1 = int(np.searchsorted(lon_native, lon_max, side="left")) + 1
    if j0 < 0 or i0 < 0 or j1 > len(lat) or i1 > len(lon_native):
        raise ValueError("kutu ızgaranın dışına taşıyor")
    sub = RegularGrid(lat[j0:j1].copy(), lon_native[i0:i1].copy())
    return Crop((len(lat), len(lon_native)), reversed_, slice(j0, j1), slice(i0, i1), sub)


@dataclass(frozen=True)
class UnstructuredGrid:
    lat: FloatArray  # (N,) kırpılmış hücre merkezleri
    lon: FloatArray  # (N,) −180…180
    grid_id: str  # kaynak ızgara kimliği (ICON: GRIB ``uuidOfHGrid``)

    @property
    def shape(self) -> tuple[int]:
        return (len(self.lat),)

    def fingerprint(self) -> str:
        desc = f"{self.grid_id}:{len(self.lat)}"
        return hashlib.sha1(desc.encode()).hexdigest()[:12]


@dataclass(frozen=True)
class CellCrop:
    """Yapısal olmayan ızgaradan kutudaki hücrelerin alınması."""

    source_size: int  # dosyadaki hücre sayısı
    cells: npt.NDArray[np.intp]  # kaynak dizideki indisler
    grid: UnstructuredGrid

    def apply(self, values: npt.NDArray[Any]) -> FloatArray:
        v = np.asarray(values, dtype=np.float64).reshape(-1)
        if v.size != self.source_size:
            raise ValueError(f"hücre sayısı {v.size} != {self.source_size}")
        return np.ascontiguousarray(v[self.cells])


def crop_cells(lat: FloatArray, lon: FloatArray, bbox: BBox, grid_id: str) -> CellCrop:
    """Hücre merkezleri (derece) kutunun içinde kalan hücreleri seçer."""
    lat = np.asarray(lat, dtype=np.float64).reshape(-1)
    lon = np.asarray(lon, dtype=np.float64).reshape(-1)
    if lat.shape != lon.shape:
        raise ValueError("CLAT/CLON boyutları farklı")
    lon = np.where(lon >= 180.0, lon - 360.0, lon)
    inside = (
        (lat >= bbox.lat_min)
        & (lat <= bbox.lat_max)
        & (lon >= bbox.lon_min)
        & (lon <= bbox.lon_max)
    )
    cells = np.flatnonzero(inside).astype(np.intp)
    if cells.size < 3:
        raise ValueError("kutuda yeterli hücre yok")
    grid = UnstructuredGrid(lat[cells].copy(), lon[cells].copy(), grid_id)
    return CellCrop(lat.size, cells, grid)
