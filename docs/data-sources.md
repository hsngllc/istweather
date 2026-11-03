# Veri Kaynakları — Faz 0 Envanteri

> **Durum:** Faz 0 keşif çıktısı. Kontrol zamanı 2026-10-31 21:40 – 2026-11-01 01:00 UTC.
> **Kapsam:** spec §5 (model verisi, geçmiş arşivler, gözlemler), §6 (ilçe noktaları ve istasyonlar — ayrıntısı [districts-and-stations.md](districts-and-stations.md)), §11 (lisans ve atıf).
> **Kural:** Bu dosyadaki her URL, dosya adı, parametre kodu ve tarih ya birincil kaynaktan (resmî doküman, lisans metni) ya da doğrudan istekle (dizin/bucket listesi, `.idx`/`.index` dosyası, GRIB başlığı) teyit edildi. Teyit edilemeyenler açıkça işaretlendi ve §8'de toplandı.
> **Not:** Kaynaklar sık değişiyor (bu keşif sırasında bile 4 büyük değişiklik bulundu: DWD URL şeması, ECMWF 0.1°, ECCC GDPS 10.0, dynamical.org taşınması). Faz 1+ kodu dokümana değil gerçek dosyalara (index, GRIB başlığı) güvenmeli.

**İşaretler:** ✅ birincil kaynak veya doğrudan istekle teyit · ⚠️ yalnız ikincil kaynak ya da çıkarım · ❓ teyit edilemedi.

