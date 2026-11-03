# NOAA GFS test verisi (gerçek örnekler)

| Dosya | Kaynak | Alındığı tarih |
|---|---|---|
| `gfs_20261103T00Z_f000.idx` | `https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.20261103/00/atmos/gfs.t00z.pgrb2.0p25.f000.idx` | 2026-11-03 |
| `gfs_20261103T00Z_f009.idx` | aynı çalıştırma, 9. saat (6 saatlik kova + 0-N birikim, anlık + ortalama bayraklar) | 2026-11-03 |
| `gfs_20261103T00Z_f123.idx` | aynı çalıştırma, 123. saat (120 sa sonrası 3 saatlik kova) | 2026-11-03 |

Yalnız index dosyaları (kayıt no, bayt offset'i, değişken, seviye, zaman); GRIB verisi yok.
Kaynak: NOAA Open Data Dissemination (NODD), NOAA/NCEP GFS.
