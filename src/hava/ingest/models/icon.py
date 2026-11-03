"""DWD ICON (global) ve ICON-EU deterministik (spec §5.1; docs/data-sources.md §2.4).

Kaynak opendata.dwd.de yeni şeması (v1): her dosya tek alan, native üçgen ızgara (ICON #26 13 km,
ICON-EU #62 ~6,5 km), CCSDS sıkıştırmalı GRIB2:
``<base>/<model>/p/<PARAM>/[lvt1/<tip>/lv1/<seviye>/]r/<YYYY-MM-DDTHH:MM>/s/PT<hhh>H00M.grib2``.
Index yok, her dosya bütünüyle iner. DWD çalıştırmaları ~24 saat tutar; kaçırılan geri gelmez.

Adımlar (dizin listesinden, 2026-11-03): 0–78 sa saatlik, sonra 3 saatlik; ICON 00/12z 180 sa,
06/18z 120 sa; ICON-EU 00/06/12/18z 120 sa. ICON-EU'nun 03/09/15/21z kısa çalıştırmaları (51 sa)
alınmaz.

Değişkenler (DWD ICON Database Reference 2.5.6):
- ``TOT_PREC``, ``RAIN_CON``, ``SNOW_CON``, ``SNOW_GSP`` başlangıçtan beri birikimli (kg m⁻² = mm).
  eccodes ``RAIN_CON``'u "kg m-2 s-1" etiketiyle gösteriyor; mesaj ``stepType=accum`` ve değerler
  ``TOT_PREC``'i aşmıyor → birikim. Konvektif = RAIN_CON + SNOW_CON; kar = SNOW_CON + SNOW_GSP.
- ``VMAX_10M``: son 1 saatin en yüksek hamlesi (ICON global'de 0. adımda yayımlanmıyor).
- ``CLCT``/``CLCL`` yüzde; ``WW``: son 1 saatin önemli hava kodu (WMO 0 20 003 alt kümesi).
- Sabitler (yalnız 0. adım): ``CLAT/CLON`` hücre merkezleri, ``FR_LAND``, ``HSURF``.

ICON-EU-EPS (ADR-0006, 00/12z): 40 üye, ~10 km (#63), her üye ayrı dosya
(``…/r/<çalıştırma>/e/<üye>/s/…``); 0–75 sa saatlik, 78–120 sa 3 saatlik. Alanlar ``T_2M``,
``TOT_PREC``, ``U/V_10M``, ``VMAX_10M`` (0. adımda yok), ``SNOW_CON`` + ``SNOW_GSP``; sabitler
1. üyenin dizininde (2026-11-03 dizin listesi ve HEAD istekleriyle).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

import httpx

from hava.ingest.archive.http_range import RemoteFileGone, get_with_retry
from hava.ingest.models import ensemble
from hava.ingest.models.ensemble import EnsembleCollector
from hava.ingest.models.grib import GribField, decode_message
from hava.ingest.models.pipeline import ModelSpec, RunCollector
from hava.ingest.models.runner import (
    Source,
    candidate_runs,
    pending,
    process_ensemble_run,
    process_run,
)
from hava.processing.grid import BBox
from hava.region import Region, load_region
from hava.settings import Settings, get_settings

LICENSE = "CC BY 4.0 (Quelle: Deutscher Wetterdienst)"
DWD_LOOKBACK_H = 30  # DWD ~24 sa tutar; daha eskisi aranmaz

# WW → yağış tipi (DWD ICON Database Reference 2.5.6, Tablo 6.1). Ham kod ``extra.ptype_code``'da
# kalır (çisenti, sağanak ve gök gürültüsü ayrımı oradan okunur).
WW_PTYPE: dict[int, str] = {
    **dict.fromkeys((0, 1, 2, 3, 45, 48), "none"),
    **dict.fromkeys((51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96), "rain"),
    **dict.fromkeys((56, 57), "freezing_drizzle"),
    **dict.fromkeys((66, 67), "freezing_rain"),
    **dict.fromkeys((71, 73, 75, 77, 85, 86), "snow"),
}


@dataclass(frozen=True)
class IconModel:
    code: str
    path: str  # DWD dizin adı
    extractor: str
    resolution: str
    long_run_hours: frozenset[int]  # 180 saatlik ufku olan çalıştırma saatleri

    def horizon(self, init: datetime) -> int:
        return 180 if init.hour in self.long_run_hours else 120

    @property
    def spec(self) -> ModelSpec:
        return ModelSpec(code=self.code, gust_definition=lambda s: "max_1h", ptype_names=WW_PTYPE)


ICON = IconModel("dwd_icon", "icon", "dwd-icon-1", "13 km R03B07 (#26)", frozenset({0, 12}))
ICON_EU = IconModel("dwd_icon_eu", "icon-eu", "dwd-icon-eu-1", "~6.5 km (#62)", frozenset())
ICON_EU_EPS = IconModel(
    "dwd_icon_eu_eps", "icon-eu-eps", "dwd-icon-eu-eps-1", "~10 km (#63); 40 üye", frozenset()
)
EPS_MEMBERS = tuple(range(1, 41))


@dataclass(frozen=True)
class Want:
    param: str  # DWD parametre dizini
    var: str  # kanonik ad (pipeline) ya da toplanacak parça
    scale: float = 1.0
    level: str = ""  # ör. "lvt1/100/lv1/85000"
    optional_at_0: bool = False


FIELDS = (
    Want("T_2M", "t2m"),
    Want("TD_2M", "d2m"),
    Want("TOT_PREC", "precip_acc"),
    Want("RAIN_CON", "rain_con"),
    Want("SNOW_CON", "snow_con"),
    Want("SNOW_GSP", "snow_gsp"),
    Want("U_10M", "u10"),
    Want("V_10M", "v10"),
    Want("VMAX_10M", "gust", optional_at_0=True),
    Want("PMSL", "msl"),
    Want("CLCT", "tcc", 0.01),
    Want("CLCL", "lcc", 0.01),
    Want("WW", "ptype"),
    Want("T", "t850", level="lvt1/100/lv1/85000"),
)
STATIC = (Want("FR_LAND", "lsm"), Want("HSURF", "orog"))
COORDS = (Want("CLAT", "lat"), Want("CLON", "lon"))
# Kanonik değişken ← parçaların toplamı (birikimli, mm)
SUMS = {"conv_acc": ("rain_con", "snow_con"), "snow_acc": ("snow_con", "snow_gsp")}
PARTS = frozenset(p for pair in SUMS.values() for p in pair)
EPS_FIELDS = (
    Want("T_2M", "t2m"),
    Want("TOT_PREC", "precip_acc"),
    Want("U_10M", "u10"),
    Want("V_10M", "v10"),
    Want("VMAX_10M", "gust", optional_at_0=True),
    Want("SNOW_CON", "snow_con"),
    Want("SNOW_GSP", "snow_gsp"),
)
EPS_SUMS = {"snow_acc": ("snow_con", "snow_gsp")}


def steps_for(model: IconModel, init: datetime, max_lead_h: int) -> list[int]:
    steps = list(range(0, 79)) + list(range(81, model.horizon(init) + 1, 3))
    return [s for s in steps if s <= max_lead_h]


def eps_steps(init: datetime, max_lead_h: int) -> list[int]:
    """Ortak ensemble adım planı ∩ ICON-EU-EPS'in yayımladığı adımlar."""
    published = {*range(0, 76), *range(78, 121, 3)}
    return [s for s in ensemble.STEPS if s in published and s <= max_lead_h]


