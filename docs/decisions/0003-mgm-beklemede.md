# ADR-0003: MGM doğrudan kullanımının iptali

- **Tarih:** 2026-11-01
- **Durum:** Kabul edildi (proje sahibi kararı)

## Bağlam
Spec, MGM "Son Durumlar" verisinin doğrudan kullanılmasını öngörüyordu. Faz 0'da `servis.mgm.gov.tr`'nin
MGM sitesi dışından gelen istekleri bilerek reddettiği ("Not allowed by MGM") ve mgm.gov.tr kullanım
şartlarının izinsiz yeniden yayımlamayı yasakladığı tespit edildi. Doğrudan kullanım bir erişim
kısıtını aşmayı gerektiriyordu.

## Karar
- Doğrudan kullanım iptal. `servis.mgm.gov.tr`'ye istek gönderilmez; erişim kısıtını aşan kod yazılmaz.
- MGM verisi yalnız MGM'nin yazılı izni veya MEVBİS lisansıyla gelirse eklenir; o zamana kadar kaynak
  "beklemede". Adaptör varsayılan kapalıdır (`HAVA_MGM_ENABLED=false`).
- Doğrulama: canlı METAR (AWC), geçmiş IEM. İlçe referans istasyon eşleştirmesi askıda; tüm ilçeler
  "doğrudan doğrulanmamış" sayılır.

## Sonuçlar
- İlçe ölçeğinde doğrulama 3 havalimanı istasyonuyla sınırlı; doğruluk iddiaları buna göre belirtilir.
- Hamle doğrulaması yalnız METAR'la yapılır.
