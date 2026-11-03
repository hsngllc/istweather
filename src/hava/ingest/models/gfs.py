"""NOAA GFS 0.25° deterministik (spec §5.1; docs/data-sources.md §2.2).

Kaynak AWS NODD (``noaa-gfs-bdp-pds``, anonim HTTPS): tüm geçmiş duruyor, Range destekleniyor.
Her adımın ``.idx`` dosyasından (``no:offset:d=YYYYMMDDHH:VAR:seviye:zaman:``) gereken mesajlar
seçilir ve byte-range ile indirilir; mesaj uzunluğu bir sonraki satırın offset'inden çıkar.

Adımlar: f000–f120 saatlik, f123–f384 3 saatlik (``model_max_lead_h``'e kadar). Kayıt seçimi zaman
alanıyla yapılır (2026-11-03 .idx'lerinden):

- Anlık alanlar ``"<N> hour fcst"`` (0. adımda ``"anl"``).
- ``APCP``/``ACPCP`` aynı dosyada iki kez: 6 saatlik (120 sa sonrası 3 saatlik) kova ``"6-9 hour acc
  fcst"`` ve başlangıçtan beri ``"0-9 hour acc fcst"``. Sürekli kayıt (``0-N``) alınır.
- ``CRAIN/CSNOW/CFRZR/CICEP`` anlık ve aralık ortalaması olarak iki kez; anlık olan alınır.
- ``GUST`` anlık tanı alanı (UPP); ``VIS`` görüş (m); ``TCDC``/``LCDC`` yüzde.
- Kar yağışının su eşdeğeri yok (``WEASD`` yerdeki kar) → ``snow_mm`` boş kalır.

Yağış tipi dört kategorik bayraktan ECMWF ptype kodlarına çevrilir; birden çok bayrak varsa öncelik:
donan yağmur (3) > buz taneleri (8) > kar + yağmur (7) > kar (5) > yağmur (1) > yok (0).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

import httpx
import numpy as np

from hava.ingest.archive.http_range import get_with_retry
from hava.ingest.models.ecmwf import PTYPE_NAMES
from hava.ingest.models.grib import GribField, decode_message
from hava.ingest.models.pipeline import ModelSpec, RunCollector
from hava.ingest.models.runner import Source, candidate_runs, pending, process_run
from hava.processing.grid import BBox
from hava.region import Region, load_region
from hava.settings import Settings, get_settings

MODEL_CODE = "ncep_gfs"
EXTRACTOR_VERSION = "ncep-gfs-1"
RESOL = "0p25"
LICENSE = "NOAA açık veri (NODD)"


@dataclass(frozen=True)
class Want:
    name: str  # .idx değişken adı
    level: str  # .idx seviye metni
    var: str  # kanonik ad (pipeline) ya da yağış tipi bayrağı
    kind: str = "instant"  # "instant" | "acc"
    scale: float = 1.0


FIELDS = (
    Want("TMP", "2 m above ground", "t2m"),
    Want("DPT", "2 m above ground", "d2m"),
    Want("APCP", "surface", "precip_acc", "acc"),
    Want("ACPCP", "surface", "conv_acc", "acc"),
    Want("UGRD", "10 m above ground", "u10"),
    Want("VGRD", "10 m above ground", "v10"),
    Want("GUST", "surface", "gust"),
    Want("PRMSL", "mean sea level", "msl"),
    Want("TCDC", "entire atmosphere", "tcc", scale=0.01),
    Want("LCDC", "low cloud layer", "lcc", scale=0.01),
    Want("VIS", "surface", "vis"),
    Want("TMP", "850 mb", "t850"),
    Want("CFRZR", "surface", "cfrzr"),
    Want("CICEP", "surface", "cicep"),
    Want("CSNOW", "surface", "csnow"),
    Want("CRAIN", "surface", "crain"),
)
STATIC = (Want("LAND", "surface", "lsm"), Want("HGT", "surface", "orog"))
FLAGS = ("cfrzr", "cicep", "csnow", "crain")

SPEC = ModelSpec(
    code=MODEL_CODE,
    gust_definition=lambda s: "instant",
    ptype_names=PTYPE_NAMES,
    visibility_definition="instant",
)


@dataclass(frozen=True)
class IdxEntry:
    offset: int
    length: int | None  # son kayıtta bilinmez (dosya sonuna kadar)
    name: str
    level: str
    time: str


def steps_for(max_lead_h: int) -> list[int]:
    steps = list(range(0, 121)) + list(range(123, 385, 3))
    return [s for s in steps if s <= max_lead_h]


def grib_url(base: str, init: datetime, step: int) -> str:
    return f"{base}/gfs.{init:%Y%m%d}/{init:%H}/atmos/gfs.t{init:%H}z.pgrb2.0p25.f{step:03d}"


def parse_idx(text: str) -> list[IdxEntry]:
    rows = [line.split(":") for line in text.splitlines() if line.strip()]
    out: list[IdxEntry] = []
    for k, r in enumerate(rows):
        offset = int(r[1])
        length = int(rows[k + 1][1]) - offset if k + 1 < len(rows) else None
        out.append(IdxEntry(offset, length, r[3], r[4], r[5]))
    return out


def time_text(w: Want, step: int) -> str | None:
    if w.kind == "acc":
        return None if step == 0 else f"0-{step} hour acc fcst"
    return "anl" if step == 0 else f"{step} hour fcst"


def select(
    entries: list[IdxEntry], wants: tuple[Want, ...], step: int
) -> list[tuple[Want, IdxEntry]]:
    """Her alan için zaman metni tutan ilk kayıt (0-N birikim, anlık bayrak)."""
    out: list[tuple[Want, IdxEntry]] = []
    for w in wants:
        when = time_text(w, step)
        if when is None:
            continue
        for e in entries:
            if (e.name, e.level, e.time) == (w.name, w.level, when):
                out.append((w, e))
                break
    return out


def precip_type(flags: dict[str, GribField]) -> GribField:
    """Dört kategorik bayraktan ECMWF ptype kodu (öncelik modül açıklamasında)."""
    on = {k: np.nan_to_num(f.values) >= 0.5 for k, f in flags.items()}
    code = np.select(
        [on["cfrzr"], on["cicep"], on["csnow"] & on["crain"], on["csnow"], on["crain"]],
        [3.0, 8.0, 7.0, 5.0, 1.0],
        default=0.0,
    )
    missing = np.zeros(code.shape, dtype=bool)
    for f in flags.values():
        missing |= np.isnan(f.values)
    return replace(flags["crain"], values=np.where(missing, np.nan, code))


def run_complete(client: httpx.Client, base: str, init: datetime, max_lead_h: int) -> bool:
    """Son adımın .idx'i yayımlandıysa çalıştırma (bizim ufkumuz için) tamamdır."""
    last = steps_for(max_lead_h)[-1]
    return client.get(grib_url(base, init, last) + ".idx").status_code == 200


