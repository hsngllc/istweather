# İstanbul Çok Modelli Hava Tahmini — Backend Spesifikasyonu

> Bu dosya Claude Code'a projeyi başlatmak için verilir. Kararların hepsi proje sahibiyle (Hasan) birlikte alındı. "Teyit et" denen her şey, kullanılmadan önce birincil kaynaktan doğrulanmalıdır.

> **Güncelleme 2026-11-01 (Faz 0 kararları):** MGM doğrudan kullanımı iptal edildi, MGM resmî veri gelene kadar "beklemede" (§5.3, §11, §16). Gözlem: canlı METAR (AWC), geçmiş IEM (§5.3). İlçe referans istasyon eşleştirmesi askıda; kıyı noktaları değişmez (§6). UKMO geçmiş nokta çıkarımı Faz 4'ü beklemeden başlatıldı, yalnız iç doğrulama (§5.2). ARPEGE canlı açık verisi Licence Ouverte 2.0 (ticari serbest), "yetersiz geçmiş" ile kalır (§5.1). Repo `C:\istweather`'da kalır, veriler Docker named volume'larda (§4). Ayrıntılı kaynak envanteri: `docs/data-sources.md`.

## 1. Proje özeti

İstanbul'un 39 ilçesi için 7 günlük, yüksek doğruluklu bir hava tahmini sitesinin **backend'i**. Sistem şu adımları izler:

1. Birçok sayısal hava tahmin modelinin (ECMWF, NOAA, DWD, Météo-France, UK Met Office, Kanada) **ham verisini** doğrudan indirir.
2. Gerçek istasyon gözlemleriyle her modelin her ilçedeki hatasını ölçer.
3. Hataları düzeltip modelleri ağırlıklandırarak tek bir **birleşik tahmin** üretir.
4. Tahmini belirsizlik aralığıyla birlikte sunar.
5. Tehlikeli hava uyarıları üretir.

İleride kapsam Türkiye geneline genişleyecek. Mimari buna izin verecek şekilde kurulmalı: bölge, nokta listesi ve model kapsamı konfigürasyondan gelmeli, kodda sabitlenmemeli.

Gelir modeli: **sadece reklam**. Kullanıcı hesabı yok. Site ticari olduğu için her veri kaynağının lisansı ticari kullanıma uygun olmalı (bkz. §11).

## 2. Temel kurallar (her fazda geçerli)

- **Veri uydurma yok.** Üretim kodunda sahte, örnek ya da "fallback" veri kullanılmaz. Bir kaynak çökerse veri "bayat" (stale) olarak işaretlenir, admin bildirimi gider ve sitede bu belirtilir. Sessizce başka bir değer gösterilmez.
- **Test verisi etiketli.** Testlerde kullanılan fixture'lar `tests/fixtures/` altında durur ve açıkça örnek olarak adlandırılır. Üretim yoluna asla sızmaz.
- **"Yüksek doğruluk" ölçülerek iddia edilir.** Birleşik tahmin, ayrılmış (held-out) bir dönemde en iyi tek modeli ve basit baz çizgilerini yenmiyorsa bu açıkça raporlanır.
- **Her tahmin değeri izlenebilir.** Hangi modelin hangi çalıştırmasından (init time) geldiği, hangi blend sürümüyle üretildiği kayıtlıdır.
- **Fazlar sırayla yapılır.** Her fazın sonunda kabul kriterleri gösterilir ve bir sonraki faza geçmeden proje sahibine özet sunulur.
- **Doğrulanmamış bilgiye dayanma.** URL'ler, model kodları, dosya adlandırma kuralları ve arşiv başlangıç tarihleri sık değişir. Kod yazmadan önce birincil kaynaktan kontrol et ve `docs/data-sources.md`'ye kaynağıyla birlikte yaz.

## 3. Kararlar (özet tablo)

| Konu | Karar |
|---|---|
| Kapsam (v1) | İstanbul'un 39 ilçesi |
| Tahmin ufku | 7 gün: 0–72 saat saatlik, 4–7. günler günlük (değer + aralık) |
| Değişkenler | Sıcaklık + hissedilen; yağış + kar; rüzgâr + hamle (lodos/poyraz); nem, bulut, sis/görüş |
| Model verisi | Ham veri, doğrudan resmi/açık kaynaklardan (GRIB2) |
| Modeller | ECMWF IFS + AIFS (+ENS), NOAA GFS + GEFS, DWD ICON + ICON-EU (+EPS), Météo-France ARPEGE, UK Met Office, Kanada GEM |
| Geçmiş veri | Ocak 2024'ten beri, hibrit: topluluk/bulut arşivleri + bugünden itibaren kendi arşivimiz |
| Gözlem | Canlı: METAR (AWC). Geçmiş: IEM METAR arşivi. MGM: doğrudan kullanım iptal; yazılı izin veya MEVBİS lisansıyla gelecek resmî veri için beklemede. WMO WIS2 SYNOP: Türkiye yayını yok (Faz 0) |
| Birleştirme | Aşamalı: bias düzeltme + hataya göre ağırlık → ensemble kalibrasyonu → (sonra) ML |
| Güncelleme | Olay tetiklemeli: yeni model çalıştırması yayınlandıkça; gözlemler sık aralıklarla |
| Dil / çatı | Python 3.12+, FastAPI |
| Veritabanı | PostgreSQL + TimescaleDB |
| Paketleme | Docker Compose |
| Geliştirme | Windows PC + Docker Desktop (WSL2 backend); repo `C:\istweather`'da, veriler Docker named volume'larda, kod GitHub'da |
| Sunucu | Kiralık VPS (sağlayıcı henüz seçilmedi) |
| API | Sadece kendi sitemiz için, sürümlü (`/api/v1`), ileride dışa açılabilir |
| Hesap/abonelik | Yok (sadece reklam) |
| Uyarılar | Backend üretir, sitede gösterilir, "resmi MGM uyarısı değildir" etiketiyle |
| Admin | Şifreli, basit dahili doğruluk paneli |
| Test/CI | pytest + ruff + mypy, GitHub Actions |
| İşletme | Veri akışı durursa Telegram/e-posta bildirimi; veritabanının günlük yedeği sunucu dışına |
| Kod dili | Kod (değişken, fonksiyon, tablo adları) İngilizce; README, dokümanlar ve açıklamalar Türkçe |

