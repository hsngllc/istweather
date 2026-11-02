"""QC kuralları (spec §13 zorunlu test). Seriler sentetiktir ve öyle adlandırılmıştır."""

from datetime import UTC, datetime, timedelta

from hava.qc.observations import ObsPoint, compute_flags, passed

T0 = datetime(2025, 1, 15, 0, 20, tzinfo=UTC)
STEP = timedelta(minutes=30)


def synthetic_series(
    station: int, temps: list[float | None], **extra: list[float | None]
) -> list[ObsPoint]:
    pts = []
    for i, t in enumerate(temps):
        values: dict[str, float | None] = {"temp_c": t}
        for name, seq in extra.items():
            values[name] = seq[i]
        pts.append(ObsPoint(station, T0 + i * STEP, values))
    return pts


def flags_for(points: list[ObsPoint], station: int, index: int) -> dict[str, list[str]]:
    return compute_flags(points)[(station, T0 + index * STEP)]


def test_range_and_internal_consistency() -> None:
    pts = synthetic_series(
        1,
        [10, 60, 10],
        dewpoint_c=[5, 5, 12],
        wind_speed_ms=[5, 5, 8],
        wind_gust_ms=[10, 10, 6],
        pressure_hpa=[1013, 1013, 900],
    )
    assert flags_for(pts, 1, 0) == {}
    assert flags_for(pts, 1, 1) == {"temp_c": ["range"]}
    last = flags_for(pts, 1, 2)
    assert last == {
        "dewpoint_c": ["dewpoint_gt_temp"],
        "wind_gust_ms": ["gust_lt_speed"],
        "pressure_hpa": ["range"],
    }


def test_spike_flags_only_the_outlier() -> None:
    pts = synthetic_series(1, [8, 8, 9, 20, 9, 9])
    flags = compute_flags(pts)
    assert flags[(1, T0 + 3 * STEP)] == {"temp_c": ["spike"]}
    assert all(flags[(1, T0 + i * STEP)] == {} for i in (0, 1, 2, 4, 5))


def test_sustained_change_is_step_not_spike() -> None:
    # Ani ve kalıcı 11 °C değişim: yalnız basamak noktası işaretlenir.
    pts = synthetic_series(1, [5, 5, 16, 16, 16])
    flags = compute_flags(pts)
    assert flags[(1, T0 + 2 * STEP)] == {"temp_c": ["step"]}
    assert flags[(1, T0 + 3 * STEP)] == {}


def test_ordinary_front_passage_is_not_flagged() -> None:
    pts = synthetic_series(1, [14, 12, 9, 7, 6], pressure_hpa=[1004, 1005, 1007, 1008, 1009])
    assert all(v == {} for v in compute_flags(pts).values())


def test_gap_breaks_temporal_checks() -> None:
    pts = synthetic_series(1, [8, 20, 8])
    moved = [
        pts[0],
        ObsPoint(1, T0 + 3 * STEP, pts[1].values),
        ObsPoint(1, T0 + 6 * STEP, pts[2].values),
    ]
    assert all(v == {} for v in compute_flags(moved).values())


def _diurnal(station: int, n: int) -> list[ObsPoint]:
    """Sentetik: komşu istasyonda 24 saatlik döngüyle 6–12 °C arası değişen sıcaklık."""
    return synthetic_series(station, [9.0 + 3.0 * ((i % 48) / 24 - 1) for i in range(n)])


def test_flatline_needs_a_varying_neighbor() -> None:
    stuck = synthetic_series(1, [7.0] * 49)  # 24 saat aynı değer
    flags = compute_flags(stuck + _diurnal(2, 49))
    assert all(flags[(1, T0 + i * STEP)] == {"temp_c": ["flatline"]} for i in range(49))
    short = synthetic_series(1, [7.0] * 48)  # 23,5 saat
    assert all(v == {} for k, v in compute_flags(short + _diurnal(2, 48)).items() if k[0] == 1)


def test_flatline_in_steady_weather_is_not_flagged() -> None:
    # Yağışlı poyrazda sıcaklık 30+ saat neredeyse sabit (gerçek vaka: LTBA 2026-03-21).
    a = synthetic_series(1, [9.0] * 68)
    b = synthetic_series(2, [8.0, 9.0] * 34)
    assert all(v == {} for v in compute_flags(a + b).values())


def test_flatline_without_neighbors_needs_48_hours() -> None:
    assert all(v == {} for v in compute_flags(synthetic_series(1, [7.0] * 90)).values())
    long = compute_flags(synthetic_series(1, [7.0] * 97))  # 48 saat
    assert all(v == {"temp_c": ["flatline"]} for v in long.values())


def test_neighbor_needs_two_agreeing_stations() -> None:
    a = synthetic_series(1, [10, 10, 10])
    b = synthetic_series(2, [11, 11, 11])
    c = synthetic_series(3, [10, 25, 10])  # ortadaki hem sıçrama hem komşulardan 14,5 °C sapma
    flags = compute_flags(a + b + c)
    assert "neighbor" in flags[(3, T0 + STEP)]["temp_c"]
    assert flags[(1, T0 + STEP)] == {} and flags[(2, T0 + STEP)] == {}
    front = compute_flags(
        a + b + synthetic_series(3, [10, 22, 22])
    )  # 11,5 °C: gerçek cephe olabilir
    assert all("neighbor" not in fl.get("temp_c", []) for fl in front.values())
    disagree = synthetic_series(2, [18, 18, 18])  # diğer ikisi de uyuşmuyorsa karar verilmez
    flags2 = compute_flags(a + disagree + synthetic_series(3, [10, 10, 10]))
    assert all("neighbor" not in fl.get("temp_c", []) for fl in flags2.values())


def test_time_mismatch_between_metar_and_source() -> None:
    p = ObsPoint(1, T0, {"temp_c": 6.0}, metar="LTFJ 150050Z 05015KT 9999 06/04 Q1023")
    assert compute_flags([p])[(1, T0)] == {"_record": ["time_mismatch"]}
    ok = ObsPoint(1, T0, {"temp_c": 6.0}, metar="LTFJ 150020Z 05015KT 9999 06/04 Q1023")
    assert compute_flags([ok])[(1, T0)] == {}


def test_passed() -> None:
    assert passed({}, "temp_c") and passed(None, "temp_c")
    assert passed({"version": "qc-1", "dewpoint_c": ["range"]}, "temp_c")
    assert not passed({"version": "qc-1", "temp_c": ["spike"]}, "temp_c")
    assert not passed({"version": "qc-1", "_record": ["time_mismatch"]}, "temp_c")
