"""Gözlem kalite kontrolü (spec §5.3).

Hatalı değer silinmez, ``qc_flags``'e işaretlenir::

    {"version": "qc-1", "temp_c": ["spike"], "_record": ["time_mismatch"]}

``_record`` tüm satırı etkiler. Doğrulama ve eğitimde yalnız ``passed()`` olan değerler kullanılır.
Eşikler İstanbul'daki üç METAR istasyonu (deniz seviyesine yakın, birbirine 15–50 km) için seçildi
ve ``docs/qc.md``'de gerekçeleriyle yazılı.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from hava.db.models import Observation, Station

QC_VERSION = "qc-1"
VARIABLES = (
    "temp_c",
    "dewpoint_c",
    "rh_pct",
    "pressure_hpa",
    "wind_speed_ms",
    "wind_gust_ms",
    "visibility_m",
)
# Fiziksel/iklimsel sınırlar (İstanbul rekorlarının epey dışında; yalnız açık hataları yakalar).
LIMITS: dict[str, tuple[float, float]] = {
    "temp_c": (-30.0, 48.0),
    "dewpoint_c": (-40.0, 32.0),
    "rh_pct": (0.0, 100.0),
    "pressure_hpa": (950.0, 1055.0),
    "wind_speed_ms": (0.0, 50.0),
    "wind_gust_ms": (0.0, 70.0),
    "visibility_m": (0.0, 10000.0),
}
# Tek noktalık sıçrama: değer iki komşusundan aynı yönde bu kadar sapıyor, komşular birbirine yakın.
SPIKE = {"temp_c": 6.0, "dewpoint_c": 8.0, "pressure_hpa": 3.0}
# Ani basamak: ≤35 dakikada bu kadar değişim.
STEP = {"temp_c": 10.0, "dewpoint_c": 12.0, "pressure_hpa": 5.0}
# Komşu istasyon: (bu istasyonun diğer ikisinin ortalamasından sapması, diğer ikisinin kendi farkı).
# Sıcaklık/çiy noktasında Karadeniz–Marmara kıyıları arasında cephe ve siste 12–13,5 °C'lik gerçek
# farklar görüldü (2024–2026); eşik bunun üstünde, yalnız kaba hatayı yakalar.
NEIGHBOR = {"temp_c": (13.0, 4.0), "dewpoint_c": (14.0, 5.0), "pressure_hpa": (5.0, 2.0)}
# Değişmeyen değer: METAR tam sayı olduğu için yağışlı/kapalı havada sıcaklık 30+ saat aynı
# kalabiliyor. Bu yüzden ancak bir komşu aynı sürede en az FLATLINE_RANGE değiştiyse işaretlenir.
FLATLINE_H = 24.0
FLATLINE_ALONE_H = 48.0  # komşu verisi yoksa
FLATLINE_RANGE = {"temp_c": 3.0, "dewpoint_c": 3.0, "pressure_hpa": 3.0}

MAX_GAP = timedelta(minutes=75)  # ardışık sayılan iki gözlem arası
STEP_GAP = timedelta(minutes=35)
SAME_TIME = timedelta(minutes=10)  # komşu istasyonda "aynı an"
MARGIN_BEFORE = timedelta(hours=49)  # değişmeyen değer kuralı için geriye bakış
MARGIN_AFTER = timedelta(hours=2)
_TIME_GROUP = re.compile(r"\b(\d{2})(\d{2})(\d{2})Z\b")


@dataclass(frozen=True)
class ObsPoint:
    station_id: int
    observed_at: datetime
    values: dict[str, float | None]
    metar: str | None = None


Key = tuple[int, datetime]


def passed(qc_flags: dict[str, Any] | None, variable: str) -> bool:
    """Değer doğrulama/eğitimde kullanılabilir mi?"""
    if not qc_flags:
        return True
    return not qc_flags.get(variable) and not qc_flags.get("_record")


def _series_ok(
    pts: Sequence[ObsPoint], var: str, flags: dict[Key, dict[str, set[str]]]
) -> list[tuple[ObsPoint, float]]:
    """Değişkenin dolu ve sınır kontrolünden geçmiş değerleri (zamana göre sıralı)."""
    out = []
    for p in pts:
        x = p.values.get(var)
        if x is not None and "range" not in flags[(p.station_id, p.observed_at)][var]:
            out.append((p, x))
    return out


def compute_flags(points: Sequence[ObsPoint]) -> dict[Key, dict[str, list[str]]]:
    flags: dict[Key, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    by_station: dict[int, list[ObsPoint]] = defaultdict(list)
    for p in points:
        by_station[p.station_id].append(p)
        key = (p.station_id, p.observed_at)
        flags[key]  # her nokta sonuçta yer alsın
        v = p.values
        for var, (lo, hi) in LIMITS.items():
            x = v.get(var)
            if x is not None and not lo <= x <= hi:
                flags[key][var].add("range")
        t, td = v.get("temp_c"), v.get("dewpoint_c")
        if t is not None and td is not None and td > t:
            flags[key]["dewpoint_c"].add("dewpoint_gt_temp")
        ws, wg = v.get("wind_speed_ms"), v.get("wind_gust_ms")
        if ws is not None and wg is not None and wg < ws:
            flags[key]["wind_gust_ms"].add("gust_lt_speed")
        if p.metar and (m := _TIME_GROUP.search(p.metar)):
            at = p.observed_at
            if (int(m[1]), int(m[2]), int(m[3])) != (at.day, at.hour, at.minute):
                flags[key]["_record"].add("time_mismatch")

    for pts in by_station.values():
        pts.sort(key=lambda p: p.observed_at)
    for var in SPIKE:
        ok = {sid: _series_ok(pts, var, flags) for sid, pts in by_station.items()}
        for series in ok.values():
            _temporal(series, var, flags)
        _flatline(ok, var, flags)
    _neighbors(by_station, flags)
    return {
        key: {var: sorted(rules) for var, rules in fl.items() if rules} for key, fl in flags.items()
    }


def _temporal(
    series: list[tuple[ObsPoint, float]], var: str, flags: dict[Key, dict[str, set[str]]]
) -> None:
    last = 0  # karşılaştırma için son sıçrama olmayan değer
    for i in range(1, len(series)):
        p, x = series[i]
        prev, xp = series[last]
        if p.observed_at - prev.observed_at > MAX_GAP:
            last = i
            continue
        key = (p.station_id, p.observed_at)
        if i + 1 < len(series):
            nxt, xn = series[i + 1]
            if nxt.observed_at - p.observed_at <= MAX_GAP:
                d1, d2 = x - xp, x - xn
                lim = SPIKE[var]
                if abs(d1) > lim and abs(d2) > lim and d1 * d2 > 0 and abs(xp - xn) <= lim / 2:
                    flags[key][var].add("spike")
                    continue
        if p.observed_at - prev.observed_at <= STEP_GAP and abs(x - xp) > STEP[var]:
            flags[key][var].add("step")
        last = i


def _runs(series: list[tuple[ObsPoint, float]]) -> list[list[tuple[ObsPoint, float]]]:
    """Aynı değerli, boşluksuz (≤75 dk) ardışık gözlem grupları."""
    runs: list[list[tuple[ObsPoint, float]]] = []
    for item in series:
        last = runs[-1][-1] if runs else None
        if (
            last is not None
            and item[1] == last[1]
            and item[0].observed_at - last[0].observed_at <= MAX_GAP
        ):
            runs[-1].append(item)
        else:
            runs.append([item])
    return runs


def _neighbor_varied(
    ok: dict[int, list[tuple[ObsPoint, float]]], sid: int, lo: datetime, hi: datetime, var: str
) -> bool | None:
    """Komşulardan biri [lo, hi] aralığında FLATLINE_RANGE kadar değişti mi? Veri yoksa None."""
    seen = False
    for osid, series in ok.items():
        if osid == sid:
            continue
        vals = [x for p, x in series if lo <= p.observed_at <= hi]
        if len(vals) >= 2:
            seen = True
            if max(vals) - min(vals) >= FLATLINE_RANGE[var]:
                return True
    return False if seen else None


def _flatline(
    ok: dict[int, list[tuple[ObsPoint, float]]], var: str, flags: dict[Key, dict[str, set[str]]]
) -> None:
    for sid, series in ok.items():
        for run in _runs(series):
            lo, hi = run[0][0].observed_at, run[-1][0].observed_at
            if hi - lo < timedelta(hours=FLATLINE_H):
                continue
            varied = _neighbor_varied(ok, sid, lo, hi, var)
            if varied or (varied is None and hi - lo >= timedelta(hours=FLATLINE_ALONE_H)):
                for p, _ in run:
                    flags[(p.station_id, p.observed_at)][var].add("flatline")


def _neighbors(
    by_station: dict[int, list[ObsPoint]], flags: dict[Key, dict[str, set[str]]]
) -> None:
    if len(by_station) < 3:
        return
    for var, (dev, agree) in NEIGHBOR.items():
        ok = {sid: _series_ok(pts, var, flags) for sid, pts in by_station.items()}
        for sid, series in ok.items():
            for p, x in series:
                others = []
                for osid, oseries in ok.items():
                    if osid == sid:
                        continue
                    near = _nearest(oseries, p.observed_at)
                    if near is not None:
                        others.append(near)
                if len(others) < 2:
                    continue
                if max(others) - min(others) <= agree and abs(x - mean(others)) > dev:
                    flags[(p.station_id, p.observed_at)][var].add("neighbor")


def _nearest(series: list[tuple[ObsPoint, float]], at: datetime) -> float | None:
    """``at``'e en yakın (±10 dk) değer; ikili arama."""
    lo, hi = 0, len(series)
    while lo < hi:
        mid = (lo + hi) // 2
        if series[mid][0].observed_at < at:
            lo = mid + 1
        else:
            hi = mid
    best: float | None = None
    best_dt = SAME_TIME
    for j in (lo - 1, lo):
        if 0 <= j < len(series):
            dt = abs(series[j][0].observed_at - at)
            if dt <= best_dt:
                best, best_dt = series[j][1], dt
    return best


