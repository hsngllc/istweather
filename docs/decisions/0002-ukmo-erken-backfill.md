# ADR-0002: UKMO geçmişinin erken ve stencil tabanlı çıkarımı

- **Tarih:** 2026-11-01
- **Durum:** Kabul edildi (çıkarımı erken başlatma proje sahibinin kararı; biçim teknik karar)

## Bağlam
UKMO Global 10 km arşivi AWS'te 2 yıllık kayan penceredir; her gün en eski gün silinir (Faz 0'da en
eski çalıştırma 2024-10-30T18Z). Lisans CC BY-SA 4.0; blend'e dahil edilmesi henüz kararlaştırılmadı.
Deterministik üründe kara-deniz maskesi yok, orografi yalnız 2025-12-12'den beri var. Spec §6 kıyı
noktalarında kara-deniz maskeli seçim ve sıcaklıkta lapse-rate düzeltmesi istiyor.

## Karar
- Nokta çıkarımı Faz 4'ü beklemeden, en eski çalıştırmadan başlar; yalnız iç doğrulama içindir.
- Her dosyadan (parametre × adım) tüm noktaların 4×4 komşuluğunu kapsayan en küçük kutu HTTP Range ile
  okunur (dosya başına ~65 KB, ~8 istek). Nokta başına 16 hücre (stencil), en yakın hücre ve maskesiz
  bilineer değer Parquet'e yazılır; stencil hücrelerinin koordinatları ve ağırlıkları ayrı dosyada.
- Açısal parametrede (rüzgâr yönü) bilineer değer yazılmaz; u/v yükleme sırasında hücre başına
  hesaplanıp birleştirilir.
- Veritabanına yükleme `extraction="bilinear_unmasked"` etiketiyle yapılır; maskeli seçim ve lapse-rate
  düzeltmesi Faz 3 processing'de stencil'den yeniden hesaplanıp üzerine yazılır.
- h5py global bir kilit kullandığı için paralellik süreç havuzuyla sağlanır.

## Sonuçlar
- Kayan pencereden veri kaybı durur; işlem hızı (~45 dosya/sn) silinme hızının çok üstünde.
- Toplam indirme ~280 GB, çıktı birkaç GB.
- Yeni nokta eklenirse eski çalıştırmalar için yeniden indirme gerekir (kutunun tamamı saklanmıyor).
