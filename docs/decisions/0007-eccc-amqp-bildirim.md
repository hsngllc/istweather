# ADR-0007: ECCC GDPS — AMQPS bildirimleriyle indirme

- **Tarih:** 2026-11-03
- **Durum:** Kabul edildi (teknik karar; Faz 3)

## Bağlam
ECCC kullanım politikası ([usage-policy](https://eccc-msc.github.io/open-data/usage-policy/readme_en/),
2026-11-03'te yeniden okundu): "For systematic data retrieval, the AMQPS service must be used";
"Do not request directory listings to assess the availability of new data"; `wget`/`curl` yalnız ad
hoc alım için; günde 86.400 ve üzeri istek için iletişim; anlamlı User-Agent. Diğer modellerde
kullandığımız "10 dakikada bir yokla" yöntemi GDPS için politikaya aykırı. Dizin yolundaki tarih
yayın günü olduğundan yol da tahmin edilemez.

## Karar
- Worker içinde sürekli açık bir **AMQPS dinleyicisi** (`hava.ingest.models.gdps.Listener`, ayrı
  iş parçacığı, `pika`): `amqps://anonymous:anonymous@dd.weather.gc.ca:5671`, exchange `xpublic`,
  konu `v02.post.*.WXO-DD.model_gdps.15km.#` (2026-11-03'te bağlanıp mesaj alınarak doğrulandı).
  Mesaj gövdesi (v02): `<zaman> <taban adres> <göreli yol>`.
- Kuyruk kalıcı (`durable`) ve kuruluma özgü ad (`q_anonymous.istweather.gdps.<rastgele>`, ad
  `/data/grib/_gdps/queue_name`'de saklanır): worker yeniden başlarken mesajlar kuyrukta bekler; iki
  kurulum (PC ve sunucu) aynı kuyruğu paylaşmaz.
- Dinleyici yalnız istenen değişkenlerin dosya yollarını çalıştırma başına bir biriktirme dosyasına
  yazar (`/data/grib/_gdps/<YYYYMMDDTHHZ>.jsonl`). Toplayıcı (10 dk'lık iş) son adımın (168 sa)
  çekirdek alanları duyurulduğunda ve 15 dakika yeni duyuru gelmediğinde dosyaları **bildirimdeki
  adresten** indirir (4 eşzamanlı istek) ve ortak hatla işler. Dizin listelenmez, yol üretilmez.
- Çalıştırma başına ~1.250 istek (günde ~2.500) → politika sınırının çok altında.
- Kaçırılan çalıştırma (bildirim gelmeden kuyruğun süresi dolarsa) geri alınmaz; `model_runs`'ta
  yoktur ve tazelik takibi bayat bildirir.

## Alanlar (2026-11-03 tek seferlik ad hoc liste ve dosya başlıklarından)
`AirTemp_AGL-2m`, `DewPoint_AGL-2m`, `WindU/WindV_AGL-10m`, `WindGust_AGL-10m` (anlık `i10fg`),
`Pressure_MSL`, `TotalCloudCover_Sfc` (%; eccodes adı yok), `Precip-Accum_Sfc`,
`ConvectivePrecip-Accum_Sfc`, `Snow-Accum_Sfc` (başlangıçtan beri kg m⁻²; 0. adımda yağış dosyası
yok), `AirTemp_IsbL-0850`; sabitler 0. adımda `GeopotentialHeight_Sfc` (m) ve
`LandWaterProportion_Sfc` (0–1). `PrecipType-Instant_Sfc` yağış olmayan yerde de dolu (Sahra'da 6,
kuru hücrelerin %100'ünde > 0) → alınmaz. Görüş ve alçak bulut yok.

## Sonuçlar
- Yeni bağımlılık `pika`. Dinleyici çökerse yeniden bağlanır (artan bekleme); bağlantı durumu
  loglanır, model tazeliği ayrıca izlenir.
- İlk canlı çalıştırma yalnız bildirimle gelir: dinleyici açıldıktan sonraki ilk GDPS çalıştırması
  (00z 03:40–05:00, 12z 15:40–17:00 UTC). Geçmiş doldurulmaz.
