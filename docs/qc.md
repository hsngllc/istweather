# Gözlem kalite kontrolü (QC)

Kod: `src/hava/qc/observations.py` · Sürüm: `qc-1` · Spec §5.3, §13

## İlke
- Hatalı değer **silinmez**, `observations.qc_flags`'e işaretlenir:
  `{"version": "qc-1", "temp_c": ["spike"], "_record": ["time_mismatch"]}`.
- `_record` tüm satırı etkiler. Doğrulama ve eğitimde yalnız `passed(qc_flags, değişken)` olan
  değerler kullanılır.
- QC her canlı toplamadan sonra son saatlere, geçmiş yüklemeden sonra tüm aralığa yeniden uygulanır;
  değişmeyen bayrak yeniden yazılmaz.

## Kurallar ve eşikler

İstasyonlar: LTFM, LTFJ, LTBA (deniz seviyesine yakın, 33–99 m; birbirine 15–50 km). METAR sıcaklık
ve çiy noktası tam sayı °C, QNH tam sayı hPa'dır.

| Kural | Değişken | Eşik | Gerekçe |
|---|---|---|---|
| `range` | temp_c | −30 … 48 °C | İstanbul rekorlarının (≈ −16 / +41 °C) epey dışı; yalnız açık hata |
| | dewpoint_c | −40 … 32 °C | |
| | rh_pct | 0 … 100 % | |
| | pressure_hpa | 950 … 1055 hPa | Bölgedeki uç değerlerin (≈ 975 / 1048) dışı |
| | wind_speed_ms | 0 … 50 m/s | |
| | wind_gust_ms | 0 … 70 m/s | |
| | visibility_m | 0 … 10000 m | METAR 9999 = "≥ 10 km" → 10000 |
| `dewpoint_gt_temp` | dewpoint_c | Td > T | Fiziksel olarak imkânsız (tam sayı yuvarlamada eşitlik serbest) |
| `gust_lt_speed` | wind_gust_ms | hamle < ortalama | Kodlama hatası |
| `spike` | temp_c / dewpoint_c / pressure_hpa | 6 °C / 8 °C / 3 hPa | Değer iki komşusundan (≤ 75 dk) aynı yönde eşikten fazla sapıyor, komşular birbirine eşiğin yarısından yakın |
| `step` | temp_c / dewpoint_c / pressure_hpa | 10 °C / 12 °C / 5 hPa | ≤ 35 dakikada bu kadar değişim (son sıçrama olmayan değere göre) |
| `flatline` | temp_c / dewpoint_c / pressure_hpa | ≥ 24 saat aynı değer **ve** bir komşu aynı sürede ≥ 3 birim değişmiş; komşu verisi yoksa ≥ 48 saat | Takılı sensör; 75 dakikadan uzun boşluk seriyi böler |
| `neighbor` | temp_c / dewpoint_c / pressure_hpa | sapma 13 °C / 14 °C / 5 hPa; diğer ikisinin farkı ≤ 4 °C / 5 °C / 2 hPa | Diğer iki istasyon (±10 dk) kendi aralarında uyuşuyor, bu istasyon uyuşmuyorsa. Yalnız iki istasyon varsa karar verilmez |
| `time_mismatch` | `_record` | METAR zaman grubu ≠ kaynağın gözlem zamanı | Yanlış eşleşmiş kayıt |

### Eşiklerin veriyle ayarlanması (2026-11-02)

İlk taslak (`flatline` ≥ 18 sa, sıcaklık komşu sapması 10 °C) 2024-01 → 2026-11 arasındaki 149.820 IEM
METAR'ında denendi ve gerçek havayı ayıkladığı görüldü:

- **`flatline`:** 18 saat eşiği 14 sıcaklık, 19 çiy noktası, 29 basınç serisini işaretledi; incelenen
  örneklerin hepsi gerçek (poyrazda yağmur, durgun yüksek basınç). En uzun seri LTBA 2026-03-21'de
  34 saat 9 °C idi ve gerçek: yağmur/çisenti sürerken LTFJ 8–9 °C, LTFM 7–8 °C. METAR tam sayı
  olduğu için süre tek başına ölçüt olamaz → komşu değişimi şartı eklendi.
- **`neighbor`, sıcaklık/çiy noktası:** Üç yılda gözlenen en büyük sapmalar 12 °C ve 13,5 °C;
  örnekler gerçek (LTFM'de Karadeniz sisi sürerken şehir 17 °C; 2024-11-23 soğuk cephesi: kuzey
  9 °C, LTFJ 21 °C). Eşik bunların üstüne çekildi; kural yalnız kaba hatayı yakalar. İşaret hatası
  (`M` eksik) gibi hatalar zaten `spike`'a takılır.
- **`neighbor`, basınç:** Diğer ikisi uyuşurken 12 hPa'dan büyük sapmaların tamamı (17) LTBA
  2024-01-07 12:50–14:50: QNH 1023 iken LTFM/LTFJ 1001–1004 → yazım hatası; kural doğru çalışıyor.

Canlı QC son ≈4 saati yeniden hesaplar; 24 saati aşan bir `flatline` serisinin eski satırları gece
IEM boşluk doldurma işinin 3 günlük QC'sinde işaretlenir.

## Rapor
```
docker compose run --rm --no-deps worker python -m hava.qc.report --since 2024-01-01 --out /tmp/qc.md
```
İçerik: istasyon başına tamlık (30 dakikalık rutin gözleme göre), en uzun boşluk, > 2 saatlik boşluk
sayısı, değişken bazında dolu / QC'den geçen oranı, kural × değişken işaret sayıları, örnek işaretli
kayıtlar (ham METAR ile).
