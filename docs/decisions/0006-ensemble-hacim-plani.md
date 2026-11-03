# ADR-0006: Ensemble ingest — hacim planı

- **Tarih:** 2026-11-03
- **Durum:** Kabul edildi — proje sahibi seçenek B'yi seçti (2026-11-03)

## Bağlam
Spec §5.1 ensemble'ları (IFS ENS, AIFS ENS, GEFS, ICON-EPS/ICON-EU-EPS), §7 `ensemble_stats` tablosunu
ve ham üyelerin Parquet'te saklanmasını, §9 EMOS (sıcaklık, rüzgâr) ve yağış olasılığı (PoP)
kalibrasyonunu istiyor. GRIB mesajları alan olarak bölünemez: İstanbul için bile her üyenin her
alanının tüm küresi (ICON'da tüm alanı) iner. ECMWF dosyalarında mesajlar karışık sırada, seçilen
mesajlar bitişik değil (300 mesaj → 262 ayrı aralık) → istek birleştirme fayda etmiyor.

## Ölçümler (gerçek index/dosyalardan, 2026-11-02 18z ve 2026-11-03 00z, 24. saat)

Temel alanlar: 2 m sıcaklık, yağış, 10 m rüzgâr (u, v), hamle, kar su eşdeğeri (varsa).

| Model | Üye | Çözünürlük | Temel alanlar, üye başına MB | Üye × adım | Adım (tüm üyeler) | Yayınlanan adımlar |
|---|---|---|---|---|---|---|
| IFS ENS | 50 pf | 0.25° | `2t` 0,32 · `tp` 0,38 · `sf` 0,16 · `10u/10v` 0,73+0,73 · `10fg` 0,66 | 2,98 MB | 149 MB | 0–144 sa 3'er, 150–360 sa 6'şar (06/18z 144 sa) |
| AIFS ENS | cf + 50 pf | 0.25° | `2t` 0,29 · `tp` 0,44 · `sf` 0,16 · `10u/10v` 0,69+0,70 · hamle yok | 2,28 MB | 116 MB | 0–360 sa 6'şar |
| GEFS | 31 | 0.25° (`pgrb2s`) | `TMP` 0,76 · `APCP` 0,27 · `UGRD/VGRD` 0,83+0,82 · `GUST` 0,54 · kar miktarı yok | 3,22 MB | 100 MB | 0–240 sa 3'er; `APCP` yalnız 6 saatlik kova |
| ICON-EU-EPS | 40 | ~10 km (#63) | `T_2M` 0,46 · `TOT_PREC` 0,28 · `U/V_10M` 0,51+0,51 · `VMAX_10M` 0,50 · `SNOW_GSP/CON` ~0,08 | 2,34 MB | 94 MB | 0–75 sa saatlik, 78–120 sa 3'er |
| ICON-EPS | 40 | ~20 km (#39) | `T_2M` 1,55 · `TOT_PREC` 0,93 · `U/V_10M` 1,80+1,81 · `VMAX_10M` 1,89 · kar yok | 7,98 MB | 319 MB | 0–75 sa saatlik, 78–180 sa 3'er |

Diğer bulgular: IFS ENS 0.1° adım başına 1,4 GB (aynı alanlar) → kullanılmaz. ICON-EU-EPS #63 alanı
24,8–71,7°K / −25,5–64,1°D, 342.428 hücre; kırpmada 1.224 hücre (İstanbul kapsanıyor ✅). ICON-EPS'te
MSLP yok, ICON-EU-EPS'te çiy noktası yok (envanter §2.8).

## Seçenekler (≤168 sa)

| | A — en az | **B — dengeli (öneri)** | C — geniş |
|---|---|---|---|
| Modeller | IFS ENS, AIFS ENS | IFS ENS, AIFS ENS, GEFS, ICON-EU-EPS | B + ICON-EPS |
| Çalıştırmalar | 00 ve 12z | 00 ve 12z | 00/06/12/18z |
| Adımlar | 6 saatlik | 0–72 sa 3 saatlik, 78–168 sa 6 saatlik | B ile aynı |
| Döngü başına indirme | ~7,7 GB | ~16,7 GB | ~30 GB (00/12z), ~23 GB (06/18z) |
| Günlük indirme (ensemble) | ~15 GB | ~33 GB | ~105 GB |
| Döngü başına istek | ~16 bin | ~37 bin | ~45 bin (00/12z) |
| Tahmini süre (5–13 MB/sn) | 10–25 dk | 20–55 dk | 40–100 dk |

Döngü başına B: IFS ENS 149 MB × 41 adım = 6,1 GB; AIFS ENS 116 × 29 = 3,4 GB; GEFS 100 × 41 =
4,1 GB; ICON-EU-EPS 94 × 33 = 3,1 GB. C'de ICON-EPS 00/12z 319 MB × 41 = 13,1 GB, 06/18z (yalnız
6 saatlik, 120 sa) 319 × 21 = 6,7 GB; IFS ENS 06/18z 144 saatte bitiyor (37 adım, 5,5 GB).

## Karar (B)
- **Modeller:** IFS ENS 0.25°, AIFS ENS, GEFS 0.25°, ICON-EU-EPS. ICON-EPS (global) şimdilik yok:
  adım başına 319 MB ve 0–120 saatte ICON-EU-EPS ile aynı model ailesi; gerekirse yalnız 126–168 sa
  için eklenir (~2,6 GB/döngü).
- **Çalıştırmalar:** 00 ve 12z (ensemble'larda yaygın uygulama; IFS ENS 06/18z zaten 144 saatte
  bitiyor).
- **Değişkenler:** 2 m sıcaklık (üye başına yükseklik düzeltmeli), yağış, 10 m rüzgâr (u, v → hız),
  hamle (IFS, GEFS, ICON-EU-EPS), kar su eşdeğeri (IFS, AIFS, ICON-EU-EPS). Çiy noktası, basınç ve
  bulut ensemble'dan alınmaz (deterministik modellerde var).
- **Adımlar:** 0–72 sa 3 saatlik (saatlik ürünün belirsizlik bandı için), 78–168 sa 6 saatlik (günlük
  ürün için). AIFS ENS yalnız 6 saatlik, ICON-EU-EPS 120 saate kadar.
- **Kayıt:**
  - Ham üye nokta değerleri Parquet: `/data/parquet/ensemble/<model>/<init>.parquet` (nokta × adım ×
    üye × değişken). Döngü başına ~7 MB, yılda ~5 GB (zstd; ilk ölçümle düzeltildi, önce ~2 GB
    tahmin edilmişti) → **süresiz** saklanır; EMOS ve eşikler sonradan yeniden hesaplanabilir.
  - `ensemble_stats`: değişken başına `n_members`, ortalama, std, p10/p25/p50/p75/p90, `exceed_probs`.
    Döngü başına ~27 bin satır (yılda ~20 milyon, TimescaleDB sıkıştırmasıyla 1–2 GB).
  - Kırpılmış alanlar 30 gün (çalıştırma başına 6–45 MB; toplam ~5 GB).
- **`exceed_probs` başlangıç eşikleri** (ham üye oranı, kalibre değil): yağış ≥ 0,1 / 1 / 5 / 10 / 20 mm
  (adım aralığında), hamle ≥ 15 / 20 / 25 m/s, sıcaklık ≤ 0 °C, kar ≥ 0,5 mm. Uyarı eşikleri ayrıca
  `docs/alerts.md`'de onaya sunulacak (spec §10).
- **Uygulama:** mevcut hat (indirme, kırpma, maskeli nokta çıkarımı) üye boyutuyla genişletilir;
  her model ayrı iş, `model_runs` durumu aynı; istatistikler ham Parquet'ten üretilir.

## Uygulama notları (2026-11-03)
- Ortak hat `hava.ingest.models.ensemble`: `EnsembleCollector` (üye × adım × alan, deterministikle aynı
  kırpma), `extract_members` (aynı maskeli ağırlıklar, `PointWeights.interpolate_many`), `member_stats`
  (std n−1; yüzdelikler doğrusal), `write_members` (Parquet, zstd), `write_crop` (NetCDF, `member`
  boyutu). Çalıştırma yönetimi `runner.process_ensemble_run`; `model_runs.files`'ta `members_file`,
  `extraction`, üye sayısı.
- `ensemble_stats`'a `extraction` ve `extra` sütunları eklendi (migration 0002): yağış/kar aralığı
  `extra.period_h`, hamle tanımı `extra.gust_definition`.
- IFS ENS açık verisinde orografi yok → sıcaklık yükseklik düzeltmesiz (`extraction = bilinear_lsm`);
  noktaya özgü sapmayı kalibrasyon giderir. Diğerleri `…_lsm_lapse`.
- GEFS kara maskesi aynı 0,25° ızgaradaki GFS `LAND`'dan; yağış 6 saatlik kovalardan başlangıçtan beri
  toplama çevrilir (kova başı 6'nın katı ve adım planında).
- Adımlar ortak plan ∩ yayımlanan adımlar (AIFS ENS yalnız 6 saatlik → 29 adım).
- Worker'da model işleri ayrı iş parçacığı havuzunda (`models`): uzun indirmeler kalp atışını ve METAR
  işini bekletmez.

## İlk canlı ölçümler (2026-11-03, Docker, dört ensemble ve deterministik modeller aynı anda)

| Model | Çalıştırma | Üye | Adım | Mesaj | İndirme | Süre | `ensemble_stats` | Parquet | Kırpılmış |
|---|---|---|---|---|---|---|---|---|---|
| IFS ENS | 02 00z / 12z | 50 | 41 | 12.251 | 6,18 / 6,13 GB | 411 / 409 sn | 8.484 | 2,6 MB | 5,3 MB |
| AIFS ENS | 03 00z | 51 | 29 | 7.399 | 3,43 GB | 300 sn | 4.788 | 1,4 MB | 2,7 MB |
| GEFS | 03 00z | 31 | 41 | 6.326 | 4,08 GB | 556 sn | 6.846 | 1,4 MB | 4,2 MB |
| ICON-EU-EPS | 02 12z / 03 00z | 40 | 33 | 9.204 | 3,06 / 3,10 GB | 255 / 213 sn | 6.804 | 1,7 MB | 21,9 MB |

- Döngü başına indirme 16,7 GB (tahminle aynı), ~27 bin istatistik satırı.
- Worker belleği en yüksek 1,39 GB (ortalama 1,18), işlemci ortalaması ~1,9 çekirdek (ilk dolum, dokuz
  model işi birlikte).
- İlk hata: hamlesiz modelde (AIFS ENS) Parquet'in boş sözlük sütunu yazılamadı
  (`ArrowNotImplementedError`); sütun türü açıkça `string` yapıldı, test eklendi, ikinci denemede yüklendi.
- Sağlama (03 00z ve 02 çalıştırmaları, METAR, küçük örnek — doğrulama değil): sıcaklıkta ensemble
  ortalamasının hatası 0,5–1,3 °C; gözlemin p10–p90 içine düşme oranı %21–67 (kalibre ensemble'da ~%80)
  → kısa vadede yayılım dar, kalibrasyon (Faz 6) gerekli. IFS ENS bu istasyonlarda ~1,2 °C soğuk
  (yükseklik düzeltmesi yok).

## Sonuçlar
- Deterministik (~33 GB/gün) + ensemble B (~33 GB/gün) ≈ **66 GB/gün, ayda ~2 TB gelen trafik**. VPS
  seçiminde gelen trafiğin ücretsiz/sınırsız olduğu doğrulanmalı.
- ECMWF portalı ve DWD için belgelenmiş istek sınırı yok (❓); model başına 8 eşzamanlı bağlantıyla
  başlanır, hata/yavaşlık izlenir.
- Faz 3 kabulü (3 gün eksiksiz çalıştırma) ensemble'lar için de VPS'te yapılır.
