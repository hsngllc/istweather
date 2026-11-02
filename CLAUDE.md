# CLAUDE.md — Claude Code için kalıcı kurallar

Tek doğru kaynak: `istanbul-hava-backend-spec.md`. `cok-modelli-hava-tahmini` skill'i ile çelişirse spec
geçerlidir (ör. model verisi Open-Meteo'dan değil, ham kaynaklardan gelir).

## Temel kurallar (spec §2)
- **Veri uydurma yok.** Üretimde sahte/örnek/"fallback" veri yok. Kaynak çökerse veri `stale` işaretlenir,
  bildirim gider; sessizce başka değer gösterilmez.
- **Test verisi etiketli** ve `tests/fixtures/` altında (veya testte sentetik olarak üretilip öyle adlandırılır).
- **"Yüksek doğruluk" ölçülerek iddia edilir**; blend en iyi tek modeli yenmiyorsa açıkça raporlanır.
- **Her tahmin değeri izlenebilir**: model, init time, çıkarım yöntemi (`extraction`), blend sürümü.
- **Fazlar sırayla.** Her faz sonunda kabul kriterlerini kanıtla ve proje sahibine özet ver; onay almadan
  sonraki faza geçme.
- **Doğrulanmamış bilgiye dayanma.** URL, model kodu, dosya adı, arşiv tarihi: önce birincil kaynaktan teyit
  et, `docs/data-sources.md`'ye kaynağıyla yaz. Kod dokümana değil gerçek dosyaya (index, GRIB başlığı) güvenir.
- Bir şey çalışmıyorsa çalışıyormuş gibi gösterme; sorunu, nedeni ve seçenekleri yaz.
- Büyük mimari kararlar `docs/decisions/` altında kısa ADR.

## Proje sahibi kararları (2026-11-01)
- **MGM: doğrudan kullanım iptal.** `servis.mgm.gov.tr`'ye istek gönderme; MGM erişim kısıtını aşan
  (`Origin`/`Referer` taklidi vb.) kod yazma. MGM yalnız yazılı izin veya MEVBİS lisansıyla gelirse eklenir.
- Gözlem: canlı METAR (AWC), geçmiş IEM. WIS2'de Türkiye yok. İBB açık verisinde meteoroloji gözlemi yok.
- UKMO (CC BY-SA) yalnız iç doğrulama (`models.internal_only`); sitede ve blend'de kullanılmaz.
- ARPEGE: yalnız açık paketler (Licence Ouverte 2.0); TIGGE'deki MF verisi CC BY-NC → kullanılmaz.
- Kıyı merkez noktaları kaydırılmaz; model değeri kara-deniz maskeli seçimle alınır.
- Repo `C:\istweather`'da; veriler Docker named volume'larda, yalnız kaynak kod bind mount; satır sonu LF.
- Anahtarlar (TIGGE, Hugging Face vb.) yalnız `.env`'e girer; sohbette isteme.

## Dil ve stil
- Kod (değişken, fonksiyon, tablo adları) İngilizce; README, dokümanlar, açıklamalar ve log mesajlarının
  açıklama kısmı Türkçe.
- Python 3.12, `ruff` (satır 100), `mypy --strict`, `pytest`. Ağ gerektiren testler `@pytest.mark.network`
  (CI'da kapalı); TimescaleDB gerektirenler `@pytest.mark.integration` (`HAVA_DATABASE_URL` yoksa atlanır).
- Zamanlar UTC (`timestamptz`), birimler SI (°C, m/s, mm, hPa, m). Rüzgâr yönü u/v ile birleştirilir.

## Komutlar
- Yerel ortam: `py -3.12 -m venv .venv` → `.venv\Scripts\python -m pip install -e ".[dev]"`
- Kalite: `ruff check .`, `ruff format --check .`, `mypy`, `pytest`
- Docker: `docker compose up --build` (önce `.env`); üretim: `-f docker-compose.yml -f docker-compose.prod.yml`
- Migration: `alembic revision -m "..."` (elle), `alembic upgrade head`; modeller değişince yeni migration.
- UKMO çıkarımı/yükleme: `docker compose run --rm --no-deps worker python -m hava.ingest.archive.ukmo --out /data/parquet/ukmo_global`, ardından `... -m hava.ingest.archive.load_ukmo`
- Windows'ta: API dış portu `.env`'de `HAVA_API_PORT` (8000 başka programda). Git Bash'ten `docker compose exec` ile
  `/data/...` yolu verirken `MSYS_NO_PATHCONV=1`; PowerShell 5.1 tırnaklı argümanları bozduğu için `psql` komutlarını Bash'ten ver.

## Commit
Küçük ve açıklayıcı commit'ler. `.env` ve veri dosyaları (GRIB, NetCDF, Parquet, `.data/`) git'e girmez.
