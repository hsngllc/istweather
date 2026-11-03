"""ECMWF açık verisi: IFS 0.1° ve AIFS Single 0.25° deterministik (spec §5.1; data-sources §2.1).

Kaynak ECMWF portalı (``data.ecmwf.int``): son ~12 çalıştırmayı tutar ve Range destekler. AWS
yansısı yoğun istekte ``503 SlowDown`` döndürdüğü için canlıda kullanılmaz. Her adımın ``.index``
dosyasından (JSON satırları) gereken mesajlar seçilir ve tek tek byte-range ile indirilir.

IFS 0.1°: yüzey ve basınç seviyesi ayrı dosyalar (``-sfc``/``-pl``). Adımlar 00/12z 0–144 sa 3'er,
150–360 sa 6'şar; 06/18z 0–144 sa 3'er. Hamle: 0–90 sa ``10fg`` (son 1 sa max), 93–144 sa
``10fg3`` (son 3 sa), 150+ sa ``10fg`` (son 6 sa) — param-db 49 / 228028. Yağış ``tp``/``cp``/``sf``
başlangıçtan beri birikimli (m); bulut 0–1.

AIFS Single 0.25°: tek dosya (yüzey + basınç seviyesi). Adımlar her çalıştırmada 0–360 sa 6'şar.
Yağış başlangıçtan beri birikimli ama **kg m⁻²** (= mm); bulut **%**. Hamle ve yağış tipi yok
(index'ten teyit, 2026-11-03).

Ensemble'lar (ADR-0006, 00/12z): IFS ENS 0.25° (``enfo``, ``ef`` dosyası, 50 pf; hamle kuralı
deterministikle aynı; orografi yok → yükseklik düzeltmesi yapılamaz), AIFS ENS (``cf`` + ``pf``
dosyaları, 51 üye; hamle yok). Index'te üye ``number`` alanında; ``cf``'de yok (üye 0).

``model_max_lead_h``'e kadar alınır.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from hava.ingest.archive.http_range import get_with_retry
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

LICENSE = "CC BY 4.0 + ECMWF Terms of Use"
G = 9.80665
# ECMWF ptype kodları (https://codes.ecmwf.int/grib/param-db/260015)
PTYPE_NAMES = {
    0: "none",
    1: "rain",
    3: "freezing_rain",
    5: "snow",
    6: "wet_snow",
    7: "rain_snow",
    8: "ice_pellets",
    12: "freezing_drizzle",
}


@dataclass(frozen=True)
class Want:
    param: str
    levtype: str  # "sfc" | "pl"
    var: str  # kanonik ad (pipeline)
    scale: float = 1.0
    level: str | None = None


@dataclass(frozen=True)
class Product:
    code: str
    extractor: str
    path: str  # portal yolu, ör. "ifs/0p1/oper"
    resolution: str
    split_levtype: bool  # yüzey ve basınç seviyesi ayrı dosyalarda mı
    sfc: tuple[Want, ...]
    pl: tuple[Want, ...]
    static: tuple[Want, ...]
    steps: Callable[[datetime], list[int]]
    gust_definition: Callable[[float], str | None]
    ptype_names: dict[int, str] = field(default_factory=dict)

    @property
    def spec(self) -> ModelSpec:
        return ModelSpec(self.code, self.gust_definition, self.ptype_names)


def gust_definition(step: float) -> str:
    """IFS hamlesinin tanımı (adıma göre)."""
    if step <= 90:
        return "max_1h"
    return "max_3h" if step <= 144 else "max_6h"


def _ifs_steps(init: datetime) -> list[int]:
    steps = list(range(0, 145, 3))
    if init.hour in (0, 12):
        steps += list(range(150, 361, 6))
    return steps


SFC = (
    Want("2t", "sfc", "t2m"),
    Want("2d", "sfc", "d2m"),
    Want("tp", "sfc", "precip_acc", 1000.0),
    Want("cp", "sfc", "conv_acc", 1000.0),
    Want("sf", "sfc", "snow_acc", 1000.0),
    Want("10u", "sfc", "u10"),
    Want("10v", "sfc", "v10"),
    Want("10fg", "sfc", "gust"),
    Want("10fg3", "sfc", "gust"),
    Want("msl", "sfc", "msl"),
    Want("tcc", "sfc", "tcc"),
    Want("lcc", "sfc", "lcc"),
    Want("ptype", "sfc", "ptype"),
)
PL = (Want("t", "pl", "t850", level="850"),)
STATIC = (Want("lsm", "sfc", "lsm"), Want("z", "sfc", "orog", 1.0 / G))

IFS = Product(
    code="ecmwf_ifs",
    extractor="ecmwf-ifs-1",
    path="ifs/0p1/oper",
    resolution="0p1",
    split_levtype=True,
    sfc=SFC,
    pl=PL,
    static=STATIC,
    steps=_ifs_steps,
    gust_definition=gust_definition,
    ptype_names=PTYPE_NAMES,
)
AIFS_SINGLE = Product(
    code="ecmwf_aifs_single",
    extractor="ecmwf-aifs-single-1",
    path="aifs-single/0p25/oper",
    resolution="0p25",
    split_levtype=False,
    sfc=(
        Want("2t", "sfc", "t2m"),
        Want("2d", "sfc", "d2m"),
        Want("tp", "sfc", "precip_acc"),
        Want("cp", "sfc", "conv_acc"),
        Want("sf", "sfc", "snow_acc"),
        Want("10u", "sfc", "u10"),
        Want("10v", "sfc", "v10"),
        Want("msl", "sfc", "msl"),
        Want("tcc", "sfc", "tcc", 0.01),
        Want("lcc", "sfc", "lcc", 0.01),
    ),
    pl=PL,
    static=STATIC,
    steps=lambda init: list(range(0, 361, 6)),
    gust_definition=lambda step: None,
)
PRODUCTS = (IFS, AIFS_SINGLE)
MODEL_CODE = IFS.code


@dataclass(frozen=True)
class EnsProduct:
    code: str
    extractor: str
    path: str  # portal yolu, ör. "ifs/0p25/enfo"
    resolution: str
    files: tuple[str, ...]  # dosya türleri: "ef" | "cf", "pf"
    members: tuple[int, ...]
    wants: tuple[Want, ...]
    static: tuple[Want, ...]
    published: Callable[[datetime], list[int]]  # kaynağın yayımladığı adımlar
    gust_definition: Callable[[float], str | None]

    @property
    def spec(self) -> ModelSpec:
        return ModelSpec(self.code, self.gust_definition)

    def steps(self, init: datetime, max_lead_h: int) -> list[int]:
        """Ortak ensemble adım planı ∩ yayımlanan adımlar (``model_max_lead_h``'e kadar)."""
        available = set(self.published(init))
        return [s for s in ensemble.STEPS if s in available and s <= max_lead_h]


IFS_ENS = EnsProduct(
    code="ecmwf_ifs_ens",
    extractor="ecmwf-ifs-ens-1",
    path="ifs/0p25/enfo",
    resolution="0p25",
    files=("ef",),
    members=tuple(range(1, 51)),
    wants=(
        Want("2t", "sfc", "t2m"),
        Want("tp", "sfc", "precip_acc", 1000.0),
        Want("sf", "sfc", "snow_acc", 1000.0),
        Want("10u", "sfc", "u10"),
        Want("10v", "sfc", "v10"),
        Want("10fg", "sfc", "gust"),
        Want("10fg3", "sfc", "gust"),
    ),
    static=(Want("lsm", "sfc", "lsm"),),
    published=_ifs_steps,  # deterministikle aynı (06/18z 144 sa)
    gust_definition=gust_definition,
)
AIFS_ENS = EnsProduct(
    code="ecmwf_aifs_ens",
    extractor="ecmwf-aifs-ens-1",
    path="aifs-ens/0p25/enfo",
    resolution="0p25",
    files=("cf", "pf"),
    members=tuple(range(0, 51)),
    wants=(
        Want("2t", "sfc", "t2m"),
        Want("tp", "sfc", "precip_acc"),
        Want("sf", "sfc", "snow_acc"),
        Want("10u", "sfc", "u10"),
        Want("10v", "sfc", "v10"),
    ),
    static=STATIC,
    published=lambda init: list(range(0, 361, 6)),
    gust_definition=lambda step: None,
)


def steps_for(init: datetime, max_lead_h: int, product: Product = IFS) -> list[int]:
    return [s for s in product.steps(init) if s <= max_lead_h]


def file_stem(base: str, init: datetime, product: Product | EnsProduct = IFS) -> str:
    return f"{base}/{init:%Y%m%d}/{init:%H}z/{product.path}/{init:%Y%m%d%H}0000"


def grib_url(
    base: str, init: datetime, step: int, levtype: str | None, product: Product = IFS
) -> str:
    suffix = f"-{levtype}" if product.split_levtype and levtype else ""
    return f"{file_stem(base, init, product)}-{step}h-oper-fc{suffix}.grib2"


def index_url(
    base: str, init: datetime, step: int, levtype: str | None, product: Product = IFS
) -> str:
    return grib_url(base, init, step, levtype, product)[: -len(".grib2")] + ".index"


def files_for(product: Product, step: int) -> list[tuple[str | None, list[Want]]]:
    """Adımda okunacak dosyalar (dosya türü, istenen alanlar); sabitler 0. adımda yüzeyle."""
    static = list(product.static) if step == 0 else []
    if product.split_levtype:
        return [("sfc", [*product.sfc, *static]), ("pl", list(product.pl))]
    return [(None, [*product.sfc, *static, *product.pl])]


def parse_index(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def select(
    entries: Sequence[dict[str, Any]], wants: Sequence[Want], step: int
) -> list[tuple[Want, dict[str, Any]]]:
    """Adımda istenen mesajları seçer; hamle için o adımın parametresi tercih edilir.

    0. adımda hamle alınmaz: "önceki saatin en yükseği" başlangıç anında tanımsız ve ECMWF bu
    mesajı sabit sıfırla dolduruyor (değer değil).
    """
    gust_param = "10fg3" if 90 < step <= 144 else "10fg"
    out: list[tuple[Want, dict[str, Any]]] = []
    for w in wants:
        if w.var == "gust" and (step == 0 or w.param != gust_param):
            continue
        for e in entries:
            if (
                e.get("param") == w.param
                and e.get("levtype", w.levtype) == w.levtype
                and (w.level is None or e.get("levelist") == w.level)
            ):
                if int(e.get("_length", 0)) > 0:
                    out.append((w, e))
                break
    return out


def run_complete(
    client: httpx.Client, base: str, init: datetime, max_lead_h: int, product: Product = IFS
) -> bool:
    """Son adımın index'i yayımlandıysa çalıştırma tamamdır."""
    last = steps_for(init, max_lead_h, product)[-1]
    levtype = files_for(product, last)[0][0]
    resp = client.get(index_url(base, init, last, levtype, product))
    return resp.status_code == 200


def _download(client: httpx.Client, url: str, entry: dict[str, Any]) -> bytes:
    lo = int(entry["_offset"])
    hi = lo + int(entry["_length"]) - 1
    return get_with_retry(client, url, headers={"Range": f"bytes={lo}-{hi}"}, attempts=5).content


def collect_run(
    client: httpx.Client,
    settings: Settings,
    region: Region,
    init: datetime,
    product: Product = IFS,
) -> tuple[RunCollector, dict[str, Any]]:
    bbox = BBox(region.lat_min, region.lat_max, region.lon_min, region.lon_max)
    col = RunCollector(bbox.expanded(settings.model_crop_margin_deg))
    base = settings.ecmwf_base_url
    stats = {"messages": 0, "bytes": 0}
    with ThreadPoolExecutor(settings.model_download_workers) as pool:
        for step in steps_for(init, settings.model_max_lead_h, product):
            jobs: list[tuple[Want, str, dict[str, Any]]] = []
            for levtype, wants in files_for(product, step):
                text = get_with_retry(client, index_url(base, init, step, levtype, product)).text
                url = grib_url(base, init, step, levtype, product)
                jobs += [(w, url, e) for w, e in select(parse_index(text), wants, step)]
            blobs = list(pool.map(lambda j: _download(client, j[1], j[2]), jobs))
            for (w, _, _), blob in zip(jobs, blobs, strict=True):
                f = decode_message(blob)
                if w in product.static:
                    col.add_static(w.var, f, w.scale)
                else:
                    col.add(w.var, step, f, w.scale)
                stats["messages"] += 1
                stats["bytes"] += len(blob)
    return col, stats


def latest_land_mask(client: httpx.Client, base: str, now: datetime) -> tuple[GribField, datetime]:
    """Portaldaki en yeni IFS 0.1° çalıştırmasının kara oranı (0. adım ``lsm``).

    Kara-deniz maskesi vermeyen ama aynı 0,1° düğümlerini kullanan modeller (ARPEGE EURAT01) için.
    """
    for init in reversed(candidate_runs(now, 72)):
        resp = client.get(index_url(base, init, 0, "sfc"))
        if resp.status_code != 200:
            continue
        chosen = select(parse_index(resp.text), [STATIC[0]], 0)
        if chosen:
            blob = _download(client, grib_url(base, init, 0, "sfc"), chosen[0][1])
            return decode_message(blob), init
    raise LookupError("portalda IFS 0.1° kara oranı bulunamadı")


def ens_url(base: str, init: datetime, step: int, ftype: str, product: EnsProduct) -> str:
    return f"{file_stem(base, init, product)}-{step}h-enfo-{ftype}.grib2"


def select_members(
    entries: Sequence[dict[str, Any]],
    wants: Sequence[Want],
    step: int,
    static: Sequence[Want] = (),
) -> list[tuple[Want, int, dict[str, Any]]]:
    """Üye mesajları (her üye için); sabit alanlardan yalnız ilk bulunan alınır."""
    out: list[tuple[Want, int, dict[str, Any]]] = []
    for w, e in select(entries, [w for w in wants if w in static], step):
        out.append((w, int(e.get("number") or 0), e))
    gust_param = "10fg3" if 90 < step <= 144 else "10fg"
    for w in wants:
        if w in static or (w.var == "gust" and (step == 0 or w.param != gust_param)):
            continue
        for e in entries:
            if (
                e.get("param") == w.param
                and e.get("levtype", w.levtype) == w.levtype
                and (w.level is None or e.get("levelist") == w.level)
                and int(e.get("_length", 0)) > 0
            ):
                out.append((w, int(e.get("number") or 0), e))
    return out


def ens_run_complete(
    client: httpx.Client, base: str, init: datetime, max_lead_h: int, product: EnsProduct
) -> bool:
    last = product.steps(init, max_lead_h)[-1]
    url = ens_url(base, init, last, product.files[-1], product)
    return client.get(url[: -len(".grib2")] + ".index").status_code == 200


def collect_ensemble_run(
    client: httpx.Client, settings: Settings, region: Region, init: datetime, product: EnsProduct
) -> tuple[EnsembleCollector, dict[str, Any]]:
    bbox = BBox(region.lat_min, region.lat_max, region.lon_min, region.lon_max)
    col = EnsembleCollector(bbox.expanded(settings.model_crop_margin_deg), product.members)
    base = settings.ecmwf_base_url
    stats = {"messages": 0, "bytes": 0}
    members = set(product.members)
    with ThreadPoolExecutor(settings.model_download_workers) as pool:
        for step in product.steps(init, settings.model_max_lead_h):
            wants = product.wants + (product.static if step == 0 else ())
            jobs: list[tuple[Want, int, str, dict[str, Any]]] = []
            for ftype in product.files:
                url = ens_url(base, init, step, ftype, product)
                index = get_with_retry(client, url[: -len(".grib2")] + ".index").text
                jobs += [
                    (w, m, url, e)
                    for w, m, e in select_members(parse_index(index), wants, step, product.static)
                    if m in members or w in product.static
                ]
            blobs = pool.map(lambda j: _download(client, j[2], j[3]), jobs)
            for (w, m, _, _), blob in zip(jobs, blobs, strict=True):
                f = decode_message(blob)
                if w in product.static:
                    col.add_static(w.var, f, w.scale)
                else:
                    col.add(w.var, step, m, f, w.scale)
                stats["messages"] += 1
                stats["bytes"] += len(blob)
    return col, stats


def collect_ensemble(product: EnsProduct, max_runs: int = 1) -> list[dict[str, Any]]:
    """Worker işi: 00/12z ensemble çalıştırmaları (yeniden eskiye)."""
    settings = get_settings()
    region = load_region(settings.region_config)
    base = settings.ecmwf_base_url
    lead = settings.model_max_lead_h
    src = Source(product.spec, product.extractor, base, product.resolution, LICENSE)
    done: list[dict[str, Any]] = []
    with httpx.Client(timeout=120.0, headers={"User-Agent": settings.http_user_agent}) as client:
        # Önce en yeni çalıştırma (tazelik), sonra eksik kalan eskiler.
        candidates = candidate_runs(datetime.now(UTC), settings.model_lookback_hours, cycle_h=12)
        for init in reversed(candidates):
            if not pending(product.code, init):
                continue
            if not ens_run_complete(client, base, init, lead, product):
                continue

            def fetch(i: datetime = init) -> tuple[EnsembleCollector, dict[str, Any]]:
                return collect_ensemble_run(client, settings, region, i, product)

            done.append(process_ensemble_run(src, settings, region, init, fetch))
            if len(done) >= max_runs:
                break
    return done


def collect_ifs_ens() -> list[dict[str, Any]]:
    return collect_ensemble(IFS_ENS)


def collect_aifs_ens() -> list[dict[str, Any]]:
    return collect_ensemble(AIFS_ENS)


def collect(product: Product = IFS, max_runs: int = 2) -> list[dict[str, Any]]:
    """Worker işi: tamamlanmış ve yüklenmemiş çalıştırmaları (yeniden eskiye) işler."""
    settings = get_settings()
    region = load_region(settings.region_config)
    base = settings.ecmwf_base_url
    lead = settings.model_max_lead_h
    src = Source(product.spec, product.extractor, base, product.resolution, LICENSE)
    done: list[dict[str, Any]] = []
    with httpx.Client(timeout=120.0, headers={"User-Agent": settings.http_user_agent}) as client:
        # Önce en yeni çalıştırma (tazelik), sonra eksik kalan eskiler.
        for init in reversed(candidate_runs(datetime.now(UTC), settings.model_lookback_hours)):
            if not pending(product.code, init):
                continue
            if not run_complete(client, base, init, lead, product):
                continue

            def fetch(i: datetime = init) -> tuple[RunCollector, dict[str, Any]]:
                return collect_run(client, settings, region, i, product)

            done.append(process_run(src, settings, region, init, fetch))
            if len(done) >= max_runs:
                break
    return done


def collect_ifs() -> list[dict[str, Any]]:
    return collect(IFS)


def collect_aifs_single() -> list[dict[str, Any]]:
    return collect(AIFS_SINGLE)