## 4. Mimari

```
                ┌──────────────────────────── worker ────────────────────────────┐
 Model kaynakları│ run-poller → downloader → cropper → point-extractor → loader  │
 (ECMWF, NOAA,   │                                                                │
  DWD, MF, UKMO, │ obs-collectors (METAR, MGM, WIS2) → QC → loader                │
  ECCC)          │                                                                │
                 │ verifier → bias/weights trainer → blender → alert-engine       │
                 │                                   └→ published_forecasts       │
                 └────────────────────────────┬───────────────────────────────────┘
                                              │
                                   PostgreSQL + TimescaleDB
                                              │
                 ┌────────────── api (FastAPI) ┴──────────────┐
                 │ /api/v1/...  (sitenin okuduğu)              │
                 │ /admin       (doğruluk paneli, şifreli)      │
                 └──────────────────────────────────────────────┘
                                              │
                                    Caddy (HTTPS, prod)
```

**Docker Compose servisleri:**
- `db`: TimescaleDB (PostgreSQL 16+)
- `api`: FastAPI + uvicorn
- `worker`: zamanlayıcı ve iş hattı
- `caddy`: yalnızca prod, otomatik HTTPS
- `backup`: günlük `pg_dump` + sunucu dışına gönderim (restic veya rclone)

**Zamanlayıcı:** v1 için `worker` içinde APScheduler yeterli. İşlerin tekrar çalıştırılması güvenli (idempotent) olmalı. Her model çalıştırmasının durumu `model_runs` tablosunda tutulur (`pending` / `downloading` / `extracted` / `loaded` / `failed`). Yarıda kalan iş yeniden başlatılınca kaldığı yerden devam eder. Redis veya kuyruk sistemi ancak ihtiyaç kanıtlanırsa eklenir.

**API performansı:** API hesap yapmaz. Worker, son birleşik tahmini `published_forecasts` tablosuna yazar; API yalnızca bunu okur. Yanıtlar kısa süreli önbelleğe alınabilir (ör. 5 dk).

**Windows notu:** `eccodes`/`cfgrib` Windows'ta sorunludur. Tüm Python kodu Linux konteynerlerinde çalışır. Repo `C:\istweather` altında kalır (WSL2 dosya sistemine taşınmaz; proje sahibi kararı, 2026-11-01). Bind mount performansı ve satır sonu sorunları için:
- Veritabanı, GRIB/NetCDF ve Parquet verileri **Docker named volume**'larda durur (`db_data`, `grib_data`, `parquet_data`); repo klasörüne veri yazılmaz.
- Konteynerlere yalnızca kaynak kod bind mount edilir (`src/`, `alembic/`, `config/`, `tests/`).
- `.gitattributes` ile tüm metin dosyalarının satır sonu LF'ye sabitlenir.
- İstisna (geçici, sona erdi): Docker Desktop kurulana kadar UKMO geçmiş çıkarımı Windows'ta yerel Python ile çalıştı ve git dışı `.data/` klasörüne yazdı. Docker 2026-11-02'de kuruldu; çıktı `parquet_data` volume'una taşındı ve çıkarıcı artık konteynerde çalışıyor (Linux çıktısı Windows çıktısıyla birebir aynı).

## 5. Veri kaynakları

> **Faz 0'ın ilk işi:** Aşağıdaki her kaynak için uç nokta, dosya adlandırma, güncelleme saatleri, arşiv başlangıcı, lisans ve atıf metnini doğrula. Sonuçları `docs/data-sources.md`'de tablo halinde, kaynak linkleriyle yaz.

### 5.1 Model verisi (canlı)

