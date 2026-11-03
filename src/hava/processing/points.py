"""Izgaradan noktaya değer çıkarımı (spec §6).

- Düzenli ızgara: bilineer ağırlıklar nokta çevresindeki 2×2 hücreden; komşuluk 4×4.
- Üçgen (yapısal olmayan) ızgara: hücre merkezlerinin Delaunay üçgenlemesinde noktayı içeren
  üçgenin köşelerinden doğrusal (barisentrik) ağırlıklar; bilineerin karşılığı. Komşuluk en yakın
  ``UNSTRUCTURED_K`` hücre.
- Kara-deniz maskeli seçim: noktalar karada olduğu için deniz hücreleri (kara oranı < 0,5)
  dışlanır ve kalan ağırlıklar yeniden ölçeklenir. Ağırlıklı hücrelerde kara yoksa komşulukta en
  yakın kara hücresi alınır; orada da yoksa maskesiz ağırlık kullanılır ve bu kaydedilir.
- Sıcaklıkta yükseklik düzeltmesi: T_nokta = T_model + γ · (z_model − z_nokta), γ = 6,5 °C/km.
- Kategorik alanlar (ör. yağış tipi) interpolasyon yapılmadan seçilen kara hücresinden alınır.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.spatial import Delaunay, cKDTree

from hava.processing.grid import FloatArray, RegularGrid, UnstructuredGrid
from hava.region import Point

LAND_THRESHOLD = 0.5
LAPSE_RATE = 0.0065  # °C/m, başlangıç değeri (spec §6); veriyle kalibre edilecek
UNSTRUCTURED_K = 12  # üçgen ızgarada komşuluk (4×4 düzenli komşuluğun karşılığı)

METHOD_LSM = "lsm_bilinear"
METHOD_NEAREST_LAND = "lsm_nearest_land"
METHOD_UNMASKED = "unmasked"


@dataclass(frozen=True)
class PointWeights:
    """Nokta başına komşuluk hücreleri (kırpılmış alanın düzleştirilmiş indisleri) ve ağırlıklar."""

    point_ids: tuple[str, ...]
    elevation_m: FloatArray  # (P,) noktanın gerçek yüksekliği
    cells: npt.NDArray[np.intp]  # (P, K)
    linear: FloatArray  # (P, K) maskesiz bilineer / barisentrik
    masked: FloatArray  # (P, K) kara-deniz maskeli
    method: tuple[str, ...]
    cat_cell: npt.NDArray[np.intp]  # (P,) kategorik alanlar için seçilen hücre

    def neighbourhood(self, field: npt.NDArray[np.float64]) -> FloatArray:
        """(P, K) komşuluk değerleri."""
        return np.asarray(field, dtype=np.float64).reshape(-1)[self.cells]

    def interpolate(self, field: npt.NDArray[np.float64], masked: bool = True) -> FloatArray:
        """Ağırlığı sıfır olan hücrelerdeki eksik değer sonucu bozmaz."""
        w = self.masked if masked else self.linear
        terms = np.where(w > 0, self.neighbourhood(field) * w, 0.0)
        return np.asarray(terms.sum(axis=1), dtype=np.float64)

    def categorical(self, field: npt.NDArray[np.float64]) -> FloatArray:
        return np.asarray(field, dtype=np.float64).reshape(-1)[self.cat_cell]


def build_weights(
    grid: RegularGrid | UnstructuredGrid,
    points: Sequence[Point],
    land_fraction: npt.NDArray[np.float64] | None,
) -> PointWeights:
    """``land_fraction`` (kırpılmış ızgarada 0–1) verilmezse maskesiz ağırlık kullanılır."""
    if isinstance(grid, UnstructuredGrid):
        cells, linear, dist2 = _unstructured_neighbourhood(grid, points)
    else:
        cells, linear, dist2 = _regular_neighbourhood(grid, points)
    land = None
    if land_fraction is not None:
        land = np.asarray(land_fraction, dtype=np.float64).reshape(-1)[cells] >= LAND_THRESHOLD
    masked = np.zeros_like(linear)
    cat = np.zeros(len(points), dtype=np.intp)
    methods: list[str] = []
    for k in range(len(points)):
        nearest = int(np.argmax(linear[k]))
        if land is None:
            masked[k], cat[k] = linear[k], cells[k, nearest]
            methods.append(METHOD_UNMASKED)
            continue
        inner = linear[k] * land[k]
        if inner.sum() > 0:
            masked[k] = inner / inner.sum()
            cat[k] = cells[k, int(np.argmax(masked[k]))]
            methods.append(METHOD_LSM)
        elif land[k].any():
            # Ağırlıklı hücrelerde kara yok: komşulukta noktaya en yakın kara hücresi.
            best = int(np.argmin(np.where(land[k], dist2[k], np.inf)))
            masked[k, best] = 1.0
            cat[k] = cells[k, best]
            methods.append(METHOD_NEAREST_LAND)
        else:
            masked[k], cat[k] = linear[k], cells[k, nearest]
            methods.append(METHOD_UNMASKED)
    return PointWeights(
        point_ids=tuple(p.point_id for p in points),
        elevation_m=np.array([p.elevation_m for p in points], dtype=np.float64),
        cells=cells,
        linear=linear,
        masked=masked,
        method=tuple(methods),
        cat_cell=cat,
    )


def _regular_neighbourhood(
    grid: RegularGrid, points: Sequence[Point]
) -> tuple[npt.NDArray[np.intp], FloatArray, FloatArray]:
    """4×4 komşuluk (düzleştirilmiş), bilineer ağırlıklar (iç 2×2) ve noktaya uzaklık²."""
    lat, lon = grid.lat, grid.lon
    n = len(points)
    cells = np.zeros((n, 16), dtype=np.intp)
    linear = np.zeros((n, 16))
    dist2 = np.zeros((n, 16))
    for k, p in enumerate(points):
        j = int(np.searchsorted(lat, p.lat, side="right")) - 1
        i = int(np.searchsorted(lon, p.lon, side="right")) - 1
        if j < 1 or i < 1 or j + 2 >= len(lat) or i + 2 >= len(lon):
            raise ValueError(f"nokta {p.point_id} kırpılmış ızgaranın kenarına çok yakın")
        ty = (p.lat - lat[j]) / (lat[j + 1] - lat[j])
        tx = (p.lon - lon[i]) / (lon[i + 1] - lon[i])
        rows, cols = np.arange(j - 1, j + 3), np.arange(i - 1, i + 3)
        cells[k] = (rows[:, None] * len(lon) + cols[None, :]).ravel()
        w = np.zeros((4, 4))
        w[1:3, 1:3] = [[(1 - ty) * (1 - tx), (1 - ty) * tx], [ty * (1 - tx), ty * tx]]
        linear[k] = w.ravel()
        coslat = math.cos(math.radians(p.lat))
        dlat = lat[rows][:, None] - p.lat
        dlon = (lon[cols][None, :] - p.lon) * coslat
        dist2[k] = (dlat**2 + dlon**2).ravel()
    return cells, linear, dist2


def _unstructured_neighbourhood(
    grid: UnstructuredGrid, points: Sequence[Point]
) -> tuple[npt.NDArray[np.intp], FloatArray, FloatArray]:
    """En yakın K hücre (ilk üçü noktayı içeren üçgenin köşeleri), barisentrik ağırlıklar."""
    coslat = math.cos(math.radians(float(np.mean(grid.lat))))
    xy = np.column_stack([grid.lon * coslat, grid.lat])
    tri = Delaunay(xy)
    tree = cKDTree(xy)
    k_max = min(UNSTRUCTURED_K, len(xy))
    n = len(points)
    cells = np.zeros((n, k_max), dtype=np.intp)
    linear = np.zeros((n, k_max))
    dist2 = np.zeros((n, k_max))
    for k, p in enumerate(points):
        q = np.array([p.lon * coslat, p.lat])
        simplex = int(tri.find_simplex(q))
        if simplex < 0:
            raise ValueError(f"nokta {p.point_id} kırpılmış hücrelerin dışında")
        verts = tri.simplices[simplex]
        t = tri.transform[simplex]
        b = t[:2] @ (q - t[2])
        bary = np.array([b[0], b[1], 1.0 - b[0] - b[1]])
        _, near = tree.query(q, k=k_max)
        rest = [int(c) for c in np.atleast_1d(near) if int(c) not in set(verts.tolist())]
        chosen = np.array([*verts.tolist(), *rest][:k_max], dtype=np.intp)
        cells[k] = chosen
        linear[k, :3] = np.clip(bary, 0.0, 1.0) / np.clip(bary, 0.0, 1.0).sum()
        dist2[k] = ((xy[chosen] - q) ** 2).sum(axis=1)
    return cells, linear, dist2


def lapse_correction(model_orography_m: FloatArray, point_elevation_m: FloatArray) -> FloatArray:
    """Sıcaklığa eklenecek düzeltme (°C): model arazisi noktadan yüksekse nokta daha sıcaktır."""
    return LAPSE_RATE * (np.asarray(model_orography_m) - np.asarray(point_elevation_m))
