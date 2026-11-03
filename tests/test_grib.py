"""GRIB çözme: eccodes örnek şablonundan üretilen sentetik mesajlarla."""

import eccodes
import numpy as np
import pytest

from hava.ingest.models.grib import GribError, decode_message, split_messages


def synthetic_grib(lon_first: float = 0.0, short_name: str = "2t", step: int = 6) -> bytes:
    """1° küresel ızgara, kuzeyden güneye; değer = enlem·1000 + dosyadaki boylam."""
    h = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    try:
        lat = np.arange(90, -91, -1.0)
        lon = lon_first + np.arange(360.0)
        for key, val in {
            "Ni": 360,
            "Nj": 181,
            "latitudeOfFirstGridPointInDegrees": 90.0,
            "latitudeOfLastGridPointInDegrees": -90.0,
            "longitudeOfFirstGridPointInDegrees": lon_first,
            "longitudeOfLastGridPointInDegrees": lon_first + 359.0,
            "iDirectionIncrementInDegrees": 1.0,
            "jDirectionIncrementInDegrees": 1.0,
            "jScansPositively": 0,
        }.items():
            eccodes.codes_set(h, key, val)
        eccodes.codes_set(h, "shortName", short_name)
        eccodes.codes_set(h, "stepUnits", 1)
        eccodes.codes_set(h, "step", step)
        values = lat[:, None] * 1000 + np.where(lon >= 180, lon - 360, lon)[None, :]
        eccodes.codes_set(h, "bitsPerValue", 24)
        eccodes.codes_set_values(h, values.ravel())
        return bytes(eccodes.codes_get_message(h))
    finally:
        eccodes.codes_release(h)


def test_decode_rolls_longitudes_to_ascending_minus180_180() -> None:
    f = decode_message(synthetic_grib(0.0))
    assert f.short_name == "2t" and f.end_step_h == 6
    assert f.values.shape == (181, 360)
    assert f.lat[0] == 90 and f.lat[-1] == -90
    assert f.lon[0] == -180 and f.lon[-1] == 179 and np.all(np.diff(f.lon) > 0)
    j = int(np.where(f.lat == 41)[0][0])
    i = int(np.where(f.lon == 29)[0][0])
    assert f.values[j, i] == pytest.approx(41 * 1000 + 29, abs=0.5)
    i_w = int(np.where(f.lon == -10)[0][0])
    assert f.values[j, i_w] == pytest.approx(41 * 1000 - 10, abs=0.5)


def test_decode_keeps_minus180_grid_as_is() -> None:
    f = decode_message(synthetic_grib(-180.0))
    assert f.lon[0] == -180 and np.all(np.diff(f.lon) > 0)


def test_split_concatenated_messages() -> None:
    a, b = synthetic_grib(step=3), synthetic_grib(step=6)
    parts = list(split_messages(a + b))
    assert [decode_message(p).end_step_h for p in parts] == [3, 6]
    with pytest.raises(GribError):
        list(split_messages(a[:-10]))


def test_decode_unstructured_grid_keeps_flat_values_and_grid_id() -> None:
    from tests.test_icon import GRID_ID, synthetic_unstructured

    f = decode_message(synthetic_unstructured(np.arange(7, dtype=float), step=3))
    assert f.values.shape == (7,) and f.lat.size == 0 and f.lon.size == 0
    np.testing.assert_allclose(f.values, np.arange(7), atol=1e-4)
    assert f.meta["grid_id"] == GRID_ID and f.end_step_h == 3.0