def run_qc(session: Session, start: datetime, end: datetime) -> dict[str, int]:
    """[start, end] aralığındaki METAR gözlemlerinin bayraklarını yeniden hesaplar ve yazar."""
    cols = [getattr(Observation, v) for v in VARIABLES]
    rows = session.execute(
        select(
            Observation.station_id,
            Observation.observed_at,
            Observation.qc_flags,
            Observation.raw["metar"].astext,
            *cols,
        )
        .join(Station, Station.id == Observation.station_id)
        .where(
            Station.source == "metar",
            Observation.observed_at >= start - MARGIN_BEFORE,
            Observation.observed_at <= end + MARGIN_AFTER,
        )
    ).all()
    points = []
    current: dict[Key, dict[str, Any]] = {}
    for r in rows:
        sid, at, qc, metar = r[0], r[1], r[2], r[3]
        points.append(ObsPoint(sid, at, dict(zip(VARIABLES, r[4:], strict=True)), metar))
        current[(sid, at)] = qc or {}
    computed = compute_flags(points)
    updates = []
    flagged = 0
    for key, fl in computed.items():
        if not start <= key[1] <= end:
            continue
        new = {"version": QC_VERSION, **fl}
        flagged += bool(fl)
        if new != current[key]:
            updates.append({"station_id": key[0], "observed_at": key[1], "qc_flags": new})
    if updates:
        session.execute(update(Observation), updates)
    checked = sum(1 for k in computed if start <= k[1] <= end)
    return {"checked": checked, "updated": len(updates), "flagged": flagged}
