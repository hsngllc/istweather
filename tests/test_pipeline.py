"""Ortak model işleme hattı: birikim, yükseklik düzeltmesi, birim dönüşümü, NetCDF.

Alanlar sentetiktir (``synthetic_field``).
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import h5netcdf
import numpy as np
import pytest

from hava.ingest.models.grib import GribField
from hava.ingest.models.pipeline import (
    GridChanged,
    ModelSpec,
    RunCollector,
    extract_rows,
    write_netcdf,
)
from hava.processing.grid import BBox
from hava.processing.thermo import relative_humidity
from hava.region import Point

LAT = np.arange(43.0, 38.99, -0.25)  # dosyadaki gibi kuzeyden güneye
LON = np.arange(26.0, 32.01, 0.25)
INIT = datetime(2026, 11, 2, 0, tzinfo=UTC)
SPEC = ModelSpec("synthetic", gust_definition=lambda s: "max_1h", ptype_names={1: "rain"})
POINTS = [
    Point("district:a:0", "district", 41.05, 29.02, 50.0, True),
    Point("station:metar:X", "station", 40.98, 28.82, 50.0),
]


def synthetic_field(value: float, name: str = "x", lat: np.ndarray = LAT) -> GribField:
    return GribField(
        name, "surface", 0, 0.0, "0", "", lat, LON, np.full((len(lat), len(LON)), value)
    )


def _collector() -> RunCollector:
    col = RunCollector(BBox(40.7, 41.7, 27.8, 30.0).expanded(0.5))
    col.add_static("lsm", synthetic_field(1.0))
    col.add_static("orog", synthetic_field(200.0))
    for step, acc, conv in ((0, 0.0, 0.0), (3, 2.0, 0.5), (6, 5.0, 0.5)):
        col.add("t2m", step, synthetic_field(288.15))
        col.add("d2m", step, synthetic_field(283.15))
        col.add("precip_acc", step, synthetic_field(acc))
        col.add("conv_acc", step, synthetic_field(conv))
        col.add("msl", step, synthetic_field(101325.0))
        col.add("tcc", step, synthetic_field(0.5))
        col.add("u10", step, synthetic_field(-3.0))
        col.add("v10", step, synthetic_field(4.0))
        if step > 0:
            col.add("gust", step, synthetic_field(12.0))
            col.add("ptype", step, synthetic_field(1.0))
    return col


def test_rows_units_accumulation_and_lapse() -> None:
    rows = extract_rows(_collector(), SPEC, POINTS, INIT)
    assert len(rows) == 6  # 2 nokta × 3 adım
    by = {(r["point_id"], r["lead_h"]): r for r in rows}
    r0, r3, r6 = (by[("district:a:0", s)] for s in (0.0, 3.0, 6.0))
    corr = 0.0065 * (200 - 50)
    assert r3["temp_c"] == pytest.approx(15.0 + corr)
    assert r3["dewpoint_c"] == pytest.approx(10.0)
    assert r3["rh_pct"] == pytest.approx(relative_humidity(15.0, 10.0))  # düzeltmesiz T/Td
    assert r0["precip_mm"] is None and r0["precip_period_h"] is None
    assert (r3["precip_mm"], r3["precip_period_h"]) == (pytest.approx(2.0), 3.0)
    assert (r6["precip_mm"], r6["precip_period_h"]) == (pytest.approx(3.0), 3.0)
    assert r3["extra"]["conv_precip_mm"] == pytest.approx(0.5)
    assert r6["extra"]["conv_precip_mm"] == pytest.approx(0.0)
    assert r3["mslp_hpa"] == pytest.approx(1013.25) and r3["cloud_cover_pct"] == pytest.approx(50)
    assert (r3["wind_u_ms"], r3["wind_v_ms"]) == (pytest.approx(-3.0), pytest.approx(4.0))
    assert r0["wind_gust_ms"] is None and r3["wind_gust_ms"] == pytest.approx(12.0)
    assert r3["extra"]["gust_definition"] == "max_1h" and "gust_definition" not in r0["extra"]
    assert r3["precip_type"] == "rain" and r0["precip_type"] is None
    assert r3["valid_time"] == INIT + timedelta(hours=3)
    assert r3["extraction"] == "bilinear_lsm_lapse"
    assert r3["extra"]["lapse_correction_c"] == pytest.approx(corr, abs=1e-3)


def test_negative_accumulation_noise_is_clipped() -> None:
    col = _collector()
    col.add("precip_acc", 9, synthetic_field(4.999))  # paketleme gürültüsü: azalma
    col.add("t2m", 9, synthetic_field(288.15))
    rows = extract_rows(col, SPEC, POINTS, INIT)
    r9 = next(r for r in rows if r["lead_h"] == 9.0)
    assert r9["precip_mm"] == 0.0


def test_grid_change_within_a_run_is_rejected() -> None:
    col = _collector()
    with pytest.raises(GridChanged):
        col.add("t2m", 9, synthetic_field(288.15, lat=np.arange(43.0, 38.99, -0.5)))


def test_netcdf_contains_crop_and_metadata(tmp_path: Path) -> None:
    col = _collector()
    path = tmp_path / "synthetic" / "20261102T00Z.nc"
    write_netcdf(col, path, {"model": "synthetic", "init_time": INIT.isoformat()})
    with h5netcdf.File(path, "r") as f:
        assert list(f["step"][:]) == [0.0, 3.0, 6.0]
        assert f["t2m"].shape == (3, len(f["lat"]), len(f["lon"]))
        assert np.all(np.diff(f["lat"][:]) > 0)
        assert np.isnan(f["gust"][0]).all() and f["gust"][1, 0, 0] == pytest.approx(12.0)
        assert f.attrs["model"] == "synthetic"
        assert f["lsm"].shape == (len(f["lat"]), len(f["lon"]))


def _cells_field(value: float, n: int, grid_id: str = "g1") -> GribField:
    empty = np.empty(0)
    return GribField(
        "x", "surface", 0, 0.0, "0", "", empty, empty, np.full(n, value), {"grid_id": grid_id}
    )


def _unstructured_collector() -> tuple[RunCollector, int]:
    lat, lon = np.meshgrid(np.arange(39.0, 43.5, 0.1), np.arange(26.0, 32.0, 0.1))
    lon = lon + 0.05 * (np.round(lat * 10) % 2)
    col = RunCollector(BBox(40.7, 41.7, 27.8, 30.0).expanded(0.5))
    col.set_cells(lat.ravel(), lon.ravel(), "g1")
    return col, lat.size


def test_unstructured_fields_need_cells_and_matching_grid() -> None:
    with pytest.raises(GridChanged):
        RunCollector(BBox(40.7, 41.7, 27.8, 30.0)).add("t2m", 0, _cells_field(288.0, 10))
    col, n = _unstructured_collector()
    col.add("t2m", 0, _cells_field(288.15, n))
    with pytest.raises(GridChanged):
        col.add("t2m", 1, _cells_field(288.15, n, grid_id="g2"))
    with pytest.raises(GridChanged):
        col.add("t2m", 1, _cells_field(288.15, n - 1))
    with pytest.raises(GridChanged):
        col.add("t2m", 1, synthetic_field(288.15))  # düzenli ızgara karışamaz


def test_unstructured_rows_and_netcdf(tmp_path: Path) -> None:
    col, n = _unstructured_collector()
    col.add_static("lsm", _cells_field(1.0, n))
    for step in (0, 1):
        col.add("t2m", step, _cells_field(288.15, n))
        col.add("precip_acc", step, _cells_field(2.0 * step, n))
    rows = extract_rows(col, SPEC, POINTS, INIT)
    assert {r["extraction"] for r in rows} == {"barycentric_lsm"}
    assert rows[-1]["precip_mm"] == pytest.approx(2.0) and rows[-1]["temp_c"] == pytest.approx(15.0)
    path = tmp_path / "icon" / "20261102T00Z.nc"
    write_netcdf(col, path, {"model": "synthetic"})
    with h5netcdf.File(path, "r") as f:
        cells = len(f["lat"])
        assert f["t2m"].shape == (2, cells) and f["lsm"].shape == (cells,)
        assert f.attrs["grid_id"] == "g1" and f["lon"].shape == (cells,)
