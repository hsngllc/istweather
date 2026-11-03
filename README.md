# İstanbul Çok Modelli Hava Tahmini — Backend

İstanbul'un 39 ilçesi için 7 günlük, çok modelli, gözlemle doğrulanmış hava tahmini üreten backend.
Tek doğru kaynak: [istanbul-hava-backend-spec.md](istanbul-hava-backend-spec.md).

- Veri kaynakları envanteri: [docs/data-sources.md](docs/data-sources.md)
- İlçe noktaları ve istasyonlar: [docs/districts-and-stations.md](docs/districts-and-stations.md)
- Mimari karar kayıtları: [docs/decisions/](docs/decisions/)

> Tahminler otomatik üretilir, resmi tahmin yerine geçmez.

## Durum

| Faz | Durum |
|---|---|
| 0. Keşif | Tamamlandı (2026-11-01) |
| 1. İskelet | Tamamlandı (2026-11-02): `docker compose up` ve CI yeşil |
| 2. Gözlem ingest | Tamamlandı (2026-11-02, proje sahibinin onayıyla): QC raporu ve bildirim testi tamam; 48 saatlik kesintisiz çalışma bilgisayar kapandığı için sunucuda kanıtlanacak ([rapor](docs/reports/qc-canli-2026-11-02.md)) |
| 3. Canlı model ingest | Sürüyor: ortak hat (GRIB, kırpma, maskeli nokta çıkarımı; düzenli ve üçgen ızgara) ile ECMWF IFS 0.1°, AIFS Single, NOAA GFS, DWD ICON ve ICON-EU canlıda ([ADR-0005](docs/decisions/0005-canli-model-hatti.md)); diğer modeller sırada |
| UKMO geçmiş çıkarımı | Tamamlandı: 2.929 çalıştırma, 2024-10-30T18Z → 2026-11-01T18Z (spec §5.2.5); veritabanında (9,1 milyon satır, 42 nokta) |

## Mimari özet

```
worker (APScheduler)  ──►  PostgreSQL + TimescaleDB  ◄──  api (FastAPI, /api/v1)
   ingest → processing → verification → blending → published_forecasts
```

Docker Compose servisleri: `db` (TimescaleDB), `migrate` (Alembic + referans verisi, tek seferlik),
`api`, `worker`, `backup` (günlük `pg_dump`, `--profile ops`), üretimde `caddy` (HTTPS).

Veriler Docker **named volume**'larda durur (`db_data`, `grib_data`, `parquet_data`, `backup_data`);
konteynerlere yalnız kaynak kod bind mount edilir. Repo `C:\istweather` altında kalır.

## Kurulum (geliştirme, Windows)

1. **Docker Desktop**'ı (WSL2 backend, kullanıcı başına kurulum yeterli) kurun.
2. Ortam dosyası:
   ```
   copy .env.example .env
   ```
   `.env` içinde en az `POSTGRES_PASSWORD`'ü doldurun. `.env` git'e girmez; anahtarları başka yerde
   paylaşmayın. 8000 portunu başka bir program kullanıyorsa `HAVA_API_PORT`'u değiştirin.
3. Başlatın:
   ```
   docker compose up --build
   ```
4. Kontrol (port `HAVA_API_PORT`, varsayılan 8000):
   - Sağlık: http://127.0.0.1:8000/api/v1/health
   - OpenAPI: http://127.0.0.1:8000/api/v1/docs

Satır sonları `.gitattributes` ile LF'ye sabitlenmiştir (Linux konteynerleri için).

## Yerel Python ortamı (Docker olmadan testler)

```
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\ruff check .
.venv\Scripts\mypy
.venv\Scripts\python -m pytest
```

Veritabanı entegrasyon testleri `HAVA_DATABASE_URL` tanımlı değilse atlanır; CI'da TimescaleDB servis
konteyneriyle çalışır.

## Gözlemler (METAR)

- **Canlı:** worker 5 dakikada bir AWC'den son 3 saatin METAR'larını alır (LTFM, LTFJ, LTBA), yazar
  ve QC uygular. Kaynak tazeliği 5 dakikada bir denetlenir; bir istasyonun son gözlemi 90 dakikadan
  eskiyse veya AWC 30 dakikadır yanıt vermiyorsa bildirim gider, düzelince tekrar gider.
- **Geçmiş:** IEM arşivinden; her gece son 3 günün boşlukları da IEM'den doldurulur.
- Değerler ham METAR'dan kendi ayrıştırıcımızla çözülür
  ([ADR-0004](docs/decisions/0004-metar-ham-metinden-ayristirma.md)); QC kuralları [docs/qc.md](docs/qc.md).
- Bildirim kanalları `.env`'de (Telegram ve/veya e-posta); ayarlanmamışsa bildirim yalnız loga yazılır.

```
# geçmiş METAR (idempotent; var olan kayıtlara dokunmaz)
docker compose run --rm --no-deps worker python -m hava.ingest.obs.iem --since 2024-01-01
# QC raporu
docker compose run --rm --no-deps worker python -m hava.qc.report --since 2024-01-01
```

## UKMO geçmiş nokta çıkarımı

UK Met Office Global arşivi AWS'te 2 yıllık kayan penceredir; her gün en eski gün silinir. Bu yüzden
39 ilçe + 3 METAR noktası için nokta çıkarımı Faz 4'ü beklemeden başlatıldı ve 2026-11-02'de
tamamlandı. Veri **yalnız iç doğrulama** içindir (CC BY-SA). Çıktı `parquet_data` volume'unda
(`/data/parquet/ukmo_global`); iş kaldığı yerden devam eder, yüklenmiş çalıştırmalar atlanır.

```
# yeni çalıştırmaları çıkar (bekleyen yoksa hemen biter)
docker compose run --rm --no-deps worker python -m hava.ingest.archive.ukmo --out /data/parquet/ukmo_global
# veritabanına yükle
docker compose run --rm --no-deps worker python -m hava.ingest.archive.load_ukmo
```

Docker olmadan yedek yol (Windows, `.data\ukmo_global\`):
`powershell -ExecutionPolicy Bypass -File scripts\ukmo-backfill.ps1 [-Stop]`.

## Depo yapısı

```
config/            bölge (ilçe/istasyon noktaları) ve model kataloğu
src/hava/api/      FastAPI uygulaması
src/hava/db/       SQLAlchemy modelleri, oturum, referans verisi (seed)
src/hava/ingest/   veri toplama (archive/: geçmiş arşiv çıkarımı ve yükleme)
src/hava/scheduler worker (APScheduler)
src/hava/ops/      loglama, işletme
alembic/           migration'lar
tests/             birim ve entegrasyon testleri
docs/              kaynak envanteri, kararlar
```

## CI

GitHub Actions (`.github/workflows/ci.yml`): `ruff check`, `ruff format --check`, `mypy`, `pytest`
(TimescaleDB servis konteyneriyle) ve `docker compose up` + `/api/v1/health` duman testi.
