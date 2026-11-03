"""ECCC GDPS 15 km (GEM global) deterministik — AMQPS bildirimleriyle (ADR-0007; kaynaklar §2.7).

ECCC politikası sistematik alımda AMQPS'i zorunlu tutar ve yeni veri için dizin listelemeyi
yasaklar. Bu yüzden:

- ``Listener`` (worker'da ayrı iş parçacığı) ``xpublic`` exchange'ine
  ``v02.post.*.WXO-DD.model_gdps.15km.#`` ile abone olur; istenen değişkenlerin duyurularını
  çalıştırma başına biriktirme dosyasına (``<grib_dir>/_gdps/<YYYYMMDDTHHZ>.jsonl``) yazar.
- ``collect`` (10 dk'lık iş) son adımın çekirdek alanları duyurulmuş ve 15 dakikadır yeni duyuru
  gelmemişse dosyaları bildirimdeki adresten indirir ve ortak hatla işler. Yol üretilmez.

Dosya adı ``<YYYYMMDD>T<HH>Z_MSC_GDPS_<DEĞİŞKEN>_<SEVİYE>_LatLon0.15_PT<hhh>H.grib2``; 0,15° küresel
ızgara. Çalıştırmalar 00/12z; 0–84 sa saatlik, sonra 3 saatlik. Birikimler başlangıçtan beri
(0. adımda yağış dosyası yok → başlangıç 0); hamle anlık; bulut %. Yağış tipi yağış olmayan yerde de
dolu olduğundan alınmaz.
"""

from __future__ import annotations

import json
import re
import ssl
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pika
import structlog

from hava.ingest.archive.http_range import get_with_retry
from hava.ingest.models.grib import decode_message
from hava.ingest.models.pipeline import ModelSpec, RunCollector
from hava.ingest.models.runner import Source, pending, process_run
from hava.processing.grid import BBox
from hava.region import Region, load_region
from hava.settings import Settings, get_settings

log = structlog.get_logger()

MODEL_CODE = "eccc_gdps"
EXTRACTOR_VERSION = "eccc-gdps-1"
RESOL = "0.15°"
LICENSE = "ECCC Data Servers End-use Licence (Data Source: Environment and Climate Change Canada)"
BROKER = "amqps://anonymous:anonymous@dd.weather.gc.ca:5671/%2F"
EXCHANGE = "xpublic"
TOPIC = "v02.post.*.WXO-DD.model_gdps.15km.#"
FILE_RE = re.compile(
    r"(?P<run>\d{8}T\d{2}Z)_MSC_GDPS_(?P<var>.+)_LatLon0\.15_PT(?P<step>\d{3})H\.grib2$"
)
# Dosya adındaki değişken_seviye → (kanonik ad, çarpan)
FIELDS: dict[str, tuple[str, float]] = {
    "AirTemp_AGL-2m": ("t2m", 1.0),
    "DewPoint_AGL-2m": ("d2m", 1.0),
    "WindU_AGL-10m": ("u10", 1.0),
    "WindV_AGL-10m": ("v10", 1.0),
    "WindGust_AGL-10m": ("gust", 1.0),
    "Pressure_MSL": ("msl", 1.0),
    "TotalCloudCover_Sfc": ("tcc", 0.01),
    "Precip-Accum_Sfc": ("precip_acc", 1.0),
    "ConvectivePrecip-Accum_Sfc": ("conv_acc", 1.0),
    "Snow-Accum_Sfc": ("snow_acc", 1.0),
    "AirTemp_IsbL-0850": ("t850", 1.0),
}
STATIC = {"GeopotentialHeight_Sfc": "orog", "LandWaterProportion_Sfc": "lsm"}
CORE = ("AirTemp_AGL-2m", "Precip-Accum_Sfc", "WindU_AGL-10m")  # son adımda duyurulmuş olmalı
LAST_STEP_H = 168
QUIET = timedelta(minutes=15)
DOWNLOAD_WORKERS = 4

SPEC = ModelSpec(code=MODEL_CODE, gust_definition=lambda s: "instant")


@dataclass(frozen=True)
class Notice:
    run: datetime
    var: str
    step: int
    url: str


def parse_notice(body: bytes) -> Notice | None:
    """Sarracenia v02 gövdesi ``<zaman> <taban adres> <göreli yol>``; istenmeyen dosyada None."""
    parts = body.decode("utf-8", errors="replace").split()
    if len(parts) < 3:
        return None
    base, rel = parts[1], parts[2]
    m = FILE_RE.search(rel)
    if m is None or (m["var"] not in FIELDS and m["var"] not in STATIC):
        return None
    run = datetime.strptime(m["run"], "%Y%m%dT%HZ").replace(tzinfo=UTC)
    return Notice(run, m["var"], int(m["step"]), f"{base.rstrip('/')}/{rel.lstrip('/')}")


def spool_dir(settings: Settings) -> Path:
    return Path(settings.grib_dir) / "_gdps"


def append_notice(folder: Path, n: Notice, received: datetime) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"var": n.var, "step": n.step, "url": n.url, "at": received.isoformat()})
    with (folder / f"{n.run:%Y%m%dT%HZ}.jsonl").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_spool(path: Path) -> tuple[dict[tuple[str, int], str], datetime | None]:
    """(değişken, adım) → adres ve son duyuru zamanı; yarım yazılmış son satır atlanır."""
    files: dict[tuple[str, int], str] = {}
    last: datetime | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        files[(rec["var"], int(rec["step"]))] = rec["url"]
        at = datetime.fromisoformat(rec["at"])
        last = at if last is None or at > last else last
    return files, last


