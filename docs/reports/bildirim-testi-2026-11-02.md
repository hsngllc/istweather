# Bildirim ve kaynak kapatma testi (Faz 2 kabulü)

- **Tarih:** 2026-11-02 · **Ortam:** yerel Docker Compose (canlı worker)
- **Kanallar:** Telegram (@weather_istanbulbot, proje sahibinin özel sohbeti) ve e-posta (Gmail SMTP)
- **Kabul kriteri (spec §15, Faz 2):** "bir kaynak kapatılınca bildirim geliyor"

## Yöntem
AWC adresi `.env`'de geçici olarak çözülemeyen bir alan adına (`aviationweather.invalid`) çevrildi ve
worker yeniden başlatıldı (`--no-deps`, veritabanına dokunmadan). Bildirim gelince adres geri alındı.

## Zaman çizelgesi (TSİ)

| Saat | Olay | Kaynak |
|---|---|---|
| 10:19 | "Deneme bildirimi" Telegram'a ve e-postaya gönderildi | proje sahibi ikisinin de geldiğini teyit etti |
| 10:19:41 | Son başarılı AWC isteği | `source_health.metar_awc` |
| 10:20 | Adres geçersiz yapıldı; `collect_metar` 5 dakikada bir `ConnectError` | worker logu |
| 10:30:03 | **"İş tekrar tekrar hata veriyor: collect_metar"** (3 kez üst üste) | `FailureWatch` |
| 10:52:00 | **"Veri kaynağı durdu: metar_awc"** — son başarılı istek 32 dk önce, son hata `ConnectError` | `check_sources` (eşik 30 dk) |
| 10:52 | Adres geri alındı; ilk toplama 15 rapor yazdı (kesintide kaçan 07:20Z dahil) | worker logu |
| 10:57:00 | **"Veri kaynağı düzeldi: metar_awc"** | `check_sources` |

Proje sahibi bildirimlerin Telegram'a ve e-postaya ulaştığını teyit etti.

## Sonuç
- Kaynak durunca ve düzelince bildirim geliyor; tekrarlayan iş hataları da bildiriliyor.
- Veri boşluğu yok: toplayıcı her seferinde son 3 saati çektiği için kesintide kaçan METAR'lar
  (LTFM, LTFJ, LTBA 07:20Z) adres geri gelince AWC'den tamamlandı.
- İstasyon tazeliği (`metar:<ICAO>`, eşik 90 dk) test süresince bozulmadı; kesinti eşiğin altındaydı.

## Bilinen sınır
"İş düzeldi" bildirimi gelmedi: ayar değişikliği için worker yeniden başlatıldı ve ardışık hata
sayacı bellekte tutulduğu için sıfırlandı. Gerçek bir kesintide worker yeniden başlamadığından bu
bildirim de gider (birim testi: `tests/test_notify.py::test_failure_watch_notifies_at_threshold_and_on_recovery`).
"Veri kaynağı düzeldi" durumu veritabanında tuttuğu için yeniden başlatmadan etkilenmedi.
