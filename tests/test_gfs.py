"""NOAA GFS adaptörü: .idx ayrıştırma, kayıt seçimi, adımlar ve yağış tipi (gerçek .idx ile)."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from tests.test_pipeline import synthetic_field

from hava.ingest.models import gfs

FIX = Path(__file__).parent / "fixtures" / "gfs"


def _idx(step: int) -> list[gfs.IdxEntry]:
    return gfs.parse_idx((FIX / f"gfs_20261103T00Z_f{step:03d}.idx").read_text(encoding="utf-8"))


def test_steps_and_url() -> None:
    steps = gfs.steps_for(168)
    assert steps[:2] == [0, 1] and steps[119:123] == [119, 120, 123, 126] and steps[-1] == 168
    assert len(steps) == 121 + 16
    init = datetime(2026, 11, 3, 0, tzinfo=UTC)
    assert (
        gfs.grib_url("https://b", init, 9)
        == "https://b/gfs.20261103/00/atmos/gfs.t00z.pgrb2.0p25.f009"
    )


def test_idx_lengths_come_from_next_offset() -> None:
    entries = _idx(9)
    assert entries[0].offset == 0 and entries[0].length == entries[1].offset
    assert entries[-1].length is None  # son kayıt dosya sonuna kadar
    assert (entries[0].name, entries[0].level, entries[0].time) == (
        "PRMSL",
        "mean sea level",
        "9 hour fcst",
    )


def test_select_takes_running_total_and_instant_flags() -> None:
    entries = _idx(9)
    chosen = {w.var: e for w, e in gfs.select(entries, gfs.FIELDS, 9)}
    assert set(chosen) == {w.var for w in gfs.FIELDS}
    assert chosen["precip_acc"].time == "0-9 hour acc fcst"  # 6-9 kovası değil
    assert chosen["conv_acc"].time == "0-9 hour acc fcst"
    assert chosen["crain"].time == "9 hour fcst"  # 6-9 ortalaması değil
    assert chosen["tcc"].time == "9 hour fcst" and chosen["t850"].level == "850 mb"
    late = {w.var: e for w, e in gfs.select(_idx(123), gfs.FIELDS, 123)}
    assert late["precip_acc"].time == "0-123 hour acc fcst"  # 120-123 kovası değil


def test_analysis_step_has_static_fields_and_no_accumulation() -> None:
    chosen = {w.var: e for w, e in gfs.select(_idx(0), gfs.FIELDS + gfs.STATIC, 0)}
    assert {"lsm", "orog", "t2m", "vis", "gust"} <= set(chosen)
    assert "precip_acc" not in chosen and "conv_acc" not in chosen
    assert all(e.time == "anl" for e in chosen.values())


def test_precip_type_priority() -> None:
    def flags(**on: int) -> dict[str, gfs.GribField]:
        return {k: synthetic_field(float(on.get(k, 0)), k) for k in gfs.FLAGS}

    code = lambda **on: float(gfs.precip_type(flags(**on)).values[0, 0])  # noqa: E731
    assert code() == 0.0 and code(crain=1) == 1.0 and code(csnow=1) == 5.0
    assert code(crain=1, csnow=1) == 7.0 and code(cicep=1, csnow=1) == 8.0
    assert code(cfrzr=1, crain=1, csnow=1) == 3.0
    missing = flags(crain=1)
    missing["csnow"] = synthetic_field(np.nan, "csnow")
    assert np.isnan(gfs.precip_type(missing).values).all()
