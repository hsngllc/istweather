"""Gözlem QC raporu (Faz 2 kabulü): tamlık, boşluklar, kural × değişken işaret sayıları.

``python -m hava.qc.report --since 2024-01-01 [--until 2026-11-02] [--source awc] --out FILE``
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from hava.db.models import Observation, Station
from hava.db.session import session_scope
from hava.ops.logging import configure_logging
from hava.qc.observations import QC_VERSION, VARIABLES, passed

INTERVAL = timedelta(minutes=30)  # rutin METAR aralığı
GAP_REPORT = timedelta(hours=2)
EXAMPLE_VARS = ("temp_c", "dewpoint_c", "pressure_hpa", "wind_speed_ms", "wind_gust_ms")


@dataclass
class StationStats:
    icao: str
    times: list[datetime] = field(default_factory=list)
    filled: Counter[str] = field(default_factory=Counter)
    ok: Counter[str] = field(default_factory=Counter)
    rules: Counter[tuple[str, str]] = field(default_factory=Counter)
    flagged_rows: int = 0
    sources: Counter[str] = field(default_factory=Counter)
    examples: dict[tuple[str, str], list[str]] = field(default_factory=lambda: defaultdict(list))


def collect(
    session: Session, start: datetime, end: datetime, source: str | None
) -> dict[str, StationStats]:
    stmt = (
        select(
            Station.external_id,
            Observation.observed_at,
            Observation.qc_flags,
            Observation.raw,
            *[getattr(Observation, v) for v in VARIABLES],
        )
        .join(Station, Station.id == Observation.station_id)
        .where(
            Station.source == "metar",
            Observation.observed_at >= start,
            Observation.observed_at < end,
        )
        .order_by(Station.external_id, Observation.observed_at)
    )
    if source:
        stmt = stmt.where(Observation.raw["source"].astext == source)
    stats: dict[str, StationStats] = {}
    for row in session.execute(stmt):
        icao, at, qc, raw = row[0], row[1], row[2] or {}, row[3] or {}
        st = stats.setdefault(icao, StationStats(icao))
        st.times.append(at)
        st.sources[str(raw.get("source"))] += 1
        rule_hit = False
        values = dict(zip(VARIABLES, row[4:], strict=True))
        for var, value in values.items():
            if value is None:
                continue
            st.filled[var] += 1
            if passed(qc, var):
                st.ok[var] += 1
        for var, rules in qc.items():
            if var == "version":
                continue
            for rule in rules:
                rule_hit = True
                st.rules[(var, rule)] += 1
                ex = st.examples[(var, rule)]
                if len(ex) < 3:
                    # Ham METAR yeniden dağıtılmaz (spec §11); örnekte çözülmüş değerler gösterilir.
                    shown = ", ".join(
                        f"{v}={values[v]:g}" for v in EXAMPLE_VARS if values[v] is not None
                    )
                    ex.append(f"{at:%Y-%m-%d %H:%M}Z ({shown})")
        st.flagged_rows += rule_hit
    return stats


def _gaps(times: list[datetime], start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    return [(a, b) for a, b in pairwise([start, *times, end]) if b - a > GAP_REPORT]


def _gap_text(a: datetime, b: datetime) -> str:
    return f"{a:%Y-%m-%d %H:%M}→{b:%Y-%m-%d %H:%M} ({(b - a).total_seconds() / 3600:.1f} sa)"


def render(
    stats: dict[str, StationStats], start: datetime, end: datetime, source: str | None
) -> str:
    expected = int((end - start) / INTERVAL)
    now = datetime.now(UTC)
    lines = [
        "# Gözlem QC raporu",
        "",
        f"- Dönem: {start:%Y-%m-%d %H:%M} – {end:%Y-%m-%d %H:%M} UTC",
        f"- Kaynak filtresi: {source or 'tümü (AWC canlı + IEM geçmiş)'}",
        f"- QC sürümü: `{QC_VERSION}` (kurallar: `docs/qc.md`)",
        f"- Oluşturulma: {now:%Y-%m-%d %H:%M} UTC",
        f"- Beklenen rutin gözlem: istasyon başına {expected} (30 dakikada bir)",
        "",
        "## Özet",
        "",
        "| İstasyon | Gözlem | Tamlık | En uzun boşluk | >2 sa boşluk | İşaretli satır | Kaynak |",
        "|---|---|---|---|---|---|---|",
    ]
    for icao, st in sorted(stats.items()):
        gaps = _gaps(st.times, start, end)
        longest = max(((b - a) for a, b in gaps), default=timedelta(0))
        src = ", ".join(f"{k} {v}" for k, v in st.sources.most_common())
        lines.append(
            f"| {icao} | {len(st.times)} | {100 * len(st.times) / max(expected, 1):.1f}% | "
            f"{longest.total_seconds() / 3600:.1f} sa | {len(gaps)} | "
            f"{st.flagged_rows} ({100 * st.flagged_rows / max(len(st.times), 1):.2f}%) | {src} |"
        )
    lines += ["", "## Değişken kullanılabilirliği (dolu / QC'den geçen)", ""]
    lines.append("| İstasyon | " + " | ".join(VARIABLES) + " |")
    lines.append("|---" * (len(VARIABLES) + 1) + "|")
    for icao, st in sorted(stats.items()):
        n = max(len(st.times), 1)
        cells = [f"{100 * st.filled[v] / n:.1f}% / {100 * st.ok[v] / n:.1f}%" for v in VARIABLES]
        lines.append(f"| {icao} | " + " | ".join(cells) + " |")
    lines += ["", "## QC işaretleri (değişken × kural)", ""]
    all_rules = sorted({k for st in stats.values() for k in st.rules})
    if not all_rules:
        lines.append("İşaret yok.")
    else:
        lines.append("| Değişken | Kural | " + " | ".join(sorted(stats)) + " |")
        lines.append("|---|---|" + "---|" * len(stats))
        for var, rule in all_rules:
            counts = " | ".join(str(stats[s].rules[(var, rule)]) for s in sorted(stats))
            lines.append(f"| {var} | {rule} | {counts} |")
    lines += ["", "## Boşluklar (> 2 saat, istasyon başına en uzun 10)", ""]
    for icao, st in sorted(stats.items()):
        gaps = sorted(_gaps(st.times, start, end), key=lambda g: g[1] - g[0], reverse=True)[:10]
        lines.append(f"**{icao}:** " + (", ".join(_gap_text(a, b) for a, b in gaps) or "yok"))
        lines.append("")
    lines += ["## Örnek işaretli kayıtlar (kural başına en fazla 3)", ""]
    for icao, st in sorted(stats.items()):
        for (var, rule), ex in sorted(st.examples.items()):
            lines.append(f"- **{icao} {var} / {rule}:** " + "; ".join(ex))
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gözlem QC raporu üretir (Markdown).")
    ap.add_argument("--since", required=True, help="YYYY-MM-DD veya YYYY-MM-DDTHH:MM (UTC)")
    ap.add_argument("--until", default=None, help="varsayılan: şimdi")
    ap.add_argument("--source", choices=["awc", "iem"], default=None)
    ap.add_argument("--out", default=None, help="dosya; verilmezse ekrana")
    args = ap.parse_args(argv)
    configure_logging()

    def parse(s: str) -> datetime:
        return datetime.fromisoformat(s).replace(tzinfo=UTC)

    start = parse(args.since)
    end = parse(args.until) if args.until else datetime.now(UTC)
    with session_scope() as session:
        stats = collect(session, start, end, args.source)
    text = render(stats, start, end, args.source)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
