"""Météo-France ARPEGE EURAT01 0.1° deterministik (spec §5.1; docs/data-sources.md §2.5).

Kaynak açık paketler (Licence Ouverte 2.0; data.gouv.fr → OVH S3, anahtarsız):
``<base>/<çalıştırma>/arpege/01/<PAKET>/arpege__01__<PAKET>__<aaaH><bbbH>__<çalıştırma>.grib2``.
Paketler parametre grubu × 12 saatlik adım aralığı; ``.idx`` yok. Yalnız yüzey paketleri SP1 ve SP2
bütünüyle indirilir (çalıştırma başına ~1,3 GB); 850 hPa sıcaklığı için IP1'in tamamı (2,4 GB)
gerekeceğinden alınmaz. Mesajlar dosyadan tek tek okunur, yalnız gerekenler çözülür.

Alanlar (2026-11-03 paketlerinden; kimlik ``discipline/kategori/numara`` + adım türü + seviye):

- SP1: ``2t``, ``10u/10v``, ``max_i10fg`` (0/2/22, son 1 sa en yüksek), ``prmsl``, toplam bulut
  0/6/1 (eccodes adı "unknown"; WMO tablo 4.2 "Total cloud cover", %), ``tp``/``cp``/``tsnowp``
  (başlangıçtan beri, kg m⁻²; 0. adımda kayıt yok → başlangıç 0).
- SP2: ``2d``, ``lcc`` (%), ``min_vis`` (0/19/0, son 1 sa en düşük görüş, m), ``h`` (0/3/6, model
  arazi yüksekliği, yalnız 0. adım).
- Yağış tipi (0/1/19) yerel kod 201 içeriyor ve anlamı birincil kaynaktan teyit edilemedi → alınmaz.
- Kara-deniz maskesi: ``constant-eurat01.grib2``'deki ``lsm`` ``grid_second_order`` ile kodlu ve
  eccodes −256…253 üretiyor (kullanılamaz). EURAT01 düğümleri IFS 0.1° düğümleriyle çakıştığından en
  yeni IFS 0.1° kara oranı kullanılır (spec §6: maske başka kaynaktan türetilebilir); kaynak
  ``model_runs.files.lsm_source``'ta.

Adımlar 0–102 sa saatlik; çalıştırmalar 00/06/12/18z. S3 ~15 gün saklıyor.
"""

from __future__ import annotations

import os
import tempfile
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import eccodes
import httpx

from hava.ingest.models import ecmwf
from hava.ingest.models.grib import decode_message
from hava.ingest.models.pipeline import ModelSpec, RunCollector
from hava.ingest.models.runner import Source, candidate_runs, pending, process_run
from hava.processing.grid import BBox
from hava.region import Region, load_region
from hava.settings import Settings, get_settings

MODEL_CODE = "mf_arpege"
EXTRACTOR_VERSION = "mf-arpege-1"
RESOL = "0p1 EURAT01"
LICENSE = "Licence Ouverte / Etalab 2.0 (Source : Météo-France)"
BASE_URL = "https://meteofrance-pnt.s3.rbx.io.cloud.ovh.net/pnt"
PACKAGES = ("SP1", "SP2")
RANGES = ((0, 12), (13, 24), (25, 36), (37, 48), (49, 60), (61, 72), (73, 84), (85, 96), (97, 102))


@dataclass(frozen=True)
class Want:
    discipline: int
    category: int
    number: int
    step_type: str
    level_type: str
    level: int
    var: str
    scale: float = 1.0


WANTS = (
    Want(0, 0, 0, "instant", "heightAboveGround", 2, "t2m"),
    Want(0, 0, 6, "instant", "heightAboveGround", 2, "d2m"),
    Want(0, 2, 2, "instant", "heightAboveGround", 10, "u10"),
    Want(0, 2, 3, "instant", "heightAboveGround", 10, "v10"),
    Want(0, 2, 22, "max", "heightAboveGround", 10, "gust"),
    Want(0, 3, 1, "instant", "meanSea", 0, "msl"),
    Want(0, 6, 1, "instant", "surface", 0, "tcc", 0.01),
    Want(0, 6, 3, "instant", "surface", 0, "lcc", 0.01),
    Want(0, 19, 0, "min", "surface", 0, "vis"),
    Want(0, 1, 52, "accum", "surface", 0, "precip_acc"),
    Want(0, 1, 37, "accum", "surface", 0, "conv_acc"),
    Want(0, 1, 66, "accum", "surface", 0, "snow_acc"),
)
OROG = Want(0, 3, 6, "instant", "surface", 0, "orog")
KEYS = ("discipline", "parameterCategory", "parameterNumber", "stepType", "typeOfLevel", "level")
INDEX = {(w.discipline, w.category, w.number, w.step_type, w.level_type, w.level): w for w in WANTS}
INDEX[(0, 3, 6, "instant", "surface", 0)] = OROG

