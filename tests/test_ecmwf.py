"""ECMWF IFS ve AIFS adaptörü: adımlar, adresler, index seçimi (gerçek index örnekleriyle)."""

from datetime import UTC, datetime
from pathlib import Path

from hava.ingest.models import ecmwf

FIX = Path(__file__).parent / "fixtures" / "ecmwf"
BASE = "https://data.ecmwf.int/forecasts"


def _index(name: str) -> list[dict[str, object]]:
    return ecmwf.parse_index((FIX / name).read_text(encoding="utf-8"))


def test_steps_follow_run_hour() -> None:
    d00 = ecmwf.steps_for(datetime(2026, 11, 2, 0, tzinfo=UTC), 168)
    d06 = ecmwf.steps_for(datetime(2026, 11, 2, 6, tzinfo=UTC), 168)
    assert d00[:3] == [0, 3, 6] and d00[-5:] == [144, 150, 156, 162, 168]
    assert d06[-1] == 144 and len(d06) == 49


def test_urls_match_portal_layout() -> None:
    init = datetime(2026, 11, 2, 6, tzinfo=UTC)
    assert ecmwf.index_url(BASE, init, 6, "pl") == (
        f"{BASE}/20261102/06z/ifs/0p1/oper/20261102060000-6h-oper-fc-pl.index"
    )
    assert ecmwf.grib_url(BASE, init, 0, "sfc").endswith("20261102060000-0h-oper-fc-sfc.grib2")


def test_select_step0_includes_static_fields_and_skips_empty_messages() -> None:
    entries = _index("ifs0p1_20261102T06Z_0h_sfc.index")
    chosen = ecmwf.select(entries, list(ecmwf.SFC) + list(ecmwf.STATIC), 0)
    got = {w.param for w, _ in chosen}
    assert {"2t", "2d", "10u", "10v", "msl", "tcc", "lcc", "ptype", "lsm", "z"} <= got
    # 0. adımda tp ve 10fg mesajları boş (_length 0) → seçilmez.
    assert all(int(e["_length"]) > 0 for _, e in chosen)


def test_select_uses_three_hour_gust_between_93_and_144() -> None:
    entries = _index("ifs0p1_20261102T06Z_96h_sfc.index")
    gust = [(w, e) for w, e in ecmwf.select(entries, ecmwf.SFC, 96) if w.var == "gust"]
    assert [w.param for w, _ in gust] == ["10fg3"]
    assert ecmwf.gust_definition(96) == "max_3h"
    assert ecmwf.gust_definition(90) == "max_1h" and ecmwf.gust_definition(150) == "max_6h"


def test_select_pressure_level_850_only() -> None:
    entries = _index("ifs0p1_20261102T06Z_6h_pl.index")
    chosen = ecmwf.select(entries, ecmwf.PL, 6)
    assert [(w.param, e["levelist"]) for w, e in chosen] == [("t", "850")]


def test_candidate_runs_are_six_hourly_and_oldest_first() -> None:
    runs = ecmwf.candidate_runs(datetime(2026, 11, 2, 17, 40, tzinfo=UTC), 24)
    assert runs[-1] == datetime(2026, 11, 2, 12, tzinfo=UTC)
    assert runs[0] == datetime(2026, 11, 1, 12, tzinfo=UTC)
    assert len(runs) == 5


AIFS = ecmwf.AIFS_SINGLE


def test_aifs_steps_and_single_file_urls() -> None:
    init = datetime(2026, 11, 2, 18, tzinfo=UTC)
    steps = ecmwf.steps_for(init, 168, AIFS)
    assert steps[:3] == [0, 6, 12] and steps[-1] == 168 and len(steps) == 29
    assert ecmwf.index_url(BASE, init, 6, None, AIFS) == (
        f"{BASE}/20261102/18z/aifs-single/0p25/oper/20261102180000-6h-oper-fc.index"
    )
    files = ecmwf.files_for(AIFS, 0)
    assert len(files) == 1 and files[0][0] is None
    assert {w.var for w in files[0][1]} >= {"t2m", "t850", "lsm", "orog"}
    assert {w.var for w in ecmwf.files_for(AIFS, 6)[0][1]} & {"lsm", "orog"} == set()


def test_aifs_select_takes_surface_z_not_pressure_level_z() -> None:
    entries = _index("aifs0p25_20261102T18Z_0h.index")
    wanted = ecmwf.files_for(AIFS, 0)[0][1]
    chosen = {w.var: e for w, e in ecmwf.select(entries, wanted, 0)}
    assert set(chosen) == {w.var for w in wanted}  # hepsi var
    assert chosen["orog"]["levtype"] == "sfc" and chosen["t850"]["levelist"] == "850"


def test_aifs_units_differ_from_ifs() -> None:
    entries = _index("aifs0p25_20261102T18Z_6h.index")
    chosen = {w.var: w for w, _ in ecmwf.select(entries, ecmwf.files_for(AIFS, 6)[0][1], 6)}
    assert chosen["precip_acc"].scale == 1.0  # kg m-2 (IFS: m → ×1000)
    assert chosen["tcc"].scale == 0.01  # % (IFS: 0–1)
    assert "gust" not in chosen and "ptype" not in chosen  # AIFS'te yok
    assert AIFS.spec.gust_definition(6) is None
