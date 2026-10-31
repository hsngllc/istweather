# İlçe noktaları ve gözlem istasyonları (Faz 0)

> Durum: Faz 0 keşif çıktısı, 2026-11-01. Bu dosyadaki koordinat ve yüksekliklerin hiçbiri elle girilmedi; hepsi aşağıda belirtilen açık kaynaklardan çekildi. Faz 1'de `config/region.istanbul.yaml` ve `points`/`stations` tablolarına bu dosyadan aktarılacak.

## 1. İlçe temsil noktaları (39 ilçe)

**Yöntem**
- Kaynak: OpenStreetMap, Overpass API (`https://overpass-api.de/api/interpreter`), sorgu zamanı 2026-10-31 21:41–21:56 UTC (`osm_base` 2026-10-31T21:41:20Z).
- İlçeler: İstanbul il relation'ı [223474](https://www.openstreetmap.org/relation/223474) (`ISO3166-2=TR-34`, `admin_level=4`) içindeki `boundary=administrative`, `admin_level=6` relation'ları. Tam 39 relation döndü; adlar spec listesiyle birebir aynı (OSM'de yalnızca "Kâğıthane" şapkalı).
- Temsil noktası: relation'ın `admin_centre` üyesi (6 ilçe); yoksa `label` üyesi (33 ilçe). 39 node'un hepsi ilçe adını taşıyan `place=town` node'u (Bahçelievler'de `place=suburb`). Üçüncü yedek yönteme (ad eşleşmesi) gerek kalmadı.
- Poligon kontrolü: 39 noktanın her biri kendi ilçe poligonunun içinde (iki bağımsız yöntem: poligon içi nokta testi + Overpass `is_in`).
- Bağımsız teyit: 3 node (Adalar 965795474, Beşiktaş 251302687, Silivri 8647442778) OSM API'sinden (`api.openstreetmap.org/api/0.6/node/<id>.json`) ayrıca okundu; koordinatlar tabloyla aynı.
- Yükseklik: OpenTopoData genel API'si, bilineer interpolasyon, 2026-10-31 21:49 UTC. DEM1 = SRTM GL1 v3 (`srtm30m`), DEM2 = ASTER GDEM v3 (`aster30m`). Fark SRTM − ASTER: ortalama −5.7 m, aralık −16…+2 m; 25 m'yi aşan fark yok. Üçüncü kontrol EU-DEM v1.1 (`eudem25m`, bağımsız değil): SRTM − EU-DEM ortalama −0.9 m (Beykoz noktasında EU-DEM deniz/NODATA veriyor).
- Copernicus DEM kullanılamadı: OpenTopoData genel API'sinde yok, doğrudan okumak için GDAL/rasterio gerekiyor (Faz 0'da paket kurulmadı). Spec SRTM'ye de izin veriyor; v1 için **SRTM30 değeri** kullanılacak.
- Kıyı: Kıyı çizgisi (`natural=coastline`) geometrisiyle belirlendi (bir segment poligonun içinde veya sınırına < 30 m ise kıyı). 24 kıyı, 15 iç ilçe. Kağıthane'nin kıyısı Haliç ucunda ~50–100 m (pratikte iç ilçe). Küçükçekmece ve Büyükçekmece gölleri deniz sayılmadı ama model kara-deniz maskelerini etkileyebilir.

