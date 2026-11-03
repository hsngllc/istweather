"""NOAA GEFS ensemble adaptörü: adımlar, adresler, 6 saatlik kovaların zincirlenmesi.

GRIB mesajları ve .idx dosyaları sentetiktir (``constant_grib``); ağ kullanılmaz.
"""

from datetime import UTC, datetime
from urllib.parse import urlparse

import eccodes
import httpx
import numpy as np
import pytest

from hava.ingest.models import gefs
from hava.ingest.models.ensemble import extract_members
from hava.ingest.models.gfs import IdxEntry
from hava.region import load_region
from hava.settings import Settings

INIT = datetime(2026, 11, 3, 0, tzinfo=UTC)
# Sentetik kovalar: adım → (kova başı saati, değer)
BUCKETS = {3: (0, 1.0), 6: (0, 2.0), 9: (6, 1.0), 12: (6, 3.0)}


def constant_grib(value: float) -> bytes:
    """1° küresel düzenli ızgara, sabit değer."""
    h = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    try:
        for key, val in {
            "Ni": 360,
            "Nj": 181,
            "latitudeOfFirstGridPointInDegrees": 90.0,
            "latitudeOfLastGridPointInDegrees": -90.0,
            "longitudeOfFirstGridPointInDegrees": 0.0,
            "longitudeOfLastGridPointInDegrees": 359.0,
            "iDirectionIncrementInDegrees": 1.0,
            "jDirectionIncrementInDegrees": 1.0,
        }.items():
            eccodes.codes_set(h, key, val)
        eccodes.codes_set(h, "bitsPerValue", 16)
        eccodes.codes_set_values(h, np.full(360 * 181, value))
        return bytes(eccodes.codes_get_message(h))
    finally:
        eccodes.codes_release(h)


def test_steps_members_and_url() -> None:
    steps = gefs.steps_for(168)
    assert steps[:3] == [0, 3, 6] and steps[24:26] == [72, 78] and steps[-1] == 168
    assert gefs.member_name(0) == "gec00" and gefs.member_name(30) == "gep30"
    assert gefs.grib_url("https://b", INIT, 7, 9) == (
        "https://b/gefs.20261103/00/atmos/pgrb2sp25/gep07.t00z.pgrb2s.0p25.f009"
    )


def test_precip_bucket_matches_step_end() -> None:
    entries = [
        IdxEntry(0, 10, "APCP", "surface", "6-9 hour acc fcst"),
        IdxEntry(10, 10, "APCP", "surface", "0-6 hour acc fcst"),
    ]
    assert gefs.precip_bucket(entries, 9) == (6, entries[0])
    assert gefs.precip_bucket(entries, 6) == (0, entries[1])
    assert gefs.precip_bucket(entries, 12) is None


class FakeS3:
    """GEFS üye dosyaları ve GFS f000 (LAND) için .idx + Range destekli sahte sunucu."""

    def __init__(self) -> None:
        cache: dict[float, bytes] = {}

        def msg(v: float) -> bytes:
            if v not in cache:
                cache[v] = constant_grib(v)
            return cache[v]

        self.files: dict[str, bytes] = {}
        for step in (0, 3, 6, 9, 12):
            when = "anl" if step == 0 else f"{step} hour fcst"
            records = [
                ("TMP", "2 m above ground", when, 288.15),
                ("UGRD", "10 m above ground", when, 3.0),
                ("VGRD", "10 m above ground", when, 4.0),
                ("GUST", "surface", when, 9.0),
            ]
            if step == 0:
                records.append(("HGT", "surface", "anl", 50.0))
            else:
                start, value = BUCKETS[step]
                records.append(("APCP", "surface", f"{start}-{step} hour acc fcst", value))
            for m in gefs.MEMBERS:
                self._add(urlparse(gefs.grib_url(gefs.BASE_URL, INIT, m, step)).path, records, msg)
        gfs_path = "/gfs.20261103/00/atmos/gfs.t00z.pgrb2.0p25.f000"
        self._add(gfs_path, [("LAND", "surface", "anl", 1.0)], msg)

    def _add(self, path: str, records: list[tuple[str, str, str, float]], msg: object) -> None:
        body, lines = b"", []
        for n, (name, level, when, value) in enumerate(records, start=1):
            lines.append(f"{n}:{len(body)}:d=2026110300:{name}:{level}:{when}:")
            body += msg(value)  # type: ignore[operator]
        self.files[path] = body
        self.files[path + ".idx"] = ("\n".join(lines) + "\n").encode()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        data = self.files.get(request.url.path)
        if data is None:
            return httpx.Response(404)
        rng = request.headers.get("Range")
        if not rng:
            return httpx.Response(200, content=data)
        lo, _, hi = rng.removeprefix("bytes=").partition("-")
        return httpx.Response(206, content=data[int(lo) : (int(hi) + 1 if hi else None)])


def test_collect_run_chains_six_hour_buckets() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url="postgresql+psycopg://x@localhost/x",
        model_max_lead_h=12,
        model_download_workers=2,
        gfs_base_url="https://noaa-gfs-bdp-pds.s3.amazonaws.com",
    )
    region = load_region(settings.region_config)
    with httpx.Client(transport=httpx.MockTransport(FakeS3())) as client:
        col, stats = gefs.collect_run(client, settings, region, INIT)
    assert set(col.static) == {"lsm", "orog"} and len(col.members) == 31
    mv = extract_members(col, gefs.SPEC, region.points, INIT)
    assert mv.steps == [0, 3, 6, 9, 12] and mv.extraction == "bilinear_lsm_lapse"
    # Kovalar 0-3=1, 0-6=2, 6-9=1, 6-12=3 → başlangıçtan beri 1, 2, 3, 5 → aralıklar 1, 1, 1, 2.
    np.testing.assert_allclose(
        mv.values["precip_mm"][1:, :, 0].mean(axis=1), [1, 1, 1, 2], atol=1e-3
    )
    assert mv.gust_definition[1] == "instant"
    assert np.nanmax(np.abs(mv.values["wind_speed_ms"][1:] - 5.0)) == pytest.approx(0.0, abs=1e-3)
    assert stats["messages"] == 2 + 31 * (4 + 4 * 5)  # sabitler + 0. adım + 4 adım × 5 alan