def file_url(
    base: str, model: IconModel, w: Want, init: datetime, step: int, member: int | None = None
) -> str:
    level = f"{w.level}/" if w.level else ""
    run = f"{init:%Y-%m-%dT%H:%M}"
    ens = f"e/{member:02d}/" if member is not None else ""
    return f"{base}/{model.path}/p/{w.param}/{level}r/{run}/{ens}s/PT{step:03d}H00M.grib2"


def run_complete(
    client: httpx.Client, base: str, model: IconModel, init: datetime, lead: int
) -> bool:
    """Son adımda tüm alanlar yayımlandıysa çalıştırma tamamdır."""
    last = steps_for(model, init, lead)[-1]
    return all(client.head(file_url(base, model, w, init, last)).status_code == 200 for w in FIELDS)


def _fetch(client: httpx.Client, url: str, optional: bool) -> bytes | None:
    try:
        return get_with_retry(client, url, attempts=5).content
    except RemoteFileGone:
        if optional:
            return None
        raise


def collect_run(
    client: httpx.Client, settings: Settings, region: Region, model: IconModel, init: datetime
) -> tuple[RunCollector, dict[str, Any]]:
    bbox = BBox(region.lat_min, region.lat_max, region.lon_min, region.lon_max)
    col = RunCollector(bbox.expanded(settings.model_crop_margin_deg))
    base = settings.dwd_base_url
    stats = {"messages": 0, "bytes": 0, "missing_optional": 0}

    def get_all(
        pool: ThreadPoolExecutor, wants: tuple[Want, ...], step: int
    ) -> list[tuple[Want, GribField | None]]:
        urls = [file_url(base, model, w, init, step) for w in wants]
        optional = [step == 0 and w.optional_at_0 for w in wants]
        blobs = list(pool.map(lambda a: _fetch(client, *a), zip(urls, optional, strict=True)))
        out: list[tuple[Want, GribField | None]] = []
        for w, blob in zip(wants, blobs, strict=True):
            if blob is None:
                stats["missing_optional"] += 1
                out.append((w, None))
                continue
            stats["messages"] += 1
            stats["bytes"] += len(blob)
            out.append((w, decode_message(blob)))
        return out

    with ThreadPoolExecutor(settings.model_download_workers) as pool:
        fixed = {w: f for w, f in get_all(pool, COORDS + STATIC, 0) if f is not None}
        lat, lon = fixed[COORDS[0]], fixed[COORDS[1]]
        col.set_cells(lat.values, lon.values, str(lat.meta.get("grid_id", "")))
        for w in STATIC:
            col.add_static(w.var, fixed[w], w.scale)
        for step in steps_for(model, init, settings.model_max_lead_h):
            parts: dict[str, GribField] = {}
            for w, f in get_all(pool, FIELDS, step):
                if f is None:
                    continue
                if w.var in PARTS:
                    parts[w.var] = f
                else:
                    col.add(w.var, step, f, w.scale)
            for target, (a, b) in SUMS.items():
                if a in parts and b in parts:
                    total = replace(parts[a], values=parts[a].values + parts[b].values)
                    col.add(target, step, total)
    return col, stats


