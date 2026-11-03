# ECMWF test verisi (gerçek örnekler)

| Dosya | Kaynak | Alındığı tarih |
|---|---|---|
| `ifs0p1_20261102T06Z_0h_sfc.index` | `https://data.ecmwf.int/forecasts/20261102/06z/ifs/0p1/oper/20261102060000-0h-oper-fc-sfc.index` | 2026-11-02 |
| `ifs0p1_20261102T06Z_96h_sfc.index` | aynı çalıştırma, 96. saat (`10fg3` içerir) | 2026-11-02 |
| `ifs0p1_20261102T06Z_6h_pl.index` | aynı çalıştırma, 6. saat basınç seviyeleri | 2026-11-02 |
| `aifs0p25_20261102T18Z_0h.index` | `https://data.ecmwf.int/forecasts/20261102/18z/aifs-single/0p25/oper/20261102180000-0h-oper-fc.index` (yüzey + basınç seviyesi tek dosyada) | 2026-11-03 |
| `aifs0p25_20261102T18Z_6h.index` | aynı çalıştırma, 6. saat | 2026-11-03 |
| `ifsens0p25_20261102T18Z_0h_ef_m1-2.index` | `…/20261102/18z/ifs/0p25/enfo/20261102180000-0h-enfo-ef.index` — **kısaltılmış**: yalnız 1. ve 2. üyenin seçili yüzey satırları (gerçek satırlar, değiştirilmeden) | 2026-11-03 |
| `ifsens0p25_20261102T18Z_96h_ef_m1-2.index` | aynı çalıştırma, 96. saat (`10fg3`), aynı kısaltma | 2026-11-03 |
| `aifsens0p25_20261102T18Z_0h_cf.index` | `…/20261102/18z/aifs-ens/0p25/enfo/20261102180000-0h-enfo-cf.index`, seçili yüzey satırları (kontrol üyesi, `number` yok) | 2026-11-03 |

Yalnız index dosyaları (JSON satırları: parametre, seviye, bayt aralığı); GRIB verisi yok.
Lisans: ECMWF açık verisi, CC BY 4.0 — "This service is based on data and products of the
European Centre for Medium-Range Weather Forecasts (ECMWF)."
