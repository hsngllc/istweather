# ADR-0001: Repo konumu ve veri depolama

- **Tarih:** 2026-11-01
- **Durum:** Kabul edildi (proje sahibi kararı)

## Bağlam
Spec ilk hâlinde repo'nun bind mount performansı için WSL2 dosya sisteminde klonlanmasını öneriyordu.
Geliştirme makinesi Windows; Docker Desktop henüz kurulu değil.

## Karar
- Repo `C:\istweather`'da kalır.
- Veritabanı, GRIB/NetCDF ve Parquet verileri Docker named volume'larda durur (`db_data`, `grib_data`,
  `parquet_data`, `backup_data`); repo klasörüne veri yazılmaz.
- Konteynerlere yalnız kaynak kod bind mount edilir (`src/`, `alembic/`, `config/`, `tests/`);
  üretimde bind mount yoktur.
- `.gitattributes` ile metin dosyalarının satır sonu LF'ye sabitlenir.
- Geliştirmede `uvicorn --reload` Windows bind mount'unda dosya olayları gelmediği için yoklamayla
  (`WATCHFILES_FORCE_POLLING`) çalışır.

## Sonuçlar
- Veri yoğun G/Ç Windows ↔ Linux sınırını geçmez; kod düzenleme Windows'ta kalır.
- Geçici istisna: UKMO geçmiş çıkarımı Docker kurulana kadar Windows'ta yerel Python ile `.data/`
  altına yazdı (bkz. ADR-0002). 2026-11-02'de Docker kuruldu, veri `parquet_data` volume'una
  taşındı; istisna sona erdi.
- Windows'ta 8000 portu başka bir programdaysa API'nin dış portu `.env`'de `HAVA_API_PORT` ile
  değiştirilir (konteyner içinde hep 8000).
