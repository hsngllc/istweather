"""Izgaradan noktaya değer çıkarımı (spec §6).

- Bilineer ağırlıklar nokta çevresindeki 2×2 hücreden.
- Kara-deniz maskeli seçim: noktalar karada olduğu için deniz hücreleri (kara oranı < 0,5)
  dışlanır ve kalan ağırlıklar yeniden ölçeklenir. İç 2×2'de kara yoksa 4×4 komşulukta en yakın
  kara hücresi alınır; orada da yoksa maskesiz bilineer kullanılır ve bu kaydedilir.
- Sıcaklıkta yükseklik düzeltmesi: T_nokta = T_model + γ · (z_model − z_nokta), γ = 6,5 °C/km.
- Kategorik alanlar (ör. yağış tipi) interpolasyon yapılmadan seçilen kara hücresinden alınır.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from hava.processing.grid import FloatArray, RegularGrid
from hava.region import Point

LAND_THRESHOLD = 0.5
LAPSE_RATE = 0.0065  # °C/m, başlangıç değeri (spec §6); veriyle kalibre edilecek

METHOD_LSM = "lsm_bilinear"
METHOD_NEAREST_LAND = "lsm_nearest_land"
METHOD_UNMASKED = "unmasked"


@dataclass(frozen=True)
class PointWeights:
    point_ids: tuple[str, ...]
    elevation_m: FloatArray  # (P,) noktanın gerçek yüksekliği
    rows: npt.NDArray[np.intp]  # (P, 4) kırpılmış ızgarada 4×4 komşuluk satırları
    cols: npt.NDArray[np.intp]  # (P, 4)
    bilinear: FloatArray  # (P, 4, 4) maskesiz bilineer (yalnız iç 2×2 dolu)
    masked: FloatArray  # (P, 4, 4) kara-deniz maskeli
    method: tuple[str, ...]
    cat_cell: npt.NDArray[np.intp]  # (P, 2) kategorik alanlar için seçilen hücre (stencil içi a, b)

    def stencil(self, field: npt.NDArray[np.float64]) -> FloatArray:
        """(P, 4, 4) komşuluk değerleri."""
        return np.asarray(field, dtype=np.float64)[self.rows[:, :, None], self.cols[:, None, :]]

    def interpolate(self, field: npt.NDArray[np.float64], masked: bool = True) -> FloatArray:
        w = self.masked if masked else self.bilinear
        return np.asarray(np.einsum("pab,pab->p", self.stencil(field), w), dtype=np.float64)

    def categorical(self, field: npt.NDArray[np.float64]) -> FloatArray:
        st = self.stencil(field)
        idx = np.arange(len(self.point_ids))
        return st[idx, self.cat_cell[:, 0], self.cat_cell[:, 1]]


def build_weights(
    grid: RegularGrid, points: Sequence[Point], land_fraction: npt.NDArray[np.float64] | None
) -> PointWeights:
    """``land_fraction`` (kırpılmış ızgarada 0–1) verilmezse maskesiz bilineer kullanılır."""
    lat, lon = grid.lat, grid.lon
    n = len(points)
    rows = np.zeros((n, 4), dtype=np.intp)
    cols = np.zeros((n, 4), dtype=np.intp)
    bil = np.zeros((n, 4, 4))
    masked = np.zeros((n, 4, 4))
    cat = np.zeros((n, 2), dtype=np.intp)
    methods: list[str] = []
    for k, p in enumerate(points):
        j = int(np.searchsorted(lat, p.lat, side="right")) - 1
        i = int(np.searchsorted(lon, p.lon, side="right")) - 1
        if j < 1 or i < 1 or j + 2 >= len(lat) or i + 2 >= len(lon):
            raise ValueError(f"nokta {p.point_id} kırpılmış ızgaranın kenarına çok yakın")
        ty = (p.lat - lat[j]) / (lat[j + 1] - lat[j])
        tx = (p.lon - lon[i]) / (lon[i + 1] - lon[i])
        rows[k] = np.arange(j - 1, j + 3)
        cols[k] = np.arange(i - 1, i + 3)
        bil[k, 1:3, 1:3] = [[(1 - ty) * (1 - tx), (1 - ty) * tx], [ty * (1 - tx), ty * tx]]
        if land_fraction is None:
            masked[k] = bil[k]
            cat[k] = (1 + int(ty >= 0.5), 1 + int(tx >= 0.5))
            methods.append(METHOD_UNMASKED)
            continue
        land = np.asarray(land_fraction)[rows[k][:, None], cols[k][None, :]] >= LAND_THRESHOLD
        inner = bil[k] * land
        if inner.sum() > 0:
            masked[k] = inner / inner.sum()
            top = int(np.argmax(masked[k]))
            cat[k] = (top // 4, top % 4)
            methods.append(METHOD_LSM)
            continue
        # İç 2×2'de kara yok: 4×4 komşulukta noktaya en yakın kara hücresi.
        coslat = math.cos(math.radians(p.lat))
        best: tuple[float, int, int] | None = None
        for a in range(4):
            for b in range(4):
                if land[a, b]:
                    dlat = float(lat[rows[k][a]]) - p.lat
                    dlon = (float(lon[cols[k][b]]) - p.lon) * coslat
                    d = dlat**2 + dlon**2
                    if best is None or d < best[0]:
                        best = (d, a, b)
        if best is not None:
            masked[k, best[1], best[2]] = 1.0
            cat[k] = (best[1], best[2])
            methods.append(METHOD_NEAREST_LAND)
        else:
            masked[k] = bil[k]
            cat[k] = (1 + int(ty >= 0.5), 1 + int(tx >= 0.5))
            methods.append(METHOD_UNMASKED)
    return PointWeights(
        point_ids=tuple(p.point_id for p in points),
        elevation_m=np.array([p.elevation_m for p in points], dtype=np.float64),
        rows=rows,
        cols=cols,
        bilinear=bil,
        masked=masked,
        method=tuple(methods),
        cat_cell=cat,
    )


def lapse_correction(model_orography_m: FloatArray, point_elevation_m: FloatArray) -> FloatArray:
    """Sıcaklığa eklenecek düzeltme (°C): model arazisi noktadan yüksekse nokta daha sıcaktır."""
    return LAPSE_RATE * (np.asarray(model_orography_m) - np.asarray(point_elevation_m))
