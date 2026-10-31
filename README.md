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
| 1. İskelet | Kod hazır; Docker ile doğrulama bekliyor (aşağıya bakın) |
| UKMO geçmiş çıkarımı | Faz 0 sonrası başlatıldı (spec §5.2.5), Windows'ta arka planda çalışıyor |

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

1. **Docker Desktop**'ı (WSL2 backend) kurun. Bu makinede henüz kurulu değil; Faz 1'in
   `docker compose up` kabulü için gerekli.
2. Ortam dosyası:
   ```
   copy .env.example .env
   ```
   `.env` içinde en az `POSTGRES_PASSWORD`'ü doldurun. `.env` git'e girmez; anahtarları başka yerde
   paylaşmayın.
3. Başlatın:
   ```
   docker compose up --build
   ```
4. Kontrol:
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

## UKMO geçmiş nokta çıkarımı (geçici, Windows)

UK Met Office Global arşivi AWS'te 2 yıllık kayan penceredir; her gün en eski gün silinir. Bu yüzden
39 ilçe + 3 METAR noktası için nokta çıkarımı Faz 4'ü beklemeden başlatıldı. Veri **yalnız iç
doğrulama** içindir (CC BY-SA). Docker kurulana kadar yerel Python ile çalışır ve git dışı
`.data\ukmo_global\` altına yazar; iş kaldığı yerden devam eder.

```
powershell -ExecutionPolicy Bypass -File scripts\ukmo-backfill.ps1          # başlat
powershell -ExecutionPolicy Bypass -File scripts\ukmo-backfill.ps1 -Stop    # durdur
```

İlerleme: `.data\ukmo_global\backfill.log` ve çalıştırma başına `manifest\*.json`. Veritabanına
yükleme: `python -m hava.ingest.archive.load_ukmo --dir <parquet dizini>`.

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
