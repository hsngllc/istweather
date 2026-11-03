"""NOAA GEFS 0.25° ensemble (31 üye; spec §5.1; docs/data-sources.md §2.3; ADR-0006).

Kaynak AWS NODD (``noaa-gefs-pds``):
``gefs.YYYYMMDD/HH/atmos/pgrb2sp25/<üye>.tHHz.pgrb2s.0p25.fFFF`` (+ ``.idx``); üyeler ``gec00``
(kontrol) ve ``gep01``–``gep30``. ``pgrb2s`` 0–240 sa 3 saatlik.
Kayıt seçimi GFS ile aynı (.idx zaman metni); 2026-11-03 .idx'lerinden:

- ``APCP`` yalnız 6 saatlik kova: f003 ``"0-3"``, f006 ``"0-6"``, f009 ``"6-9"``, f012 ``"6-12"``,
  f078 ``"72-78"``. Başlangıçtan beri toplam = kova başındaki toplam + kova değeri; kova başı (6'nın
  katı) her zaman adım planında olduğundan zincir kopmaz.
- ``GUST`` anlık. Kar miktarı yok.
- Orografi ``HGT:surface`` (f000, ``gec00``). ``pgrb2s``'te kara maskesi yok → aynı 0,25° ızgaradaki
  GFS deterministik ``LAND`` alanı kullanılır (spec §6: maske aynı merkezin başka ürününden).
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import httpx

from hava.ingest.archive.http_range import get_with_retry
from hava.ingest.models import ensemble, gfs
from hava.ingest.models.ensemble import EnsembleCollector
from hava.ingest.models.gfs import IdxEntry, Want, parse_idx, select
from hava.ingest.models.grib import decode_message
from hava.ingest.models.pipeline import ModelSpec
from hava.ingest.models.runner import Source, candidate_runs, pending, process_ensemble_run
from hava.processing.grid import BBox, FloatArray
from hava.region import Region, load_region
from hava.settings import Settings, get_settings

MODEL_CODE = "ncep_gefs"
EXTRACTOR_VERSION = "ncep-gefs-1"
RESOL = "0p25"
BASE_URL = "https://noaa-gefs-pds.s3.amazonaws.com"
MEMBERS = tuple(range(0, 31))
HORIZON_H = 240

FIELDS = (
    Want("TMP", "2 m above ground", "t2m"),
    Want("UGRD", "10 m above ground", "u10"),
    Want("VGRD", "10 m above ground", "v10"),
    Want("GUST", "surface", "gust"),
)
OROG = Want("HGT", "surface", "orog")
LAND = Want("LAND", "surface", "lsm")
BUCKET = re.compile(r"^(\d+)-(\d+) hour acc fcst$")

SPEC = ModelSpec(code=MODEL_CODE, gust_definition=lambda s: "instant")


def member_name(member: int) -> str:
    return "gec00" if member == 0 else f"gep{member:02d}"


def steps_for(max_lead_h: int) -> list[int]:
    return [s for s in ensemble.STEPS if s % 3 == 0 and s <= min(HORIZON_H, max_lead_h)]


def grib_url(base: str, init: datetime, member: int, step: int) -> str:
    return (
        f"{base}/gefs.{init:%Y%m%d}/{init:%H}/atmos/pgrb2sp25/"
        f"{member_name(member)}.t{init:%H}z.pgrb2s.0p25.f{step:03d}"
    )


def precip_bucket(entries: list[IdxEntry], step: int) -> tuple[int, IdxEntry] | None:
    """Adımdaki ``APCP`` kovası: (kova başı saati, kayıt)."""
    for e in entries:
        m = BUCKET.match(e.time)
        if e.name == "APCP" and e.level == "surface" and m and int(m.group(2)) == step:
            return int(m.group(1)), e
    return None


def run_complete(client: httpx.Client, base: str, init: datetime, max_lead_h: int) -> bool:
    last = steps_for(max_lead_h)[-1]
    url = grib_url(base, init, MEMBERS[-1], last) + ".idx"
    return client.get(url).status_code == 200


def _download(client: httpx.Client, url: str, e: IdxEntry) -> bytes:
    end = "" if e.length is None else str(e.offset + e.length - 1)
    headers = {"Range": f"bytes={e.offset}-{end}"}
    return get_with_retry(client, url, headers=headers, attempts=5).content


def _fetch_one(client: httpx.Client, url: str, idx_text: str, want: Want) -> bytes:
    e = next(iter(select(parse_idx(idx_text), (want,), 0)), None)
    if e is None:
        raise ValueError(f"{want.name}:{want.level} bulunamadı: {url}")
    return _download(client, url, e[1])


def collect_run(
    client: httpx.Client, settings: Settings, region: Region, init: datetime
) -> tuple[EnsembleCollector, dict[str, Any]]:
    bbox = BBox(region.lat_min, region.lat_max, region.lon_min, region.lon_max)
    col = EnsembleCollector(bbox.expanded(settings.model_crop_margin_deg), MEMBERS)
    stats = {"messages": 0, "bytes": 0}
    # Sabitler: GEFS orografisi ve GFS kara maskesi (aynı 0,25° ızgara).
    for url, want in (
        (grib_url(BASE_URL, init, 0, 0), OROG),
        (gfs.grib_url(settings.gfs_base_url, init, 0), LAND),
    ):
        blob = _fetch_one(client, url, get_with_retry(client, url + ".idx").text, want)
        col.add_static(want.var, decode_message(blob))
        stats["messages"] += 1
        stats["bytes"] += len(blob)
    totals: dict[int, dict[int, FloatArray]] = {m: {} for m in MEMBERS}  # üye → saat → toplam
    with ThreadPoolExecutor(settings.model_download_workers) as pool:
        for step in steps_for(settings.model_max_lead_h):
            urls = {m: grib_url(BASE_URL, init, m, step) for m in MEMBERS}
            idx = dict(
                zip(
                    MEMBERS,
                    pool.map(lambda u: get_with_retry(client, u + ".idx").text, urls.values()),
                    strict=True,
                )
            )
            # (üye, değişken, kayıt, kova başı saati)
            jobs: list[tuple[int, str, IdxEntry, int | None]] = []
            for m in MEMBERS:
                entries = parse_idx(idx[m])
                jobs += [(m, w.var, e, None) for w, e in select(entries, FIELDS, step)]
                bucket = precip_bucket(entries, step)
                if bucket is not None:
                    jobs.append((m, "precip_acc", bucket[1], bucket[0]))
            blobs = pool.map(lambda j, u=urls: _download(client, u[j[0]], j[2]), jobs)
            for (m, var, _, start), blob in zip(jobs, blobs, strict=True):
                values = col.crop_field(decode_message(blob))
                stats["messages"] += 1
                stats["bytes"] += len(blob)
                if start is None:
                    col.add_cropped(var, step, m, values)
                    continue
                if start == 0:
                    total = values
                elif start in totals[m]:
                    total = totals[m][start] + values
                else:
                    raise ValueError(f"üye {m}: {start}-{step} kovasının başı ({start} sa) yok")
                totals[m][step] = total
                col.add_cropped("precip_acc", step, m, total)
    return col, stats


def collect(max_runs: int = 1) -> list[dict[str, Any]]:
    """Worker işi: 00/12z çalıştırmaları (yeniden eskiye)."""
    settings = get_settings()
    region = load_region(settings.region_config)
    src = Source(SPEC, EXTRACTOR_VERSION, BASE_URL, RESOL, gfs.LICENSE)
    done: list[dict[str, Any]] = []
    with httpx.Client(timeout=120.0, headers={"User-Agent": settings.http_user_agent}) as client:
        # Önce en yeni çalıştırma (tazelik), sonra eksik kalan eskiler.
        candidates = candidate_runs(datetime.now(UTC), settings.model_lookback_hours, cycle_h=12)
        for init in reversed(candidates):
            if not pending(MODEL_CODE, init):
                continue
            if not run_complete(client, BASE_URL, init, settings.model_max_lead_h):
                continue

            def fetch(i: datetime = init) -> tuple[EnsembleCollector, dict[str, Any]]:
                return collect_run(client, settings, region, i)

            done.append(process_ensemble_run(src, settings, region, init, fetch))
            if len(done) >= max_runs:
                break
    return done
