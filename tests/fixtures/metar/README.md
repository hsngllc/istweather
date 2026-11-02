# METAR test verisi (gerçek örnekler)

Bu klasördeki dosyalar **gerçek** METAR yanıtlarıdır; testlerde ayrıştırıcı ve toplayıcıları doğrulamak
için kullanılır. Üretimde kullanılmaz.

| Dosya | Kaynak | Alındığı tarih | İçerik |
|---|---|---|---|
| `awc_metar_2026-11-02.json` | AWC Data API, `GET /api/data/metar?ids=LTFM,LTFJ,LTBA&format=json&hours=6` | 2026-11-02 05:30 UTC | Ham JSON yanıtı (33 kayıt) |
| `iem_2025_cases.csv` | IEM ASOS/METAR arşivi (`asos.py`, `data=metar`, 2025 yılı) | 2026-11-02 | Her zor durum için seçilmiş birer satır (`case` sütunu) |

Lisans: AWC verisi ABD kamu malı (NOAA/NWS onayı ima edilmez); IEM verisi kamu malı. Türkiye kaynaklı
METAR'ların ticari yeniden dağıtım durumu belirsiz olduğundan ürün ham METAR'ı yeniden dağıtmaz
(spec §11). Bu küçük örneklerin yalnız test amacıyla herkese açık depoda tutulması proje sahibinin
kararıdır (2026-11-02).

Not: `iem_2025_cases.csv`'de bazı desenler yalnız trend veya RMK bölümünde geçer (ör. `vrb_wind`,
`gust_variable_dir`, `calm`, `vertical_visibility`); testler bu bölümlerin gövde gibi okunmadığını da
doğrular.
