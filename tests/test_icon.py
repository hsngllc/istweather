"""DWD ICON adaptörü: adımlar, adresler, WW eşlemesi ve sahte sunucuyla uçtan uca toplama.

GRIB mesajları sentetiktir (``synthetic_unstructured``); ağ kullanılmaz.
"""

from datetime import UTC, datetime
from urllib.parse import unquote

import eccodes
import httpx
import numpy as np
import pytest

from hava.ingest.archive.http_range import RemoteFileGone
from hava.ingest.models import icon
from hava.ingest.models.pipeline import extract_rows, extraction_label
from hava.region import load_region
from hava.settings import Settings

INIT = datetime(2026, 11, 3, 0, tzinfo=UTC)
GRID_ID = "0123456789abcdef0123456789abcdef"


def synthetic_unstructured(values: np.ndarray, step: int = 0, grid_id: str = GRID_ID) -> bytes:
    h = eccodes.codes_grib_new_from_samples("GRIB2")
    try:
        eccodes.codes_set(h, "gridDefinitionTemplateNumber", 101)
        eccodes.codes_set(h, "numberOfDataPoints", len(values))
        eccodes.codes_set(h, "uuidOfHGrid", grid_id)
        eccodes.codes_set(h, "stepUnits", 1)
        eccodes.codes_set(h, "endStep", step)
        eccodes.codes_set(h, "bitsPerValue", 24)
        eccodes.codes_set_values(h, np.asarray(values, dtype=np.float64))
        return bytes(eccodes.codes_get_message(h))
    finally:
        eccodes.codes_release(h)


def test_steps_follow_dwd_listing() -> None:
    long_run = icon.steps_for(icon.ICON, INIT, 180)
    assert long_run[:3] == [0, 1, 2] and long_run[78:81] == [78, 81, 84] and long_run[-1] == 180
    assert len(long_run) == 79 + 34
    assert icon.steps_for(icon.ICON, INIT.replace(hour=6), 180)[-1] == 120
    assert icon.steps_for(icon.ICON, INIT, 168)[-1] == 168
    assert len(icon.steps_for(icon.ICON_EU, INIT, 168)) == 93  # dizinde 93 dosya


def test_urls_match_documented_layout() -> None:
    base = "https://opendata.dwd.de/weather/nwp/v1/m"
    t2m = icon.Want("T_2M", "t2m")
    t850 = next(w for w in icon.FIELDS if w.var == "t850")
    run = datetime(2026, 10, 31, 18, tzinfo=UTC)
    assert icon.file_url(base, icon.ICON, t2m, run, 0) == (
        f"{base}/icon/p/T_2M/r/2026-10-31T18:00/s/PT000H00M.grib2"
    )
    assert icon.file_url(base, icon.ICON_EU, t850, run, 81) == (
        f"{base}/icon-eu/p/T/lvt1/100/lv1/85000/r/2026-10-31T18:00/s/PT081H00M.grib2"
    )


def test_every_documented_ww_code_has_a_type() -> None:
    # DWD ICON Database Reference 2.5.6, Tablo 6.1
    documented = [0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77]
    documented += [80, 81, 82, 85, 86, 95, 96]
    assert sorted(icon.WW_PTYPE) == documented
    assert icon.WW_PTYPE[56] == "freezing_drizzle" and icon.WW_PTYPE[85] == "snow"


