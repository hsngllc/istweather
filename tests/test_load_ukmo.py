"""UKMO yükleyici dönüşümü. Girdi, çıkarıcının kendi kod yoluyla (``_points_table``) üretilen
etiketli sentetik veridir; gerçek model verisi değildir."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from hava.ingest.archive.load_ukmo import batches, inner_weights, transform_run
from hava.ingest.archive.ukmo import FileRef, _points_table, build_stencil
from hava.region import Point

RUN = datetime(2025, 1, 15, 0, 0, tzinfo=UTC)


def _sample_run() -> tuple[object, object]:
    lat = np.arange(40.0, 42.0, 0.1)
    lon = np.arange(27.5, 30.5, 0.15)
    pts = [Point("district:test:0", "district", 41.03, 29.07, 50.0, True)]
    st = build_stencil(lat, lon, pts)
    j0, j1, i0, i1 = st.box
    shape = (j1 - j0, i1 - i0)
    fields = {
        "temperature_at_screen_level": (np.full(shape, 290.0), "K"),
        "temperature_of_dew_point_at_screen_level": (np.full(shape, 280.0), "K"),
        "relative_humidity_at_screen_level": (np.full(shape, 0.5), "1"),
        "wind_speed_at_10m": (np.full(shape, 10.0), "m s-1"),
        "wind_direction_at_10m": (np.full(shape, 90.0), "degrees"),
        "precipitation_accumulation-PT01H": (np.full(shape, 0.002), "m"),
        "precipitation_accumulation-PT03H": (np.full(shape, 0.005), "m"),
        "pressure_at_mean_sea_level": (np.full(shape, 101325.0), "Pa"),
        "cloud_amount_of_total_cloud": (np.full(shape, 0.25), "1"),
        "temperature_on_pressure_levels": (np.full(shape, 270.0), "K"),
        "wind_gust_at_10m_max-PT01H": (np.full(shape, 15.0), "m s-1"),
    }
    refs, results = {}, []
    lead = 60
    for param, (values, units) in fields.items():
        key = f"sample/{param}.nc"
        refs[key] = FileRef(key, RUN, RUN + timedelta(minutes=lead), lead, param)
        results.append(
            {
                "key": key,
                "values": values.astype(np.float32),
                "units": units,
                "cell_methods": None,
                "level_pa": 85000 if "pressure_levels" in param else None,
            }
        )
    return _points_table(st, refs, results), st.cell_table


def test_transform_converts_units_and_wind_components() -> None:
    table, cells = _sample_run()
    recs = transform_run(table, inner_weights(cells))
    assert len(recs) == 1
    r = recs[0]
    assert r["point_key"] == "district:test:0"
    assert r["lead_h"] == 1.0
    assert r["temp_c"] == pytest.approx(16.85, abs=1e-3)
    assert r["dewpoint_c"] == pytest.approx(6.85, abs=1e-3)
    assert r["rh_pct"] == pytest.approx(50.0)
    assert r["mslp_hpa"] == pytest.approx(1013.25)
    assert r["cloud_cover_pct"] == pytest.approx(25.0)
    assert r["t850_c"] == pytest.approx(-3.15, abs=1e-3)
    # En kısa pencere seçilir: PT01H, 2 mm.
    assert r["precip_mm"] == pytest.approx(2.0)
    assert r["precip_period_h"] == 1.0
    # Doğudan esen 10 m/s: u = -10, v = 0.
    assert r["wind_u_ms"] == pytest.approx(-10.0, abs=1e-4)
    assert r["wind_v_ms"] == pytest.approx(0.0, abs=1e-4)
    assert r["extra"]["gust_max_ms"] == pytest.approx(15.0)
    assert r["extra"]["gust_max_period_h"] == 1.0
    assert r["extraction"] == "bilinear_unmasked"


def test_wind_direction_bilinear_column_is_empty() -> None:
    table, _ = _sample_run()
    rows = [r for r in table.to_pylist() if r["param"] == "wind_direction_at_10m"]
    assert rows and all(r["bilinear"] is None or np.isnan(r["bilinear"]) for r in rows)


def test_batches_respect_postgres_parameter_limit() -> None:
    # 7 günlük bir çalıştırma ~3700 satır × 22 sütun; tek pakette 65535 parametreyi aşar.
    rows = [{f"c{j}": j for j in range(22)} for _ in range(3738)]
    chunks = batches(rows, batch=5000)
    assert sum(len(c) for c in chunks) == len(rows)
    assert all(len(c) * 22 <= 65535 for c in chunks)
    assert batches([], batch=5000) == []
