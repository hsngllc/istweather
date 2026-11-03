"""ECCC GDPS: AMQPS duyurusu ayrıştırma, biriktirme dosyası, tamlık kuralı ve indirme-işleme.

Duyuru gövdeleri gerçek biçimde ama sentetik; GRIB mesajları sentetik (``constant_grib``).
Ağ ve AMQP sunucusu kullanılmaz.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
from tests.test_gefs import constant_grib

from hava.ingest.models import gdps
from hava.ingest.models.pipeline import extract_rows
from hava.region import load_region
from hava.settings import Settings

INIT = datetime(2026, 11, 3, 12, tzinfo=UTC)
BASE = "https://dd2.weather.gc.ca/"


def body(var: str, step: int, day: str = "20261103") -> bytes:
    rel = (
        f"{day}/WXO-DD/model_gdps/15km/12/{step:03d}/"
        f"20261103T12Z_MSC_GDPS_{var}_LatLon0.15_PT{step:03d}H.grib2"
    )
    return f"20261103154012.345 {BASE} {rel}".encode()


def test_parse_notice_keeps_only_wanted_files() -> None:
    n = gdps.parse_notice(body("AirTemp_AGL-2m", 6))
    assert n is not None and (n.run, n.var, n.step) == (INIT, "AirTemp_AGL-2m", 6)
    assert n.url.startswith("https://dd2.weather.gc.ca/20261103/WXO-DD/model_gdps/15km/12/006/")
    assert gdps.parse_notice(body("WindGust-Max_AGL-10m", 6)) is None  # istenmeyen
    assert gdps.parse_notice(body("PrecipType-Instant_Sfc", 6)) is None  # bilerek alınmıyor
    assert gdps.parse_notice(body("LandWaterProportion_Sfc", 0)) is not None  # sabit
    assert gdps.parse_notice(b"eksik") is None


def test_spool_roundtrip_tolerates_partial_line(tmp_path: Path) -> None:
    at = INIT + timedelta(hours=4)
    for var in ("AirTemp_AGL-2m", "Precip-Accum_Sfc"):
        n = gdps.parse_notice(body(var, 168))
        assert n is not None
        gdps.append_notice(tmp_path, n, at)
    path = tmp_path / "20261103T12Z.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write('{"var": "WindU_AGL-10m", "st')  # yazılırken okunan yarım satır
    files, last = gdps.read_spool(path)
    assert set(files) == {("AirTemp_AGL-2m", 168), ("Precip-Accum_Sfc", 168)} and last == at


def test_ready_needs_core_fields_at_last_step_and_quiet_period() -> None:
    last = INIT + timedelta(hours=5)
    files = {(v, 168): "u" for v in gdps.CORE}
    assert gdps.ready(files, last, last + timedelta(minutes=20), 168)
    assert not gdps.ready(files, last, last + timedelta(minutes=5), 168)  # duyurular sürüyor
    partial = {k: v for k, v in files.items() if k[0] != "WindU_AGL-10m"}
    assert not gdps.ready(partial, last, last + timedelta(hours=1), 168)
    short = {(v, 48): "u" for v in gdps.CORE}
    assert gdps.ready(short, last, last + timedelta(hours=1), 48)  # ufuk ayarı daha kısa
    assert not gdps.ready({}, None, last, 168)


def test_queue_name_is_stable_per_installation(tmp_path: Path) -> None:
    first = gdps.queue_name(tmp_path)
    assert first.startswith("q_anonymous.istweather.gdps.") and gdps.queue_name(tmp_path) == first
    assert gdps.queue_name(tmp_path / "baska") != first


def test_collect_run_downloads_announced_files() -> None:
    values = {
        "AirTemp_AGL-2m": 288.15,
        "DewPoint_AGL-2m": 283.15,
        "WindU_AGL-10m": 3.0,
        "WindV_AGL-10m": 4.0,
        "WindGust_AGL-10m": 9.0,
        "Pressure_MSL": 101500.0,
        "TotalCloudCover_Sfc": 40.0,
        "Precip-Accum_Sfc": 2.0,
        "GeopotentialHeight_Sfc": 0.0,
        "LandWaterProportion_Sfc": 1.0,
    }
    messages = {v: constant_grib(x) for v, x in values.items()}
    files: dict[tuple[str, int], str] = {}
    for var in values:
        steps = (0,) if var in gdps.STATIC else (1,) if var == "Precip-Accum_Sfc" else (0, 1)
        for step in steps:
            files[(var, step)] = f"https://dd.test/{var}/{step}.grib2"

    def handler(request: httpx.Request) -> httpx.Response:
        var = request.url.path.split("/")[1]
        return httpx.Response(200, content=messages[var])

    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url="postgresql+psycopg://x@localhost/x",
        model_max_lead_h=6,
    )
    region = load_region(settings.region_config)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        col, stats = gdps.collect_run(client, settings, region, files)
    assert stats["messages"] == len(files) and set(col.static) == {"orog", "lsm"}
    rows = {r["lead_h"]: r for r in extract_rows(col, gdps.SPEC, region.points, INIT)}
    one = rows[1.0]
    assert one["precip_mm"] is not None and abs(one["precip_mm"] - 2.0) < 1e-3  # başlangıç 0
    assert (
        abs(one["cloud_cover_pct"] - 40.0) < 1e-3 and one["extra"]["gust_definition"] == "instant"
    )
    assert np.isclose(one["wind_gust_ms"], 9.0, atol=1e-3)
