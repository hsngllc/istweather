"""ECMWF açık verisi: IFS 0.1° deterministik (spec §5.1; docs/data-sources.md §2.1).

Kaynak ECMWF portalı (``data.ecmwf.int``): son ~12 çalıştırmayı tutar ve Range destekler. AWS
yansısı yoğun istekte ``503 SlowDown`` döndürdüğü için canlıda kullanılmaz. Her adımın ``.index``
dosyasından (JSON satırları) gereken mesajlar seçilir ve tek tek byte-range ile indirilir.

Adımlar: 00/12z 0–144 sa 3'er, 150–360 sa 6'şar; 06/18z 0–144 sa 3'er. ``model_max_lead_h``'e kadar
alınır. Hamle: 0–90 sa ``10fg`` (son 1 sa max), 93–144 sa ``10fg3`` (son 3 sa), 150+ sa ``10fg``
(son 6 sa) — param-db 49 / 228028. Yağış ``tp``/``cp``/``sf`` başlangıçtan beri birikimli (m).
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import structlog

from hava.db.session import session_scope
from hava.ingest.archive.http_range import get_with_retry
from hava.ingest.models import runs
from hava.ingest.models.grib import decode_message
from hava.ingest.models.pipeline import (
    ModelSpec,
    RunCollector,
    extract_rows,
    store_rows,
    write_netcdf,
)
from hava.processing.grid import BBox
from hava.region import Region, load_region
from hava.settings import Settings, get_settings

log = structlog.get_logger()

MODEL_CODE = "ecmwf_ifs"
EXTRACTOR_VERSION = "ecmwf-ifs-1"
RESOL = "0p1"
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


def gust_definition(step: float) -> str:
    if step <= 90:
        return "max_1h"
    return "max_3h" if step <= 144 else "max_6h"


SPEC = ModelSpec(code=MODEL_CODE, gust_definition=gust_definition, ptype_names=PTYPE_NAMES)


def steps_for(init: datetime, max_lead_h: int) -> list[int]:
    steps = list(range(0, 145, 3))
    if init.hour in (0, 12):
        steps += list(range(150, 361, 6))
    return [s for s in steps if s <= max_lead_h]


def file_stem(base: str, init: datetime) -> str:
    return f"{base}/{init:%Y%m%d}/{init:%H}z/ifs/{RESOL}/oper/{init:%Y%m%d%H}0000"


def grib_url(base: str, init: datetime, step: int, levtype: str) -> str:
    return f"{file_stem(base, init)}-{step}h-oper-fc-{levtype}.grib2"


def index_url(base: str, init: datetime, step: int, levtype: str) -> str:
    return grib_url(base, init, step, levtype)[: -len(".grib2")] + ".index"


def parse_index(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def select(
    entries: Sequence[dict[str, Any]], wants: Sequence[Want], step: int
) -> list[tuple[Want, dict[str, Any]]]:
    """Adımda istenen mesajları seçer; hamle için o adımın parametresi tercih edilir."""
    gust_param = "10fg3" if 90 < step <= 144 else "10fg"
    out: list[tuple[Want, dict[str, Any]]] = []
    for w in wants:
        if w.var == "gust" and w.param != gust_param:
            continue
        for e in entries:
            if e.get("param") == w.param and (w.level is None or e.get("levelist") == w.level):
                if int(e.get("_length", 0)) > 0:
                    out.append((w, e))
                break
    return out


def candidate_runs(now: datetime, lookback_hours: int) -> list[datetime]:
    """Bakış penceresindeki 00/06/12/18 çalıştırmaları, eskiden yeniye."""
    last = now.replace(minute=0, second=0, microsecond=0)
    last -= timedelta(hours=last.hour % 6)
    n = lookback_hours // 6 + 1
    return [last - timedelta(hours=6 * k) for k in range(n)][::-1]


def run_complete(client: httpx.Client, base: str, init: datetime, max_lead_h: int) -> bool:
    """Son adımın index'i yayımlandıysa çalıştırma tamamdır."""
    last = steps_for(init, max_lead_h)[-1]
    resp = client.get(index_url(base, init, last, "sfc"))
    return resp.status_code == 200


def _download(client: httpx.Client, url: str, entry: dict[str, Any]) -> bytes:
    lo = int(entry["_offset"])
    hi = lo + int(entry["_length"]) - 1
    return get_with_retry(client, url, headers={"Range": f"bytes={lo}-{hi}"}, attempts=5).content


