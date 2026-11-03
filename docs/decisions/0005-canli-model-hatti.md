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
  düzeltmesiz model T/Td'den. Kategorik alanlar (yağış tipi) seçilen kara hücresinden, ham kodu
  `extra.ptype_code`'da. `extraction = bilinear_lsm_lapse`.
- **Üçgen ızgara (ICON, 2026-11-03):** yeniden ızgaralama yapılmaz (ek yumuşatma ve bağımlılık
  getirir). Kutudaki hücreler `CLAT/CLON`'dan indisle seçilir; hücre merkezlerinin Delaunay
  üçgenlemesinde noktayı içeren üçgenin köşelerinden barisentrik (doğrusal) ağırlık — düzenli
  ızgaradaki bilineerin karşılığı. Kara-deniz maskesi aynı kuralla (köşelerde kara yoksa en yakın 12
  hücrede en yakın kara hücresi). `extraction = barycentric_lsm_lapse`. Kırpılmış NetCDF'te boyut
  `cell`, koordinatlar `lat(cell)`, `lon(cell)`, öznitelik `grid_id`. Bağımlılık: `scipy`.
- **Durum makinesi:** `model_runs` pending → downloading → extracted → loaded | failed; en fazla 3
  deneme; çalıştırma "tamam" sayılması için son adımın dosyaları yayımlanmış olmalı. Ortak akış
  `hava.ingest.models.runner`'da. Worker'da **her model ayrı iş** (`collect_model:<kod>`, 10 dk):
  yavaş bir model diğerini bekletmez, hata bildirimi model adıyla gelir. Her iş son 72 saatteki
  (DWD için 30 saat) yüklenmemiş çalıştırmaları **yeniden eskiye** işler (çağrı başına en fazla 2):
  kesinti sonrası önce güncel veri gelir, eksik eskiler sonraki turlarda dolar (2026-11-03; önceden
  eskiden yeniye işleniyordu ve ilk dolumda tazelik uyarısına yol açtı).
- **Tazelik:** `models.meta.stale_hours` olan modeller `source_health`'te `model:<kod>` olarak izlenir.
  Hiç yüklenmiş çalıştırması olmayan yeni bir model, toplayıcısı (`collector:<kod>`) ilk turunu
  başarıyla bitirene kadar bayat sayılmaz; toplayıcı hata verirse iş hatası bildirimi gider.

## ECMWF IFS özel notları
- Kaynak ECMWF portalı (`data.ecmwf.int`). AWS yansısı 2026-11-02'de tek bir index isteğine bile
  `503 SlowDown` döndürdü → canlıda kullanılmıyor.
- 0.1° (`-sfc`/`-pl` ayrı dosyalar). İlk gerçek çalıştırma (2026-11-02 06z, 49 adım): 639 mesaj,
  1,49 GB indirme, 107 sn, 2.058 satır, kırpılmış dosya 0,99 MB. 42 noktanın tamamında
  `lsm_bilinear`; yükseklik düzeltmesi −0,7…+0,6 °C.