SPEC = ModelSpec(
    code=MODEL_CODE, gust_definition=lambda s: "max_1h", visibility_definition="min_1h"
)


def file_url(base: str, init: datetime, package: str, first: int, last: int) -> str:
    run = f"{init:%Y-%m-%dT%H:00:00Z}"
    name = f"arpege__01__{package}__{first:03d}H{last:03d}H__{run}.grib2"
    return f"{base}/{run}/arpege/01/{package}/{name}"


def files_for(max_lead_h: int) -> list[tuple[str, int, int]]:
    return [(p, a, b) for a, b in RANGES if a <= max_lead_h for p in PACKAGES]


def run_complete(client: httpx.Client, base: str, init: datetime, max_lead_h: int) -> bool:
    """Son adım aralığının iki paketi de yayımlandıysa çalıştırma tamamdır."""
    last = [f for f in files_for(max_lead_h) if f[1] == files_for(max_lead_h)[-1][1]]
    return all(client.head(file_url(base, init, *f)).status_code == 200 for f in last)


def _download(client: httpx.Client, url: str, folder: Path) -> Path:
    """Dosyayı diske akıtır (paketler 40–110 MB); yarım kalırsa siler."""
    fd, name = tempfile.mkstemp(suffix=".grib2", dir=folder)
    path = Path(name)
    try:
        with os.fdopen(fd, "wb") as out, client.stream("GET", url) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_bytes(1 << 20):
                out.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def iter_wanted(path: Path) -> Iterator[tuple[Want, bytes]]:
    """Dosyadaki mesajlardan istenenler (başlık anahtarlarıyla eşlenir)."""
    with path.open("rb") as fh:
        while (h := eccodes.codes_grib_new_from_file(fh)) is not None:
            try:
                key = tuple(eccodes.codes_get(h, k) for k in KEYS)
                w = INDEX.get(key)
                if w is not None:
                    yield w, bytes(eccodes.codes_get_message(h))
            finally:
                eccodes.codes_release(h)


def collect_run(
    client: httpx.Client, settings: Settings, region: Region, init: datetime
) -> tuple[RunCollector, dict[str, Any]]:
    bbox = BBox(region.lat_min, region.lat_max, region.lon_min, region.lon_max)
    col = RunCollector(bbox.expanded(settings.model_crop_margin_deg))
    stats: dict[str, Any] = {"messages": 0, "bytes": 0}
    folder = Path(settings.grib_dir) / "_tmp"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.grib2"):  # çöken önceki denemeden kalanlar
        if old.stat().st_mtime < time.time() - 6 * 3600:
            old.unlink(missing_ok=True)
    files = files_for(settings.model_max_lead_h)
    with ThreadPoolExecutor(3) as pool:  # bellek yerine disk: aynı anda en fazla 3 dosya
        urls = [file_url(BASE_URL, init, *f) for f in files]
        futures = [pool.submit(_download, client, url, folder) for url in urls]
        for fut in futures:
            path = fut.result()
            try:
                stats["bytes"] += path.stat().st_size
                for w, msg in iter_wanted(path):
                    f = decode_message(msg)
                    if w is OROG:
                        col.add_static("orog", f)
                    elif f.end_step_h <= settings.model_max_lead_h:
                        col.add(w.var, f.end_step_h, f, w.scale)
                    stats["messages"] += 1
            finally:
                path.unlink(missing_ok=True)
    lsm, lsm_init = ecmwf.latest_land_mask(client, settings.ecmwf_base_url, datetime.now(UTC))
    col.add_static_aligned("lsm", lsm)
    stats["lsm_source"] = f"ecmwf_ifs 0p1 {lsm_init:%Y-%m-%dT%HZ} lsm"
    return col, stats


def collect(max_runs: int = 2) -> list[dict[str, Any]]:
    """Worker işi: tamamlanmış ve yüklenmemiş çalıştırmaları (yeniden eskiye) işler."""
    settings = get_settings()
    region = load_region(settings.region_config)
    src = Source(SPEC, EXTRACTOR_VERSION, BASE_URL, RESOL, LICENSE)
    done: list[dict[str, Any]] = []
    with httpx.Client(timeout=300.0, headers={"User-Agent": settings.http_user_agent}) as client:
        # Önce en yeni çalıştırma (tazelik), sonra eksik kalan eskiler.
        for init in reversed(candidate_runs(datetime.now(UTC), settings.model_lookback_hours)):
            if not pending(MODEL_CODE, init):
                continue
            if not run_complete(client, BASE_URL, init, settings.model_max_lead_h):
                continue

            def fetch(i: datetime = init) -> tuple[RunCollector, dict[str, Any]]:
                return collect_run(client, settings, region, i)

            done.append(process_run(src, settings, region, init, fetch))
            if len(done) >= max_runs:
                break
    return done