def collect_run(
    client: httpx.Client, settings: Settings, region: Region, init: datetime
) -> tuple[RunCollector, dict[str, Any]]:
    bbox = BBox(region.lat_min, region.lat_max, region.lon_min, region.lon_max)
    col = RunCollector(bbox.expanded(settings.model_crop_margin_deg))
    base = settings.ecmwf_base_url
    stats = {"messages": 0, "bytes": 0}
    with ThreadPoolExecutor(settings.model_download_workers) as pool:
        for step in steps_for(init, settings.model_max_lead_h):
            jobs: list[tuple[Want, str, dict[str, Any]]] = []
            for levtype, wants in (("sfc", SFC), ("pl", PL)):
                text = get_with_retry(client, index_url(base, init, step, levtype)).text
                entries = parse_index(text)
                chosen = list(wants) + (list(STATIC) if step == 0 and levtype == "sfc" else [])
                url = grib_url(base, init, step, levtype)
                jobs += [(w, url, e) for w, e in select(entries, chosen, step)]
            blobs = list(pool.map(lambda j: _download(client, j[1], j[2]), jobs))
            for (w, _, _), blob in zip(jobs, blobs, strict=True):
                f = decode_message(blob)
                if w in STATIC:
                    col.add_static(w.var, f, w.scale)
                else:
                    col.add(w.var, step, f, w.scale)
                stats["messages"] += 1
                stats["bytes"] += len(blob)
    return col, stats


def process_run(
    client: httpx.Client, settings: Settings, region: Region, init: datetime
) -> dict[str, Any]:
    started = time.monotonic()
    with session_scope() as session:
        mid = runs.model_id(session, MODEL_CODE)
        run = runs.get_run(session, mid, init)
        attempts = int(((run.files if run else None) or {}).get("attempts", 0)) + 1
        files = {"attempts": attempts, "source": settings.ecmwf_base_url, "resolution": RESOL}
        runs.set_status(session, mid, init, "downloading", files=files)
        session.commit()
    try:
        col, stats = collect_run(client, settings, region, init)
        rows = extract_rows(col, SPEC, region.points, init)
        path = Path(settings.grib_dir) / MODEL_CODE / f"{init:%Y%m%dT%H}Z.nc"
        write_netcdf(
            col,
            path,
            {
                "model": MODEL_CODE,
                "init_time": init.isoformat(),
                "source": settings.ecmwf_base_url,
                "resolution": RESOL,
                "license": "CC BY 4.0 + ECMWF Terms of Use",
            },
        )
        with session_scope() as session:
            runs.set_status(session, mid, init, "extracted", files={"crop_file": str(path)})
            n = store_rows(session, mid, init, rows)
            runs.set_status(
                session,
                mid,
                init,
                "loaded",
                files={
                    "extractor": EXTRACTOR_VERSION,
                    "steps": len(col.steps),
                    "rows": n,
                    "messages": stats["messages"],
                    "bytes": stats["bytes"],
                    "seconds": round(time.monotonic() - started, 1),
                },
            )
            session.commit()
    except Exception as exc:
        with session_scope() as session:
            runs.set_status(
                session, mid, init, "failed", error=f"{type(exc).__name__}: {exc}"[:500]
            )
            session.commit()
        raise
    summary = {
        "run": init.isoformat(),
        "rows": n,
        **stats,
        "seconds": round(time.monotonic() - started, 1),
    }
    log.info("model_run_loaded", model=MODEL_CODE, **summary)
    return summary


def collect(max_runs: int = 2) -> list[dict[str, Any]]:
    """Worker işi: tamamlanmış ve yüklenmemiş IFS çalıştırmalarını (eskiden yeniye) işler."""
    settings = get_settings()
    region = load_region(settings.region_config)
    done: list[dict[str, Any]] = []
    with httpx.Client(timeout=120.0, headers={"User-Agent": settings.http_user_agent}) as client:
        for init in candidate_runs(datetime.now(UTC), settings.model_lookback_hours):
            with session_scope() as session:
                run = runs.get_run(session, runs.model_id(session, MODEL_CODE), init)
                if not runs.should_process(run):
                    continue
            if not run_complete(client, settings.ecmwf_base_url, init, settings.model_max_lead_h):
                continue
            done.append(process_run(client, settings, region, init))
            if len(done) >= max_runs:
                break
    return done
