"""Nokta çıkarımı: bilineer, kara-deniz maskeli seçim, yükseklik düzeltmesi (spec §13 zorunlu test).

Izgaralar ve alanlar sentetiktir.
"""

import numpy as np
import pytest

from hava.processing.grid import BBox, crop_cells, crop_grid
from hava.processing.points import (
    METHOD_LSM,
    METHOD_NEAREST_LAND,
    METHOD_UNMASKED,
    build_weights,
    lapse_correction,
)
from hava.region import Point

LAT = np.arange(40.0, 42.01, 0.25)  # 9 satır
LON = np.arange(28.0, 30.01, 0.25)  # 9 sütun
GRID = crop_grid(LAT, LON, BBox(40.0, 42.0, 28.0, 30.0)).grid


def _pt(lat: float, lon: float, elev: float = 0.0) -> Point:
    return Point(f"synthetic:{lat}:{lon}", "district", lat, lon, elev, True)


def linear_field(a: float = 2.0, b: float = -3.0, c: float = 10.0) -> np.ndarray:
    return c + a * GRID.lat[:, None] + b * GRID.lon[None, :]


def test_bilinear_is_exact_on_linear_field_without_mask() -> None:
    pts = [_pt(41.1, 29.05), _pt(40.6, 28.7)]
    pw = build_weights(GRID, pts, None)
    got = pw.interpolate(linear_field())
    want = [10 + 2 * p.lat - 3 * p.lon for p in pts]
    np.testing.assert_allclose(got, want, atol=1e-9)
    assert pw.method == (METHOD_UNMASKED, METHOD_UNMASKED)


def test_sea_cells_are_excluded_and_weights_renormalised() -> None:
    p = _pt(41.1, 29.1)  # hücre (41.0–41.25) × (29.0–29.25)
    land = np.ones(GRID.shape)
    j, i = 4, 4  # 41.0, 29.0
    land[j + 1, i + 1] = 0.0  # kuzeydoğu köşe deniz
    field = np.zeros(GRID.shape)
    field[j + 1, i + 1] = 100.0  # deniz hücresi çok farklı
    pw = build_weights(GRID, [p], land)
    assert pw.method == (METHOD_LSM,)
    assert pw.interpolate(field)[0] == pytest.approx(0.0)  # deniz hücresi hiç etki etmiyor
    assert pw.interpolate(field, masked=False)[0] > 0  # maskesizde etki ediyor
    assert pw.masked[0].sum() == pytest.approx(1.0)


def test_nearest_land_when_inner_cells_are_all_sea() -> None:
    p = _pt(41.1, 29.1)
    land = np.zeros(GRID.shape)
    land[3, 4] = 1.0  # iç 2×2'nin dışında (40.75, 29.0) tek kara hücresi
    field = np.arange(GRID.shape[0] * GRID.shape[1], dtype=float).reshape(GRID.shape)
    pw = build_weights(GRID, [p], land)
    assert pw.method == (METHOD_NEAREST_LAND,)
    assert pw.interpolate(field)[0] == field[3, 4]
    assert pw.categorical(field)[0] == field[3, 4]


def test_no_land_falls_back_to_unmasked() -> None:
    pw = build_weights(GRID, [_pt(41.1, 29.1)], np.zeros(GRID.shape))
    assert pw.method == (METHOD_UNMASKED,)


def test_point_near_edge_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_weights(GRID, [_pt(40.05, 29.0)], None)


def test_lapse_correction_sign_and_magnitude() -> None:
    # Model arazisi 300 m, nokta 100 m: nokta 200 m aşağıda → 1,3 °C daha sıcak.
    assert lapse_correction(np.array([300.0]), np.array([100.0]))[0] == pytest.approx(1.3)
    assert lapse_correction(np.array([0.0]), np.array([65.0]))[0] == pytest.approx(-0.4225)


def test_crop_handles_north_to_south_rows() -> None:
    lat_native = np.arange(42.0, 39.99, -0.25)  # dosyada kuzeyden güneye
    values = np.arange(len(lat_native))[:, None] * np.ones(len(LON))[None, :]
    crop = crop_grid(lat_native, LON, BBox(40.6, 41.4, 28.6, 29.4))
    out = crop.apply(values)
    assert np.all(np.diff(crop.grid.lat) > 0)
    # Kırpılmış ilk satır en güneydeki enlem olmalı → dosyadaki satır indisi en büyük olan.
    assert out[0, 0] == list(lat_native).index(crop.grid.lat[0])
    assert crop.grid.lat[0] <= 40.6 and crop.grid.lat[-1] >= 41.4


# Üçgen (yapısal olmayan) ızgara: kaydırılmış nokta kafesi, ICON hücre merkezlerine benzer.
_ULAT, _ULON = np.meshgrid(np.arange(40.0, 42.01, 0.1), np.arange(28.0, 30.01, 0.1))
_ULON = _ULON + 0.05 * (np.round(_ULAT * 10) % 2)
UCROP = crop_cells(_ULAT.ravel(), _ULON.ravel(), BBox(40.0, 42.0, 28.0, 30.1), "test-grid")
UGRID = UCROP.grid


def test_barycentric_is_exact_on_linear_field() -> None:
    pts = [_pt(41.03, 29.07), _pt(40.61, 28.66)]
    field = 10 + 2 * UGRID.lat - 3 * UGRID.lon
    pw = build_weights(UGRID, pts, None)
    np.testing.assert_allclose(pw.interpolate(field), [10 + 2 * p.lat - 3 * p.lon for p in pts])
    assert pw.method == (METHOD_UNMASKED, METHOD_UNMASKED)
    assert np.count_nonzero(pw.linear[0]) <= 3 and pw.linear[0].sum() == pytest.approx(1.0)


def test_unstructured_sea_cells_excluded_and_nearest_land_fallback() -> None:
    p = _pt(41.03, 29.07)
    pw0 = build_weights(UGRID, [p], None)
    tri = pw0.cells[0, :3]
    land = np.ones(UGRID.shape)
    land[tri[0]] = 0.0  # üçgenin bir köşesi deniz
    field = np.zeros(UGRID.shape)
    field[tri[0]] = 100.0
    pw = build_weights(UGRID, [p], land)
    assert pw.method == (METHOD_LSM,) and pw.interpolate(field)[0] == pytest.approx(0.0)

    land = np.zeros(UGRID.shape)
    outer = pw0.cells[0, 5]  # komşulukta ama üçgende değil
    land[outer] = 1.0
    field = np.arange(UGRID.shape[0], dtype=float)
    pw = build_weights(UGRID, [p], land)
    assert pw.method == (METHOD_NEAREST_LAND,)
    assert pw.interpolate(field)[0] == field[outer] == pw.categorical(field)[0]


def test_unstructured_point_outside_crop_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_weights(UGRID, [_pt(43.0, 29.0)], None)


def test_crop_cells_selects_box_and_wraps_longitudes() -> None:
    lat = np.array([41.0, 41.0, 41.0, 41.5, 40.5])
    lon = np.array([0.5, 359.5, 10.0, 0.0, 180.5])  # 359.5 → −0.5; 180.5 → −179.5
    crop = crop_cells(lat, lon, BBox(40.0, 42.0, -1.0, 1.0), "g")
    assert crop.cells.tolist() == [0, 1, 3]
    np.testing.assert_allclose(crop.grid.lon, [0.5, -0.5, 0.0])
    np.testing.assert_allclose(crop.apply(np.arange(5.0)), [0, 1, 3])
    with pytest.raises(ValueError):
        crop.apply(np.arange(4.0))