**Lisans:** OSM verisi ODbL 1.0, "© OpenStreetMap contributors" (https://www.openstreetmap.org/copyright). Atıf kuralları: [OSMF Attribution Guidelines](https://osmfoundation.org/wiki/Licence/Attribution_Guidelines). SRTM GL1 v3 ve ASTER GDEM v3: NASA EOSDIS, "openly shared, without restriction" ([SRTMGL1](https://www.earthdata.nasa.gov/data/catalog/lpcloud-srtmgl1-003), [ASTGTM](https://www.earthdata.nasa.gov/data/catalog/lpcloud-astgtm-003)).

**geoBoundaries karşılaştırması:** [gbOpen TUR ADM2](https://www.geoboundaries.org/api/current/gbOpen/TUR/ADM2/) (boundaryID `TUR-ADM2-54988432`, kaynak verisi 2023-01-19) kendisi bir OSM türevi (ODbL); 39 ilçeyi içeriyor ama OSM id'si ve merkez node'u yok, bazı adlar hatalı ("Prince Islands"). **Karar önerisi: OSM doğrudan kullanılsın.**

| slug | İlçe | OSM relation | Merkez node (yöntem) | Enlem | Boylam | SRTM30 (m) | ASTER30 (m) | Kıyı | Kıyıya uzaklık (m) |
|---|---|---|---|---|---|---|---|---|---|
| adalar | Adalar | [963209](https://www.openstreetmap.org/relation/963209) | [965795474](https://www.openstreetmap.org/node/965795474) (admin_centre) | 40.87417 | 29.12933 | 10 | 10 | evet | 101 |
| arnavutkoy | Arnavutköy | [1766093](https://www.openstreetmap.org/relation/1766093) | [8582371040](https://www.openstreetmap.org/node/8582371040) (label) | 41.18447 | 28.74124 | 165 | 165 | evet | 13770 |
| atasehir | Ataşehir | [1276672](https://www.openstreetmap.org/relation/1276672) | [3933476042](https://www.openstreetmap.org/node/3933476042) (label) | 40.99294 | 29.11352 | 74 | 85 | hayır | 4777 |
| avcilar | Avcılar | [1766094](https://www.openstreetmap.org/relation/1766094) | [2686436887](https://www.openstreetmap.org/node/2686436887) (label) | 40.97994 | 28.72167 | 69 | 74 | evet | 1025 |
| bagcilar | Bağcılar | [1766098](https://www.openstreetmap.org/relation/1766098) | [27426565](https://www.openstreetmap.org/node/27426565) (label) | 41.03455 | 28.85676 | 90 | 94 | hayır | 6592 |
| bahcelievler | Bahçelievler | [1766095](https://www.openstreetmap.org/relation/1766095) | [976490088](https://www.openstreetmap.org/node/976490088) (label) | 41.00305 | 28.86577 | 52 | 58 | hayır | 3211 |
| bakirkoy | Bakırköy | [1766096](https://www.openstreetmap.org/relation/1766096) | [26504247](https://www.openstreetmap.org/node/26504247) (label) | 40.97826 | 28.87445 | 22 | 28 | evet | 490 |
| basaksehir | Başakşehir | [1766099](https://www.openstreetmap.org/relation/1766099) | [965804205](https://www.openstreetmap.org/node/965804205) (label) | 41.10758 | 28.79507 | 147 | 153 | hayır | 13189 |
| bayrampasa | Bayrampaşa | [1766097](https://www.openstreetmap.org/relation/1766097) | [7427633848](https://www.openstreetmap.org/node/7427633848) (label) | 41.03455 | 28.91184 | 101 | 104 | hayır | 2482 |
| besiktas | Beşiktaş | [1765893](https://www.openstreetmap.org/relation/1765893) | [251302687](https://www.openstreetmap.org/node/251302687) (label) | 41.04285 | 29.00753 | 12 | 17 | evet | 169 |
| beykoz | Beykoz | [1276910](https://www.openstreetmap.org/relation/1276910) | [251303423](https://www.openstreetmap.org/node/251303423) (admin_centre) | 41.13430 | 29.09204 | 6 | 12 | evet | 38 |
| beylikduzu | Beylikdüzü | [1766100](https://www.openstreetmap.org/relation/1766100) | [965804730](https://www.openstreetmap.org/node/965804730) (label) | 41.00381 | 28.63729 | 154 | 152 | evet | 3178 |
| beyoglu | Beyoğlu | [1765892](https://www.openstreetmap.org/relation/1765892) | [1651655687](https://www.openstreetmap.org/node/1651655687) (label) | 41.02842 | 28.97368 | 66 | 66 | evet | 539 |
| buyukcekmece | Büyükçekmece | [1275387](https://www.openstreetmap.org/relation/1275387) | [26504699](https://www.openstreetmap.org/node/26504699) (label) | 41.02165 | 28.57976 | 3 | 14 | evet | 426 |
| catalca | Çatalca | [1275389](https://www.openstreetmap.org/relation/1275389) | [965804875](https://www.openstreetmap.org/node/965804875) (admin_centre) | 41.14368 | 28.46052 | 85 | 92 | evet | 11759 |
| cekmekoy | Çekmeköy | [1276034](https://www.openstreetmap.org/relation/1276034) | [5048705441](https://www.openstreetmap.org/node/5048705441) (label) | 41.03516 | 29.17391 | 126 | 126 | hayır | 10305 |
| esenler | Esenler | [1766101](https://www.openstreetmap.org/relation/1766101) | [965806119](https://www.openstreetmap.org/node/965806119) (label) | 41.03762 | 28.88245 | 90 | 94 | hayır | 4619 |
| esenyurt | Esenyurt | [1766102](https://www.openstreetmap.org/relation/1766102) | [26505356](https://www.openstreetmap.org/node/26505356) (label) | 41.03429 | 28.68011 | 128 | 132 | hayır | 6886 |
| eyupsultan | Eyüpsultan | [1766103](https://www.openstreetmap.org/relation/1766103) | [251301080](https://www.openstreetmap.org/node/251301080) (admin_centre) | 41.04784 | 28.93274 | 10 | 16 | evet | 287 |
| fatih | Fatih | [1766104](https://www.openstreetmap.org/relation/1766104) | [26504810](https://www.openstreetmap.org/node/26504810) (label) | 41.01928 | 28.94793 | 59 | 65 | evet | 1182 |
| gaziosmanpasa | Gaziosmanpaşa | [1766105](https://www.openstreetmap.org/relation/1766105) | [965806995](https://www.openstreetmap.org/node/965806995) (label) | 41.05783 | 28.91225 | 123 | 130 | hayır | 2062 |
| gungoren | Güngören | [1766106](https://www.openstreetmap.org/relation/1766106) | [965807755](https://www.openstreetmap.org/node/965807755) (label) | 41.02528 | 28.87265 | 82 | 90 | hayır | 5137 |
| kadikoy | Kadıköy | [1276548](https://www.openstreetmap.org/relation/1276548) | [2673025441](https://www.openstreetmap.org/node/2673025441) (label) | 40.99130 | 29.02456 | 9 | 22 | evet | 159 |
| kagithane | Kağıthane | [1765894](https://www.openstreetmap.org/relation/1765894) | [26505332](https://www.openstreetmap.org/node/26505332) (label) | 41.08121 | 28.97302 | 12 | 22 | evet | 2774 |
| kartal | Kartal | [1276013](https://www.openstreetmap.org/relation/1276013) | [251364891](https://www.openstreetmap.org/node/251364891) (label) | 40.88850 | 29.18589 | 5 | 16 | evet | 214 |
| kucukcekmece | Küçükçekmece | [7786498](https://www.openstreetmap.org/relation/7786498) | [26504855](https://www.openstreetmap.org/node/26504855) (label) | 40.99187 | 28.77120 | 12 | 20 | evet | 243 |
| maltepe | Maltepe | [1276407](https://www.openstreetmap.org/relation/1276407) | [251364890](https://www.openstreetmap.org/node/251364890) (label) | 40.92475 | 29.13108 | 22 | 31 | evet | 671 |
| pendik | Pendik | [1276011](https://www.openstreetmap.org/relation/1276011) | [965808549](https://www.openstreetmap.org/node/965808549) (admin_centre) | 40.87687 | 29.23497 | 6 | 10 | evet | 242 |
| sancaktepe | Sancaktepe | [1276014](https://www.openstreetmap.org/relation/1276014) | [965808713](https://www.openstreetmap.org/node/965808713) (label) | 40.99052 | 29.22886 | 126 | 128 | hayır | 11360 |
| sariyer | Sarıyer | [1765895](https://www.openstreetmap.org/relation/1765895) | [2686428097](https://www.openstreetmap.org/node/2686428097) (label) | 41.16858 | 29.05726 | 6 | 13 | evet | 58 |
| sile | Şile | [1275310](https://www.openstreetmap.org/relation/1275310) | [247999748](https://www.openstreetmap.org/node/247999748) (label) | 41.17441 | 29.61252 | 47 | 46 | evet | 482 |
| silivri | Silivri | [1275379](https://www.openstreetmap.org/relation/1275379) | [8647442778](https://www.openstreetmap.org/node/8647442778) (admin_centre) | 41.07425 | 28.24817 | 8 | 14 | evet | 455 |
| sisli | Şişli | [1765896](https://www.openstreetmap.org/relation/1765896) | [251302611](https://www.openstreetmap.org/node/251302611) (label) | 41.06379 | 28.98316 | 95 | 103 | hayır | 2916 |
| sultanbeyli | Sultanbeyli | [1276012](https://www.openstreetmap.org/relation/1276012) | [5048705440](https://www.openstreetmap.org/node/5048705440) (label) | 40.96702 | 29.26713 | 139 | 147 | hayır | 10470 |
| sultangazi | Sultangazi | [1766108](https://www.openstreetmap.org/relation/1766108) | [8458146161](https://www.openstreetmap.org/node/8458146161) (label) | 41.10433 | 28.86144 | 152 | 154 | hayır | 8182 |
| tuzla | Tuzla | [1276010](https://www.openstreetmap.org/relation/1276010) | [251376256](https://www.openstreetmap.org/node/251376256) (label) | 40.81617 | 29.30342 | 6 | 10 | evet | 143 |
| umraniye | Ümraniye | [1276890](https://www.openstreetmap.org/relation/1276890) | [251358378](https://www.openstreetmap.org/node/251358378) (label) | 41.02564 | 29.09630 | 153 | 157 | hayır | 4473 |
| uskudar | Üsküdar | [1276889](https://www.openstreetmap.org/relation/1276889) | [26505047](https://www.openstreetmap.org/node/26505047) (label) | 41.02655 | 29.01513 | 2 | 9 | evet | 83 |
| zeytinburnu | Zeytinburnu | [1766109](https://www.openstreetmap.org/relation/1766109) | [26505044](https://www.openstreetmap.org/node/26505044) (label) | 40.98987 | 28.90375 | 30 | 46 | evet | 811 |

**Karar (2026-11-01): kıyı noktaları kaydırılmaz;** model değeri kara-deniz maskeli seçimle alınır (spec §6).

**Dikkat:** Bazı merkez noktaları denize çok yakın: Beykoz 38 m, Sarıyer 58 m, Üsküdar 83 m, Adalar 101 m, Tuzla 143 m, Kadıköy 159 m, Beşiktaş 169 m. Bu noktalarda model ızgarasından kara-deniz maskeli seçim zorunlu (spec §6). Noktalar elle kaydırılmadı. Arnavutköy ve Çatalca merkezleri kıyıdan 12–14 km içeride; bu ilçelerin uzun Karadeniz kıyısı tek noktayla temsil edilmiyor (spec'teki çoklu nokta desteği bunun için).

Ham sorgu dosyaları ve tam CSV (wikidata, sınıra uzaklık, kıyı uzunluğu, alan vb.) Faz 0 çalışma klasöründe duruyor; Faz 1'de repoya `config/` altına aktarılacak.

## 2. MGM istasyonları (İstanbul, plaka 34)

> **Durum (2026-11-01):** MGM doğrudan kullanımı iptal edildi. Bu liste ve Bölüm 3'teki eşleştirme **MGM resmî verisi (yazılı izin veya MEVBİS) gelene kadar askıda**; yalnız Faz 0 kaydı olarak duruyor. Bu sürede doğrulama METAR istasyonlarında (Bölüm 4) yapılır ve tüm ilçeler "doğrudan doğrulanmamış" sayılır. Resmî veri geldiğinde istasyon meta verisi o kaynaktan yeniden alınıp eşleştirme tekrarlanacak.

**Kaynak:** `GET https://servis.mgm.gov.tr/web/istasyonlar/il?plaka=34` (45 kayıt) ve `GET https://servis.mgm.gov.tr/web/sondurumlar/ilTumSondurum?ilPlaka=34` (42 kayıt), 2026-10-31 21:43 UTC, tek seferlik çağrı. Erişim kısıtı ve hukuki not için bkz. `docs/data-sources.md` → MGM bölümü.

**Sınıflandırma (bizim):** `kara`, `havalimanı`, `kıyı feneri` (karada) referans için uygun; `deniz (şamandıra)` ve `mendirek/liman feneri` (deniz üzerinde) uygun değil. Ayrıca anlık verisi olmayan istasyon uygun değil.

**Tutarlılık:** Karadaki 42 istasyonun MGM `ilce` alanı, OSM poligon testiyle %100 aynı. 3 şamandıra denizde (poligon dışı). MGM, Eyüpsultan için eski ad "Eyüp"ü kullanıyor. 3 havalimanı istasyonu aynı zamanda METAR yayınlıyor: 17058 = LTFM, 17060 = LTBA, 17063 = LTFJ (LTBA'nın 2026-10-31 21:20Z METAR'ı MGM yanıtında mevcut).

| istNo | Ad | MGM `ilce` | OSM poligonu | Enlem | Boylam | Yük. (m) | Tür | Referans için uygun | Anlık veri 2026-10-31 ~21:39Z | METAR |
|---|---|---|---|---|---|---|---|---|---|---|
| 17058 | İSTANBUL HAVALİMANI | Arnavutköy | arnavutkoy | 41.264714 | 28.728836 | 99 | havalimanı | evet | var | LTFM |
| 17494 | İSTANBUL HAVALİMANI LİMAN FENERİ | Arnavutköy | arnavutkoy | 41.313998 | 28.788586 | 14 | mendirek/liman feneri | hayır | var |  |
| 18402 | ARNAVUTKÖY | Arnavutköy | arnavutkoy | 41.22111 | 28.707882 | 140 | kara | evet | var |  |
| 18734 | ARNAVUTKÖY/TERKOS BARAJI | Arnavutköy | arnavutkoy | 41.33639 | 28.6175 | 16 | kara | evet | var |  |
| 17060 | İSTANBUL ATATÜRK HAVALİMANI | Bakırköy | bakirkoy | 40.966936 | 28.815562 | 33 | havalimanı | evet | var | LTBA |
| 17636 | FLORYA | Bakırköy | bakirkoy | 40.975796 | 28.786722 | 37 | kara | evet | var |  |
| 18396 | BEYKOZ | Beykoz | beykoz | 41.141667 | 29.073889 | 5 | kara | evet | var |  |
| 18421 | BEYKOZ/ANADOLU FENERİ | Beykoz | beykoz | 41.223333 | 29.165833 | 58 | kıyı feneri | evet | var |  |
| 19110 | BEYLİKDÜZÜ | Beylikdüzü | beylikduzu | 40.965729 | 28.622512 | 90 | kara | evet | var |  |
| 18099 | BÜYÜKÇEKMECE | Büyükçekmece | buyukcekmece | 41.045278 | 28.59 | 20 | kara | evet | var |  |
| 17047 | ÇATALCA RADAR SAHASI | Çatalca | catalca | 41.340943 | 28.356803 | 381 | kara | evet | var |  |
| 19111 | ÇATALCA | Çatalca | catalca | 41.168037 | 28.490868 | 40 | kara | evet | var |  |
| 18397 | ÇEKMEKÖY/ÖMERLİ | Çekmeköy | cekmekoy | 41.078333 | 29.325556 | 80 | kara | evet | var |  |
| 18101 | EYÜPSULTAN | Eyüp | eyupsultan | 41.102778 | 28.924167 | 54 | kara | evet | var |  |
| 17454 | FATİH/KUMKAPI FENERİ | Fatih | fatih | 41.000994 | 28.965432 | 8 | kıyı feneri | evet | var |  |
| 17603 | FATİH/İST.DEN.BİL.ENS. | Fatih | fatih | 41.015571 | 28.959991 | 10 | kara | evet | var |  |
| 17814 | GÜNGÖREN/DAVUTPAŞA MARMARA | Güngören | gungoren | 41.0266 | 28.8853 | 68 | kara | evet | var |  |
| 17062 | KADIKÖY GÖZTEPE RIHTIM | Kadıköy | kadikoy | 40.9883 | 29.01895 | 5 | kara | evet | var |  |
| 17813 | KADIKÖY/GÖZTEPE | Kadıköy | kadikoy | 40.979451 | 29.057147 | 41 | kara | evet | var |  |
| 17064 | İSTANBUL BÖLGE | Kartal | kartal | 40.911345 | 29.155803 | 18 | kara | evet | var |  |
| 19112 | KARTAL/AYDOS DAĞI | Kartal | kartal | 40.932104 | 29.228568 | 321 | kara | evet | var |  |
| 17063 | İSTANBUL SABİHA GÖKÇEN HAVALİMANI | Pendik | pendik | 40.892797 | 29.297236 | 99 | havalimanı | evet | var | LTFJ |
| 18736 | PENDİK/ÖMERLİ BARAJI | Pendik | pendik | 41.008302 | 29.341834 | 70 | kara | evet | var |  |
| 17065 | SAMANDIRA HAVALİMANI | Sancaktepe | sancaktepe | 40.986676 | 29.214909 | 123 | havalimanı | evet | var |  |
| 18399 | SANCAKTEPE | Sancaktepe | sancaktepe | 41.008611 | 29.282222 | 110 | kara | evet | var |  |
| 17059 | SARIYER/KUMKÖY-KİLYOS | Sarıyer | sariyer | 41.25047 | 29.038367 | 38 | kara | evet | var (sıcaklık eksik) |  |
| 17061 | SARIYER | Sarıyer | sariyer | 41.146515 | 29.050201 | 59 | kara | evet | var |  |
| 17455 | SARIYER/RUMELİ FENERİ BAL. BAR. ANA MENDİREK FENERİ | Sarıyer | sariyer | 41.229151 | 29.114919 | 2 | mendirek/liman feneri | hayır | **yok** |  |
| 18980 | SARIYER/İTÜ MASLAK YERLEŞKESİ | Sarıyer | sariyer | 41.099909 | 29.025127 | 75 | kara | evet | var |  |
| 19365 | SARIYER/YAVUZ SULTAN SELİM KÖPRÜSÜ | Sarıyer | sariyer | 41.20993 | 29.104873 | 90 | kara | evet | var |  |
| 17610 | ŞİLE | Şile | sile | 41.168851 | 29.600454 | 83 | kara | evet | var |  |
| 18735 | ŞİLE/İSAKÖY | Şile | sile | 41.108163 | 29.828284 | 6 | kara | evet | var |  |
| 18792 | ŞİLE/DARLIK KÖYÜ | Şile | sile | 41.042939 | 29.57156 | 256 | kara | evet | var |  |
| 17438 | SİLİVRİ ANA MENDİREK FENERİ | Silivri | silivri | 41.072866 | 28.238398 | 9 | mendirek/liman feneri | hayır | var |  |
| 18400 | SİLİVRİ | Silivri | silivri | 41.185331 | 28.157393 | 195 | kara | evet | var |  |
| 18793 | SİLİVRİ ORMAN SAHASI | Silivri | silivri | 41.306389 | 28.186944 | 208 | kara | evet | var |  |
| 18401 | ŞİŞLİ | Şişli | sisli | 41.054722 | 28.968333 | 60 | kara | evet | var |  |
| 17437 | TUZLA AYDINLI LİMAN FENERİ | Tuzla | tuzla | 40.850611 | 29.271174 | 8 | mendirek/liman feneri | hayır | var |  |
| 17448 | TUZLA İTÜ GÜNEY MENDİREK FENERİ | Tuzla | tuzla | 40.811828 | 29.297373 | 13 | mendirek/liman feneri | hayır | var |  |
| 18100 | TUZLA | Tuzla | tuzla | 40.827623 | 29.292767 | 3 | kara | evet | var |  |
| 18403 | ÜMRANİYE | Ümraniye | umraniye | 41.029444 | 29.138247 | 191 | kara | evet | var |  |
| 18404 | ÜSKÜDAR | Üsküdar | uskudar | 41.032778 | 29.046389 | 75 | kara | evet | var |  |
| 17388 | SİLİVRİ TPAO ŞAMANDIRA | Silivri | — (denizde) | 41.039667 | 28.186983 | 0 | deniz (şamandıra) | hayır | **yok** |  |
| 17389 | ADALAR ŞAMANDIRA | Adalar | — (denizde) | 40.93278 | 28.94889 | 0 | deniz (şamandıra) | hayır | var |  |
| 17390 | İSTANBUL BOĞAZI KARADENİZ ÇIKIŞI ŞAMANDIRA | Beykoz | — (denizde) | 41.475959 | 28.716918 | 0 | deniz (şamandıra) | hayır | **yok** |  |

**Not:** Bu liste MGM "Son Durumlar" haritasında yayımlanan istasyonlardır; MGM'nin İstanbul'daki tüm istasyon ağı olmayabilir. MGM sitesinin ilçe sayfaları da yalnızca bu 45 istasyondan birini kullanıyor (bkz. Bölüm 3), bu da listenin site için eksiksiz olduğunu gösteriyor.

## 3. İlçe ↔ referans istasyon eşleştirmesi

**Kural (spec §6):** Önce ilçe içinde olmak, sonra yükseklik farkı (|Δz| = istasyon − nokta, SRTM30) küçük olan; eşitlikte mesafe. İlçe içinde uygun istasyon yoksa ilçe "doğrudan doğrulanmamış" olur; en yakın 3 uygun komşu bilgi olarak listelendi (doğrulukları bunlardan tahmin edilecek).

**Sonuç:** 21 ilçe doğrudan doğrulanabilir; 18 ilçe doğrudan doğrulanmamış: Adalar (yalnızca şamandıra var), Ataşehir, Avcılar, Bağcılar, Bahçelievler, Başakşehir, Bayrampaşa, Beşiktaş, Beyoğlu, Esenler, Esenyurt, Gaziosmanpaşa, Kağıthane, Küçükçekmece, Maltepe, Sultanbeyli, Sultangazi, Zeytinburnu.

"MGM sitesinin kullandığı istasyon" sütunu: mgm.gov.tr `il-ve-ilceler.aspx?il=İstanbul&ilce=…` sayfalarında gösterilen anlık değerlerin (sıcaklık, 24 saatlik yağış, nem, zaman) istasyon anlık görüntüsüyle eşleştirilmesinden **çıkarım** (2026-11-01 ~00:40 TSİ, tarayıcıda normal sayfa gezintisiyle okundu). Sayfadaki enlem/boylam her zaman istasyonun koordinatı değil (ör. Sultangazi sayfası 18402'nin koordinatını gösterip 18101'in değerlerini veriyor). `?` işaretliler farklı zaman damgalı gözlemle eşleşti, daha az kesin. Yalnızca çapraz kontrol içindir; bizim eşleştirmemiz spec kuralına göre yapıldı.

| İlçe | Nokta yük. (m) | Durum | Kurala göre referans istasyon (mesafe, Δz) | İlçedeki diğer istasyonlar | En yakın uygun komşular (mesafe, Δz) | MGM sitesinin kullandığı istasyon | Not |
|---|---|---|---|---|---|---|---|
| Adalar | 10 | **doğrudan doğrulanmamış** | — | — | 17064 İSTANBUL BÖLGE (4.7 km, +8 m); 19112 KARTAL/AYDOS DAĞI (10.5 km, +311 m); 17813 KADIKÖY/GÖZTEPE (13.2 km, +31 m) | — | İlçedeki tek MGM istasyonu 17389 bir şamandıra (deniz); kara referansı yok. |
| Arnavutköy | 165 | doğrudan doğrulanabilir | 18402 ARNAVUTKÖY (4.9 km, -25 m) | 17058 (havalimanı), 17494 (mendirek/liman feneri), 18734 (kara) | — | — |  |
| Ataşehir | 74 | **doğrudan doğrulanmamış** | — | — | 18403 ÜMRANİYE (4.6 km, +117 m); 17813 KADIKÖY/GÖZTEPE (5.0 km, -33 m); 18404 ÜSKÜDAR (7.2 km, +1 m) | 18403 |  |
| Avcılar | 69 | **doğrudan doğrulanmamış** | — | — | 17636 FLORYA (5.5 km, -32 m); 17060 İSTANBUL ATATÜRK HAVALİMANI (8.0 km, -36 m); 19110 BEYLİKDÜZÜ (8.5 km, +21 m) | 17060 |  |
| Bağcılar | 90 | **doğrudan doğrulanmamış** | — | — | 17814 GÜNGÖREN/DAVUTPAŞA MARMARA (2.6 km, -22 m); 17060 İSTANBUL ATATÜRK HAVALİMANI (8.3 km, -57 m); 17636 FLORYA (8.8 km, -53 m) | 17814 |  |
| Bahçelievler | 52 | **doğrudan doğrulanmamış** | — | — | 17814 GÜNGÖREN/DAVUTPAŞA MARMARA (3.1 km, +16 m); 17060 İSTANBUL ATATÜRK HAVALİMANI (5.8 km, -19 m); 17636 FLORYA (7.3 km, -15 m) | 17060? |  |
| Bakırköy | 22 | doğrudan doğrulanabilir | 17060 İSTANBUL ATATÜRK HAVALİMANI (5.1 km, +11 m) | 17636 (kara) | — | — |  |
| Başakşehir | 147 | **doğrudan doğrulanmamış** | — | — | 18101 EYÜPSULTAN (10.8 km, -93 m); 17814 GÜNGÖREN/DAVUTPAŞA MARMARA (11.8 km, -79 m); 18402 ARNAVUTKÖY (14.6 km, -7 m) | 18402 |  |
| Bayrampaşa | 101 | **doğrudan doğrulanmamış** | — | — | 17814 GÜNGÖREN/DAVUTPAŞA MARMARA (2.4 km, -33 m); 17603 FATİH/İST.DEN.BİL.ENS. (4.6 km, -91 m); 18401 ŞİŞLİ (5.2 km, -41 m) | 17814 |  |
| Beşiktaş | 12 | **doğrudan doğrulanmamış** | — | — | 18404 ÜSKÜDAR (3.4 km, +63 m); 18401 ŞİŞLİ (3.5 km, +48 m); 17603 FATİH/İST.DEN.BİL.ENS. (5.0 km, -2 m) | 18401 |  |
| Beykoz | 6 | doğrudan doğrulanabilir | 18396 BEYKOZ (1.7 km, -1 m) | 18421 (kıyı feneri) | — | — |  |
| Beylikdüzü | 154 | doğrudan doğrulanabilir | 19110 BEYLİKDÜZÜ (4.4 km, -64 m) | — | — | — |  |
| Beyoğlu | 66 | **doğrudan doğrulanmamış** | — | — | 17603 FATİH/İST.DEN.BİL.ENS. (1.8 km, -56 m); 18401 ŞİŞLİ (3.0 km, -6 m); 17454 FATİH/KUMKAPI FENERİ (3.1 km, -58 m) | 18401 |  |
| Büyükçekmece | 3 | doğrudan doğrulanabilir | 18099 BÜYÜKÇEKMECE (2.8 km, +17 m) | — | — | — |  |
| Çatalca | 85 | doğrudan doğrulanabilir | 19111 ÇATALCA (3.7 km, -45 m) | 17047 (kara) | — | — | 17047 Çatalca Radar Sahası 381 m, merkezden 23.6 km. |
| Çekmeköy | 126 | doğrudan doğrulanabilir | 18397 ÇEKMEKÖY/ÖMERLİ (13.6 km, -46 m) | — | — | — | İlçe içindeki tek istasyon 18397 Ömerli 13.6 km uzakta; ilçe dışındaki 18403 Ümraniye 3.1 km. Gözden geçirilmeli. |
| Esenler | 90 | **doğrudan doğrulanmamış** | — | — | 17814 GÜNGÖREN/DAVUTPAŞA MARMARA (1.2 km, -22 m); 17603 FATİH/İST.DEN.BİL.ENS. (7.0 km, -80 m); 18401 ŞİŞLİ (7.4 km, -30 m) | 17814 |  |
| Esenyurt | 128 | **doğrudan doğrulanmamış** | — | — | 18099 BÜYÜKÇEKMECE (7.7 km, -108 m); 19110 BEYLİKDÜZÜ (9.0 km, -38 m); 17636 FLORYA (11.1 km, -91 m) | 18099 |  |
| Eyüpsultan | 10 | doğrudan doğrulanabilir | 18101 EYÜPSULTAN (6.2 km, +44 m) | — | — | — |  |
| Fatih | 59 | doğrudan doğrulanabilir | 17603 FATİH/İST.DEN.BİL.ENS. (1.1 km, -49 m) | 17454 (kıyı feneri) | — | 17603 |  |
| Gaziosmanpaşa | 123 | **doğrudan doğrulanmamış** | — | — | 17814 GÜNGÖREN/DAVUTPAŞA MARMARA (4.1 km, -55 m); 18401 ŞİŞLİ (4.7 km, -63 m); 18101 EYÜPSULTAN (5.1 km, -69 m) | 17814 |  |
| Güngören | 82 | doğrudan doğrulanabilir | 17814 GÜNGÖREN/DAVUTPAŞA MARMARA (1.1 km, -14 m) | — | — | — |  |
| Kadıköy | 9 | doğrudan doğrulanabilir | 17062 KADIKÖY GÖZTEPE RIHTIM (0.6 km, -4 m) | 17813 (kara) | — | 17062 |  |
| Kağıthane | 12 | **doğrudan doğrulanmamış** | — | — | 18401 ŞİŞLİ (3.0 km, +48 m); 18101 EYÜPSULTAN (4.7 km, +42 m); 18980 SARIYER/İTÜ MASLAK YERLEŞKESİ (4.8 km, +63 m) | 18401 |  |
| Kartal | 5 | doğrudan doğrulanabilir | 17064 İSTANBUL BÖLGE (3.6 km, +13 m) | 19112 (kara) | — | — | 19112 Aydos Dağı (321 m) dağ istasyonu; referans için uygun değil, rejim/yükseklik kalibrasyonu için değerli. |
| Küçükçekmece | 12 | **doğrudan doğrulanmamış** | — | — | 17636 FLORYA (2.2 km, +25 m); 17060 İSTANBUL ATATÜRK HAVALİMANI (4.6 km, +21 m); 17814 GÜNGÖREN/DAVUTPAŞA MARMARA (10.3 km, +56 m) | 17060? |  |
| Maltepe | 22 | **doğrudan doğrulanmamış** | — | — | 17064 İSTANBUL BÖLGE (2.6 km, -4 m); 19112 KARTAL/AYDOS DAĞI (8.2 km, +299 m); 17813 KADIKÖY/GÖZTEPE (8.7 km, +19 m) | 17064 |  |
| Pendik | 6 | doğrudan doğrulanabilir | 18736 PENDİK/ÖMERLİ BARAJI (17.2 km, +64 m) | 17063 (havalimanı) | — | — | Kural 18736'yı seçiyor (17.2 km, barajda). İlçe içindeki en yakın istasyon 17063 LTFJ (5.5 km, Δz +93 m). Gözden geçirilmeli. |
| Sancaktepe | 126 | doğrudan doğrulanabilir | 17065 SAMANDIRA HAVALİMANI (1.2 km, -3 m) | 18399 (kara) | — | — |  |
| Sarıyer | 6 | doğrudan doğrulanabilir | 17059 SARIYER/KUMKÖY-KİLYOS (9.2 km, +32 m) | 17061 (kara), 17455 (mendirek/liman feneri), 18980 (kara), 19365 (kara) | — | — | Kural 17059 Kilyos'u seçiyor (9.2 km, Karadeniz kıyısı) ama anlık görüntüde sıcaklığı eksikti (-9999). İlçe merkezine en yakın 17061 Sarıyer (2.5 km, Δz +53 m). Gözden geçirilmeli. |
| Şile | 47 | doğrudan doğrulanabilir | 17610 ŞİLE (1.2 km, +36 m) | 18735 (kara), 18792 (kara) | — | — |  |
| Silivri | 8 | doğrudan doğrulanabilir | 18400 SİLİVRİ (14.5 km, +187 m) | 17438 (mendirek/liman feneri), 18793 (kara) | — | — | Tek uygun kara istasyonu 18400 merkezden 14.5 km içeride ve 187 m yüksekte. 0.8 km'deki 17438 mendirek feneri (Δz +1 m) deniz üzerinde olduğu için dışlandı. Gözden geçirilmeli. |
| Şişli | 95 | doğrudan doğrulanabilir | 18401 ŞİŞLİ (1.6 km, -35 m) | — | — | — |  |
| Sultanbeyli | 139 | **doğrudan doğrulanmamış** | — | — | 18399 SANCAKTEPE (4.8 km, -29 m); 17065 SAMANDIRA HAVALİMANI (4.9 km, -16 m); 19112 KARTAL/AYDOS DAĞI (5.1 km, +182 m) | 17065 |  |
| Sultangazi | 152 | **doğrudan doğrulanmamış** | — | — | 18101 EYÜPSULTAN (5.3 km, -98 m); 17814 GÜNGÖREN/DAVUTPAŞA MARMARA (8.9 km, -84 m); 18401 ŞİŞLİ (10.5 km, -92 m) | 18101? |  |
| Tuzla | 6 | doğrudan doğrulanabilir | 18100 TUZLA (1.6 km, -3 m) | 17437 (mendirek/liman feneri), 17448 (mendirek/liman feneri) | — | — |  |
| Ümraniye | 153 | doğrudan doğrulanabilir | 18403 ÜMRANİYE (3.5 km, +38 m) | — | — | — |  |
| Üsküdar | 2 | doğrudan doğrulanabilir | 18404 ÜSKÜDAR (2.7 km, +73 m) | — | — | — |  |
| Zeytinburnu | 30 | **doğrudan doğrulanmamış** | — | — | 17814 GÜNGÖREN/DAVUTPAŞA MARMARA (4.4 km, +38 m); 17454 FATİH/KUMKAPI FENERİ (5.3 km, -22 m); 17603 FATİH/İST.DEN.BİL.ENS. (5.5 km, -20 m) | 17060? |  |

**Gözden geçirilmesi gereken 4 eşleşme** (kural mekanik olarak uygulandı; proje sahibi/Faz 2 verisiyle karar verilecek): Pendik, Sarıyer, Silivri, Çekmeköy (gerekçeler "Not" sütununda). Kural iyileştirme önerisi: mesafeyi de içeren bir skor (ör. |Δz|/100 m + mesafe/10 km) ve en az 30 günlük QC'den geçmiş veri tamlığı şartı; Faz 2'de gerçek veri tamlığı ölçüldükten sonra karar verilsin.

## 4. METAR istasyonları

LTFM (MGM 17058, Arnavutköy), LTFJ (MGM 17063, Pendik), LTBA (MGM 17060, Bakırköy). Ayrıntılar ve AWC uç noktası için bkz. `docs/data-sources.md` → METAR bölümü.