**Yöntem notu:** Araştırma yedi paralel koldan yürütüldü; her kolun kritik iddiaları ayrıca bağımsız bir istekle yeniden kontrol edildi (aşağıda "çapraz kontrol" diye anılıyor). Proje kodu yazılmadı; yalnızca ad-hoc `curl` istekleri ve çalışma klasöründe atılabilir veri işleme betikleri kullanıldı. Ham kanıt dosyaları (index dosyaları, listeler, lisans PDF'leri) Faz 0 çalışma klasöründe duruyor.

---

## 0. Spec'i değiştiren veya acil aksiyon gerektiren bulgular

| # | Bulgu | Etki | Durum |
|---|---|---|---|
| 1 | **MGM servisi, MGM sitesi dışından gelen istekleri reddediyor** (`Origin` başlığı yoksa `HTTP 500 "Not allowed by MGM"`). MGM "Yasal Uyarı" sayfası izinsiz kopyalama/yeniden yayımlamayı yasaklıyor. | **Karar (2026-11-01): doğrudan kullanım iptal.** `servis.mgm.gov.tr`'ye istek gönderilmez; MGM, yazılı izin veya MEVBİS lisansıyla gelecek resmî veri için **beklemede** (§4.2). | ✅ |
| 2 | **DWD eski URL şeması 30.11.2026'dan sonra kapanıyor.** Yeni şema (`/weather/nwp/v1/m/…`) yalnız native üçgen ızgara; **ICON-EU regular-lat-lon bitiyor; görüş (VIS) ICON zincirinden kalkıyor; `lib/cdo` siliniyor.** | ICON adaptörü ilk günden v1 + native ızgaraya yazılmalı. DWD'den görüş gelmeyecek. | ✅ çapraz kontrol |
| 3 | **UKMO Global AWS arşivi 2 yıllık kayan pencere** (bugün en eski çalıştırma 2024-10-30T18Z). | Her gün bir günlük geçmiş siliniyor; Ocak–Ekim 2024 zaten yok. **Karar (2026-11-01):** 39 ilçe + METAR noktaları için nokta çıkarımı en eski tarihten başlatıldı (yalnız iç doğrulama). | ✅ çapraz kontrol |
| 4 | **TIGGE (ECMWF Data Store) lisansı değişmiş:** DWD, ECCC, ECMWF, KMA, NCEP, UKMO verisi **CC BY 4.0 (ticari serbest)**; Météo-France dahil diğerleri CC BY-NC. | ICON global, ICON-EPS, GEM global ve MOGREPS-G için tek ücretsiz + ticari geçmiş kaynağı. ECMWF hesabı ve lisans kabulü gerekir (proje sahibi yapmalı). | ✅ çapraz kontrol (lisans PDF'i) |
| 5 | **ECMWF 0.1° yayını 2026-10-20 06z'de başladı** (HRES ve ENS; 0.25°'ten ~2 sa sonra). **IFS ENS açık verisinde kontrol üyesi yok** (2026-05-12'den beri `ef` = 50 pf; kontrol = `oper/fc`). 06/18z akış adı `scda`→`oper`. | Spec'teki "51 üye" = 50 pf + oper fc. İndirici iki akışı birlikte okumalı. | ✅ çapraz kontrol |
| 6 | **Görüş ve SST ECMWF açık verisinde yok; AIFS'te hamle ve yağış tipi yok.** | Görüş için GFS, ARPEGE, UKMO (ve 30.11.2026'ya kadar ICON-EU) kalıyor. SST için `skt` vekil. | ✅ |
| 7 | **dynamical.org ICON-EU arşivi 2026-02-10'da başlıyor** (2024 değil). `data.dynamical.org` emekli; yeni erişim Icechunk/STAC. | ICON-EU için 2024–2026 geçmişi parçalı (§3). | ✅ çapraz kontrol (STAC) |
| 8 | **ECCC GDPS 10.0 2026-05-26 12Z'de devreye girdi** (model değişikliği + dizin/dosya adı değişikliği). Datamart 30 gün tutuyor; sistematik indirme için AMQP zorunlu. | Bias eğitiminde kırılma noktası. Eski `model_gem_global` yolları 404. | ✅ çapraz kontrol |
| 9 | **ARPEGE deterministik ve ICON-EU-EPS için ücretsiz ve ticari kullanıma uygun geçmiş arşiv yok.** CC BY-NC yalnız TIGGE'deki Météo-France verisine (PEARP) uygulanıyor; ARPEGE canlı açık paketleri Licence Ouverte 2.0 (ticari serbest). | **Karar (2026-11-01):** ARPEGE canlıda "yetersiz geçmiş" ile kalır (spec §5.2.3). | ✅ çapraz kontrol |
| 10 | **MGM'nin WIS2 yayını yok** (centre-id yok, GDC kaydı yok, broker metriklerinde yok). | Spec §5.3 gereği WIS2 kaynağı devre dışı. | ✅ çapraz kontrol |
| 11 | **AWC METAR API yalnız son 30 günü veriyor.** Ocak 2024'ten bu yana geçmiş METAR için ticari açıdan en güvenli kaynak IEM (public domain beyanı). | Geçmiş doğrulama METAR'ı IEM'den alınmalı. | ✅ çapraz kontrol |
| 12 | **Hamle tanımları modeller arasında çok farklı** ve çoğunda 3–6 saatlik adımlarda yalnız son 1 saatin maksimumu var (ECMWF 0–90 sa, ICON, ARPEGE). GFS/GEFS/GDPS hamlesi anlık. | Hamle tanımı `point_forecasts` metadata'sına yazılmalı (spec §5.1 zaten istiyor); doğrulama tanıma göre ayrılmalı. | ✅ |
| 13 | **NOAA GFSv17 "late 2027"ye ertelendi;** dizin ve dosya adları değişecek (yürürlükten 30 gün önce SCN). | Faz 3'te etkisi yok; izlenmeli. | ✅ |

---

## 1. Özet tablo

| Kaynak | Tür | Birincil uç nokta | Lisans | Ticari | Ücretsiz geçmiş başlangıcı | Teyit linki |
|---|---|---|---|---|---|---|
| ECMWF IFS 0.25° / 0.1° | Model (det.) | `https://data.ecmwf.int/forecasts/`; yansılar AWS `s3://ecmwf-forecasts`, GCS `ecmwf-open-data`, Azure `ai4edataeuwest/ecmwf` | CC BY 4.0 + ECMWF ToU | Evet (atıfla) | Azure 2022-01-21, AWS 2023-01-18 (0.25°: 2024-02-01; 0.1°: 2026-10-20) | [Open data](https://www.ecmwf.int/en/forecasts/datasets/open-data), [Confluence](https://confluence.ecmwf.int/display/DAC/ECMWF+open+data%3A+real-time+forecasts+from+IFS+and+AIFS) |
| ECMWF IFS ENS | Model (ens., 50 pf + oper fc) | aynı (`enfo`) | aynı | Evet | yansılar (yukarıdaki gibi); dynamical 2024-04-01; MARS backfill 2016-03-08–2024-03-31 | aynı + [dynamical STAC](https://stac.dynamical.org/catalog.json) |
| ECMWF AIFS Single | Model (det., ML) | aynı (`aifs-single`) | CC BY 4.0 + ECMWF ToU | Evet | AWS `aifs/` 2024-02-29 (deneysel), dynamical 2024-04-01 | [AIFS open data](https://confluence.ecmwf.int/pages/viewpage.action?pageId=738041086), [dynamical STAC](https://stac.dynamical.org/ecmwf-aifs-single-forecast/collection.json) |
| ECMWF AIFS ENS | Model (ens., cf + 50 pf) | aynı (`aifs-ens`) | CC BY 4.0 + ECMWF ToU | Evet | 2025-07-01 06z | [AIFS open data](https://confluence.ecmwf.int/pages/viewpage.action?pageId=738041086), [dynamical STAC](https://stac.dynamical.org/ecmwf-aifs-ens-forecast/collection.json) |
| NOAA GFS 0.25° | Model (det.) | AWS `s3://noaa-gfs-bdp-pds`; NOMADS | NOAA açık veri (NODD) | Evet (koşullu) | AWS 2021-01-01 (eksiksiz); NCAR 2015-01-15 | [NCO GFS](https://www.nco.ncep.noaa.gov/pmb/products/gfs/), [registry](https://raw.githubusercontent.com/awslabs/open-data-registry/main/datasets/noaa-gfs-bdp-pds.yaml) |
| NOAA GEFS | Model (ens., 31) | AWS `s3://noaa-gefs-pds`; NOMADS | aynı | Evet (koşullu) | AWS 2017-01-01 | [NCO GENS](https://www.nco.ncep.noaa.gov/pmb/products/gens/), [registry](https://raw.githubusercontent.com/awslabs/open-data-registry/main/datasets/noaa-gefs.yaml) |
| DWD ICON / ICON-EU / ICON-EPS / ICON-EU-EPS | Model | `https://opendata.dwd.de/weather/nwp/v1/m/<model>/…` | CC BY 4.0 | Evet (atıfla) | Resmî arşiv yok; TIGGE (ICON, ICON-EPS) 2020-03; dynamical ICON-EU 2026-02-10 | [DWD bülten 09/2026](https://www.dwd.de/DE/leistungen/opendata/neuigkeiten/opendata_september2026_1.html), [legal notice](https://www.dwd.de/EN/service/legal_notice/legal_notice_node.html) |
| Météo-France ARPEGE | Model (det.) | OVH S3 `meteofrance-pnt` (data.gouv.fr açık paketleri); portail-api (anahtarlı) | Licence Ouverte 2.0 | Evet (atıfla) | **Yok** (~15 gün kayan) | [data.gouv 0.1°](https://www.data.gouv.fr/datasets/paquets-arpege-resolution-0-1deg) |
| UK Met Office Global 10 km | Model (det.) | AWS `s3://met-office-atmospheric-model-data` (eu-west-2) | **CC BY-SA 4.0** | Belirsiz (share-alike) | 2024-10-30T18Z (kayan 2 yıl) | [registry](https://github.com/awslabs/open-data-registry/blob/main/datasets/met-office-global-deterministic.yaml) |
| UKMO MOGREPS-G | Model (ens., 18/çalıştırma) | AWS `s3://met-office-global-ensemble-model-data` | CC BY-SA 4.0 (AWS); **CC BY 4.0 (TIGGE)** | AWS: belirsiz; TIGGE: evet | AWS 30 gün; TIGGE 2006 | registry, [TIGGE lisansı](https://object-store.os-api.cci2.ecmwf.int/cci2-prod-catalogue/licences/tigge-licence/tigge-licence_5a08d5ef121b263c870e46ddd923398f3f586bb696e866efb9da5bda97ae3e35.pdf) |
| ECCC GDPS (GEM global) / GEPS | Model | `https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_gdps/15km/…` (+ AMQPS bildirim) | ECCC Data Servers End-use Licence 2.1.1 | Evet (atıfla) | Datamart 30 gün; TIGGE GDPS 2021-06 | [Datamart](https://eccc-msc.github.io/open-data/msc-datamart/readme_en/), [kullanım politikası](https://eccc-msc.github.io/open-data/usage-policy/readme_en/) |
| dynamical.org arşivleri | Topluluk arşivi | STAC `https://stac.dynamical.org/catalog.json` → Icechunk (AWS `s3://dynamical-*`) | CC BY 4.0 (+ECMWF ToU) | Evet | veri kümesine göre (§3) | [migration-2026](https://dynamical.org/migration-2026/) |
| TIGGE | Arşiv (ens. + bazı det.) | ECMWF Data Store `tigge-forecasts` | CC BY 4.0 (DWD/ECCC/ECMWF/KMA/NCEP/UKMO); CC BY-NC (MF vb.) | Kısmen | 2006+ (merkeze göre) | [ECDS STAC](https://ecds.ecmwf.int/api/catalogue/v1/collections/tigge-forecasts), lisans PDF |
| METAR (AWC) | Gözlem | `https://aviationweather.gov/api/data/metar` | ABD kamu malı (NWS koşulları) | Evet (koşullu; yabancı orijin ❓) | 30 gün | [Data API](https://aviationweather.gov/data/api/) |
| METAR geçmişi (IEM) | Gözlem arşivi | `https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py` | Public domain | Evet | LTBA 1945, LTFJ 2003, LTFM 2018-11-02 | [disclaimer](https://mesonet.agron.iastate.edu/disclaimer.php) |
| MGM gözlemleri | Gözlem | **BEKLEMEDE** — doğrudan kullanım iptal (2026-11-01); yalnız yazılı izin veya MEVBİS lisansıyla resmî veri | Resmî lisansa bağlı | Resmî lisansa bağlı | — | [Yasal Uyarı](https://www.mgm.gov.tr/site/yasal-uyari.aspx), [mgm.gov.tr](https://www.mgm.gov.tr/) |
| İBB hava kalitesi web servisi | Gözlem (yalnız kirletici) | `https://api.ibb.gov.tr/havakalitesi/OpenDataPortalHandler/GetAQIByStationId` | İBB Açık Veri Lisansı (CC BY 4.0 uyumlu) | Evet (atıfla) | Ocak 2024 ve öncesi sorgulanabiliyor | [veri seti](https://data.ibb.gov.tr/dataset/hava-kalitesi-istasyon-olcum-sonuclari-web-servisi) — **meteoroloji parametresi yok, doğrulamada kullanılmaz** (§4.4) |
| İBB AKOM AWOS istasyon konumları | İstasyon meta (yalnız konum) | CSV (data.ibb.gov.tr) | İBB Açık Veri Lisansı | Evet (atıfla) | — (ölçüm yok) | [veri seti](https://data.ibb.gov.tr/dataset/meteoroloji-gozlem-istasyon-konumlari) — **ölçüm yayınlanmıyor** (§4.4) |
| WMO WIS2 SYNOP | Gözlem | — (Türkiye yayını yok) | UDP core = free & unrestricted | — | — | [GDC](https://wis2-gdc.weather.gc.ca/collections/wis2-discovery-metadata) |
| OpenStreetMap | İlçe sınırı / nokta | Overpass API | ODbL 1.0 | Evet (atıf + ODbL koşulları) | — | [copyright](https://www.openstreetmap.org/copyright) |
| SRTM GL1 v3 / ASTER GDEM v3 | Yükseklik | OpenTopoData genel API (yalnız Faz 0) | NASA EOSDIS açık | Evet | — | [SRTMGL1](https://www.earthdata.nasa.gov/data/catalog/lpcloud-srtmgl1-003) |
| ~~Open-Meteo~~ | — | — | — | — | — | Proje sahibi kararıyla **kullanılmıyor** (yalnız envanter, §3.4) |

---

## 2. Canlı model verisi

### 2.1 ECMWF — IFS (0.25°/0.1°), IFS ENS, AIFS Single, AIFS ENS

**Erişim** ✅
- Portal: `https://data.ecmwf.int/forecasts/` — anonim; `Accept: application/json` ile JSON dizin listesi; Range (tekli ve çoklu) destekli. Bağlantı sınırı: "500 ile 2000 eşzamanlı bağlantı" ([Open data](https://www.ecmwf.int/en/forecasts/datasets/open-data)); her paralel Range parçası ayrı oturum sayılıyor. IP başına sınır ❓.
- AWS `s3://ecmwf-forecasts` (eu-central-1): anonim; **tek aralık Range 206, çoklu aralık isteğine dosyanın tamamını (200) döndürüyor**; yoğun istekte `503 SlowDown` → backoff şart.
- GCS `https://storage.googleapis.com/ecmwf-open-data`; Azure `https://ai4edataeuwest.blob.core.windows.net/ecmwf` (Planetary Computer'dan anonim **SAS token** gerekir, ~60 dk).
- Python istemcisi `ecmwf-opendata` **0.3.35** (PyPI 2026-10-16): `Client(source="ecmwf"|"aws"|"azure"|"google", model="ifs"|"aifs-single"|"aifs-ens", resol="0p25"|"0p1")`. `0p1` yalnız IFS. ❓ 50r1 sonrası `type="cf"` isteğinde davranışı test edilmedi (kontrol için `stream=oper, type=fc` istenmeli).

**Dosya adlandırma** ✅ ([kural](https://confluence.ecmwf.int/pages/viewpage.action?pageId=738041084))
`[ROOT]/[yyyymmdd]/[HH]z/[model]/[resol]/[stream]/[yyyymmdd][HH]0000-[step]h-[stream]-[type](-[sfc|pl]).grib2` + aynı adlı `.index` (JSON-lines, `_offset`/`_length`). `-sfc`/`-pl` eki yalnız 0.1°'de.

| Ürün | Gerçek örnek (2026-10-31, portal) | Boyut/adım |
|---|---|---|
| IFS 0.25 | `/20261031/00z/ifs/0p25/oper/20261031000000-6h-oper-fc.grib2` | 93–97 MB |
| IFS 0.1 | `/20261031/00z/ifs/0p1/oper/20261031000000-6h-oper-fc-sfc.grib2` (+`-pl`) | sfc 74–89 MB, pl 353–367 MB |
| IFS ENS 0.25 | `/20261031/00z/ifs/0p25/enfo/20261031000000-6h-enfo-ef.grib2` | ~4 GB |
| AIFS Single | `/20261031/00z/aifs-single/0p25/oper/20261031000000-6h-oper-fc.grib2` | 53–60 MB |
| AIFS ENS | `/20261031/00z/aifs-ens/0p25/enfo/20261031000000-6h-enfo-cf.grib2` (+`-pf`) | cf ~54 MB, pf ~2.7 GB |

Byte-range ile tek parametre indirme denendi: index satırındaki `_offset/_length` ile `2t` alanı 206 döndü, `GRIB…7777` tam mesaj ✅.

**Çalıştırmalar ve adımlar** ✅ (listeleme)

| Ürün | Koşular | 00/12z | 06/18z |
|---|---|---|---|
| IFS oper / ENS `ef` | 00/06/12/18 | 0–144 sa 3'er, 150–360 sa 6'şar | 0–144 sa 3'er (Confluence tablosundaki "0–90h" gerçek dosyalarla çelişiyor) |
| AIFS Single / AIFS ENS | 00/06/12/18 | 0–360 sa 6'şar | aynı |

Yayın (portal zaman damgası, UTC): IFS 0.25 00z 07:34, 06z 12:27, 12z 19:34, 18z 00:27 (+1 gün); 0.1° bunlardan ~2 sa sonra. AIFS Single kademeli (00z 05:45→07:34); **yansılar AIFS'i portaldan önce alıyor** (S3'te 00z 360h 05:25) ✅. Resmî takvim: [Dissemination schedule](https://confluence.ecmwf.int/display/DAC/Dissemination+schedule).

**Saklama** ✅: Portal son ~12–13 çalıştırma (2–3 gün; gözlemde 13). Yansılarda silme görülmedi; yazılı saklama politikası ❓.

**Arşiv ve tarihçe** ✅ (AWS her tarih tarandı)
- AWS 2023-01-18'den; **2023-04-27…2023-05-02 boşluk** (Azure'da dolu). Azure 2022-01-21, GCS 2023-07-12.
- Yollar: 2023-01-18→2024-02-28 `0p4-beta/`; 2024-02-01→2024-02-28 `0p25/`; 2024-02-29→ `ifs/0p25/`; 2024-02-29→2025-02-24 `aifs/0p25/` (deneysel, 10 param); 2025-02-25 06z→ `aifs-single/`; 2025-07-01 06z→ `aifs-ens/`; 2026-05-12 06z 50r1 (06/18z `oper`, ENS `ef`'ten cf kalktı); 2026-10-20 06z→ `ifs/0p1/`.
- **IFS oper yüzey parametre seti zamanla genişledi** (spec'in Ocak 2024 hedefini doğrudan etkiliyor): Ocak 2024'te yalnız `10u 10v 2t lsm msl ro skt sp st tcwv tp` (çapraz kontrol ✅: `2d` yok). Eklenenler: `2d` 2024-03-06; `10fg`, `ptype`, `mx2t3/mn2t3` 2024-11-13; `tcc`, `sf`, `sd` 2025-11-21; `cp`, `lcc/mcc/hcc` 2026-10-20.

**0.1° IFS** ✅: 2026-10-20 06z'de başladı (aynı günün 00z'sinde yok — çapraz kontrol ✅); 0.25° devam ediyor; ikisi aynı ~9 km koşudan; yansılarda var; `enfo`, `wave`, `waef` de 0.1°'de. Parametre seti 0.25° ile aynı görünüyor ("extra fields" ❓). Aynı tarihten itibaren tüm açık veride bits-per-value düştü (`2t/2d` 9 bit) ([CF-738041093](https://confluence.ecmwf.int/pages/viewpage.action?pageId=738041093)). Duyuru: [What's new at 0.1°](https://confluence.ecmwf.int/pages/viewpage.action?pageId=738041087).

**Birimler (dikkat)** ✅: AIFS yağış kg m⁻² (=mm), IFS metre; AIFS bulut %, IFS 0–1 ([param-db](https://codes.ecmwf.int/grib/param-db/228228)).

**Faz 3 bulguları (2026-11-02)** ✅ — canlı adaptör bunlara göre yazıldı ([ADR-0005](decisions/0005-canli-model-hatti.md)):
- AWS yansısı tek bir `.index` isteğine bile `503 SlowDown` döndürdü → canlıda portal (`data.ecmwf.int`) kullanılıyor; portal index'leri < 0,5 sn'de geliyor.
- IFS 0.1° 06z koşusu 144 saatte bitiyor (150h index'i yok); 00z'de 150/168h var.
- Hamle parametresi: 0–90 sa `10fg`, 93–144 sa `10fg3`, 150+ sa `10fg` (03/06/93/96/144/150/168h index'lerinden). 0. adımda `tp`, `cp`, `sf` ve `10fg` 224 baytlık **sabit sıfır** mesajları (2026-11-03 düzeltmesi: önceki not "`_length` 0" diyordu, yanlış); `10fg` 0. adımda tanımsız olduğundan alınmaz, birikimlerde 0 başlangıç değeridir. `z` (orografi) yalnız 0. adımda.
- 0.1° mesaj boyutları (06z, MB): `2t` 1,4 · `2d` 1,4 · `tp` 1,1–2,3 · `msl` 2,2 · `10u/10v` 3,7 · `10fg` 3,1 · `tcc` 2,2 · `t@850` 1,2 · `lsm` 0,75 · `z` 4,0. Çalıştırma başına seçilen 13 yüzey + 1 basınç alanı: ~1,2–1,5 GB.
- `ptype` kodları ([param-db 260015](https://codes.ecmwf.int/grib/param-db/260015)): 0 yok, 1 yağmur, 3 donan yağmur, 5 kar, 6 sulu kar, 7 yağmur-kar, 8 buz taneleri, 12 donan çisenti.
- **Ensemble'lar (2026-11-03, index'lerden; [ADR-0006](decisions/0006-ensemble-hacim-plani.md)):** IFS ENS 0.25° `…/ifs/0p25/enfo/<stem>-<adım>h-enfo-ef.grib2` tek dosyada 50 pf (`number` 1–50, `type` pf; kontrol yok), adım başına 8.850 mesaj. **`z` (orografi) ENS açık verisinde yok** (0/96/144 sa index'leri) → IFS ENS sıcaklığına yükseklik düzeltmesi uygulanamıyor; `lsm` her adımda üye başına. Hamle kuralı deterministikle aynı (`10fg` ≤ 90 sa, `10fg3` 93–144 sa, `10fg` 150+ sa; 12z 90/93/150/168 sa'ten). AIFS ENS: `-enfo-cf` (kontrol, `number` yok) + `-enfo-pf` (1–50); `lsm` ve `z` 0. adımda ikisinde de. Mesajlar dosyada karışık sırada (seçilen 300 mesaj → 262 ayrı aralık) → istek birleştirme fayda etmiyor. IFS ENS 0.1° de var (`-ef-sfc`/`-ef-pl`), adım başına 5 kat büyük.
- **AIFS Single (2026-11-03):** yüzey ve basınç seviyesi tek dosyada (`…-<adım>h-oper-fc.grib2`, `-sfc/-pl` eki yok); index'te `levtype` alanı ayırıyor (`z` hem yüzeyde hem basınç seviyelerinde var → seçimde `levtype` şart). 0. adımda 126, sonra 122 mesaj; `lsm`, `z`, `sdor`, `slor` yalnız 0. adımda. IFS'ten farklı olarak 0. adımda `tp/cp/sf` boş değil (224 baytlık sabit sıfır). Hamle ve yağış tipi yok. Izgara 0,25° (1440×721), boylam 180°'den başlıyor (çözücü −180…180'e çeviriyor), CCSDS. Birimler mesajdan: `tp/cp/sf` kg m⁻² `stepType=accum` "0-6"; `tcc/lcc` %; `z` m² s⁻². Çalıştırma başına (≤168 sa, 29 adım) 321 mesaj, ~113 MB, 15–30 sn.

### 2.2 NOAA GFS 0.25°

**Erişim** ✅
- AWS `s3://noaa-gfs-bdp-pds` (us-east-1), anonim. SNS: `arn:aws:sns:us-east-1:123901341784:NewGFSObject` (Lambda/SQS).
- NOMADS: `https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/gfs.YYYYMMDD/HH/atmos/`; grib filter `filter_gfs_0p25.pl` (saatlik: `filter_gfs_0p25_1hr.pl`). **IP başına 120 istek/dk** (tüm NOMADS toplamı) ([SCN21-32](https://www.weather.gov/media/notification/pdf2/scn21-32nomad_changes.pdf)); grib filter döngülerinde 10 sn bekleme öneriliyor ([info](https://nomads.ncep.noaa.gov/info.php?page=gribfilter)). OpenDAP 2026-02-23'te kapandı. TLS 1.2+ zorunlu.
- GCS `gs://global-forecast-system` (2021-01-01'den); Azure `noaagfs` (kayan pencere, politika ❓).

**Dosya adı** ✅: `gfs.YYYYMMDD/HH/atmos/gfs.tHHz.pgrb2.0p25.fFFF` + `.idx`. Örnek: `s3://noaa-gfs-bdp-pds/gfs.20261031/12/atmos/gfs.t12z.pgrb2.0p25.f006` (537.598.222 B). `.idx` ile byte-range tek değişken indirme çalışıyor (206). **S3 `.idx` dosyalarında `CLMR`, NOMADS/GCS'de `CLWMR` yazıyor** (offset'ler aynı) — ayrıştırıcı ad farkına toleranslı olmalı.

**Çalıştırmalar** ✅: 00/06/12/18; f000–f120 saatlik, f123–f384 3 saatlik (209 dosya). S3'e varış: ilk adımlar ~T+3s33dk, f384 ~T+5s15dk; NOMADS 1–2 dk önde.

**Saklama/arşiv** ✅: NOMADS 10 gün. AWS en eski `gfs.20210101` (çapraz kontrol ✅); 2021-01-01→2026-10-31 arası **eksik gün yok**; `atmos/` alt dizini 2021-03-22 12Z'den (v16). NCEI'nin "trailing 30-day window" ifadesi listelemeyle çelişiyor; resmî saklama taahhüdü yok ⚠️.

**Faz 3 bulguları (2026-11-03, .idx ve mesajlardan ✅)**
- `.idx` satırı `no:offset:d=YYYYMMDDHH:DEĞİŞKEN:seviye:zaman:`; mesaj uzunluğu sonraki satırın offset'inden (son satır dosya sonuna kadar). S3'te olmayan nesne 404.
- Zaman metinleri: anlık `"<N> hour fcst"` (f000'da `"anl"`); `APCP`/`ACPCP` iki kayıt: kova (`"6-9 hour acc fcst"`; 120 sa sonrası 3 saatlik kova `"120-123"`) ve sürekli `"0-<N> hour acc fcst"` → sürekli kayıt alınıyor. f000'da birikim kaydı yok (başlangıç 0).
- `CRAIN/CSNOW/CFRZR/CICEP`, `TCDC`, `LCDC` hem anlık hem `"a-b hour ave fcst"` olarak var → anlık alınıyor. Bayraklar 0/1 (Code table 4.222).
- `VIS:surface` m (İstanbul kutusunda 0,5–24 km; üst sınır ~24.135 m), `GUST:surface` m/s anlık, `TCDC`/`LCDC` %, `APCP` kg m⁻², `LAND:surface` 0/1, `HGT:surface` m (orografi). Kar yağışının su eşdeğeri yok (`WEASD`/`SNOD` yerdeki kar).
- Izgara 0,25° (1440×721), boylam 0°'dan, `grid_complex_spatial_differencing`. Adım başına seçilen 16 alan ~9 MB.
- Hız: AWS'den 8 bağlantıyla 1–11 MB/sn (değişken); GCS yansısı (`https://storage.googleapis.com/global-forecast-system/…`, aynı yollar, Range destekli) 5–14 MB/sn — yedek kaynak.

**Sürüm** ✅: GFS v16.3 (`gfs.v16.3.34`). **GFSv17 "late 2027"** ([PNS26-29](https://www.weather.gov/media/notification/pdf_2026/pns26-29_Updated_Science_for_GFSv17_aaa.pdf)); dizin/ad değişecek; 0.5°/1° pgrb2 ve zaman ortalamalı CRAIN/CSNOW kaldırılacak ([PNS26-30](https://www.weather.gov/media/notification/pdf_2026/pns26-30_CommentsGFSv17_ProductRemoval.pdf)).

### 2.3 NOAA GEFS (v12.3, 31 üye)

**Erişim** ✅: AWS `s3://noaa-gefs-pds` (bucket adı teyit edildi; SNS `NewGEFSObject`); NOMADS `com/gens/prod/gefs.YYYYMMDD/HH/atmos/{pgrb2ap5,pgrb2bp5,pgrb2sp25}/`; grib filter `filter_gefs_atmos_0p25s.pl`, `_0p50a.pl`, `_0p50b.pl`; GCS `gs://gfs-ensemble-forecast-system`. AWS open-data-docs README'si eski (21 üye, v11) — güvenilmemeli.

**Dosya adı** ✅: `gefs.YYYYMMDD/HH/atmos/<dizin>/geXXX.tHHz.pgrb2{a,b,s}.{0p50,0p25}.fFFF[.idx]`; üyeler `gec00`, `gep01`–`gep30` (+`geavg`, `gespr`). Örnek: `gefs.20261031/12/atmos/pgrb2sp25/gep01.t12z.pgrb2s.0p25.f006`.

| Dizin | Çözünürlük | Ufuk/adım | İçerik |
|---|---|---|---|
| `pgrb2sp25` | 0.25° | f000–f240, 3 sa | 38 seçili yüzey alanı |
| `pgrb2ap5` | 0.5° | 0–240 3 sa, 246–384 6 sa (00Z 840 sa'e kadar) | basınç seviyeleri + temel yüzey |
| `pgrb2bp5` | 0.5° | aynı | ikincil alanlar |

0.25° tam set yok ✅. Varış: f000 ~T+3s47dk, f240 (s) ~T+5s30dk.

**Saklama/arşiv** ✅: NOMADS 4 gün. AWS en eski `gefs.20170101` (çapraz kontrol ✅), eksik gün yok; v12 `atmos/` düzeni 2020-09-23'ten. NCEI: "Data on the NODD is not officially archived" ⚠️ → kendi arşivimiz kritik.

**Faz 3 bulguları (2026-11-03, .idx'lerden ✅)**: HTTPS `https://noaa-gefs-pds.s3.amazonaws.com/gefs.YYYYMMDD/HH/atmos/pgrb2sp25/<üye>.tHHz.pgrb2s.0p25.fFFF`. `APCP` yalnız 6 saatlik kova: f003 `"0-3"`, f006 `"0-6"`, f009 `"6-9"`, f012 `"6-12"`, f078 `"72-78"`, f084 `"78-84"` (0–N kaydı yok). `pgrb2s` f000'da `HGT:surface` var, `LAND` yok (yalnız `pgrb2b` 0.5°'de) → kara maskesi aynı 0,25° ızgaradaki GFS `LAND`'dan. `GUST` anlık; kar miktarı yok; `TCDC`/kategorik bayraklar yalnız aralık ortalaması. Üye × adım başına temel 5 alan ~3,2 MB.

**Sürüm**: v12.3.23; 2026 SCN'leri dosya adı değiştirmedi ✅; GEFSv13 tarihi ❓.

**Ek (talep dışı)**: NOMADS'ta 2025-12-17'den beri AIGFS/AIGEFS (GraphCast tabanlı) ve HGEFS var; yalnız NOMADS, NODD yok ✅ ([SCN25-89](https://www.weather.gov/media/notification/pdf_2025/scn25-89_AIGFS_AIGEFS_and_HGEFS.pdf)).

### 2.4 DWD — ICON, ICON-EU, ICON-EPS, ICON-EU-EPS

**Zamanlama uyarısı** ✅ (çapraz kontrol: [DWD bülten 02.09.2026](https://www.dwd.de/DE/leistungen/opendata/neuigkeiten/opendata_september2026_1.html))
- Eski şema (`/weather/nwp/{icon,icon-eu,icon-eps,icon-eu-eps}/grib/…bz2`) **30.11.2026'dan sonra kapanıyor**.
- Yeni şema yalnız native üçgen ızgara, GRIB içi CCSDS sıkıştırma, EPS üyeleri ayrı dosyada. **ICON-EU regular-lat-lon ve VIS bitiyor; `/weather/lib/cdo/` siliniyor.**
- 2026-10-06'da ızgaralar değişti: ICON-EPS 26→20 km (#39), ICON-EU-EPS 13→10 km (#63), ICON-EU native #62 (genişletilmiş nest); ICON global #26 aynı ([bülten 28.07.2026](https://www.dwd.de/DE/leistungen/opendata/neuigkeiten/opendata_juli2026_2.html)).
- 2026-06-16'dan beri tüm dosyalar CCSDS (GRIB template 5.42): **ecCodes libaec ile derlenmiş olmalı**.

**Erişim** ✅: Anahtarsız HTTPS ([README](https://opendata.dwd.de/README.txt)). Yol: `/weather/nwp/v1/m/<model>/p/<PARAM>/[lvt1/<tip>/lv1/<seviye>/]r/<run ISO>/[e/<üye>/]s/<PTxxxHyyM>.grib2`. Fair-use/oran sınırı belgelenmemiş ❓.

| Model | v1 örneği (2026-10-31 18 UTC) |
|---|---|
| ICON | `…/v1/m/icon/p/T_2M/r/2026-10-31T18:00/s/PT000H00M.grib2` (3,3 MB) |
| ICON 850 hPa | `…/v1/m/icon/p/T/lvt1/100/lv1/85000/r/<run>/s/<step>.grib2` |
| ICON-EU | `…/v1/m/icon-eu/p/T_2M/r/2026-10-31T18:00/s/PT000H00M.grib2` (1,0 MB) |
| ICON-EPS | `…/v1/m/icon-eps/p/T_2M/r/2026-10-31T18:00/e/01/s/PT000H00M.grib2` (üye başına) |
| ICON-EU-EPS | `…/v1/m/icon-eu-eps/p/T_2M/r/2026-10-31T18:00/e/01/s/PT000H00M.grib2` |

Her dosya tek alan; `.idx` yok (gerek de yok). Sabit alanlar (`HSURF`, `FR_LAND`, `CLAT/CLON`) her çalıştırmada yayınlanıyor.

**Izgara ve İstanbul** ✅
- ICON global yalnız ikosahedral (#26 R03B07, 13 km); regular-lat-lon hiç yok. ICON-EU eski regular 0.0625° alanı 23.5°B–62.5°D / 29.5–70.5°K (indirilen dosyanın başlığından ✅) → İstanbul kapsanıyor. v1 native #62 "genişletilmiş": 768.608 hücre, CLAT/CLON 24,9–71,6°K / −25,5–64,0°D ✅ (2026-11-03, indirilen dosyadan) → İstanbul kapsanıyor.
- Nokta çıkarımı: `CLAT/CLON` ile 39 ilçe + istasyon için en yakın hücre/komşu ağırlık tablosu bir kez kurulur. Grid dosyaları `/lib/cdo` silindikten sonra [MPI dwd_grids.xml](http://icon-downloads.mpimet.mpg.de/dwd_grids.xml)'de; yeniden ızgaralama: [DWD regrid](https://gitlab.opencode.de/dwd/open-data/regrid-native-icon-grid).

**Çalıştırmalar** ✅ (listeleme; v1 zaman damgaları)

| Model | Koşular | Ufuk/adım | Yayın |
|---|---|---|---|
| ICON | 00/06/12/18 | 00/12: 180 sa, 06/18: 120 sa; 0–78 saatlik, sonra 3 sa | ~T+2s39 → +3s20 |
| ICON-EU | 00/06/12/18 (+03/09/15/21 kısa) | 120 sa; 0–78 saatlik, 81–120 3 sa | ~T+2s38 → +3s10 |
| ICON-EPS | 00/12 (06/18 yalnız 6 sa adım, 120 sa) | 180 sa; 1/3/6/12 sa | ~T+2s42 → +3s20 |
| ICON-EU-EPS | 00/06/12/18 | 120 sa; 1/3/6 sa | ~T+2s42 → +3s11 |

Üye sayısı: ICON-EPS ve ICON-EU-EPS **40** ✅ (GRIB `numberOfForecastsInEnsemble=40`).

**Saklama** ✅: ~24 saat; kaçırılan çalıştırma geri gelmez. **Resmî ücretsiz tahmin arşivi yok** (yalnız reanaliz `/REA/ICON-DREAM-*`).

**Faz 3 bulguları (2026-11-03, gerçek dosyalardan ✅)**
- Adımlar dizin listesinden: ICON 00/12z 0–78 saatlik + 81–180 3 saatlik (113 dosya), 06/18z 120 sa'e kadar (93); ICON-EU ana çalıştırmalar 93 dosya (120 sa), 03/09/15/21z kısa çalıştırmalar 0–51 sa.
- GRIB: `gridType=unstructured_grid`, `packingType=grid_ccsds`, `uuidOfHGrid` CLAT/CLON ile alanlarda aynı (ICON `a27b8de6…`, ICON-EU `832c1507…`); `numberOfGridUsed` 26 / 62. ICON 2.949.120 hücre. Çözme alan başına 8–34 ms (eccodes 2.50 + libaec).
- Dosya boyutları (tek alan, tüm küre/alan): ICON ~3–4,8 MB, ICON-EU ~0,8–1,1 MB; birikimli alanlar 0. adımda 197 baytlık sabit sıfır mesajı.
- **ICON global `VMAX_10M` 0. adımda yok (404)**; ICON-EU'da var. Hamle `max_i10fg`, `stepType=max`, aralık "0-1" → son 1 saat ([DWD ICON Database Reference 2.5.6](https://www.dwd.de/DWD/forschung/nwv/fepub/icon_database_main.pdf) §6.4: "Maxima are collected over hourly intervals").
- `RAIN_CON` eccodes'ta `crr`, birim "kg m**-2 s**-1" görünüyor; ama `stepType=accum`, aralık "0-1" ve ICON'da hiçbir hücrede `TOT_PREC`'i aşmıyor (ICON-EU'da 16 hücrede ≤ 0,13 mm paketleme farkı) → başlangıçtan beri birikim (kg m⁻²). Belge: `TOT_PREC = RAIN_GSP + SNOW_GSP + RAIN_CON + SNOW_CON`, hepsi "accumulated since model start".
- `WW`: "Significant weather of the last hour"; alabileceği değerler 0–3, 45, 48, 51–57, 61–67, 71–77, 80–86, 95, 96 (Database Reference Tablo 6.1, WMO 0 20 003 alt kümesi). ICON global'de 96 da görüldü (belge "yalnız ICON-D2" diyor).
- Kırpma (bölge kutusu + 1°): ICON 687 hücre, ICON-EU 2.751 hücre.
- **ICON-EU-EPS (2026-11-03):** 00/06/12/18z; 0–75 sa saatlik, 78–120 sa 3 saatlik; parametreler `T_2M`, `TOT_PREC`, `U/V_10M`, `VMAX_10M`, `PS`, `CLCT`, `SNOW_CON`, `SNOW_GSP`, `T` (çiy noktası ve `PMSL` yok). Sabitler (`CLAT/CLON/FR_LAND/HSURF`) üye dizininde (`…/r/<çalıştırma>/e/01/s/PT000H00M.grib2`; üyesiz yol 404). `VMAX_10M` 0. adımda yok. Izgara #63, 342.428 hücre; kırpmada 1.224. Üye × adım başına temel alanlar ~2,3 MB. ICON-EPS (global, #39): `T_2M`, `TD_2M`, `TOT_PREC`, `U/V_10M`, `VMAX_10M`, `PS`, `CLCT` (kar yok); üye × adım ~8 MB.
- v1 dizin adları: `T_2M`, `TD_2M`, `TOT_PREC`, `RAIN_CON`, `SNOW_CON`, `SNOW_GSP`, `U_10M`, `V_10M`, `VMAX_10M`, `PMSL`, `CLCT`, `CLCL`, `WW`, `T` (850 hPa: `lvt1/100/lv1/85000`), sabitler `CLAT`, `CLON`, `FR_LAND`, `HSURF` (yalnız 0. adım). ICON-EU'da ek olarak `CEILING`, `SNOWLMT` var; `VIS` hiçbirinde yok.

### 2.5 Météo-France — ARPEGE

**Erişim** ✅
- **Açık paketler (anahtarsız, önerilen):** data.gouv.fr [0.1°](https://www.data.gouv.fr/datasets/paquets-arpege-resolution-0-1deg) / [0.25°](https://www.data.gouv.fr/datasets/paquets-arpege-resolution-0-25deg) → OVH S3 `https://meteofrance-pnt.s3.rbx.io.cloud.ovh.net/pnt/<run>/arpege/{01,025}/<PAKET>/…` (listelenebiliyor).
- **Portal API (isteğe bağlı):** `https://public-api.meteofrance.fr/public/arpege/1.0` (WCS/WMS, alt alan + 0.05° `005-EURAT`) ve `…/previnum/DPPaquetARPEGE/v1/…`. Hesap + API anahtarı/OAuth2 gerekiyor (anahtarsız 401), **50 istek/dk**, ücretsiz. Kullanım lisansında CRPA L.322-1'e atıfla **"verileri değiştirme yasağı"** var → blend ürünü için yorum gerektirir (§9).

**Dosya adı** ✅: `arpege__{01|025}__{SP1|SP2|SP3|IP1-4|HP1-2}__{hhhHhhhH}__{YYYY-MM-DDTHH:00:00Z}.grib2`. Örnek: `…/pnt/2026-10-31T00:00:00Z/arpege/01/SP1/arpege__01__SP1__000H012H__2026-10-31T00:00:00Z.grib2` (74,8 MB, 325 mesaj; çapraz kontrol ✅). Paketler parametre grubu × adım aralığı; `.idx` yok ama S3 Range çalışıyor (mesaj başlıklarından kendi index'imiz kurulabilir). Sabit alanlar: `constant-eurat01.grib2` (orografi + kara-deniz maskesi). GRIB içi CCSDS.

**Izgara** ✅ (GRIB başlığı): EURAT01 0.1°, 741×521, 72°K–20°K, 32°B–42°D → **İstanbul kapsanıyor**. GLOB025 küresel. Model değişken çözünürlüklü (Fransa'da 7,5 km, uzakta kabalaşıyor; İstanbul'da etkin çözünürlük 0.1°'den kaba olabilir ⚠️).

**Çalıştırmalar** ✅: 00/06/12/18, paketlerde dördü de **102 saat**; 0.1° SP1 ana alanlar 0–102 saatlik. Dokümanlar (2025-10 ve 2026-09 PDF'leri) gerçek paketlerle çelişiyor → GRIB başlığı esas. Yayın (S3): 00Z 02:53–03:28, 06Z 09:40–10:18, 12Z 14:32–15:08, 18Z 21:41–22:25 (0.1°).

**Lisans netleştirmesi (2026-11-01)** ✅: data.gouv.fr API'sinde her iki paket veri kümesinin lisansı `lov2` (Licence Ouverte / Open Licence 2.0), yayıncı Météo-France. Licence Ouverte 2.0 metni yeniden kullanımı "à des fins commerciales ou non" serbest bırakıyor; uyarlama, türetme ve başka bilgilerle birleştirme açıkça izinli ([LO 2.0](https://www.etalab.gouv.fr/wp-content/uploads/2017/04/ETALAB-Licence-Ouverte-v2.0.pdf)). Météo-France açık veri sayfası: "Sans redevance sous Licence Ouverte d'Etalab", kaynak "Météo-France". **CC BY-NC yalnız TIGGE'deki Météo-France verisi (PEARP ensemble) için geçerli**; o kopya kullanılmaz. Sonuç: ARPEGE canlıda kalır, geçmişi olmadığı için "yetersiz geçmiş".

**Saklama** ✅: S3 ~15 gün (2026-10-17 → 2026-10-31 gözlendi; resmî değil ❓). API paketleri 24 saat kayan. **Ücretsiz arşiv yok**; resmî arşiv talep üzerine `vd@meteo.fr` (EURAT01 2010-04-06'dan; ücret ❓). AWS `mf-nwp-models` bucket'ı ölü (yalnız 2019'dan 18 statik dosya) ✅.

### 2.6 UK Met Office — Global Deterministic 10 km (+ MOGREPS-G)

**Erişim** ✅: AWS `s3://met-office-atmospheric-model-data/global-deterministic-10km/` (eu-west-2), anonim, requester-pays değil. SNS: `arn:aws:sns:eu-west-2:633885181284:met-office-atmospheric-model-data-object_created`. "Free, unsupported basis"; oran sınırı yayınlanmamış ❓. MOGREPS-G: `s3://met-office-global-ensemble-model-data/global-ensemble/YYYY/MM/DD/THHMMZ/`.

**Dosya adı** ✅: `global-deterministic-10km/{RUN:YYYYMMDDTHHMMZ}/{VALID:YYYYMMDDTHHMMZ}-PT{hhhh}H{mm}M-{parametre}.nc` — **dosya adının başındaki zaman geçerlilik zamanı.** Örnek: `…/20261031T1200Z/20261031T1300Z-PT0001H00M-precipitation_accumulation-PT01H.nc`. Format NetCDF-4/HDF5 (CF-1.7), dosya başına 1 parametre × 1 adım; `.idx` yok ama HDF5 chunk'ları (128×128) + S3 Range ile kısmi okuma çalışıyor (158 MB'lık T850 dosyasından İstanbul kutusu ~11 MB ile okundu ✅).

**Izgara** ✅: Global 2560×1920 (0.140625° × 0.09375°); İstanbul kutusunda 11×15 nokta. MOGREPS-G 1280×960 (~20 km).

**Çalıştırmalar** ✅: 00/06/12/18. 00/12Z T+168; 06/18Z T+69. Adımlar: 0–54 saatlik, 57–144 3 sa, 150–168 6 sa. Gözlenen yayın: T+5,5–7,5 sa. MOGREPS-G: T+246, çalıştırma başına 18 üye.

**Saklama/arşiv** ✅: Deterministik **2 yıl kayan** — en eski 20241030T1800Z (çapraz kontrol ✅). MOGREPS-G 30 gün kayan. Parametre seti iki kez değişti: `height_of_orography` 2025-12-12'den; 2026-01-21 12Z'den yeni set (`geopotential_height_on_pressure_levels` vb.). Microsoft Planetary Computer aynası 2023-12'den görünüyor ama 2024-01-01 sorgusu boş döndü ⚠️❓.

**Önemli eksikler** ✅: Deterministikte **u/v yok** (hız + yön var), **kara-deniz maskesi yok**, **konvektif yağış birikimi yok**, kar birikimi ve kategorik yağış tipi yok. 2 m sıcaklık aslında **1,5 m** (`temperature_at_screen_level`).

**Lisans**: CC BY-SA 4.0 — spec §11 gereği karar verilene kadar yalnız iç doğrulama.

### 2.7 ECCC — GDPS (GEM global) ve GEPS

**Erişim** ✅ (çapraz kontrol: yeni yol 206, eski yol 404)
- `https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_gdps/15km/{HH}/{hhh}/` (ayrıca `/today/…`). **Tarih dizini çalıştırma günü değil, yayın (varış) günü** → yol üretmek yerine bildirimdeki tam yolu kullanmalı.
- GDPS 10.0, 2026-05-26 12Z'den ([dd_info](https://eccc-msc.github.io/open-data/msc-datamart/readme_en/)): dosya adı `CMC_glb*` → `YYYYMMDDTHHZ_MSC_GDPS*`, boylam 0..360.
- **Kullanım politikası** ([usage-policy](https://eccc-msc.github.io/open-data/usage-policy/readme_en/)): sistematik indirmede **AMQPS (Sarracenia) zorunlu**, dizin taraması yapılmamalı; günde ≥86.400 istek için iletişim; anlamlı User-Agent. Broker `amqps://dd.weather.gc.ca:5671` (anonymous/anonymous) ✅; GDPS subtopic `*.WXO-DD.model_gdps.15km.#` ⚠️ (resmî örnekler eski yolu gösteriyor).
- Yedek: HPFX `hpfx.collab.science.gc.ca` (doküman 30 gün, gözlenen 53 gün).

**Dosya adı** ✅: `{YYYYMMDD}T{HH}Z_MSC_GDPS_{VAR}_{LVLTYPE-LVL}_LatLon0.15_PT{hhh}H.grib2`. Örnek: `https://dd.weather.gc.ca/20261031/WXO-DD/model_gdps/15km/12/006/20261031T12Z_MSC_GDPS_Precip-Accum_Sfc_LatLon0.15_PT006H.grib2`. GEPS hâlâ eski ad: `CMC_geps-raw_{VAR}_{LVLTYPE}_{LVL}_latlon0p5x0p5_{YYYYMMDDHH}_P{hhh}_allmbrs.grib2` (21 mesaj = 20 pert. + kontrol).

**Izgara** ✅: GDPS 2400×1201, 0.15° global. GEPS Datamart'ta 0.5° (İstanbul kutusunda ~2×5 nokta ⚠️).

**Çalıştırmalar** ✅: GDPS yalnız **00/12** (06/18 Datamart'ta yok), 240 sa; 0–84 saatlik (yüzey alt kümesi), 87–168 3 sa, 171–240 6 sa. Yayın 00Z 03:40–04:56, 12Z 15:38–16:58. GEPS 00/12, 384 sa (Pzt/Per 00Z 936 sa).

**Saklama/arşiv** ✅: Datamart 30 gün. **Resmî ücretsiz arşiv yok** (arşivden çekme saatlik 118 $). TIGGE'de GDPS 2021-06'dan, 0.25°, CC BY 4.0.

### 2.8 Değişken matrisi — deterministik modeller

✅ = gerçek dosya/index/dizin listesinden. Tarihli notlar, parametrenin açık veriye eklendiği tarih.

| Değişken | ECMWF IFS | AIFS Single | GFS | ICON / ICON-EU | ARPEGE 0.1° | UKMO Global | GDPS |
|---|---|---|---|---|---|---|---|
| 2 m sıcaklık | `2t` | `2t` | `TMP:2 m` | `t_2m` | T(2m) 0/0/0 (SP1) | `temperature_at_screen_level` (1,5 m) | `AirTemp_AGL-2m` |
| Çiy noktası / nem | `2d` (2024-03-06+) | `2d` | `DPT`, `RH:2 m` | `td_2m`, `relhum_2m` | TD(2m) (SP2), HU(2m) (SP1) | dew point + RH | `DewPoint`, `RelativeHumidity` |
| Toplam yağış | `tp` (m) | `tp` (kg m⁻²) | `APCP` | `tot_prec` | PRECIP | `precipitation_accumulation-PT01H/03H/06H` | `Precip-Accum_Sfc` |
| Konvektif yağış | `cp` (2026-10-20+) | `cp` | `ACPCP` | `rain_con`+`snow_con` | PREC_CONVEC | yalnız oran (birikim yok) | `ConvectivePrecip-Accum` |
| Kar / yağış tipi | `sf` (2025-11-21+), `ptype` (2024-11-13+) | `sf`; ptype yok | `CSNOW/CRAIN/CFRZR/CICEP`, `CPOFP`, `WEASD`, `SNOD` | `snow_con`, `snow_gsp`, `ww` (EU'da `snowlmt`) | NEIGE, PTYPE_60 | `snowfall_rate` (anlık); birikim ve tip yok | `Snow-Accum`, `PrecipType-Instant` |
| 10 m rüzgâr | `10u/10v` | `10u/10v` | `UGRD/VGRD` | `u_10m/v_10m` | U/V(10m) | hız + yön (**u/v yok**) | `WindU/WindV` |
| Hamle | `10fg`, `10fg3` (2024-11-13+) | **yok** | `GUST` | `vmax_10m` | FF_RAF | `wind_gust_at_10m`, `_max-PTnnH` | `WindGust` |
| MSLP | `msl` | `msl` | `PRMSL`, `MSLET` | `pmsl` | P(mer) | `pressure_at_mean_sea_level` | `Pressure_MSL` |
| Toplam bulut | `tcc` 0–1 (2025-11-21+) | `tcc` % | `TCDC` | `clct` | NEBUL | `cloud_amount_of_total_cloud` | `TotalCloudCover` |
| Alçak bulut | `lcc` (2026-10-20+) | `lcc` % | `LCDC` | `clcl` | NEBBAS (SP2) | `cloud_amount_of_low_cloud` | **yok** |
| Görüş | **yok** | **yok** | `VIS` | yalnız ICON-EU `vis` — **30.11.2026'da bitiyor** | VISIN_60 (1 sa min.) | `visibility_at_screen_level` | **yok** |
| 850 hPa sıcaklık | `t`@850 | `t`@850 | `TMP:850 mb` | `t` 850 | T izobarik (IP1; başlıkta görülmedi ⚠️) | `temperature_on_pressure_levels` | `AirTemp_IsbL-0850` |
| Deniz yüzeyi sıcaklığı | yok (`skt` vekil ⚠️) | yok | `TMP:surface`+`LAND` | `t_so` lv0 / `t_g` (analizden, prognostik değil) | yok (T(sol) vekil ⚠️) | yok (`temperature_at_surface` vekil ⚠️) | `SeaWaterTemp_Sfc` (000) |
| Orografi | `z` (adım 0) | `z` | `HGT:surface` | `hsurf` | ALTITUDE (sabit dosya) | `height_of_orography` (2025-12-12+) | `GeopotentialHeight_Sfc` |
| Kara-deniz maskesi | `lsm` | `lsm` | `LAND` | `fr_land` (oran) | 2/0/0 (sabit dosya) | **yok** | `LandWaterProportion` |

**Ensemble'lar (özet)**

| | IFS ENS | AIFS ENS | GEFS | ICON-EPS | ICON-EU-EPS | MOGREPS-G | GEPS |
|---|---|---|---|---|---|---|---|
| Üye | 50 pf (+ oper fc) | cf + 50 pf | 31 | 40 | 40 | 18/çalıştırma | 21 |
| Çözünürlük (açık veri) | 0.25° / 0.1° | 0.25° | 0.25° (s) / 0.5° | 20 km native | 10 km native | ~20 km | 0.5° |
| Hamle | `10fg/10fg3` | yok | `GUST` | `vmax_10m` | `vmax_10m` | ❓ | yok (yalnız olasılık ürünü) |
| MSLP | `msl` | `msl` | `PRMSL` | yok (`ps`) | yok (`ps`) | ❓ | `PRMSL` |
| 2 m nem | `2d` | `2d` | `DPT`/`RH` | `td_2m` | **yok** | ❓ | `RH` (Td yok) |
| T850 | ✓ | ✓ | `pgrb2a` | yok | ✓ | ❓ | ✓ |
| Kara-deniz | `lsm` | `lsm` | `LAND` (b) | `fr_land` | `fr_land` | `landsea_mask` | yok |

MOGREPS-G'nin tam değişken listesi çıkarılmadı ❓ (bilinen ekler: `rainfall_accumulation_from_convection`, `snowfall_accumulation`, `landsea_mask`).

### 2.9 Birikim kuralları, hamle tanımları ve zaman adımları

Spec §5.1'deki tuzakların modele göre karşılığı. Hepsi GRIB/NetCDF başlıklarından (PDT 4.8/4.11, `cell_methods`) ve resmî dokümandan ✅.

| Model | Yağış birikimi | Hamle tanımı | Not |
|---|---|---|---|
| ECMWF IFS / ENS | Başlangıçtan beri (m) | `10fg`: 0–90 sa **son 1 sa**; 93–144 sa `10fg3` son 3 sa; 150–360 sa `10fg` son 6 sa ([param-db 49](https://codes.ecmwf.int/grib/param-db/49)) | 0–90 sa'te 3 saatlik aralığın ilk 2 saatinin hamlesi veride yok |
| AIFS Single / ENS | Başlangıçtan beri (kg m⁻²) | yok | |
| GFS | **Aynı dosyada iki kayıt:** 6 saatlik kova (f007 "6-7", f009 "6-9", … 120 sa sonrası da 6 saatte sıfırlanır) **ve** 0–N sürekli kayıt ("0-9 hour acc") | `GUST` **anlık** tanı alanı (UPP `CALGUST.f`) | f001–f006'da iki kayıt aynı metni taşır; sıra önce kova. Öneri: 0–N kaydı al, ardışık fark |
| GEFS | **Yalnız 6 saatlik kova** (0–N kaydı yok) | `GUST` anlık | |
| ICON ailesi | Başlangıçtan beri | `vmax_10m`: **son 60 dk** — 3/6 saatlik adımlarda da | |
| ARPEGE | Başlangıçtan beri | FF_RAF: son 1 sa max (0.25°'nin 3 saatlik bölümünde de) | |
| UKMO Global | **Aralık toplamı** (önceki 1/3/6 sa; `cell_methods: time: sum`) | `wind_gust_at_10m`: geçerlilik zamanından önceki 10 dk'daki en yüksek 3 sn ortalaması (Global PDF); `_max-PTnnH`: önceki 1/3/6 sa'in maksimumu. MOGREPS-G PDF'i "anlık" diyor ⚠️ | |
| GDPS | `Precip-Accum` başlangıçtan beri; `Accum1h/3h` aralık | `WindGust` anlık; `WindGust-Max` TKE'den anlık parametrize (2019 duyurusu ⚠️) | |
| GEPS | Başlangıçtan beri | raw'da yok | |

**Sonuç:** Hiçbir model "3 saatlik aralığın gerçek maksimum hamlesi"ni tutarlı biçimde vermiyor. Hamle tanımı (`instant`, `max_1h`, `max_3h`, `max_6h`, `max_10min_3s`) model × adım bazında metadata olarak kaydedilmeli ve METAR/SYNOP hamle doğrulaması tanıma göre ayrılmalı.

---

## 3. Geçmiş model verisi (Ocak 2024 → bugün)

### 3.1 Kapsama tablosu

Ticari = ticari kullanıma uygun mu. Tüm başlangıç tarihleri doğrudan listeleme/STAC/API ile ✅ (aksi belirtilmedikçe).

| Model | Önerilen arşiv(ler) | Kapsam | Ufuk / adım | Format | Lisans | Ticari |
|---|---|---|---|---|---|---|
| IFS HRES | ECMWF açık veri yansıları (Azure + AWS) | 2024-01 tamamı (0.4°, dar parametre seti, `2d` yok); 0.25° 2024-02-01'den | 0–240 / 3–6 sa | GRIB2 + index | CC BY 4.0 | Evet |
| IFS HRES (ek) | TIGGE | 2006+ | 0–240 / 6 sa, 00/12Z | GRIB | CC BY 4.0 | Evet |
| IFS ENS | Source Coop `dynamical/ecmwf-ifs-grib` (MARS'tan) | 2016-03-08 – 2024-03-31, yalnız 00Z, 0.25° | 0–360 sa | GRIB1 + JSON idx | CC BY 4.0 | Evet |
| IFS ENS | dynamical `ecmwf-ifs-ens-forecast-15-day-0-25-degree` | 2024-04-01 → bugün, yalnız 00Z | 0–144/3 sa, 144–360/6 sa | Icechunk | CC BY 4.0 + ToU | Evet |
| IFS ENS (diğer koşular) | açık veri yansıları `enfo` | 2023-01-18 → (0.4° sonra 0.25°) | | GRIB2 | CC BY 4.0 | Evet |
| AIFS Single | dynamical `ecmwf-aifs-single-forecast` | **2024-04-01** → | 0–360 / 6 sa | Icechunk | CC BY 4.0 + ToU | Evet |
| AIFS Single (ek) | AWS `aifs/0p25/` (deneysel, 10 param) | 2024-02-29 → 2025-02-24 | | GRIB2 | CC BY 4.0 | Evet |
| AIFS ENS | dynamical `ecmwf-aifs-ens-forecast` / yansılar | **2025-07-01/02** → (model daha önce operasyonel değil) | 0–360 / 6 sa | Icechunk / GRIB2 | CC BY 4.0 + ToU | Evet |
| GFS | AWS `noaa-gfs-bdp-pds` | 2021-01-01 →, eksiksiz | 0–384 | GRIB2 + idx | NOAA | Evet |
| GFS (ek) | dynamical `noaa-gfs-forecast(-virtual)`; NCAR GDEX d084001 | 2021-05-01 →; 2015-01-15 → | | Icechunk; GRIB2 | CC BY 4.0 | Evet |
| GEFS | AWS `noaa-gefs-pds` | 2017-01-01 →, eksiksiz | 0–384 | GRIB2 + idx | NOAA | Evet |
| GEFS (ek) | dynamical `noaa-gefs-forecast-35-day` vb. | 2020-10-01 → | | Icechunk | CC BY 4.0 | Evet |
| ICON global | TIGGE (DWD) | 2020-03 →, **0.5°, 00/12Z, 0–180/6 sa, hamle/görüş yok** | | GRIB | CC BY 4.0 | Evet |
| ICON global (ek) | OCF Hugging Face `openclimatefix/dwd-icon-global` | 2023-03 – 2025-08-12, boşluklu (2024-04 kısmi, 2024-05, 2025-02/03 yok), **gated** | ~48–96 sa ⚠️ | zarr.zip, ikosahedral | CC BY 4.0 | Evet |
| ICON-EU | OCF HF `openclimatefix/dwd-icon-eu` | 2020 – 2025-08-12, aynı boşluklar, **gated** | ~0–120 sa ⚠️ | zarr.zip | CC BY 4.0 | Evet |
| ICON-EU | dynamical `dwd-icon-eu-forecast-5-day` + Source Coop GRIB | **2026-02-10** → | 0–78/1 sa, 81–120/3 sa | Icechunk / GRIB2.bz2 | CC BY 4.0 | Evet |
| ICON-EPS | TIGGE (DWD, 40 üye) | 2020-03 →, 0.5°, 00/12Z | 0–180 / 6 sa | GRIB | CC BY 4.0 | Evet |
| ICON-EU-EPS | — | **bulunamadı** | | | | |
| ARPEGE | — (TIGGE MF yalnız PEARP ve CC BY-NC) | **bulunamadı** | | | | |
| UKMO Global | AWS Met Office | **2024-10-30T18Z → (kayan 2 yıl)** | 0–168 | NetCDF | CC BY-SA 4.0 | Belirsiz |
| MOGREPS-G | TIGGE (UKMO) | 2006 → | 0–246 | GRIB | **CC BY 4.0** | Evet |
| GDPS | TIGGE (ECCC) | 2021-06 →, 0.25°, 00/12Z | 0–240 / 6 sa, kar/hamle/görüş yok | GRIB | CC BY 4.0 | Evet |
| GEPS | TIGGE (ECCC) | ✓ | 0–384 / 6 sa | GRIB | CC BY 4.0 | Evet |

TIGGE notları ✅: erişim ECMWF hesabı + lisans kabulü ister (proje sahibi yapmalı); 48 saat gecikmeli; alt bölge kesimi yapılabiliyor; ortak değişkenler T2m, Td, 10 m u/v, MSLP, tp, tcc, basınç seviyeleri — **hamle ve görüş yok**. ECDS kota/maliyet ❓.

dynamical notları ✅: `data.dynamical.org` 2026-09-30'da emekliye ayrıldı ([migration-2026](https://dynamical.org/migration-2026/)); eski URL'ler hâlâ 200 dönüyor ama `Sunset: 2026-10-01` başlığı taşıyor, güvenilmemeli. Erişim: STAC'tan `icechunk-https` asset'i her açılışta çözülmeli (Icechunk 2, Python 3.12+). Ayrıca anahtarsız nokta API'si `api.dynamical.org/v1/forecasts` (beta; 30 istek/10 sn). STAC'taki atıf metinleri kullanılmalı (ör. "ECMWF AIFS Single forecast data processed by dynamical.org from ECMWF Open Data."). "Virtual" veri kümeleri tam ızgara × tek adım chunk'lı → uzun dönem nokta çıkarımı için materialized olanlar tercih edilmeli.

### 3.2 Arşivi olmayan model / dönem kombinasyonları (spec §5.2.3)

Bunlar doğrulama tablosunda **"yetersiz geçmiş"** olarak işaretlenecek:

| Model | Eksik dönem | Not |
|---|---|---|
| ARPEGE (det.) | 2024-01 → bugün (tamamı) | Kendi arşivimiz ilk canlı ingest gününden başlar; resmî ücretli arşiv sorulabilir |
| ICON-EU-EPS | Tamamı | |
| UKMO Global | 2024-01-01 → 2024-10-30 | Kayan pencere: her gün bir gün daha kayboluyor |
| ICON-EU | 2025-08-13 → 2026-02-09 | 2024-01 → 2025-08 yalnız OCF'de (gated, boşluklu) |
| ICON global (tam çözünürlük) | 2025-08-13 → bugün | Yalnız TIGGE 0.5°, 00/12Z, 6 sa adım |
| AIFS Single | 2024-01-01 → 2024-03-31 (ham deneysel veri 2024-02-29'dan) | |
| AIFS ENS | 2024-01 → 2025-06-30 | Model yoktu |
| IFS ENS 06/12/18Z | dynamical/MARS backfill'de yok | Yansılarda ham GRIB var |
| ECMWF IFS (tümü) | 2024-01 → 2024-03-05 arası `2d` yok; hamle/ptype 2024-11-13 öncesi yok; `tcc`/`sf` 2025-11-21 öncesi yok | Değişken bazında "yetersiz geçmiş" |
| GDPS, ICON, ICON-EPS | 06/18Z, 6 saatten ince adım, hamle, görüş | Yalnız TIGGE var |

**Model sürüm kırılmaları** (bias eğitiminde dönem ayırıcı olarak `models` metadata'sına yazılmalı): ECMWF 50r1 2026-05-12; ECMWF 0.1° + düşük bits-per-value 2026-10-20; GDPS 10.0 2026-05-26; ICON ızgara değişikliği 2026-10-06; UKMO parametre seti 2026-01-21.

### 3.3 Ticari kullanıma uygun olmayan arşivler

- **TIGGE'deki Météo-France (PEARP), JMA, CMA, BoM, CPTEC, IMD, NCMRWF verisi**: CC BY-NC 4.0 ✅.
- **ECMWF MARS**: Veri CC BY 4.0, ama ticari kullanıcı için Web API/arşiv erişimi ayrı hizmet sözleşmesi ve ücret gerektiriyor (3.000 €/yıl hizmet ücreti) ✅ ([tariffs](https://www.ecmwf.int/en/forecasts/accessing-forecasts/payment-rules-and-options/tariffs)). Ekim 2025 açılımı arşive ücretsiz erişim getirmedi ✅.
- **Source Coop `bkr/icon`** (ham ICON global GRIB aynası 2026-03-12 – 2026-10-15): lisans belirtilmemiş ❓ → kullanılmamalı.
- **ECCC arşivi**: veri ücretsiz ama çekme saatlik 118 $ ✅.

### 3.4 Open-Meteo (yalnız envanter — kullanılmayacak)

Proje sahibi model verisinin Open-Meteo'dan alınmamasına karar verdi. Bilgi için: `s3://openmeteo` (CC BY 4.0; UKMO kaynaklı veri upstream'de CC BY-SA). `data/` katmanı modeller arası birleştirilmiş zaman serisi (ufuk/init bilgisi yok) → ufuk bazlı doğrulamaya uygun değil; run bazlı katman AWS'te yalnız 3 ay ✅.

---

## 4. Gözlemler

### 4.1 METAR

**Canlı — AWC Data API** ✅ (çapraz kontrol)
- `GET https://aviationweather.gov/api/data/metar?ids=LTFM,LTFJ,LTBA&format=json&hours=N` ([Data API](https://aviationweather.gov/data/api/), [OpenAPI 3.1](https://aviationweather.gov/data/schema/openapi.yaml)).
- Parametreler: `ids`, `bbox`, `format` (`raw|decoded|json|geojson|xml|iwxxm`; csv yok), `hours`, `date` (`yyyymmdd_hhmm`), `taf`. Belgelenmemiş parametre 400; veri yoksa 204.
- Sınırlar: **en fazla 30 gün geriye** (`date=20240115_1200` → 400 "Data is available for up to 30 days"); **100 istek/dk**; istek başına en fazla 400 kayıt; özel User-Agent isteniyor; toplu ihtiyaç için `/data/cache/metars.cache.csv.gz` (dakikalık). CORS yok → yalnız backend'den.
- İstanbul: **LTFM, LTFJ, LTBA üçü de yayında** (LTBA hâlâ METAR + TAF yayınlıyor); 30 dakikada bir (:20, :50). `reportTime` :50 gözlemini sonraki saate yuvarlıyor → gerçek zaman için `obsTime`.
- Alanlar: `temp, dewp, wdir, wspd, wgst, visib` ("6+" gibi metin, statute mil), `altim` (QNH, hPa), `clouds[]`, `wxString`, `rawOb`. **Türk METAR'larında `slp` ve yağış miktarı yok.** LTFJ'de anlamsız `maxT` değerleri görüldü → QC.
- İstasyon meta: LTFM 41.262/28.740/99 m; LTFJ 40.899/29.309/83 m (OSCAR/MGM 99 m — tutarsız; AWC il kodunu "KO" yazıyor); LTBA 40.982/28.821/33 m.
- Çevre: LTBX Samandıra ve LTBP Yalova yalnız TAF; LTBW Hezarfen yok; **LTBU Çorlu** (Tekirdağ, İstanbul dışı) ve LTBQ (Kocaeli) METAR yayınlıyor.

**Geçmiş METAR (Ocak 2024+)**

| Kaynak | Kapsam | Erişim | Lisans | Değerlendirme |
|---|---|---|---|---|
| **IEM ASOS/METAR** | LTBA 1945, LTFJ 2003-11-18, LTFM 2018-11-02, LTBU 2005 ✅; 2024-01-01 isteği veri döndürdü ✅ | `https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=LTFM&data=…&sts=…&ets=…&tz=Etc/UTC&format=onlycomma`; IP başına 1 istek/sn | "public domain and may be used freely by anyone for any lawful purpose" (çapraz kontrol ✅) | **Önerilen** |
| NOAA NCEI ISD → GHCNh v1 | ISD 2025-08'de dondu; GHCNh günlük güncelleniyor (LTFM, LTFJ, 17061 için 2024 dosyaları var) | NCEI | Güncel metadata'da ticari kısıt yok; eski (2017) bildirimde ABD dışı veride WMO Res. 40 kısıtı vardı ⚠️ | Belirsiz → yalnız iç kullanım / yazılı teyit |
| OGIMET | SYNOP + METAR | kişisel sunucu | Telif kaynak kuruma ait, "read WMO resolution 40" ✅ | **Ticari kullanım için uygun değil** |

Lisans: AWC verisi NWS feragatnamesine göre kamu malı; koşullar: kendi verin gibi sunmamak, NOAA/NWS onayı ima etmemek, değiştirip resmî materyal gibi sunmamak ([disclaimer](https://www.weather.gov/disclaimer)) ✅. Türkiye kaynaklı (DHMİ/MGM) METAR'ların ticari yeniden dağıtımı hiçbir birincil kaynakta ayrıca ele alınmamış ❓. Öneri: ham METAR'ı yeniden dağıtmadan doğrulamada kullanmak; gösterimde "Kaynak: NOAA/NWS AWC" atfı.

**Faz 2 bulguları (2026-11-02)** ✅ — değerler bu yüzden ham METAR'dan kendi ayrıştırıcımızla çözülüyor
([ADR-0004](decisions/0004-metar-ham-metinden-ayristirma.md)):
- AWC JSON: boş alanlar anahtarıyla birlikte düşüyor (ör. `wgst`, `slp` yok); `visib` statute mile
  (4100 m → 2,55; 9999 → `"6+"`); `rawOb` `"METAR LTFJ …"` önekiyle geliyor.
- IEM `asos.py`: `data=metar` ham metni öneksiz verir; `report_type=3` (rutin) ve `4` (SPECI) birlikte
  istenir. Çözülmüş alanlarda sıcaklık °F, görüş mil; ölçülemeyen görüşü (`////`) 6,21 mil (10 km)
  yazıyor, Türk METAR'larında olmayan yağışı `p01i=0.00` diye dolduruyor, `RESHRA`'yı hadise
  sayıyor → bu alanlar kullanılmıyor.
- 2025'te üç istasyonda 52.844 METAR (istasyon başına ≈ 48/gün); SPECI görülmedi. Ayrıştırıcı hepsini
  başlık hatası ve tanınmayan grup olmadan çözdü.
- Rutin METAR zamanları :20 ve :50; AWC'de yayın gecikmesi ≈ 5–8 dakika (`receiptTime`).

### 4.2 MGM "Son Durumlar" — BEKLEMEDE

> **Durum (2026-11-01, proje sahibi kararı):** Doğrudan kullanım **iptal edildi**. `servis.mgm.gov.tr`'ye istek gönderilmez ve MGM erişim kısıtını aşmaya yönelik kod yazılmaz. MGM verisi yalnızca MGM'nin yazılı izni veya MEVBİS lisansıyla resmî yoldan gelirse eklenir; o zamana kadar bu kaynak "beklemede". Aşağıdaki teknik bulgular yalnız Faz 0 kaydı olarak duruyor; uygulamada kullanılmaz.

**Tespit yöntemi (2026-10-31 / 2026-11-01):** mgm.gov.tr sayfalarının yüklediği betikler incelendi:
- `https://www.mgm.gov.tr/sondurum/js/sondurumlar.js?v=3` ("Son Gözlemler" — `https://www.mgm.gov.tr/sondurum/turkiye.aspx`)
- `https://www.mgm.gov.tr/Scripts/ziko16_js/angularService/ililceler.js?v=4` ("İl ve İlçe Merkezleri" — `https://www.mgm.gov.tr/tahmin/il-ve-ilceler.aspx?il=İstanbul`)

Taban adres: `https://servis.mgm.gov.tr/web` (Express/nginx arkasında JSON servis). Not: spec'te geçen `https://www.mgm.gov.tr/sondurumlar/` adresi 404 veriyor; doğru sayfa `sondurum/turkiye.aspx`.

| Uç nokta | Kullanan sayfa | İçerik | Durum |
|---|---|---|---|
| `GET /istasyonlar/il?plaka=34` | sondurum/turkiye.aspx | İldeki istasyonların meta verisi: `istNo, istAd, enlem, boylam, yukseklik, ilPlaka, il, ilce` | ✅ 2026-10-31 21:43Z çağrıldı, 45 kayıt |
| `GET /sondurumlar/ilTumSondurum?ilPlaka=34` | sondurum/turkiye.aspx | İldeki tüm istasyonların son gözlemi, **tek toplu istek** | ✅ aynı anda çağrıldı, 42 kayıt |
| `GET /sondurumlar/ilmerkezleri` | sondurum/turkiye.aspx | 81 il merkezinin son durumu | ⚠️ betikte görüldü, çağrılmadı |
| `GET /sondurumlar?merkezid={merkezId}` | il-ve-ilceler.aspx | Tek merkezin son durumu | ⚠️ betikte görüldü, çağrılmadı |
| `GET /merkezler?il={il}[&ilce={ilce}]` | il-ve-ilceler.aspx | Merkez meta verisi; betik `merkezId`, `sondurumIstNo` (dolaylı), `saatlikTahminIstNo`, `gunlukTahminIstNo` alanlarını kullanıyor | ⚠️ betikte görüldü, çağrılmadı |
| `GET /merkezler/iller`, `/merkezler/ililcesi?il=`, `/merkezler?sorgu=…&limit=50`, `/merkezler/lokasyon?enlem=&boylam=` | il-ve-ilceler.aspx | Merkez listeleri / arama | ⚠️ betikte görüldü |
| `GET /tahminler/saatlik?istno=`, `/tahminler/gunluk?istno=`, `/ucdegerler?merkezid=&ay=&gun=` | il-ve-ilceler.aspx | MGM'nin kendi tahminleri ve uç değerler (bizim kullanım alanımız dışında) | ⚠️ betikte görüldü |

**Erişim kısıtı (kritik bulgu):**
- `Origin` başlığı olmadan istek → `HTTP 500 {"error":"ServerError","message":"Not allowed by MGM"}`.
- `Origin: https://www.mgm.gov.tr` ile → `HTTP 200`; yanıt başlıkları `Access-Control-Allow-Origin: https://www.mgm.gov.tr`, `Vary: Origin`.
- `https://servis.mgm.gov.tr/robots.txt` → 403. `https://www.mgm.gov.tr/robots.txt` genel botlara açık (yalnızca Meta ve Amazon botlarını engelliyor).
- Yani servis, bilerek yalnızca MGM'nin kendi sitesinden gelen isteklere yanıt veriyor. Sunucu tarafı bir adaptör ancak `Origin` başlığını MGM sitesiymiş gibi göndererek çalışabilir; bu, "resmî API yok" durumunun ötesinde, **bir erişim kısıtının aşılması** anlamına gelir. Bu oturumda ikinci bir böyle istek Claude Code güvenlik denetimi tarafından "bot kontrolü atlatma" olarak engellendi; MGM'den gelen sonraki veriler yalnızca tarayıcıda sitenin kendi sayfaları normal şekilde gezilerek okundu.
- MGM "Yasal Uyarı – Site Kullanım Şartları" (`https://www.mgm.gov.tr/site/yasal-uyari.aspx`): sitedeki bilgilerin "önceden izin alınmadan ve kaynak gösterilmeden" kopyalanamayacağını, yeniden yayımlanamayacağını ve dağıtılamayacağını söylüyor. Ücretli/resmî veri yolu: MGM "Ücretli Ürünler" (MEVBİS).
- → Proje sahibinin kararı gerekiyor (bkz. "Proje sahibine sorulacaklar").

**Alan sözlüğü (`ilTumSondurum` yanıtı, 2026-10-31 21:39Z anlık görüntüsü):**

| Alan | Anlam / birim | Not |
|---|---|---|
| `istNo` | İstasyon no | `istasyonlar/il` ile eşleşir |
| `veriZamani` | Gözlem zamanı, UTC (`…Z`) | AWOS'larda 21:38–21:41, havalimanlarında 21:10/21:20 (METAR saati) |
| `sicaklik` | °C | |
| `nem` | % | |
| `ruzgarHiz` | **km/sa (çıkarım)** | Değerler m/s×3.6 katları (16.56 = 4.6×3.6). LTBA METAR `06009KT` (16.7 km/sa) ↔ MGM 16.56. Resmî tanım bulunamadı ❓ |
| `ruzgarYon` | derece | |
| `aktuelBasinc` | hPa, istasyon seviyesi | 18/42 eksik |
| `denizeIndirgenmisBasinc` | hPa, MSLP | 19/42 eksik |
| `yagis10Dk`, `yagis1Saat`, `yagis6Saat`, `yagis12Saat`, `yagis24Saat` | mm, son X süre | Kayan pencere mi, sinoptik saatlere bağlı mı ❓ |
| `yagis00Now` | mm | Muhtemelen yerel gece yarısından beri ❓ |
| `gorus` | m | 33/42 eksik |
| `kapalilik` | bulutluluk (birim ❓) | 38/42 eksik |
| `karYukseklik` | kar kalınlığı (birim ❓) | 42/42 eksik |
| `denizSicaklik`, `denizVeriZamani` | deniz suyu sıcaklığı | 37/42 eksik |
| `hadiseKodu` | Hadise kodu (A, AB, PB, CB, HY, Y …) | Sözlük `sondurumlar.js` içindeki `convertHadise` fonksiyonunda |
| `rasatMetar`, `rasatSinoptik`, `rasatTaf` | Ham rasat metinleri | METAR yalnızca 3 havalimanında dolu |
| `hissedilenSicaklik` | °C | MGM'nin hesabı |

- **Eksik değer kodu:** `-9999` (sayı) veya `"-9999"` (metin).
- **Hamle (gust) alanı yok.** Spec'teki `wind_gust_ms` MGM son durumlarından gelmez; hamle doğrulaması METAR (ve varsa SYNOP) ile sınırlı kalır.
- **Yalnızca anlık değer var**; geçmiş sorgusu yok (spec ile uyumlu).
- Güncelleme sıklığı: AWOS'larda dakika düzeyinde zaman damgası görüldü; gerçek güncelleme aralığı ölçülmedi ❓ (Faz 2'de ölçülecek; spec gereği istasyon başına ≤ 10 dk'da bir, toplu istek).

### 4.3 WMO WIS2 — SYNOP

**Sonuç: MGM'nin WIS2 yayını YOK → spec §5.3 gereği bu kaynak devre dışı** ✅ (çapraz kontrol).
- GDC'ler ([Kanada](https://wis2-gdc.weather.gc.ca/collections/wis2-discovery-metadata), [Çin](https://gdc.wis.cma.cn/collections/wis2-discovery-metadata), [Almanya](https://wis2.dwd.de/gdc/collections/wis2-discovery-metadata)): `turkey`, `turkiye`, `mgm`, `tr-mgm`, `istanbul` aramaları 0 sonuç; kontrol `synop` 134 sonuç. Resmî centre-id listesinde (178 kayıt) `tr-*` yok. NOAA Global Broker metriklerinde 148 centre-id, `tr-*` yok.
- Global Broker'lar (everyone/everyone, MQTTS 8883): `globalbroker.inmet.gov.br`, `gb.wis.cma.cn`, `globalbroker.meteo.fr`, `wis2broker.globaldata.nws.noaa.gov` — bağlantı test edildi ✅.
- **Dolaylı yol — belirsiz:** Türk GTS bültenleri DWD'nin geçici "GTS-to-WIS2" geçidinde akıyor (METAR/TAF/SIGMET görüldü; "recommended" ve erişimi ulusal servislerle sınırlı). İstanbul SYNOP bültenleri (SMTU10/60 LTAA, TAC formatı, 3 saatlik) geçitte dinleme penceresinde görülmedi ❓.
- **WMO Unified Data Policy** ([Res. 1 Cg-Ext 2021](https://public.wmo.int/sites/default/files/Cg-Ext2021-d04-1-WMO-UNIFIED-POLICY-FOR-THE-INTERNATIONAL-approved_en_0.pdf)) ✅: "core data" (GBON yüzey gözlemleri) "free and unrestricted" = "no conditions on use" (ticari dahil); atıf koşul değil, teşvik ediliyor. RBON gözlemleri "recommended" → koşul konabilir.
- **OSCAR/Surface — İstanbul WMO istasyonları** ✅: 17059 Sarıyer/Kumköy-Kilyos (**GBON**), 17061 Sarıyer (**GBON**), 17064 İstanbul Bölge/Kartal (**GBON**, GSN), 17060 Atatürk HVL (RBON), 17063 Sabiha Gökçen (RBON), 17058 İstanbul HVL (RBON). GBON olanlar core → bir kanaldan erişilirse ticari kullanılabilir. 17062 OSCAR'da yok (ISD'ye göre 2007'de kapanmış) ama MGM'de "KADIKÖY GÖZTEPE RIHTIM" adıyla aktif → MGM istasyon no'su WMO no'suyla karıştırılmamalı.

### 4.4 İBB Açık Veri Portalı (ek araştırma, 2026-11-01)

**Sonuç: portalda model doğrulamasında kullanılabilecek, lisanslı, saatlik ve güncel meteoroloji gözlemi yok** ✅. Doğrulama planı METAR (canlı) + IEM (geçmiş) olarak kalır.

**(A) Hava Kalitesi İstasyon Ölçüm Sonuçları Web Servisi** ✅ ([veri seti](https://data.ibb.gov.tr/dataset/hava-kalitesi-istasyon-olcum-sonuclari-web-servisi); CKAN id `602bd2c7-8480-404d-b52d-41d0dd906b7b`; yayıncı Çevre Koruma ve Kontrol Dairesi Başkanlığı)
- Uç noktalar (anahtarsız): `GET https://api.ibb.gov.tr/havakalitesi/OpenDataPortalHandler/GetAQIStations` (28 istasyon; `Id`, `Name`, `Adress`, `Location` = WKT `POINT(lon lat)`) ve `GET …/GetAQIByStationId?StationId=<GUID>&StartDate=dd.MM.yyyy HH:mm:ss&EndDate=…` (saatlik; JSON). Kullanım dokümanı v1.01'deki tarih biçimi ("dd-MM-yyyy") yanlış, çalışan biçim nokta ayraçlı.
- **Meteoroloji parametresi YOK** (çapraz kontrol ✅): `Concentration` ve `AQI` nesnelerinde yalnız `CO`, `NO2`, `O3`, `PM10`, `SO2` var (PM2.5 bile yok). Sıcaklık, nem, rüzgâr, basınç ve yağış yayınlanmıyor.
- İstasyonlarda meteoroloji sensörü bulunduğu biliniyor (2020 tarihli tek günlük XLSX'te 14–15 istasyon için T, RH, rüzgâr, basınç var; veri seti "artık güncellenmeyecek" notlu) ama bu servis ölçümlerini vermiyor. havakalitesi.ibb.gov.tr web arayüzündeki sıcaklık/rüzgâr alanları açık lisanslı veri değil → kullanılmaz.
- Zaman: saatlik, `ReadTime` ofsetsiz (yerel saat, TRT, olduğu güçlü çıkarım ⚠️); Ocak 2024 ve daha eskisi sorgulanabiliyor.
- **Doğrulamada kullanılabilir mi: Hayır.** İleride ayrı bir "hava kalitesi" özelliği için uygun (lisans ticari kullanıma açık).

**(B) İstanbul Meteoroloji Gözlem İstasyon Konumları Veri Seti (AKOM AWOS/BEUS)** ✅ ([veri seti](https://data.ibb.gov.tr/dataset/meteoroloji-gozlem-istasyon-konumlari); yayıncı Afet İşleri Dairesi Başkanlığı / AKOM)
- AWOS CSV: 10 istasyon (Çanta, Çavuşbaşı, Olimpiyat, Terkos, Hadımköy, AKOM, Ömerli, Aksaray, Kamiloba, Büyükada); alanlar `Sıra No; İstasyon Adı; İstasyon Koordinatları`. BEUS (buzlanma erken uyarı) CSV: 57 istasyon.
- **Yalnız konum var; ölçüm yok.** Koordinatlar derece-dakika hassasiyetinde (~1,8 km), bazı satırlar bozuk; yükseklik, ilçe ve sensör bilgisi yok. AWOS/AKOM ölçümleri portalda ve AKOM sitesinde lisanslı bir kanaldan yayınlanmıyor (AKOM'a yazılı başvuru gerekebilir ❓).
- Not: İBB trafik haritasının kullandığı belgelenmemiş bir hava uç noktası bulundu (`tkmservices.ibb.gov.tr`, MGM kaynaklı istasyonlar içeriyor, sorgu anında tüm değerler -999). Açık veri değil, lisans/kullanım koşulu yok ve MGM verisi içeriyor → **kullanılmaz**.
- **Doğrulamada kullanılabilir mi: Hayır.**

**(C) Diğer veri setleri** (portalda 576 paket tarandı): İSKİ baraj yağışları (günlük, 2011-01-01 → 2024-02-18; ölçüm kaynağı belirsiz ❓) yalnız Ocak–Şubat 2024 için ikincil günlük yağış kontrolü olabilir; Dünya Bankası 1991–2020 mevsimsel döngüsü zaman serisi değil.

**Lisans** ✅ ([İBB Açık Veri Lisansı](https://data.ibb.gov.tr/en/license), CKAN `ibb-license`, v1.0, CC BY 4.0 ve ODC-BY ile uyumlu): kopyalama, yayımlama, dağıtma, uyarlama ve "commercially and non-commercially" kullanma serbest. Atıf zorunlu; sağlayıcıya özel metin yoksa: "Contains public sector information licensed under the Attribution 4.0 International (CC BY 4.0)." (TR: "Atıf 4.0 Uluslararası (CC BY 4.0) kapsamında lisanslanan kamu sektörü bilgilerini içerir."). Resmî statü veya İBB onayı ima edilemez; sürekli sağlama garantisi yok.

---

## 5. İlçe noktaları ve istasyonlar

Ayrıntılı tablolar: **[districts-and-stations.md](districts-and-stations.md)**.

- 39 ilçe noktası OSM'den (admin_centre/label node), hepsi kendi poligonunun içinde; yükseklik SRTM30 (ASTER ile fark ≤ 16 m). 24 kıyı, 15 iç ilçe.
- 45 MGM istasyonu (42'sinde anlık veri); MGM ilçe alanı OSM poligonuyla %100 tutarlı.
- Eşleştirme (spec §6 kuralı): **21 ilçe doğrudan doğrulanabilir, 18 ilçe doğrudan doğrulanmamış.** 4 eşleşme gözden geçirilmeli (Pendik, Sarıyer, Silivri, Çekmeköy).
- Copernicus DEM Faz 0'da kullanılamadı (GDAL gerekiyor); OpenTopoData genel API'si üretim için uygun değil (koşul/SLA yok) → Faz 1'de DEM doğrudan indirilmeli.

---

## 6. Lisans ve atıf metinleri

Tüm metinler `models.attribution_text` ve `/api/v1/meta/sources`'a taşınacak (spec §11). Site geneli: "Tahminler otomatik üretilir, resmi tahmin yerine geçmez."

| Kaynak | Lisans | Atıf metni (birincil kaynaktan) | Ek koşullar |
|---|---|---|---|
| ECMWF (açık veri, IFS/AIFS) | CC BY 4.0 + [ECMWF ToU](https://apps.ecmwf.int/datasets/licences/general/) | Hizmetler için: Copyright "This service is based on data and products of the European Centre for Medium-Range Weather Forecasts (ECMWF)" · Source www.ecmwf.int · Licence Statement: "This ECMWF data is published under a Creative Commons Attribution 4.0 International (CC BY 4.0). https://creativecommons.org/licenses/by/4.0/" · Disclaimer: "ECMWF does not accept any liability whatsoever for any error or omission in the data, their availability, or for any loss or damage arising from their use." · değişiklik belirtilmeli | Atıf belirgin gösterilmeli; ECMWF isterse kaldırılmalı. ToU'daki "service agreement" maddesinin anonim indirmeye uygulanıp uygulanmadığı ❓ |
| NOAA (GFS, GEFS) | NODD açık veri | Resmî atıf cümlesi yok ❓. NODD: "NOAA requests attribution for the use or dissemination of unaltered NOAA data. However, it is not permissible to state or imply endorsement by or affiliation with NOAA. If you modify NOAA data, you may not state or imply that it is original, unaltered NOAA data." Önerilen: "Model verisi: NOAA/NCEP GFS ve GEFS. İşlenmiş ve diğer modellerle birleştirilmiştir; NOAA tarafından onaylanmamıştır." | NWS adı/logosu kullanılamaz |
| DWD (ICON ailesi) | CC BY 4.0 ([legal notice](https://www.dwd.de/EN/service/legal_notice/legal_notice_node.html)) | "Quelle: Deutscher Wetterdienst" / "Source: Deutscher Wetterdienst"; değiştirilmiş veri için ör. "Datenbasis: Deutscher Wetterdienst, eigene Elemente ergänzt" ([şablonlar](https://www.dwd.de/EN/service/legal_notice/templates_dwd_as_source.html)) | Bilginin hemen yanında |
| Météo-France (ARPEGE) | Licence Ouverte / Etalab 2.0 | "Source : Météo-France" veya "Informations créées à partir de données de Météo-France" ([MF açık veri dokümanı](https://confluence-meteofrance.atlassian.net/wiki/spaces/OpenDataMeteoFrance/pages/621019138)) + son güncelleme tarihi | Portal API lisansında "değiştirme yasağı" (açık paketlerde yok) |
| UK Met Office | **CC BY-SA 4.0** | Registry: "British Crown copyright 2023-2025, the Met Office, is licensed under CC BY-SA" | Share-alike → karar verilene kadar yalnız iç doğrulama |
| ECCC (GDPS/GEPS) | [ECCC Data Servers End-use Licence](https://eccc-msc.github.io/open-data/licence/readme_en/) 2.1.1 | "Data Source: Environment and Climate Change Canada" (+ lisans linki); çoklu atıf pratik değilse: "Contains information licenced under the Data Server End-use Licence of Environment and Climate Change Canada." | Onay ima edilmez; logo yok. Open Gov. Portal kaydı OGL-Canada gösteriyor (tutarsızlık ⚠️) |
| TIGGE (DWD/ECCC/ECMWF/NCEP/UKMO) | CC BY 4.0 ([lisans PDF](https://object-store.os-api.cci2.ecmwf.int/cci2-prod-catalogue/licences/tigge-licence/tigge-licence_5a08d5ef121b263c870e46ddd923398f3f586bb696e866efb9da5bda97ae3e35.pdf)) | ECDS'deki "citation and attribution" bölümüne göre veri sağlayıcıya atıf + lisans linki + değişiklik belirtme (tam metin ❓ — hesap gerekiyor) | ECMWF verisi için ToU da geçerli |
| dynamical.org | CC BY 4.0 (+ ECMWF ToU) | STAC `attribution` alanı, ör. "ECMWF AIFS Single forecast data processed by dynamical.org from ECMWF Open Data." / "NOAA NWS NCEP GFS data processed by dynamical.org from NOAA Open Data Dissemination archives." / "DWD ICON-EU data processed by dynamical.org." | |
| METAR (AWC) | ABD kamu malı ([NWS](https://www.weather.gov/disclaimer)) | "Kaynak: NOAA/NWS Aviation Weather Center" (önerilen) | Onay ima edilmez; yabancı orijin ❓ |
| IEM | Public domain | "Iowa Environmental Mesonet of Iowa State University" (rica) | |
| MGM | Beklemede: resmî izin/MEVBİS lisansına bağlı | Lisansın gerektirdiği atıf ("Kaynak: MGM") | Doğrudan kullanım iptal (§4.2) |
| OpenStreetMap | ODbL 1.0 | "© OpenStreetMap contributors" (openstreetmap.org/copyright linkiyle, tıklamadan görünür) ([guidelines](https://osmfoundation.org/wiki/Licence/Attribution_Guidelines)) | Koordinat/poligonlar API'den dışa verilirse türev veritabanı ODbL ile sunulmalı olabilir |
| SRTM GL1 v3 / ASTER GDEM v3 | NASA EOSDIS açık | NASA JPL (2013) doi:10.5067/MEASURES/SRTM/SRTMGL1.003; NASA/METI/AIST/Japan Spacesystems (2019) doi:10.5067/ASTER/ASTGTM.003 | |

---

## 7. Faz 1 ve sonrasına taşınan teknik notlar

1. **Repo konumu (karar 2026-11-01):** Repo `C:\istweather`'da kalır; veriler Docker named volume'larda, yalnız kaynak kod bind mount; `.gitattributes` ile LF. Geliştirme makinesinde Docker Desktop henüz kurulu değil (Faz 1 kabulü için gerekli).
2. **ecCodes libaec ile** derlenmiş olmalı (DWD ve Météo-France CCSDS sıkıştırması). Docker imajında test edilmeli.
3. **DWD:** yalnız v1 şeması; native ızgara için `CLAT/CLON`'dan en yakın hücre/ağırlık tablosu; grid dosyaları MPI'dan.
4. **ECCC:** AMQPS (Sarracenia) aboneliği; bildirimdeki tam yol kullanılmalı (tarih dizini = varış günü).
5. **ECMWF:** `.index` JSON-lines; AWS'de yalnız tekli Range; ENS için `enfo/ef` + `oper/fc` birlikte; Azure için SAS token; 0.1° +2 sa gecikmeli.
6. **NOAA:** `.idx` ad toleransı (`CLMR`/`CLWMR`); GFS'te APCP 0–N kaydı; GEFS'te 6 saatlik kova; NOMADS 120 istek/dk.
7. **UKMO:** NetCDF/HDF5 kısmi okuma (h5py/fsspec); u/v hız-yönden türetilecek; kara-deniz maskesi MOGREPS-G'den veya başka kaynaktan.
8. **ARPEGE:** paket başına mesaj başlıklarından kendi index'imizi kurma; yerel GRIB kodları (0/19/201, 0/1/83 vb.) için MF "définition des GRIB" dokümanı gerekli ❓.
9. **MGM birimleri:** `ruzgarHiz` km/sa (çıkarım) → m/s'ye çevrilmeli; eksik değer `-9999`; `stations.external_id` = MGM `istNo` (WMO no'suyla karıştırılmamalı).
10. **Hamle tanımı** model × adım bazında metadata.
11. **Model sürüm kırılma tarihleri** `models`/`model_runs` metadata'sına (bkz. §3.2).
12. **DEM:** Copernicus GLO-30 doğrudan indirilip kendi tarafımızda okunmalı (OpenTopoData genel API üretimde kullanılmaz).
13. **İzleme:** DWD v1'in 30.11.2026'daki tam geçişi, GFSv17 SCN'leri, GEPS'in yeni `MSC_` adlandırmasına geçişi, dynamical.org asset yolları.

---

## 8. Bilinmeyenler / teyit edilemeyenler

**Model verisi**
1. ECMWF portalında IP başına bağlantı sınırı; 500–2000 sınırının tüm anonim kullanıcılarda ortak olup olmadığı. Yansıların resmî saklama politikası.
2. ECMWF ToU'daki "service agreement" maddesinin reklam gelirli bir sitenin anonim açık veri indirmesine uygulanıp uygulanmadığı (ECMWF'ye sorulabilir).
3. `ecmwf-opendata` 0.3.35'in 50r1 sonrası `type="cf"` davranışı; 0.1°'deki "extra fields"; ENS pf yerel çözünürlüğünün ~9 km olduğu (çıkarım ⚠️).
4. NOAA'nın resmî atıf cümlesi; NODD bucket'larının resmî saklama politikası; NOMADS engelleme eşikleri; GFSv17 ve GEFSv13'ün kesin tarihleri ve yeni dosya adları; GFS `TMP:surface` deniz üstünde skin mi foundation SST mi; `LAND` ikili mi kesirli mi.
5. ~~ICON-EU (#62) ve ICON-EU-EPS (#63) doğu kenarı~~ ✅ 64,0°D / 64,1°D (2026-11-03, CLAT/CLON'dan; EPS sabitleri üye dizininde `e/01/`); opendata.dwd.de fair-use kuralları ❓. Ensemble boyut ölçümleri: [ADR-0006](decisions/0006-ensemble-hacim-plani.md).
6. Météo-France S3 açık paketlerinin resmî saklama süresi; portal WCS katmanlarının parametre seti; yerel GRIB kodlarının adları; ARPEGE T850'nin başlıkta doğrulanması; resmî arşivin ücreti.
7. UKMO S3 oran sınırı; `temperature_at_surface`'in denizde SST'ye eşit olup olmadığı; `wind_gust_at_10m` tanımında iki PDF arasındaki tutarsızlık; Planetary Computer aynasının 2024 kapsamı; MOGREPS-G tam değişken listesi.
8. **UKMO CC BY-SA'nın birleşik tahmine etkisi** — Met Office'in resmî açıklaması bulunamadı (hukuki görüş gerekli).
9. ECCC AMQP subtopic'leri canlı abonelikle denenmedi; GDPS 10.0 için hamle tanımının güncel resmî kaynağı; GEPS'in adlandırma geçişi; lisans sürüm tutarsızlığı (2.1.1 / 2.1; OGL-Canada).
10. TIGGE'de ECDS kota/maliyeti, ECMWF verisinin 2026-10 öncesi arşiv çözünürlüğü, tam atıf metni.
11. OCF Hugging Face veri kümelerinin kesin ufku ve değişken listesi (gated); `bkr/icon` lisansı; NCAR GDEX d084001'in güncellenmeye devam edip etmediği.

**Gözlemler**
12. Türkiye kaynaklı METAR'ların AWC/IEM/NCEI üzerinden ticari yeniden dağıtım durumu (hiçbir birincil kaynak açıkça ele almıyor).
13. NCEI/GHCNh'de ABD dışı veriye ticari kısıt olup olmadığı (güncel metinde yok, 2017 arşivinde var).
14. İstanbul SYNOP'larının DWD GTS-to-WIS2 geçidinde yayınlanıp yayınlanmadığı ve core/recommended sınıfı; MGM'nin RBON istasyonlarına koşul koyup koymadığı.
15. MGM alanlarının birim/tanımları: `ruzgarHiz` (km/sa çıkarım), `kapalilik`, `karYukseklik`, `yagis00Now`, `yagisXSaat`'in kayan pencere olup olmadığı; MGM verisinin gerçek güncelleme aralığı.
16. MGM "Son Durumlar" listesinin MGM'nin İstanbul'daki tüm istasyon ağı olup olmadığı (sitede kullanılan ağ için eksiksiz görünüyor).

**Noktalar**
17. Copernicus DEM ile yükseklik karşılaştırması yapılmadı; SRTM düşey datumu; temsil noktalarının belediye binası/en yoğun yerleşim olduğu teyit edilmedi (OSM yerleşim node'u).

---

## 9. Proje sahibi kararları (Faz 0'dan çıkanlar)

Karar tarihi 2026-11-01. Açık kalanlar spec §16'da da listeli.

| # | Konu | Karar / durum |
|---|---|---|
| 1 | MGM | **Doğrudan kullanım iptal.** `servis.mgm.gov.tr`'ye istek yok, erişim kısıtını aşan kod yok. MGM, yazılı izin veya MEVBİS lisansıyla gelecek resmî veri için beklemede (proje sahibi yürütecek). |
| 2 | Gözlem | Canlı doğrulama METAR (AWC), geçmiş doğrulama IEM. İBB hava kalitesi web servisi ve AKOM AWOS konumları incelendi (§4.4). |
| 3 | UKMO geçmişi | 39 ilçe + METAR noktaları için nokta çıkarımı Faz 4'ü beklemeden, en eski tarihten başlatıldı; yalnız iç doğrulama; çıktı Parquet, Faz 1'de veritabanına yüklenecek. |
| 4 | UKMO CC BY-SA | **Açık:** birleşik tahmine dahil edilip edilmeyeceği (spec §16). MOGREPS-G'nin TIGGE kopyası CC BY 4.0. |
| 5 | ARPEGE | CC BY-NC yalnız TIGGE kopyası için; canlı açık paketler Licence Ouverte 2.0 (ticari serbest) → canlıda "yetersiz geçmiş" ile kalır. Erişim açık paketlerden (portal API değil). |
| 6 | TIGGE ve Hugging Face | Hesapları proje sahibi açacak; değişkenler `.env.example`'da (`ECMWF_DATASTORES_URL`, `ECMWF_DATASTORES_KEY`, `HF_TOKEN`). Anahtarlar sohbette istenmez. |
| 7 | İlçe noktaları | MGM istasyon eşleştirmeleri MGM verisi gelene kadar askıda. Kıyı merkez noktaları değişmez; model değeri kara-deniz maskeli seçimle alınır. |
| 8 | Repo | `C:\istweather`'da kalır (WSL2'ye taşınmaz). Veritabanı, GRIB ve Parquet Docker named volume'larda; yalnız kaynak kod bind mount; `.gitattributes` ile LF. |
| 9 | Geçmiş METAR kaynağı | IEM birincil; NCEI/GHCNh yalnız iç kullanım (karar 2 ile uyumlu). |
| 10 | ODbL | **Açık:** ilçe koordinatları/poligonları API'den dışa verilecek mi (v1 önerisi: yalnız ad/slug). |
| 11 | Görüş kaynağı | Bilgi: ECMWF ve (30.11.2026'dan sonra) DWD görüş vermiyor; sis/görüş kuralı GFS, ARPEGE, UKMO (iç) ve türetilmiş değişkenlerle kurulacak. |
