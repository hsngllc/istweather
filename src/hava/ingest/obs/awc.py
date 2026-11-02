"""AWC Data API'den canlı METAR (spec §5.3).

``GET /api/data/metar?ids=...&format=json&hours=N``: en fazla 30 gün geriye, 100 istek/dk, istek
başına 400 kayıt; veri yoksa 204. Gerçek gözlem zamanı ``obsTime``'dır (``reportTime`` :50
gözlemini sonraki saate yuvarlar). Değerler ``rawOb``'dan kendi ayrıştırıcımızla çözülür.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import httpx

from hava.ingest.archive.http_range import get_with_retry
from hava.ingest.obs.store import RawReport

MAX_RECORDS = 400


class AwcResponseError(RuntimeError):
    """AWC yanıtı beklenen biçimde değil."""


def fetch_awc(
    client: httpx.Client, url: str, stations: Sequence[str], hours: int
) -> list[RawReport]:
    resp = get_with_retry(
        client,
        url,
        attempts=3,
        params={"ids": ",".join(stations), "format": "json", "hours": str(hours)},
    )
    if resp.status_code == 204:
        return []
    records: Any = resp.json()
    if not isinstance(records, list):
        raise AwcResponseError(f"liste bekleniyordu: {type(records).__name__}")
    if len(records) >= MAX_RECORDS:
        raise AwcResponseError(f"{MAX_RECORDS} kayıt sınırına ulaşıldı; saat aralığını küçültün")
    reports = []
    for r in records:
        try:
            reports.append(
                RawReport(
                    station=str(r["icaoId"]),
                    observed_at=datetime.fromtimestamp(int(r["obsTime"]), UTC),
                    text=str(r["rawOb"]),
                    source="awc",
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AwcResponseError(f"eksik alan: {exc}") from exc
    return reports
