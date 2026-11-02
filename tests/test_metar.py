"""METAR ayrıştırıcı testleri: gerçek örnekler (fixtures/metar) ve etiketli sentetik dizgiler."""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hava.ingest.obs.metar import (
    MetarParseError,
    observation_values,
    parse_metar,
    relative_humidity,
)

FIXTURES = Path(__file__).parent / "fixtures" / "metar"


def _cases() -> dict[str, str]:
    with open(FIXTURES / "iem_2025_cases.csv", newline="", encoding="utf-8") as fh:
        return {row["case"]: row["metar"] for row in csv.DictReader(fh)}


CASES = _cases()


def test_all_real_cases_parse_without_leftovers() -> None:
    for name, raw in CASES.items():
        assert parse_metar(raw).unparsed == (), name


def test_cavok_and_variable_wind() -> None:
    m = parse_metar(CASES["cavok"])  # 21010KT 180V240 CAVOK 09/06 Q1033
    assert m.station == "LTFM" and (m.day, m.hour, m.minute) == (1, 8, 50)
    assert m.wind_dir_deg == 210 and m.wind_speed_ms == pytest.approx(5.14, abs=0.01)
    assert m.wind_variable and m.wind_gust_ms is None
    assert m.cavok and m.visibility_m == 10000 and m.visibility_ge_10km
    assert (m.temp_c, m.dewpoint_c, m.qnh_hpa) == (9, 6, 1033)
    assert m.cloud_cover_pct is None  # CAVOK 1500 m üstünü söylemez


def test_correction_negative_temperature_and_snow_shower() -> None:
    m = parse_metar(CASES["negative_temp"])  # COR ... -SHSN FEW006 BKN022 M00/M01
    assert m.correction
    assert m.temp_c == 0 and m.dewpoint_c == -1
    assert m.weather == ("-SHSN",)
    assert [(c.cover, c.base_m) for c in m.clouds] == [("FEW", 183), ("BKN", 671)]
    assert m.cloud_cover_pct == 75.0


def test_remarks_and_trend_are_not_parsed_as_body() -> None:
    # RMK'deki VRB / G18 / 00000KT ve TEMPO'daki VV002 gövdeye karışmamalı.
    assert parse_metar(CASES["vrb_wind"]).wind_dir_deg == 210
    assert parse_metar(CASES["gust_variable_dir"]).wind_gust_ms is None
    assert parse_metar(CASES["calm"]).wind_dir_deg == 220
    m = parse_metar(
        CASES["vertical_visibility"]
    )  # 1800 0550SW ... BCFG SCT002 ... TEMPO 0400 FG VV002
    assert not m.sky_obscured and m.vertical_visibility_m is None
    assert (m.visibility_m, m.visibility_min_m) == (1800, 550)
    assert m.weather == ("BCFG",)
    tempo = parse_metar(CASES["tempo"])  # 2500 BR SCT003 ... TEMPO 0600 FG BKN002
    assert tempo.visibility_m == 2500 and tempo.weather == ("BR",)
    assert parse_metar(CASES["becmg"]).visibility_m == 4000  # BECMG TL0750 9999 değil


def test_calm_fog_and_vertical_visibility() -> None:
    m = parse_metar(CASES["rvr_missing"])  # 00000KT 0100 R05////// R23/0100N FG VV000 07/06
    assert m.wind_speed_ms == 0 and m.wind_dir_deg is None and not m.wind_variable
    assert m.visibility_m == 100
    assert m.weather == ("FG",)
    assert m.sky_obscured and m.vertical_visibility_m == 0
    assert m.cloud_cover_pct == 100.0


def test_missing_visibility_is_not_invented() -> None:
    m = parse_metar(CASES["vis_missing"])  # 05003KT //// BR NSC
    assert m.visibility_m is None and not m.visibility_ge_10km
    assert m.no_significant_cloud and m.cloud_cover_pct is None


