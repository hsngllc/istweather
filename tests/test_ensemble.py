"""Ensemble hattı: üye çıkarımı, istatistikler, Parquet ve NetCDF çıktıları.

Alanlar ve üye değerleri sentetiktir.
"""

from datetime import UTC, datetime
from pathlib import Path

import h5netcdf
import numpy as np
import pyarrow.parquet as pq
import pytest
from tests.test_pipeline import INIT, POINTS, synthetic_field

from hava.ingest.models import ensemble
from hava.ingest.models.ensemble import (
    EnsembleCollector,
    MemberValues,
    extract_members,
    member_stats,
    write_crop,
    write_members,
)
from hava.ingest.models.pipeline import ModelSpec
from hava.processing.grid import BBox

SPEC = ModelSpec("synthetic_ens", gust_definition=lambda s: "max_1h")


def test_step_plan_three_hourly_then_six_hourly() -> None:
    steps = ensemble.STEPS
    assert steps[:3] == (0, 3, 6) and 72 in steps and 75 not in steps
    assert steps[steps.index(72) + 1] == 78 and 168 in steps


def _collector() -> EnsembleCollector:
    col = EnsembleCollector(BBox(40.7, 41.7, 27.8, 30.0).expanded(0.5), members=(0, 1, 2))
    col.add_static("lsm", synthetic_field(1.0))
    col.add_static("orog", synthetic_field(100.0))
    for m in (0, 1, 2):
        for step in (3, 6):  # 0. adımda yağış kaydı yok (başlangıç 0)
            col.add("t2m", step, m, synthetic_field(288.15 + m))
            col.add("u10", step, m, synthetic_field(3.0))
            col.add("v10", step, m, synthetic_field(4.0))
            col.add("gust", step, m, synthetic_field(10.0 + m))
            col.add("precip_acc", step, m, synthetic_field(step * (m + 1) / 3.0))
        col.add("t2m", 0, m, synthetic_field(288.15 + m))
    return col


def test_members_extracted_with_lapse_and_intervals() -> None:
    mv = extract_members(_collector(), SPEC, POINTS, INIT)
    assert mv.steps == [0, 3, 6] and mv.members == [0, 1, 2]
    assert mv.period_h == [None, 3, 3] and mv.gust_definition == [None, "max_1h", "max_1h"]
    lapse = 0.0065 * (100.0 - POINTS[0].elevation_m)
    np.testing.assert_allclose(mv.values["temp_c"][1, :, 0], [15 + lapse, 16 + lapse, 17 + lapse])
    np.testing.assert_allclose(mv.values["precip_mm"][1, :, 0], [1.0, 2.0, 3.0])  # 0 → 3. saat
    np.testing.assert_allclose(mv.values["precip_mm"][2, :, 0], [1.0, 2.0, 3.0])
    np.testing.assert_allclose(mv.values["wind_speed_ms"][1], 5.0)
    assert np.isnan(mv.values["snow_mm"]).all()
    assert mv.extraction == "bilinear_lsm_lapse"


def _values(arr: list[list[float]]) -> MemberValues:
    """Tek adım, tek nokta için ``arr[değişken_sırası]`` üye değerleri."""
    data = {c: np.full((1, len(arr[0]), 1), np.nan) for c in ensemble.MEMBER_COLUMNS}
    data["temp_c"][0, :, 0] = arr[0]
    data["precip_mm"][0, :, 0] = arr[1]
    return MemberValues(
        point_keys=("station:metar:X",),
        members=list(range(len(arr[0]))),
        steps=[6.0],
        valid_times=[datetime(2026, 11, 3, 6, tzinfo=UTC)],
        period_h=[6.0],
        gust_definition=[None],
        values=data,
        extraction="bilinear_lsm",
        point_method=("lsm_bilinear",),
    )