def collect(model: IconModel, max_runs: int = 2) -> list[dict[str, Any]]:
    """Worker işi: tamamlanmış ve yüklenmemiş çalıştırmaları (yeniden eskiye) işler."""
    settings = get_settings()
    region = load_region(settings.region_config)
    base = settings.dwd_base_url
    src = Source(model.spec, model.extractor, f"{base}/{model.path}", model.resolution, LICENSE)
    lookback = min(settings.model_lookback_hours, DWD_LOOKBACK_H)
    done: list[dict[str, Any]] = []
    with httpx.Client(timeout=120.0, headers={"User-Agent": settings.http_user_agent}) as client:
        # Önce en yeni çalıştırma (tazelik), sonra eksik kalan eskiler.
        for init in reversed(candidate_runs(datetime.now(UTC), lookback)):
            if not pending(model.code, init):
                continue
            if not run_complete(client, base, model, init, settings.model_max_lead_h):
                continue

            def fetch(i: datetime = init) -> tuple[RunCollector, dict[str, Any]]:
                return collect_run(client, settings, region, model, i)

            done.append(process_run(src, settings, region, init, fetch))
            if len(done) >= max_runs:
                break
    return done


def eps_run_complete(client: httpx.Client, base: str, init: datetime, lead: int) -> bool:
    """Son üyenin son adımında tüm alanlar yayımlandıysa çalıştırma tamamdır."""
    last = eps_steps(init, lead)[-1]
    return all(
        client.head(file_url(base, ICON_EU_EPS, w, init, last, EPS_MEMBERS[-1])).status_code == 200
        for w in EPS_FIELDS
    )