def test_weather_recent_weather_and_convective_clouds() -> None:
    m = parse_metar(CASES["recent_weather"])  # -SHRA SCT009 FEW020CB BKN025 ... RETSRA
    assert m.weather == ("-SHRA",) and m.recent_weather == ("RETSRA",)
    assert [c.cloud_type for c in m.clouds] == [None, "CB", None]
    assert parse_metar(CASES["thunderstorm_cb"]).weather == ("-TSRA",)
    assert parse_metar(CASES["shower_tcu"]).clouds[1].cloud_type == "TCU"
    heavy = parse_metar(CASES["heavy_rain"])  # VRB05KT 3400 +RA ... RESHRA
    assert heavy.wind_variable and heavy.wind_dir_deg is None
    assert heavy.weather == ("+RA",) and heavy.recent_weather == ("RESHRA",)


def test_snow_humidity_and_wind_shear() -> None:
    m = parse_metar(CASES["snow"])  # -SN BKN030 00/M03
    assert m.weather == ("-SN",)
    assert m.rh_pct == pytest.approx(80.2, abs=0.1)
    ws = parse_metar(CASES["ws"])  # Q1006 WS R17L NOSIG
    assert ws.qnh_hpa == 1006 and ws.unparsed == ()


def test_awc_raw_observations_match_awc_decoded_fields() -> None:
    records = json.loads((FIXTURES / "awc_metar_2026-11-02.json").read_text(encoding="utf-8"))
    assert len(records) == 33
    for r in records:
        m = parse_metar(r["rawOb"])  # "METAR LTFJ ..." önekiyle gelir
        assert m.station == r["icaoId"] and m.unparsed == ()
        assert (m.temp_c, m.dewpoint_c, m.qnh_hpa) == (r["temp"], r["dewp"], r["altim"])
        assert m.wind_speed_ms == pytest.approx(r["wspd"] * 0.514444, abs=0.01)
        obs = datetime.fromtimestamp(r["obsTime"], UTC)
        assert (m.day, m.hour, m.minute) == (obs.day, obs.hour, obs.minute)


# --- Sentetik dizgiler (Türk METAR'larında görülmeyen biçimler) ---


@pytest.mark.parametrize(
    ("raw", "expected_m"),
    [
        ("KXYZ 011200Z 00000KT P6SM CLR 10/05 A2992", 9656),
        ("KXYZ 011200Z 00000KT 1 1/2SM BR OVC004 10/09 A2992", 2414),
        ("KXYZ 011200Z 00000KT 1/2SM FG VV001 10/10 A2992", 805),
    ],
)
def test_synthetic_statute_mile_visibility(raw: str, expected_m: float) -> None:
    m = parse_metar(raw)
    assert m.visibility_m == expected_m and m.unparsed == ()


def test_synthetic_units_and_missing_groups() -> None:
    m = parse_metar("SPECI ABCD 011200Z AUTO 27010G20MPS 9999 //// SKC ///// A2992 RMK X")
    assert m.report_type == "SPECI" and m.auto
    assert (m.wind_speed_ms, m.wind_gust_ms) == (10.0, 20.0)
    assert m.sky_clear and m.cloud_cover_pct == 0.0
    assert m.qnh_hpa == pytest.approx(1013.2, abs=0.1)
    missing = parse_metar("ABCD 011200Z /////KT 9999 NSC ///// Q////")
    assert missing.wind_speed_ms is None and missing.temp_c is None and missing.qnh_hpa is None


@pytest.mark.parametrize("raw", ["", "LTFM", "LTFM 0120Z 00000KT", "12345 011200Z"])
def test_header_errors_raise(raw: str) -> None:
    with pytest.raises(MetarParseError):
        parse_metar(raw)


def test_relative_humidity_saturation_and_clip() -> None:
    assert relative_humidity(15, 15) == pytest.approx(100.0)
    assert relative_humidity(15, 16) == 100.0  # yuvarlama kaynaklı Td > T kırpılır


def test_observation_values_keep_raw_and_units() -> None:
    m = parse_metar(CASES["heavy_rain"])
    at = datetime(2025, 9, 29, 8, 20, tzinfo=UTC)
    v = observation_values(m, at, "iem")
    assert v["observed_at"] == at and v["present_weather"] == "+RA"
    assert v["precip_mm"] is None  # Türk METAR'larında yağış miktarı yok
    assert v["pressure_hpa"] == 1014 and v["raw"]["pressure_kind"] == "qnh"
    assert v["raw"]["source"] == "iem" and v["raw"]["metar"].startswith("LTFJ 290820Z")
    assert v["cloud_cover_pct"] == 75.0