def _download(client: httpx.Client, url: str, e: IdxEntry) -> bytes:
    end = "" if e.length is None else str(e.offset + e.length - 1)
    headers = {"Range": f"bytes={e.offset}-{end}"}
    return get_with_retry(client, url, headers=headers, attempts=5).content


def collect_run(
    client: httpx.Client, settings: Settings, region: Region, init: datetime
) -> tuple[RunCollector, dict[str, Any]]:
    bbox = BBox(region.lat_min, region.lat_max, region.lon_min, region.lon_max)
    col = RunCollector(bbox.expanded(settings.model_crop_margin_deg))
    base = settings.gfs_base_url
    stats = {"messages": 0, "bytes": 0}
    with ThreadPoolExecutor(settings.model_download_workers) as pool:
        for step in steps_for(settings.model_max_lead_h):
            url = grib_url(base, init, step)
            entries = parse_idx(get_with_retry(client, url + ".idx").text)
            wants = FIELDS + (STATIC if step == 0 else ())
            jobs = select(entries, wants, step)
            blobs = list(pool.map(lambda j, u=url: _download(client, u, j[1]), jobs))
            flags: dict[str, GribField] = {}
            for (w, _), blob in zip(jobs, blobs, strict=True):
                f = decode_message(blob)
                stats["messages"] += 1
                stats["bytes"] += len(blob)
                if w in STATIC:
                    col.add_static(w.var, f, w.scale)
                elif w.var in FLAGS:
                    flags[w.var] = f
                else:
                    col.add(w.var, step, f, w.scale)
            if set(flags) == set(FLAGS):
                col.add("ptype", step, precip_type(flags))
    return col, stats


def collect(max_runs: int = 2) -> list[dict[str, Any]]:
    """Worker işi: tamamlanmış ve yüklenmemiş çalıştırmaları (yeniden eskiye) işler."""
    settings = get_settings()
    region = load_region(settings.region_config)
    base = settings.gfs_base_url
    src = Source(SPEC, EXTRACTOR_VERSION, base, RESOL, LICENSE)
    done: list[dict[str, Any]] = []
    with httpx.Client(timeout=120.0, headers={"User-Agent": settings.http_user_agent}) as client:
        # Önce en yeni çalıştırma (tazelik), sonra eksik kalan eskiler.
        for init in reversed(candidate_runs(datetime.now(UTC), settings.model_lookback_hours)):
            if not pending(MODEL_CODE, init):
                continue
            if not run_complete(client, base, init, settings.model_max_lead_h):
                continue

            def fetch(i: datetime = init) -> tuple[RunCollector, dict[str, Any]]:
                return collect_run(client, settings, region, i)

            done.append(process_run(src, settings, region, init, fetch))
            if len(done) >= max_runs:
                break
    return done