class FakeDwd:
    """Sentetik DWD sunucusu: üçgen ızgara yerine kutuyu kaplayan kaydırılmış nokta kafesi."""

    def __init__(self, missing: set[tuple[str, int]] | None = None) -> None:
        lat, lon = np.meshgrid(np.arange(39.0, 43.5, 0.1), np.arange(26.0, 32.0, 0.1))
        lon = lon + 0.05 * (np.round(lat * 10) % 2)  # üçgen kafes
        self.lat, self.lon = lat.ravel(), lon.ravel()
        self.missing = missing or set()
        self.requests: list[str] = []
        # eccodes örnek yükleyicisi iş parçacığına dayanıklı değil: mesajlar baştan üretilir.
        params = [w.param for w in icon.FIELDS + icon.STATIC + icon.COORDS]
        self.messages = {
            (p, step): synthetic_unstructured(self.field(p, step), step)
            for p in params
            for step in range(3)
        }

    def field(self, param: str, step: int) -> np.ndarray:
        n = self.lat.size
        values = {
            "CLAT": self.lat,
            "CLON": self.lon,
            "FR_LAND": np.ones(n),
            "HSURF": np.zeros(n),
            "T_2M": 288.15 + 0.5 * (self.lat - 41.0),
            "TD_2M": np.full(n, 280.15),
            "TOT_PREC": np.full(n, 1.0 * step),  # saatte 1 mm
            "RAIN_CON": np.full(n, 0.5 * step),
            "SNOW_CON": np.full(n, 0.1 * step),
            "SNOW_GSP": np.full(n, 0.2 * step),
            "U_10M": np.full(n, 3.0),
            "V_10M": np.full(n, -4.0),
            "VMAX_10M": np.full(n, 9.0),
            "PMSL": np.full(n, 101500.0),
            "CLCT": np.full(n, 50.0),
            "CLCL": np.full(n, 25.0),
            "WW": np.full(n, 61.0),
            "T": np.full(n, 275.15),
        }
        return values[param]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        parts = unquote(request.url.path).split("/")
        param = parts[parts.index("p") + 1]
        step = int(parts[-1][2:5])
        self.requests.append(f"{param}:{step}")
        if (param, step) in self.missing:
            return httpx.Response(404)
        return httpx.Response(200, content=self.messages[(param, step)])


def _settings(lead: int = 2) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url="postgresql+psycopg://x@localhost/x",
        model_max_lead_h=lead,
        model_download_workers=2,
    )


REGION = load_region(_settings().region_config)


def _collect(server: FakeDwd) -> tuple[list[dict[str, object]], dict[str, int]]:
    with httpx.Client(transport=httpx.MockTransport(server)) as client:
        col, stats = icon.collect_run(client, _settings(), REGION, icon.ICON, INIT)
    assert extraction_label(col) == "barycentric_lsm_lapse"
    return extract_rows(col, icon.ICON.spec, REGION.points, INIT), stats


def test_collect_run_end_to_end() -> None:
    server = FakeDwd(missing={("VMAX_10M", 0)})  # ICON global'de 0. adımda hamle yok
    rows, stats = _collect(server)
    assert stats["missing_optional"] == 1
    assert server.requests.count("CLAT:0") == 1  # sabitler yalnız bir kez
    by_lead = {r["lead_h"]: r for r in rows if r["point_id"] == "station:metar:LTFM"}
    first, second = by_lead[0.0], by_lead[1.0]
    assert first["wind_gust_ms"] is None and first["precip_mm"] is None
    assert second["precip_mm"] == pytest.approx(1.0, abs=1e-3)
    assert second["precip_period_h"] == 1.0
    assert second["snow_mm"] == pytest.approx(0.3, abs=1e-3)  # SNOW_CON + SNOW_GSP
    extra = second["extra"]
    assert isinstance(extra, dict)
    assert extra["conv_precip_mm"] == pytest.approx(0.6, abs=1e-3)  # RAIN_CON + SNOW_CON
    assert extra["gust_definition"] == "max_1h" and extra["ptype_code"] == 61
    assert second["precip_type"] == "rain" and second["wind_gust_ms"] == pytest.approx(9.0)
    assert second["cloud_cover_pct"] == pytest.approx(50.0)
    assert second["t850_c"] == pytest.approx(2.0, abs=1e-3)  # GRIB paketleme hassasiyeti
    # Doğrusal alan üçgen içinde tam çıkarılır (arazi 0 m, nokta yüksekliğine göre düzeltilir).
    p = next(x for x in REGION.points if x.point_id == "station:metar:LTFM")
    want = 15.0 + 0.5 * (p.lat - 41.0) - 0.0065 * p.elevation_m
    assert second["temp_c"] == pytest.approx(want, abs=1e-3)


def test_missing_required_file_fails_the_run() -> None:
    with pytest.raises(RemoteFileGone):
        _collect(FakeDwd(missing={("T_2M", 1)}))


def test_eps_steps_and_member_urls() -> None:
    steps = icon.eps_steps(INIT, 168)
    assert steps[:2] == [0, 3] and steps[-1] == 120 and len(steps) == 33
    base = "https://opendata.dwd.de/weather/nwp/v1/m"
    w = icon.EPS_FIELDS[0]
    assert icon.file_url(base, icon.ICON_EU_EPS, w, INIT, 24, 7) == (
        f"{base}/icon-eu-eps/p/T_2M/r/2026-11-03T00:00/e/07/s/PT024H00M.grib2"
    )
