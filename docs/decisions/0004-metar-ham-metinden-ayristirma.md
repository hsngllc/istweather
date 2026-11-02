# ADR-0004: METAR değerleri ham metinden, tek ayrıştırıcıyla

- **Tarih:** 2026-11-02
- **Durum:** Kabul edildi (teknik karar)

## Bağlam
Canlı doğrulama AWC'den, geçmiş doğrulama IEM'den gelir (spec §5.3). İki kaynak da METAR'ı kendi
biçimine çevirir ve bu sırada bilgi kaybolur ya da değer uydurulur:

- AWC görüşü statute mile çevirir (4100 m → 2,55; 9999 → "6+"), boş alanları JSON'dan tamamen düşürür.
- IEM sıcaklığı °F'ye çevirir (6 °C → 42,8 °F), ölçülemeyen görüşü (`////`) 10 km yazar, Türk
  METAR'larında olmayan yağışı `p01i=0.00` diye doldurur ve `RESHRA`'yı (son bir saatte sağanak) şu
  anki hadise sayar.

Canlı ve geçmiş gözlemin aynı ölçütle karşılaştırılabilmesi ve değer uydurulmaması (spec §2) gerekir.

## Karar
- İki kaynakta da yalnız **ham METAR metni** ve **gözlem zamanı** alınır (AWC `rawOb` + `obsTime`,
  IEM `metar` + `valid`). Değerler `hava.ingest.obs.metar` ayrıştırıcısıyla çözülür.
- Yalnız gövde okunur; trend (NOSIG/BECMG/TEMPO) ve RMK alınmaz. Tanınmayan grup `unparsed`'a düşer,
  değer üretilmez. Ölçülemeyen değer (`////`, `//`, `/////KT`) boş kalır.
- `pressure_hpa` QNH'dir (MSLP değil); `raw.pressure_kind = "qnh"`.
- `cloud_cover_pct` bildirilen en yoğun katmanın okta orta noktasıdır (FEW 18,75 … OVC 100; VV 100).
  NSC/NCD/CAVOK 1500 m üstünü söylemediği için boş kalır; SKC/CLR 0'dır.
- Bağıl nem T/Td'den Magnus formülüyle (Alduchov & Eskridge 1996) türetilir.
- Ham METAR `raw.metar`'da saklanır; yeniden dağıtılmaz (spec §11).

## Doğrulama
2025 yılının üç istasyondaki 52.844 IEM METAR'ı ayrıştırıldı: başlık hatası 0, tanınmayan grup 0.
IEM'in kendi çözümüyle karşılaştırmada sıcaklık, çiy noktası, rüzgâr, hamle, görüş ve QNH'de fark
yok; tek fark IEM'in `RESHRA`'yı hadise sayması (2 kayıt). AWC örneğindeki 33 kaydın tamamında
değerler AWC'nin çözümüyle aynı.

## Sonuçlar
- Ayrıştırıcının bakımı bizde; Türk METAR'larında görülmeyen biçimler (SM görüş, inHg) yalnız temel
  düzeyde destekleniyor ve sentetik testlerle sınanıyor.
- Ayrıştırıcı değişirse `PARSER_VERSION` artırılır; geçmiş satırlar `raw.metar`'dan yeniden üretilebilir.