| Model | Kaynak | Not |
|---|---|---|
| ECMWF IFS (deterministik, 0.25°; 20 Ekim 2026'dan itibaren 0.1° de var, teyit et) | ECMWF Open Data — `ecmwf-opendata` Python istemcisi; yansılar AWS `s3://ecmwf-forecasts` (eu-central-1), Azure, GCP | ECMWF sunucusu yalnızca son ~12 çalıştırmayı (2–3 gün) tutar. Lisans CC BY 4.0 + ECMWF Kullanım Koşulları, ticari kullanım atıfla serbest |
| ECMWF IFS ENS (51 üye), AIFS Single, AIFS ENS | Aynı | AIFS ve AIFS ENS 0.25° |
| NOAA GFS 0.25° | AWS `s3://noaa-gfs-bdp-pds` (us-east-1) veya NOMADS grib filter | NOAA verisi serbest; değiştirilmiş veri "orijinal NOAA verisi" gibi sunulmaz, NOAA onayı ima edilmez |
| NOAA GEFS (31 üye) | AWS NODD GEFS bucket'ı (adı teyit et) | |
| DWD ICON global, ICON-EU (~6.5 km), ICON-EPS / ICON-EU-EPS | opendata.dwd.de | DWD yalnızca yaklaşık son 24 saati tutar; kaçırılan çalıştırma geri gelmez, poller güvenilir olmalı. ICON-EU alanının İstanbul'u kapsadığını teyit et |
| Météo-France ARPEGE (Avrupa) | Météo-France açık paketleri (data.gouv.fr → OVH S3) | Faz 0: EURAT01 0.1° İstanbul'u kapsıyor. Canlı açık paketler **Licence Ouverte 2.0** (ticari kullanım ve türetme serbest, atıf "Source : Météo-France"). CC BY-NC yalnız TIGGE kopyası için geçerli; o kopya kullanılmaz. Portal API'nin lisansındaki "değiştirme yasağı" nedeniyle API değil açık paketler kullanılır. Ücretsiz geçmiş arşiv yok → "yetersiz geçmiş" ile canlıda kalır |
| UK Met Office Global (10 km) | AWS üzerindeki Met Office açık verisi | **Dikkat:** CC BY-SA 4.0 (share-alike). Birleşik tahmine dahil etmenin türev veriye etkisini değerlendir ve proje sahibine sor |
| ECCC GEM global | MSC Datamart (dd.weather.gc.ca) | Lisansı teyit et |

**İndirme stratejisi:**
- Tüm küreyi değil, yalnızca gereken parametreleri indir. Mümkünse `.idx`/`.index` dosyalarıyla byte-range isteği kullan.
- İstanbul kutusuna kırp (yaklaşık 40.7–41.7°K, 27.8–30.0°D; konfigürasyondan gelsin). Poyraz ve deniz etkili kar teşhisi için ayrıca daha geniş bir Karadeniz/Marmara kutusu tutulabilir (ör. deniz yüzeyi sıcaklığı ve 850 hPa sıcaklığı).
- Kırpılmış GRIB/NetCDF dosyalarını varsayılan 30 gün sakla (konfigüre edilebilir). Nokta çıkarımları kalıcı olarak saklanır.

**Değişkenler (her model için mevcut olanlar):**
- 2 m sıcaklık, 2 m çiy noktası/bağıl nem
- Yağış (toplam, konvektif varsa), kar yağışı / yağış tipi
- 10 m rüzgâr (u, v), hamle
- Ortalama deniz seviyesi basıncı
- Toplam/alçak bulut, görüş (varsa)
- 850 hPa sıcaklık, deniz yüzeyi sıcaklığı (rejim teşhisi için)
- Model orografisi ve kara-deniz maskesi (bir kere)

**Dikkat edilecek tuzaklar:**
- **Birikimli değişkenler** (yağış, radyasyon): Her model farklı birikim kuralı kullanır. ECMWF başlangıçtan beri birikimlidir. GFS'te 6 saatlik kovalarla sıfırlanma vardır. Saatlik/aralık miktarına çevirmeden önce her modelin kuralını dokümandan teyit et ve test yaz.
- **Hamle tanımları farklıdır:** "son X saatteki maksimum" ile "anlık" aynı şey değildir. Tanımı metadata olarak kaydet.
- **Zaman adımı farklıdır:** Bazı modeller ileri ufukta 3 veya 6 saatlik adıma geçer. Saatlik seriye interpolasyon yalnızca anlık değişkenlerde yapılır; birikimli değişkenler zaman içinde dağıtılırken toplam korunur.

### 5.2 Geçmiş model verisi (Ocak 2024'ten beri, hibrit)

1. **Envanter çıkar** (`docs/data-sources.md`). Her model için şunları kaydet: hangi bulut veya topluluk arşivi var, başlangıç tarihi, format, lisans.
   - Bilinen bir örnek: dynamical.org'da ECMWF AIFS Single arşivi 2024-04-01'den beri Zarr/Icechunk formatında, CC BY 4.0 lisanslı. Source Cooperative ve AWS Open Data Registry üzerinden erişiliyor. `data.dynamical.org` adresi 30 Eylül 2026'da kapandı; migration rehberine bak.
   - ICON-EU için de dynamical.org/Source Cooperative arşivi var, başlangıcını teyit et.
   - AWS'teki ECMWF ve NOAA bucket'larının ne kadar geriye gittiğini listeleyerek tespit et (`aws s3 ls --no-sign-request`).
2. Bulunan arşivlerden 39 ilçe noktası ve gözlem istasyonu noktaları için **nokta çıkarımı** yap. Tüm alanı indirme.
3. Arşivi olmayan model/dönem kombinasyonlarını açıkça raporla. Bu modeller doğrulama tablosunda "yetersiz geçmiş" diye işaretlenir ve geçmişi birikene kadar birleştirmede düşük ağırlıkla veya hiç kullanılmaz.
4. **Kendi arşivimiz** ilk canlı ingest gününden itibaren her çalıştırmayı saklar. Bu, projenin en değerli varlığıdır; yedeklenir.
5. **UKMO istisnası (2026-11-01 kararı):** UKMO Global'in AWS arşivi 2 yıllık kayan penceredir (her gün en eski gün silinir). Bu yüzden 39 ilçe noktası ve METAR istasyon noktaları için nokta çıkarımı Faz 4'ü beklemeden, en eski tarihten itibaren başlatıldı. Çıktı Parquet'tir, iş kaldığı yerden devam eder, Faz 1'de veritabanına yüklenir. Veri CC BY-SA olduğu için §11 kararı verilene kadar **yalnız iç doğrulama** içindir.

### 5.3 Gözlemler

**METAR — canlı doğrulama (ücretsiz):**
- aviationweather.gov Data API: `GET https://aviationweather.gov/api/data/metar?ids=LTFM,LTFJ,LTBA&format=json&hours=N` (Faz 0'da teyit edildi). En fazla 30 gün geriye, 100 istek/dk, istek başına en fazla 400 kayıt; özel User-Agent gönderilir.
- İstasyonlar: LTFM (İstanbul Havalimanı), LTFJ (Sabiha Gökçen), LTBA (Atatürk; Faz 0'da hâlâ METAR ve TAF yayınladığı teyit edildi). 30 dakikada bir (:20, :50). Gerçek gözlem zamanı için `obsTime` kullanılır.
- Sıcaklık, çiy noktası, rüzgâr/hamle, QNH, görüş, bulut ve hadise (RA, SN, FG…) verir. Türk METAR'larında yağış *miktarı* ve SLP yoktur.

**METAR — geçmiş doğrulama:**
- Iowa Environmental Mesonet (IEM) ASOS/METAR arşivi (`mesonet.agron.iastate.edu/cgi-bin/request/asos.py`). Kamu malı beyanı var; atıf rica ediliyor. LTFM 2018-11-02'den, LTFJ 2003'ten, LTBA 1945'ten. IP başına 1 istek/sn.
- NOAA NCEI ISD/GHCNh: ABD dışı veride ticari kısıt durumu belirsiz → yalnız iç kullanım. OGIMET: ticari kullanıma uygun değil.
- Faz 2'den itibaren AWC'den gelen METAR'lar kendi arşivimizde de birikir.

**MGM — beklemede (2026-11-01 kararı):**
- Faz 0'da `servis.mgm.gov.tr`'nin MGM sitesi dışından gelen istekleri bilerek reddettiği ("Not allowed by MGM") ve mgm.gov.tr kullanım şartlarının izinsiz yeniden yayımlamayı yasakladığı tespit edildi. Proje sahibi doğrudan kullanımı **iptal etti**.
- `servis.mgm.gov.tr`'ye istek gönderilmez. MGM erişim kısıtını aşmaya yönelik (ör. `Origin`/`Referer` taklidi) kod yazılmaz.
- MGM verisi yalnızca resmî yoldan — MGM'nin yazılı izni veya MEVBİS lisansı — gelirse eklenir. O zamana kadar `docs/data-sources.md`'de "beklemede" kaynak olarak durur.
- Resmî veri geldiğinde: ayrı adaptör modülü, `MGM_ENABLED` bayrağı (varsayılan kapalı), lisansın gerektirdiği atıf ("Kaynak: MGM"), kendi QC'miz. İstasyon meta verisi de bu resmî kaynaktan alınır.

**WMO WIS2 (SYNOP):**
- Faz 0 sonucu: MGM'nin WIS2 yayını yok (GDC kaydı, centre-id ve broker metriği yok). Kaynak devre dışı.
- WIS2'de Türkiye yayını başlarsa: Global Broker'a (MQTT) abone olunur, BUFR `eccodes` ile çözülür; yalnız "core" (GBON: 17059, 17061, 17064) veri ticari olarak kullanılır.

**İBB açık verisi (Faz 0 ek araştırması):** İBB Açık Veri Portalı'ndaki hava kalitesi istasyon web servisi ve AKOM AWOS istasyon konumları incelendi; sonuç ve lisans `docs/data-sources.md` §4.4'te.

**Gözlem kalite kontrolü (QC):**
- Fiziksel sınır kontrolü, zamansal sıçrama kontrolü ve komşu istasyon tutarlılığı.
- Sonuçlar `qc_flags` olarak kaydedilir. Hatalı değer silinmez, işaretlenir. Doğrulama ve eğitimde yalnızca QC'den geçen değerler kullanılır.

## 6. İlçeler ve noktalar

**39 ilçe:** Adalar, Arnavutköy, Ataşehir, Avcılar, Bağcılar, Bahçelievler, Bakırköy, Başakşehir, Bayrampaşa, Beşiktaş, Beykoz, Beylikdüzü, Beyoğlu, Büyükçekmece, Çatalca, Çekmeköy, Esenler, Esenyurt, Eyüpsultan, Fatih, Gaziosmanpaşa, Güngören, Kadıköy, Kağıthane, Kartal, Küçükçekmece, Maltepe, Pendik, Sancaktepe, Sarıyer, Silivri, Sultanbeyli, Sultangazi, Şile, Şişli, Tuzla, Ümraniye, Üsküdar, Zeytinburnu.

- **Temsil noktası:** Her ilçe için bir nokta belirlenir: yerleşimin yoğun olduğu merkez (ör. ilçe merkezi). Koordinatı açık bir kaynaktan al (OpenStreetMap / geoBoundaries) ve kaynağı kaydet; elle uydurma.
- **Büyük ilçeler** (Çatalca, Silivri, Şile, Arnavutköy, Beykoz, Sarıyer gibi) iklim olarak homojen değil. Şema, bir ilçeye birden fazla nokta eklenmesine izin vermeli; v1'de tek nokta yeterli.
- **Yükseklik:** Her nokta için açık bir sayısal yükseklik modelinden (Copernicus DEM veya SRTM) alınır.
- **Referans istasyon:** MGM istasyonlarıyla eşleştirme (öncelik: ilçe içinde olması, yükseklik farkının küçük olması) **MGM resmî verisi gelene kadar askıdadır** (Faz 0 eşleştirmesi `docs/districts-and-stations.md`'de yalnız referans olarak durur). Bu sürede doğrulama METAR istasyonlarında (LTFM, LTFJ, LTBA) yapılır; tüm ilçeler "doğrudan doğrulanmamış" sayılır, doğrulukları METAR noktalarından tahmin edilir ve bu sitede belirtilir.
- **Kıyı noktaları:** Kıyıdaki merkez noktaları (ör. Beykoz, Sarıyer, Üsküdar; kıyıya < 250 m) **kaydırılmaz**. Model değeri aşağıdaki kara-deniz maskeli seçimle alınır.
- **Nokta çıkarımı:** Model ızgarasından noktaya bilineer interpolasyon yapılır. Kıyı ilçelerinde kara noktası için deniz hücrelerini dışlayan, kara-deniz maskesine duyarlı seçim kullanılır. Kara-deniz maskesi vermeyen modellerde (UKMO Global) maske başka bir kaynaktan (ör. OSM kıyı çizgisi veya aynı merkezin başka ürünü) türetilir; bu yüzden ham çıkarımda nokta çevresindeki ızgara hücreleri (stencil) saklanır ve seçim sonradan yapılabilir. Sıcaklıkta model orografisi ile gerçek yükseklik farkı için lapse-rate düzeltmesi uygulanır; başlangıç 6.5 °C/km, sonra veriyle kalibre edilir.
- Model çıktıları hem **ilçe noktalarına** hem **istasyon noktalarına** çıkarılır. Doğrulama istasyon noktalarında yapılır.

## 7. Veritabanı şeması (taslak)

Tüm zamanlar UTC (`timestamptz`). Birimler içeride SI: °C, m/s, mm, hPa, m. Zaman serisi tabloları TimescaleDB hypertable olur; eski bölümler için sıkıştırma politikası tanımlanır.

- `districts` (id, slug, name, …)
- `points` (id, district_id NULL, station_id NULL, kind[`district`|`station`], lat, lon, elevation_m, source)
- `stations` (id, source[`mgm`|`metar`|`wis2`], external_id, name, lat, lon, elevation_m, district_id, active, meta jsonb)
- `observations` ★ (station_id, observed_at, temp_c, dewpoint_c, rh_pct, pressure_hpa, wind_speed_ms, wind_dir_deg, wind_gust_ms, precip_mm, precip_period_h, visibility_m, cloud_cover_pct, present_weather, qc_flags jsonb, raw jsonb)
- `models` (id, code, provider, kind[`deterministic`|`ensemble`], resolution, license, attribution_text, active)
- `model_runs` (model_id, init_time, status, discovered_at, completed_at, files jsonb, error)
- `point_forecasts` ★ (model_id, init_time, point_id, valid_time, lead_h, temp_c, dewpoint_c, rh_pct, precip_mm, snow_mm, precip_type, wind_u_ms, wind_v_ms, wind_gust_ms, mslp_hpa, cloud_cover_pct, visibility_m, t850_c, …). Wide format: bir satır = model × çalıştırma × nokta × geçerlilik zamanı.
- `ensemble_stats` ★ (model_id, init_time, point_id, valid_time, variable, mean, std, p10, p25, p50, p75, p90, exceed_probs jsonb)
  - Ham ensemble üyeleri veritabanına yazılmaz. Model/çalıştırma bazında bölümlenmiş Parquet dosyalarında tutulur; saklama süresi konfigüre edilebilir. Kalibrasyon için yeniden işlenebilmeleri gerekir.
- `verification_metrics` (subject[model code | `blend:<version>`], point_id, variable, lead_bucket, period_start, period_end, season, regime, n, mae, rmse, bias, crps, brier, …)
- `bias_params`, `blend_weights` (sürümlü; hangi dönemde, hangi veriyle eğitildi)
- `published_forecasts` ★ (district_id, issued_at, valid_time, resolution[`hourly`|`daily`], variable değerleri için p10/p50/p90, pop, confidence, models_used jsonb, blend_version)
- `alerts` (district_id, hazard, level, probability, valid_from, valid_to, issued_at, message_tr, blend_version)
- `source_health` (source, last_success_at, last_error_at, last_error, stale bool)

★ = hypertable

## 8. Tahmin birleştirme (aşamalı)

Her aşama, bir öncekini ayrılmış dönemde (son N hafta, zaman sırasına göre) yenerse devreye alınır. Yenemezse sonuç raporlanır ve önceki aşama yayında kalır.

**Aşama 0 — Baz çizgileri:**
- Ham modellerin basit ortalaması
- En iyi tek model (beklenti: ECMWF IFS)
- Persistence (dün aynı saat)
- Klimatoloji

**Aşama 1 — Bias düzeltme + ağırlıklı ortalama:**
- Bias, şu kırılımların her biri için ayrı hesaplanır: model × nokta × değişken × ufuk kovası × günün saati. Kayan pencere varsayılan 30 gün, konfigüre edilebilir. Az örnekli hücreler için hiyerarşik geri düşme: nokta → ilçe grubu → tüm İstanbul.
- Ağırlık w ∝ 1/MSE (son 30–60 gün, ufuk kovası bazında); normalize edilir.
- Yağış:
  - Miktar için kantil eşleme.
  - Yağış olasılığı (PoP) için ensemble üye oranının lojistik kalibrasyonu.
- Rüzgâr yönü: u/v bileşenleriyle birleştirilir; açı ortalaması alınmaz.

**Aşama 2 — Olasılıksal kalibrasyon:**
- Tüm ensemble'lar birleştirilir. Sıcaklık ve rüzgâr için EMOS/NGR (CRPS minimizasyonu) uygulanır.
- Yağış için sansürlü bir dağılım kullanılır (ör. sansürlü kaydırılmış gamma); seçimi literatürle gerekçelendir.
- Çıktı: p10 / p50 / p90 ve eşik aşma olasılıkları.

**Aşama 3 — ML (sonraki sürüm):**
- LightGBM ile stacking. Öznitelikler: model tahminleri, ensemble istatistikleri, ufuk, saat, mevsim, rejim bayrakları, deniz yüzeyi − 850 hPa sıcaklık farkı, yükseklik.
- Zaman serisine uygun çapraz doğrulama yapılır; gelecekten veri sızıntısı olmamalı.

**Türetilmiş değişkenler:**
- **Hissedilen sıcaklık:** Formülü seç (ör. rüzgâr soğuğu + ısı indeksi birleşimi ya da Steadman tipi apparent temperature), dokümante et ve test yaz.
- **Kar / yağmur ayrımı:** Model yağış tipi, ıslak termometre sıcaklığı ve donma seviyesinden.
- **Sis/görüş:** Model görüş çıktıları zayıftır. v1'de çiy noktası farkı, rüzgâr, nem ve (ilkbaharda) deniz-hava sıcaklık farkına dayalı basit bir olasılık kuralı uygulanır, METAR görüş verisiyle doğrulanır; ML aşamasında iyileştirilir.

**Rejimler** (eşikler konfigürasyonda; başlangıç değerleri gözden geçirilecek):
- **Lodos:** rüzgâr yönü yaklaşık GB sektöründe (≈ 200–250°) ve hız eşiğin üstünde.
- **Poyraz:** rüzgâr yönü yaklaşık KD sektöründe (≈ 20–70°).
- **Deniz etkili kar potansiyeli:** poyraz + Karadeniz yüzey sıcaklığı − T850 farkı büyük.
- **Doğrulama:** Metrikler rejime göre ayrıca raporlanır. Bias düzeltme rejime göre koşullanabilir (Aşama 1'in alt seçeneği).

**Güven düzeyi:** Ensemble yayılımı ve deterministik modeller arası uyumdan türetilir: `yüksek` / `orta` / `düşük`. Kalibre edilmiş aralık genişliğine dayanır.

## 9. Doğrulama

- **Metrikler:**
  - Sürekli değişkenler: MAE, RMSE, bias; beceri skoru SS = 1 − MAE / MAE_baz.
  - Olasılıksal: CRPS, Brier skoru, güvenilirlik diyagramı verisi.
  - Olaylar: POD, FAR, ETS.
- **Kırılımlar:** model / blend sürümü × istasyon/ilçe × değişken × ufuk kovası × mevsim × rejim.
- **Geçmiş doğrulama:** Her model için §5.2'deki arşivlerle, Ocak 2024'ten (veya arşivin başladığı tarihten) bugüne kadar.
- **Canlı doğrulama:** Her gün otomatik çalışır, sonuçlar `verification_metrics`'e yazılır.
- **Kabul ölçütü:** Birleşik tahmin, 1–3 günlük ufukta sıcaklık MAE ve yağış Brier skorunda en iyi tek modeli ayrılmış dönemde yenmeli. Sonuçlar `docs/verification-report.md`'de, yenemediği durumlar dahil dürüstçe raporlanır.

## 10. API (FastAPI, `/api/v1`)

- **Erişim:** Yalnızca kendi sitemiz. CORS sadece site alan adına açık. IP bazlı oran sınırlaması uygulanır. OpenAPI dokümanı otomatik üretilir.
- **Yanıt formatı:**
  - Yanıt zamanları Europe/Istanbul (UTC+3) olarak döner; ham UTC alanı da eklenir.
  - Rüzgâr hem m/s hem km/s olarak verilir.
  - Her yanıtta `issued_at`, `blend_version`, `sources` (atıf metinleri) ve veri tazeliği bilgisi bulunur.

Uç noktalar (taslak):
- `GET /api/v1/districts`: ilçe listesi
- `GET /api/v1/districts/{slug}/forecast`: 0–72 saat saatlik + 4–7. gün günlük; değer, p10/p90, PoP, güven düzeyi
- `GET /api/v1/districts/{slug}/current`: en yakın/referans istasyonun son gözlemi (kaynak atfıyla) ve tazelik. MGM beklemede olduğu sürece kaynak en yakın METAR istasyonudur ve mesafesi yanıtta belirtilir
- `GET /api/v1/alerts?district={slug}`: aktif uyarılar
- `GET /api/v1/meta/sources`: kullanılan modeller, son çalıştırma saatleri, atıf ve lisans bilgileri
- `GET /api/v1/health`: servis ve veri tazeliği durumu

**Uyarılar:**
- Tehlikeler: lodos fırtınası, kuvvetli rüzgâr/hamle, kar, yoğun yağış, Boğaz sisi.
- Seviyeler: sarı / turuncu / kırmızı.
- Uyarı, kalibre edilmiş eşik aşma olasılığına göre üretilir. Eşikler ve olasılık seviyeleri konfigürasyonda tutulur. Başlangıç değerleri `docs/alerts.md`'de gerekçesiyle yazılır ve proje sahibine onaylatılır. MGM'nin yayımlanmış uyarı kriterleri bulunursa referans alınır.
- Her uyarı metninde şu ibare yer alır: "Bu bir MGM resmi uyarısı değildir; resmi uyarılar için mgm.gov.tr."
- Opsiyonel: MGM'nin resmi uyarıları da toplanıp ayrı bir etiketle gösterilebilir; proje sahibine sor.

**Admin paneli (`/admin`):**
- Şifreyle korunur (ortam değişkeniyle tanımlı tek admin kullanıcısı; prod'da yalnızca HTTPS).
- Basit, sunucu tarafında render edilen sayfalar (Jinja2 + hafif bir grafik kütüphanesi).
- İçerik:
  - Kaynak sağlığı ve son çalıştırmalar
  - Model × ilçe hata tabloları
  - Blend ile en iyi tek model karşılaştırması
  - Ufka göre hata grafiği
  - Rejim kırılımı
  - Son uyarılar

## 11. Lisans ve atıf

- **ECMWF:** CC BY 4.0 + ECMWF Kullanım Koşulları. Sitede atıf zorunlu.
- **NOAA:** Serbest kullanım. Atıf istenir; NOAA onayı ima edilmez; işlenmiş veri "orijinal NOAA verisi" diye sunulmaz.
- **DWD:** CC BY 4.0. Atıf "Source: Deutscher Wetterdienst" (değiştirilmiş veride "Based on data from Deutscher Wetterdienst…" biçimi). Faz 0'da teyit edildi.
- **Météo-France:** Canlı açık paketler Licence Ouverte 2.0; ticari kullanım ve türetme serbest. Atıf "Source : Météo-France" veya "Informations créées à partir de données de Météo-France" + son güncelleme tarihi. TIGGE'deki MF verisi CC BY-NC'dir, kullanılmaz. Faz 0'da teyit edildi.
- **ECCC:** ECCC Data Servers End-use Licence 2.1.1; ticari serbest. Atıf "Data Source: Environment and Climate Change Canada". Faz 0'da teyit edildi.
- **UK Met Office:** CC BY-SA 4.0. Share-alike etkisini değerlendir ve proje sahibine sor; karar verilene kadar yalnızca iç doğrulamada kullan (Faz 0 sonrası başlatılan geçmiş nokta çıkarımı dahil).
- **TIGGE (ECMWF Data Store):** DWD, ECCC, ECMWF, KMA, NCEP, UKMO verisi CC BY 4.0 (ticari serbest); diğer merkezler CC BY-NC (kullanılmaz). Hesabı proje sahibi açar.
- **Topluluk arşivleri (dynamical.org vb.):** Lisanslarını kaydet. AIFS arşivi için CC BY 4.0 + ECMWF koşulları geçerli.
- **METAR / IEM:** AWC verisi ABD kamu malı (NOAA/NWS onayı ima edilmez); IEM kamu malı, atıf rica ediliyor. Türkiye kaynaklı METAR'ın ticari yeniden dağıtım durumu belirsiz olduğundan ham METAR yeniden dağıtılmaz, doğrulamada ve "son gözlem" gösteriminde atıfla kullanılır.
- **MGM:** Doğrudan kullanım iptal edildi (2026-11-01). Yalnızca MGM'nin yazılı izni veya MEVBİS lisansıyla gelen resmî veri kullanılır; lisansın gerektirdiği atıf ("Kaynak: MGM") her gösterimde yer alır. Adaptör varsayılan olarak kapalıdır.
- **WMO WIS2:** Türkiye yayını yok (Faz 0). Yayın başlarsa yalnız "core" veri ticari kullanılır (Unified Data Policy: free and unrestricted).
- **Site geneli bilgilendirme metni:** "Tahminler otomatik üretilir, resmi tahmin yerine geçmez."
- Tüm atıf metinleri `models.attribution_text` ve `/api/v1/meta/sources` üzerinden siteye taşınır.

## 12. Repo yapısı (öneri)

```
.
├── README.md                 # Türkçe: kurulum, çalıştırma, mimari özet
├── CLAUDE.md                 # Claude Code için kalıcı kurallar (§2'den özet)
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example              # gizli değer yok; .env git'e girmez
├── pyproject.toml            # ruff, mypy, pytest ayarları
├── alembic/                  # migration'lar
├── config/
│   ├── region.istanbul.yaml  # kutu, ilçeler, noktalar
│   ├── models.yaml           # model listesi, kaynak, değişkenler, aktiflik
│   └── alerts.yaml           # eşikler
├── src/hava/
│   ├── api/                  # FastAPI uygulaması, router'lar, admin
│   ├── db/                   # SQLAlchemy modelleri, oturum
│   ├── ingest/
│   │   ├── models/           # ecmwf.py, gfs.py, icon.py, arpege.py, ukmo.py, gem.py
│   │   ├── obs/              # metar.py, mgm.py, wis2.py
│   │   └── archive/          # geçmiş backfill
│   ├── processing/           # crop, point extraction, de-accumulation, lapse-rate
│   ├── qc/
│   ├── verification/
│   ├── blending/             # stage1.py, stage2.py, derived.py, regimes.py
│   ├── alerts/
│   ├── scheduler/            # APScheduler işleri
│   └── ops/                  # health, notifications (Telegram/e-posta)
├── tests/
│   ├── fixtures/             # küçük, etiketli örnek GRIB/METAR/MGM yanıtları
│   └── ...
├── docs/
│   ├── data-sources.md
│   ├── alerts.md
│   ├── verification-report.md
│   └── decisions/            # mimari karar kayıtları (ADR)
└── .github/workflows/ci.yml
```

**Kütüphaneler:**
- Web ve veritabanı: fastapi, uvicorn, pydantic v2, pydantic-settings, sqlalchemy 2, alembic, psycopg 3
- Meteoroloji verisi: xarray, cfgrib + eccodes, ecmwf-opendata, numpy, pandas veya polars, pyarrow
- İstatistik ve ML: scipy, scikit-learn, properscoring (CRPS)
- Altyapı: httpx, apscheduler, structlog, jinja2
- Test ve kalite: pytest, ruff, mypy
- Daha sonra: lightgbm

## 13. Test ve CI

- **GitHub Actions:** Her push/PR'da çalışır.
  - `ruff check`, `ruff format --check`, `mypy`
  - `pytest` (TimescaleDB servis konteyneriyle entegrasyon testleri)
- **Zorunlu birim testleri:**
  - Birikimli yağışın saatliğe çevrilmesi (her model için)
  - Rüzgâr u/v ↔ hız/yön dönüşümü ve u/v ortalaması
  - Lapse-rate düzeltmesi
  - Kara-deniz maskeli nokta seçimi
  - Bias ve ağırlık hesapları
  - Metrikler (MAE, CRPS, Brier); bilinen değerlerle karşılaştırılır
  - Hissedilen sıcaklık formülü
  - Uyarı eşik mantığı
  - QC kuralları
- Ağ gerektiren testler `@pytest.mark.network` ile işaretlenir; CI'da varsayılan olarak kapalıdır.

## 14. İşletme (prod)

- **Sunucu:** Kiralık VPS; sağlayıcı henüz seçilmedi. Kaba tahmin (doğrulanmalı): 4 vCPU, 8–16 GB RAM, 160 GB+ SSD. GRIB işleme bellek ister; ensemble Parquet arşivi yılda onlarca GB'a ulaşabilir. Faz 3 sonunda gerçek kullanımı ölç ve tahmini güncelle.
- **Caddy:** Otomatik HTTPS ve reverse proxy.
- **İzleme:**
  - Her kaynak için tazelik kontrolü. Örnek: son ECMWF çalıştırması beklenenden X saat eskiyse, ya da MGM/METAR N dakikadır gelmiyorsa bildirim.
  - Bildirim kanalı: Telegram bot (token `.env`'de) ve/veya e-posta.
  - Worker çökmeleri ve tekrarlayan iş hataları da bildirilir.
- **Yedekleme:**
  - Günlük `pg_dump` (sıkıştırılmış) ve ensemble Parquet arşivi, restic veya rclone ile sunucu dışına gönderilir. Hedef proje sahibine sorulacak (ör. Hetzner Storage Box, Backblaze B2 veya evdeki QNAP NAS).
  - Saklama: 7 günlük + 4 haftalık + 6 aylık.
  - Geri yükleme prosedürü `docs/`'ta yazılı olur ve en az bir kez denenir.
- **Loglar:** structlog ile JSON formatında. Docker log rotasyonu açık.
- **Gizli değerler:** Yalnızca `.env` dosyasında tutulur, git'e girmez.

## 15. Fazlar ve kabul kriterleri

| Faz | İçerik | Kabul kriteri |
|---|---|---|
| **0. Keşif** | §5 kaynak envanteri; 39 ilçe noktası + yükseklik; MGM istasyon listesi ve ilçe eşleştirmesi; WIS2 kontrolü | `docs/data-sources.md` tamam: her kaynak için uç nokta, lisans, arşiv başlangıcı, teyit linki. Bilinmeyenler açıkça listelenmiş |
| **1. İskelet** | Repo, Docker Compose, şema + migration'lar, CI, `/health`, CLAUDE.md, README | `docker compose up` ile her şey ayağa kalkar; CI yeşil |
| **2. Gözlem ingest** | METAR (AWC) toplayıcısı + IEM geçmiş yüklemesi; (lisansı uygunsa) İBB kaynağı; QC; `source_health`; bildirimler. MGM beklemede, WIS2 yok | 48 saat kesintisiz toplama; QC raporu; bir kaynak kapatılınca bildirim geliyor |
| **3. Canlı model ingest** | Önce ECMWF (IFS, AIFS, ENS), GFS/GEFS, ICON/ICON-EU(-EPS); sonra ARPEGE, UKMO, GEM. Kırpma, nokta çıkarımı, ensemble istatistikleri | Her model için en az 3 gün eksiksiz çalıştırma; `model_runs` durumları doğru; disk ve RAM kullanımı ölçülmüş |
| **4. Geçmiş backfill** | Envanterdeki arşivlerden Ocak 2024'ten beri nokta çıkarımı (UKMO çıkarımı Faz 0 sonrası başladı, bkz. §5.2.5) | Model × dönem kapsama tablosu; boşluklar raporlanmış |
| **5. Doğrulama motoru** | §9 metrikleri, baz çizgileri, rapor | `verification-report.md`: model sıralaması, ufka göre hata, rejim kırılımı |
| **6. Blend v1** | §8 Aşama 1 (+ hazır olursa Aşama 2), `published_forecasts` | Ayrılmış dönemde en iyi tek modelle karşılaştırma raporu; yenmiyorsa nedenleri |
| **7. API + uyarılar + admin** | §10 | OpenAPI dokümanı; uyarı eşikleri onaylı; admin paneli çalışıyor |
| **8. Prod deploy** | VPS, Caddy, yedek, izleme | HTTPS çalışıyor; yedekten geri yükleme denenmiş; bildirimler test edilmiş |
| **9. Sonra** | ML stacking (Aşama 3), Türkiye'ye genişleme, ilçe başına çoklu nokta, dışa açık API | — |

## 16. Proje sahibine sorulacak açık konular

- Alan adı ve VPS sağlayıcısı
- Yedekleme hedefi (Storage Box / B2 / NAS)
- Telegram bot token'ı ve bildirim e-posta adresi
- Uyarı eşiklerinin onayı (Faz 7)
- UK Met Office verisinin (CC BY-SA) birleşik tahmine dahil edilip edilmeyeceği
- MGM resmi uyarılarının da gösterilip gösterilmeyeceği
- MGM gözlem verisi: yazılı izin veya MEVBİS başvurusu (proje sahibi yürütecek; sonuç gelene kadar MGM beklemede)
- TIGGE (ECMWF Data Store) ve Hugging Face hesapları (proje sahibi açacak; anahtarlar yalnızca `.env`'e girer, sohbette paylaşılmaz)
- GitHub deposu (CI için; Faz 1 kabulünün "CI yeşil" yarısı buna bağlı)

Kapanan konular: WIS2'de Türkiye verisi yok (Faz 0); ek gözlem kaynağı olarak METAR + IEM seçildi, İBB açık verisi incelendi (`docs/data-sources.md` §4.4). Docker Desktop geliştirme makinesine kuruldu (2026-11-02).

## 17. Claude Code için çalışma kuralları

- Faz 0'dan başla. Her fazın sonunda kabul kriterlerini kanıtla (komut çıktısı, test sonucu, rapor) ve proje sahibine kısa bir özet ver.
- Doğrulanmamış bir URL, model kodu veya dosya adlandırması varsayma. Önce kontrol et, sonra `docs/data-sources.md`'ye yaz.
- Bir şey çalışmıyorsa çalışıyormuş gibi gösterme. Sorunu, nedenini ve seçenekleri açıkça yaz.
- Büyük mimari kararları `docs/decisions/` altına kısa ADR olarak kaydet.
- Commit'ler küçük ve açıklayıcı olsun. `.env` ve veri dosyaları git'e girmez.