def test_stats_percentiles_spread_and_probabilities() -> None:
    temps = [-1.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    rain = [0.0, 0.0, 0.05, 0.2, 1.0, 1.5, 4.9, 5.0, 12.0, 25.0]
    rows = {r["variable"]: r for r in member_stats(_values([temps, rain]))}
    t = rows["temp_c"]
    assert t["n_members"] == 10 and t["mean"] == pytest.approx(3.5)
    assert t["std"] == pytest.approx(np.std(temps, ddof=1))
    assert t["p50"] == pytest.approx(3.5) and t["p10"] == pytest.approx(np.percentile(temps, 10))
    assert t["exceed_probs"] == {"le_0": 0.2}
    r = rows["precip_mm"]
    assert r["exceed_probs"] == {
        "ge_0.1": 0.7,
        "ge_1": 0.6,
        "ge_5": 0.3,
        "ge_10": 0.2,
        "ge_20": 0.1,
    }
    assert r["extra"] == {"period_h": 6.0} and r["extraction"] == "bilinear_lsm"
    assert "wind_speed_ms" not in rows  # tüm üyeler eksik → satır yok


def test_missing_members_reduce_count() -> None:
    temps = [1.0, np.nan, 3.0]
    rows = {r["variable"]: r for r in member_stats(_values([temps, [0.0, 0.0, 0.0]]))}
    assert rows["temp_c"]["n_members"] == 2 and rows["temp_c"]["mean"] == pytest.approx(2.0)
    single = {r["variable"]: r for r in member_stats(_values([[1.0, np.nan], [0.0, 0.0]]))}
    assert single["temp_c"]["std"] is None  # tek üyede yayılım tanımsız


def test_parquet_and_netcdf_outputs(tmp_path: Path) -> None:
    col = _collector()
    mv = extract_members(col, SPEC, POINTS, INIT)
    path = tmp_path / "ensemble" / "synthetic_ens" / "20261102T00Z.parquet"
    n = write_members(mv, path, {"model": "synthetic_ens", "init_time": INIT.isoformat()})
    table = pq.read_table(path)
    assert n == table.num_rows == 3 * 3 * len(POINTS)
    meta = table.schema.metadata
    assert meta[b"model"] == b"synthetic_ens" and meta[b"extraction"] == b"bilinear_lsm_lapse"
    rows = table.to_pylist()
    first = next(r for r in rows if r["lead_h"] == 3.0 and r["member"] == 2)
    assert first["precip_mm"] == pytest.approx(3.0) and first["precip_period_h"] == 3.0
    assert first["snow_mm"] is None and first["gust_definition"] == "max_1h"
    nc = tmp_path / "grib" / "20261102T00Z.nc"
    write_crop(col, nc, {"model": "synthetic_ens"})
    with h5netcdf.File(nc, "r") as f:
        assert f["t2m"].shape == (3, 3, len(f["lat"]), len(f["lon"]))
        assert list(f["member"][:]) == [0, 1, 2] and f["lsm"].shape == (
            len(f["lat"]),
            len(f["lon"]),
        )


def test_parquet_without_gust_model(tmp_path: Path) -> None:
    # AIFS ENS hamle üretmiyor: hamle tanımı sütunu tamamen boş olmalı, yazım hata vermemeli.
    col = EnsembleCollector(BBox(40.7, 41.7, 27.8, 30.0).expanded(0.5), members=(0, 1))
    col.add_static("lsm", synthetic_field(1.0))
    for m in (0, 1):
        for step in (0, 6):
            col.add("t2m", step, m, synthetic_field(288.15))
    no_gust = ModelSpec("synthetic_ens", gust_definition=lambda s: None)
    mv = extract_members(col, no_gust, POINTS, INIT)
    path = tmp_path / "m.parquet"
    assert write_members(mv, path, {"model": "synthetic_ens"}) == 2 * 2 * len(POINTS)
    rows = pq.read_table(path).to_pylist()
    assert {r["gust_definition"] for r in rows} == {None}
