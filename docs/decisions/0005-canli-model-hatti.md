# ADR-0005: Canlı model hattı — indirme, kırpma, nokta çıkarımı

- **Tarih:** 2026-11-02
- **Durum:** Kabul edildi (teknik karar; Faz 3)

## Bağlam
Spec §5.1 her model için yalnız gereken parametrelerin indirilmesini, İstanbul kutusuna kırpılmasını,
kırpılmış dosyaların 30 gün saklanmasını ve kara-deniz maskeli nokta çıkarımını (§6) istiyor.
GRIB2 mesajları alan olarak bölünemez: İstanbul için bile her parametrenin tüm küresi iner.

## Karar
- **Ortak hat** (`hava.ingest.models.pipeline`): adaptör GRIB alanlarını kanonik adlarla (`t2m`,
  `precip_acc`, `lsm`, `orog` …) ve beklenen birimlerle verir; hat kırpar, noktaya çevirir, birikimli
  değişkenleri adım aralığına böler, NetCDF'e yazar ve `point_forecasts`'a yükler. Her model yalnız
  kendi adaptörünü yazar.
- **GRIB çözümü:** pip'teki `eccodes` + `eccodeslib` ikili paketi (libaec/CCSDS dahil; DWD ICON-EU
  CCSDS dosyası sorunsuz çözüldü). Sistem kütüphanesi kurulmaz; Windows'ta da çalışır.
- **İndirme:** index dosyasından (ECMWF `.index`, NOAA `.idx`) seçilen mesajlar tek tek byte-range ile;
  bir adımın mesajları paralel (`model_download_workers`), adımlar sırayla işlenir (bellek düşük kalır).
- **Kırpma:** bölge kutusu + 1° pay (4×4 komşuluk ve ileride maske türetme için). İçeride ızgara
  güneyden kuzeye, batıdan doğuya tutulur; boylamlar −180…180'e çevrilir.
- **Saklama:** kırpılmış alanlar çalıştırma başına NetCDF-4 (`/data/grib/<model>/<init>.nc`,
  `h5netcdf`); 30 gün sonra günlük işle silinir. Nokta çıkarımları kalıcı.
- **Nokta çıkarımı** (`hava.processing.points`): bilineer; kara oranı < 0,5 olan hücreler dışlanıp
  ağırlıklar yeniden ölçeklenir; iç 2×2'de kara yoksa 4×4'te en yakın kara hücresi; yöntem nokta
  başına `extra.point_method`'a yazılır. Sıcaklığa γ = 6,5 °C/km ile yükseklik düzeltmesi; düzeltme ve
  model arazi yüksekliği `extra`'da. Çiy noktası düzeltilmez (sıcaklığı aşarsa kırpılır); bağıl nem
  düzeltmesiz model T/Td'den. Kategorik alanlar (yağış tipi) seçilen kara hücresinden.
  `extraction = bilinear_lsm_lapse`.
- **Durum makinesi:** `model_runs` pending → downloading → extracted → loaded | failed; en fazla 3
  deneme; çalıştırma "tamam" sayılması için son adımın index'i yayımlanmış olmalı. Worker 10 dakikada
  bir son 72 saatteki yüklenmemiş çalıştırmaları eskiden yeniye işler (çağrı başına en fazla 2).
- **Tazelik:** `models.meta.stale_hours` olan modeller `source_health`'te `model:<kod>` olarak izlenir.

## ECMWF IFS özel notları
- Kaynak ECMWF portalı (`data.ecmwf.int`). AWS yansısı 2026-11-02'de tek bir index isteğine bile
  `503 SlowDown` döndürdü → canlıda kullanılmıyor.
- 0.1° (`-sfc`/`-pl` ayrı dosyalar). İlk gerçek çalıştırma (2026-11-02 06z, 49 adım): 639 mesaj,
  1,49 GB indirme, 107 sn, 2.058 satır, kırpılmış dosya 0,99 MB. 42 noktanın tamamında
  `lsm_bilinear`; yükseklik düzeltmesi −0,7…+0,6 °C.
- Hamle parametresi adıma göre değişiyor (index'ten teyit): 0–90 sa `10fg` (son 1 sa), 93–144 sa
  `10fg3` (son 3 sa), 150+ sa `10fg` (son 6 sa). 0. adımda `tp` ve `10fg` mesajları boş.

## Sonuçlar
- İndirme hacmi çalıştırma başına ~1,2–1,5 GB (IFS 0.1°); ensemble'larda çok daha fazla olacak →
  ensemble'da adım/parametre sınırlaması ayrıca kararlaştırılacak.
- Kanonik ad ve birim sözleşmesi bozulursa tüm modeller etkilenir; testler (`tests/test_pipeline.py`)
  bu sözleşmeyi sabitler.