def ready(
    files: dict[tuple[str, int], str], last: datetime | None, now: datetime, lead: int
) -> bool:
    """Son adımın çekirdek alanları duyuruldu ve bir süredir yeni duyuru yok."""
    final = min(LAST_STEP_H, lead)
    if last is None or now - last < QUIET:
        return False
    return all((v, final) in files for v in CORE)


def queue_name(folder: Path) -> str:
    """Kuruluma özgü kalıcı kuyruk adı (iki kurulum aynı kuyruğu paylaşmasın)."""
    path = folder / "queue_name"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    folder.mkdir(parents=True, exist_ok=True)
    name = f"q_anonymous.istweather.gdps.{uuid.uuid4().hex[:12]}"
    path.write_text(name, encoding="utf-8")
    return name


class Listener(threading.Thread):
    """AMQPS duyurularını biriktirme dosyalarına yazar; koparsa artan beklemeyle yeniden bağlar."""

    def __init__(self, folder: Path, user_agent: str) -> None:
        super().__init__(name="gdps-amqp", daemon=True)
        self.folder = folder
        self.user_agent = user_agent
        self.stop_event = threading.Event()

    def run(self) -> None:
        delay = 5.0
        while not self.stop_event.is_set():
            try:
                self._consume()
                delay = 5.0
            except Exception as exc:  # bağlantı hataları beklenir; iş parçacığı ölmemeli
                log.warning("gdps_amqp_error", error=f"{type(exc).__name__}: {exc}"[:300])
                self.stop_event.wait(delay)
                delay = min(delay * 2, 600.0)

    def _consume(self) -> None:
        params = pika.URLParameters(BROKER)
        params.ssl_options = pika.SSLOptions(ssl.create_default_context(), "dd.weather.gc.ca")
        params.heartbeat = 300
        params.client_properties = {"product": self.user_agent}
        conn = pika.BlockingConnection(params)
        try:
            ch = conn.channel()
            queue = queue_name(self.folder)
            ch.queue_declare(queue=queue, durable=True, auto_delete=False)
            ch.queue_bind(queue=queue, exchange=EXCHANGE, routing_key=TOPIC)
            ch.basic_qos(prefetch_count=200)
            log.info("gdps_amqp_connected", queue=queue)
            for method, _props, body in ch.consume(queue, inactivity_timeout=60):
                if self.stop_event.is_set():
                    break
                if method is None:
                    continue
                notice = parse_notice(body)
                if notice is not None:
                    append_notice(self.folder, notice, datetime.now(UTC))
                ch.basic_ack(method.delivery_tag)
        finally:
            if conn.is_open:
                conn.close()


def collect_run(
    client: httpx.Client, settings: Settings, region: Region, files: dict[tuple[str, int], str]
) -> tuple[RunCollector, dict[str, Any]]:
    bbox = BBox(region.lat_min, region.lat_max, region.lon_min, region.lon_max)
    col = RunCollector(bbox.expanded(settings.model_crop_margin_deg))
    stats = {"messages": 0, "bytes": 0}
    jobs = [(k, url) for k, url in sorted(files.items()) if k[1] <= settings.model_max_lead_h]
    with ThreadPoolExecutor(DOWNLOAD_WORKERS) as pool:
        blobs = pool.map(lambda j: get_with_retry(client, j[1], attempts=5).content, jobs)
        for ((var, step), _), blob in zip(jobs, blobs, strict=True):
            f = decode_message(blob)
            stats["messages"] += 1
            stats["bytes"] += len(blob)
            if var in STATIC:
                col.add_static(STATIC[var], f)
            else:
                name, scale = FIELDS[var]
                col.add(name, step, f, scale)
    return col, stats


def collect(max_runs: int = 1) -> list[dict[str, Any]]:
    """Worker işi: duyuruları tamamlanan çalıştırmaları (yeniden eskiye) işler."""
    settings = get_settings()
    region = load_region(settings.region_config)
    folder = spool_dir(settings)
    now = datetime.now(UTC)
    src = Source(SPEC, EXTRACTOR_VERSION, "https://dd.weather.gc.ca", RESOL, LICENSE)
    done: list[dict[str, Any]] = []
    if not folder.exists():
        return done
    with httpx.Client(timeout=120.0, headers={"User-Agent": settings.http_user_agent}) as client:
        for path in sorted(folder.glob("*.jsonl"), reverse=True):
            init = datetime.strptime(path.stem, "%Y%m%dT%HZ").replace(tzinfo=UTC)
            if not pending(MODEL_CODE, init) or now - init > timedelta(days=7):
                path.unlink(missing_ok=True)  # yüklendi, denemeler bitti ya da çok eski
                continue
            files, last = read_spool(path)
            if not ready(files, last, now, settings.model_max_lead_h):
                continue

            def fetch(
                f: dict[tuple[str, int], str] = files,
            ) -> tuple[RunCollector, dict[str, Any]]:
                return collect_run(client, settings, region, f)

            done.append(process_run(src, settings, region, init, fetch))
            path.unlink(missing_ok=True)
            if len(done) >= max_runs:
                break
    return done