def collect_eps_run(
    client: httpx.Client, settings: Settings, region: Region, init: datetime
) -> tuple[EnsembleCollector, dict[str, Any]]:
    bbox = BBox(region.lat_min, region.lat_max, region.lon_min, region.lon_max)
    col = EnsembleCollector(bbox.expanded(settings.model_crop_margin_deg), EPS_MEMBERS)
    base = settings.dwd_base_url
    model = ICON_EU_EPS
    stats = {"messages": 0, "bytes": 0, "missing_optional": 0}

    def decode(blob: bytes | None) -> GribField | None:
        if blob is None:
            stats["missing_optional"] += 1
            return None
        stats["messages"] += 1
        stats["bytes"] += len(blob)
        return decode_message(blob)

    with ThreadPoolExecutor(settings.model_download_workers) as pool:
        fixed_wants = COORDS + STATIC
        urls = [file_url(base, model, w, init, 0, EPS_MEMBERS[0]) for w in fixed_wants]
        blobs = pool.map(lambda u: _fetch(client, u, False), urls)
        fixed = {w: f for w, b in zip(fixed_wants, blobs, strict=True) if (f := decode(b))}
        lat, lon = fixed[COORDS[0]], fixed[COORDS[1]]
        col.set_cells(lat.values, lon.values, str(lat.meta.get("grid_id", "")))
        for w in STATIC:
            col.add_static(w.var, fixed[w], w.scale)
        for step in eps_steps(init, settings.model_max_lead_h):
            jobs = [(m, w) for m in EPS_MEMBERS for w in EPS_FIELDS]
            blobs = pool.map(
                lambda j, s=step: _fetch(
                    client,
                    file_url(base, model, j[1], init, s, j[0]),
                    s == 0 and j[1].optional_at_0,
                ),
                jobs,
            )
            parts: dict[int, dict[str, GribField]] = {m: {} for m in EPS_MEMBERS}
            for (m, w), blob in zip(jobs, blobs, strict=True):
                f = decode(blob)
                if f is None:
                    continue
                if w.var in PARTS:
                    parts[m][w.var] = f
                else:
                    col.add(w.var, step, m, f, w.scale)
            for m, got in parts.items():
                for target, (a, b) in EPS_SUMS.items():
                    if a in got and b in got:
                        total = replace(got[a], values=got[a].values + got[b].values)
                        col.add(target, step, m, total)
    return col, stats


def collect_eps(max_runs: int = 1) -> list[dict[str, Any]]:
    """Worker işi: ICON-EU-EPS 00/12z çalıştırmaları (yeniden eskiye)."""
    settings = get_settings()
    region = load_region(settings.region_config)
    base = settings.dwd_base_url
    model = ICON_EU_EPS
    src = Source(model.spec, model.extractor, f"{base}/{model.path}", model.resolution, LICENSE)
    lookback = min(settings.model_lookback_hours, DWD_LOOKBACK_H)
    done: list[dict[str, Any]] = []
    with httpx.Client(timeout=120.0, headers={"User-Agent": settings.http_user_agent}) as client:
        # Önce en yeni çalıştırma (tazelik), sonra eksik kalan eskiler.
        for init in reversed(candidate_runs(datetime.now(UTC), lookback, cycle_h=12)):
            if not pending(model.code, init):
                continue
            if not eps_run_complete(client, base, init, settings.model_max_lead_h):
                continue

            def fetch(i: datetime = init) -> tuple[EnsembleCollector, dict[str, Any]]:
                return collect_eps_run(client, settings, region, i)

            done.append(process_ensemble_run(src, settings, region, init, fetch))
            if len(done) >= max_runs:
                break
    return done


def collect_icon() -> list[dict[str, Any]]:
    return collect(ICON)


def collect_icon_eu() -> list[dict[str, Any]]:
    return collect(ICON_EU)