- Hamle parametresi adıma göre değişiyor (index'ten teyit): 0–90 sa `10fg` (son 1 sa), 93–144 sa
  `10fg3` (son 3 sa), 150+ sa `10fg` (son 6 sa). 0. adımda `tp/cp/sf/10fg` sabit sıfır mesajları:
  birikimlerde başlangıç değeri olarak kullanılır, **hamle alınmaz** (2026-11-03 düzeltmesi: ilk 14
  çalıştırmada 0. saate "0 m/sn" hamle yazılmıştı; 588 satır boşaltıldı).

## Ortak kurallar (2026-11-03 eklemeleri)
- Birikimli değişkenin 0. adımda mesajı yoksa (GFS) başlangıç değeri tanım gereği 0 alınır; ilk aralık
  kaybolmaz.
- Kaynak bir alanı başlangıç anında "değer yok" anlamında sabit doldurursa o alan 0. adımda alınmaz
  (IFS `10fg`). Kaynak gerçek değer veriyorsa alınır (ICON-EU `VMAX_10M`).
- Görüş (`vis`, m) kanonik değişkenlere eklendi → `visibility_m` (şimdilik yalnız GFS).

## NOAA GFS özel notları (2026-11-03)
- Kaynak AWS NODD (`noaa-gfs-bdp-pds`); `.idx`'ten byte-range. Kayıt seçimi değişken + seviye +
  zaman metniyle: birikimde sürekli `0-N` kaydı, kategorik bayraklarda anlık kayıt.
- Yağış tipi dört kategorik bayraktan ECMWF ptype kodlarına çevrilir (donan yağmur > buz taneleri >
  kar+yağmur > kar > yağmur > yok); `extra.ptype_code` bu koddur. Kar miktarı yok (su eşdeğeri
  alanı yayımlanmıyor). Hamle anlık (`gust_definition = instant`).
- İlk canlı çalıştırma (2026-11-03 00z, Docker): 137 adım, 2.178 mesaj, 1,30 GB, 243 sn, 5.754
  satır; worker belleği en yüksek 0,35 GB, işlemci ortalaması tek çekirdeğin %36'sı.
- Görüş doğrulamasında METAR `9999` "≥ 10 km" demek (sansürlü); GFS üst sınırı ~24 km. Faz 5'te
  karşılaştırma bu eşikle yapılmalı.

## ECMWF AIFS Single özel notları (2026-11-03)
- IFS adaptörü "ürün" yapısıyla genelleştirildi (`ecmwf.Product`): yol, dosya bölünmesi, alanlar,
  birim çarpanları, adımlar ve hamle tanımı ürün başına. AIFS: tek dosya, 0–360 sa 6'şar, yağış
  kg m⁻² (çarpan 1), bulut % (çarpan 0,01), hamle ve yağış tipi yok.
- İlk çalıştırmalar: 321 mesaj, ~113 MB, 15–30 sn; 42 noktanın 41'i maskeli bilineer, 1 kıyı
  noktası en yakın kara hücresinden.

## DWD ICON / ICON-EU özel notları (2026-11-03)
- Kaynak opendata.dwd.de v1 şeması (eski şema 30.11.2026'da kapanıyor); yalnız native üçgen ızgara.
  Index yok: her dosya tek alan, bütünüyle iner (ICON ~3–4,8 MB, ICON-EU ~1 MB). DWD ~24 saat tutar.
- ICON-EU yalnız 00/06/12/18z (120 sa); 03/09/15/21z kısa çalıştırmalar (51 sa) şimdilik alınmıyor.
- Değişken eşlemesi ve birikim/hamle tanımları `docs/data-sources.md` §2.4 "Faz 3 bulguları"nda;
  konvektif = RAIN_CON + SNOW_CON, kar = SNOW_CON + SNOW_GSP, hamle son 1 sa (ICON global'de
  0. adımda yok), yağış tipi `WW`'den.
- Görüş yok (v1'de `VIS` yayımlanmıyor).
- İlk canlı çalıştırmalar (Docker, iki model aynı anda):

  | Çalıştırma | Model | Adım | Dosya | İndirme | Süre | Satır | Kırpılmış dosya |
  |---|---|---|---|---|---|---|---|
  | 2026-11-02 06z | ICON | 93 | 1.305 | 4,04 GB | 1.533 sn | 3.906 | 1,7 MB |
  | 2026-11-02 06z | ICON-EU | 93 | 1.306 | 1,05 GB | 1.477 sn | 3.906 | 6,7 MB |
  | 2026-11-02 12z | ICON | 109 | — | 4,76 GB | 369 sn | 4.578 | 2,0 MB |
  | 2026-11-02 12z | ICON-EU | 93 | — | 1,06 GB | 340 sn | 3.906 | 6,8 MB |

  Süreyi indirme belirliyor ve DWD hızı değişken (ilk turda toplam ~3,4 MB/sn, ikincide ~16 MB/sn);
  çözme alan başına ~58 ms, işlemci ortalaması tek çekirdeğin %10'u. Worker belleği en yüksek
  1,09 GB (iki ICON işi aynı anda). 6 saatlik çevrimde yeterli; sunucuda yeniden ölçülecek.

## Sonuçlar
- İndirme hacmi çalıştırma başına ~1,2–1,5 GB (IFS 0.1°), ~0,1 GB (AIFS), ~1,2 GB (GFS), ~4–4,7 GB
  (ICON; index olmadığından tüm küre), ~1 GB (ICON-EU) → günde ~33 GB. Ensemble'larda çok daha fazla olacak → ensemble'da
  adım/parametre sınırlaması ayrıca kararlaştırılacak.
- Kanonik ad ve birim sözleşmesi bozulursa tüm modeller etkilenir; testler (`tests/test_pipeline.py`)
  bu sözleşmeyi sabitler.
