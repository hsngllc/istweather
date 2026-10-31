from datetime import UTC, datetime

import numpy as np
import pytest

from hava.ingest.archive.ukmo import (
    WANTED_PARAMS,
    build_stencil,
    grid_fingerprint,
    needs_processing,
    parse_key,
    point_values,
)
from hava.region import Point


def _pt(pid: str, lat: float, lon: float) -> Point:
    return Point(point_id=pid, kind="district", lat=lat, lon=lon, elevation_m=0.0)


def test_parse_key_valid() -> None:
    key = (
        "global-deterministic-10km/20241031T0000Z/"
        "20241031T1300Z-PT0013H00M-precipitation_accumulation-PT01H.nc"
    )
    ref = parse_key(key)
    assert ref is not None
    assert ref.run == datetime(2024, 10, 31, 0, 0, tzinfo=UTC)
    assert ref.valid == datetime(2024, 10, 31, 13, 0, tzinfo=UTC)
    assert ref.lead_min == 13 * 60
    assert ref.param == "precipitation_accumulation-PT01H"


def test_parse_key_rejects_other_keys() -> None:
    assert parse_key("global-deterministic-10km/20241031T0000Z/readme.txt") is None


def test_parse_key_inconsistent_lead_raises() -> None:
    bad = "global-deterministic-10km/20241031T0000Z/20241031T1400Z-PT0013H00M-wind_speed_at_10m.nc"
    with pytest.raises(ValueError):
        parse_key(bad)


def test_wanted_params_cover_spec_variables() -> None:
    for p in (
        "temperature_at_screen_level",
        "temperature_of_dew_point_at_screen_level",
        "precipitation_accumulation-PT01H",
        "wind_speed_at_10m",
        "wind_direction_at_10m",
        "wind_gust_at_10m_max-PT03H",
        "pressure_at_mean_sea_level",
        "visibility_at_screen_level",
        "temperature_on_pressure_levels",
    ):
        assert p in WANTED_PARAMS


def _grid() -> tuple[np.ndarray, np.ndarray]:
    lat = np.arange(40.0, 42.0, 0.1)
    lon = np.arange(27.5, 30.5, 0.15)
    return lat, lon


def test_bilinear_reproduces_linear_field() -> None:
    lat, lon = _grid()
    pts = [_pt("a", 41.03, 29.07), _pt("b", 40.87, 28.24)]
    st = build_stencil(lat, lon, pts)
    j0, j1, i0, i1 = st.box
    field = 2.0 * lat[:, None] + 3.0 * lon[None, :]
    stencil, nearest, bilinear = point_values(st, field[j0:j1, i0:i1])
    assert stencil.shape == (2, 16)
    np.testing.assert_allclose(bilinear, [2 * p.lat + 3 * p.lon for p in pts], rtol=1e-6)
    assert np.all(np.isfinite(nearest))


def test_bilinear_weights_sum_to_one_and_stencil_surrounds_point() -> None:
    lat, lon = _grid()
    pts = [_pt("a", 41.03, 29.07)]
    st = build_stencil(lat, lon, pts)
    np.testing.assert_allclose(st.weights.sum(axis=(1, 2)), 1.0)
    cells = st.cell_table.to_pylist()
    inner = [c for c in cells if c["bilinear_weight"] > 0]
    assert len(inner) == 4
    assert min(c["cell_lat"] for c in inner) <= 41.03 <= max(c["cell_lat"] for c in inner)
    assert min(c["cell_lon"] for c in inner) <= 29.07 <= max(c["cell_lon"] for c in inner)
    assert sum(c["is_nearest"] for c in cells) == 1


def test_missing_inner_cell_gives_nan_bilinear() -> None:
    lat, lon = _grid()
    st = build_stencil(lat, lon, [_pt("a", 41.03, 29.07)])
    j0, j1, i0, i1 = st.box
    box = np.ones((j1 - j0, i1 - i0))
    box[st.rows[0, 1], st.cols[0, 1]] = np.nan
    _, _, bilinear = point_values(st, box)
    assert np.isnan(bilinear[0])


def test_point_at_grid_edge_rejected() -> None:
    lat, lon = _grid()
    with pytest.raises(ValueError):
        build_stencil(lat, lon, [_pt("edge", 40.01, 29.0)])


def test_fingerprint_changes_with_grid() -> None:
    lat, lon = _grid()
    assert grid_fingerprint(lat, lon) != grid_fingerprint(lat[1:], lon)


def test_needs_processing_respects_manifest(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "manifest").mkdir()
    assert needs_processing(tmp_path, "20241031T0000Z")
    (tmp_path / "manifest" / "20241031T0000Z.json").write_text('{"status": "complete"}')
    assert not needs_processing(tmp_path, "20241031T0000Z")
    (tmp_path / "manifest" / "20241031T0600Z.json").write_text(
        '{"status": "partial", "attempts": 1}'
    )
    assert needs_processing(tmp_path, "20241031T0600Z")
    (tmp_path / "manifest" / "20241031T1200Z.json").write_text(
        '{"status": "partial", "attempts": 3}'
    )
    assert not needs_processing(tmp_path, "20241031T1200Z")
