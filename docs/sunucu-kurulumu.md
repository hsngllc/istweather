# Sunucu kurulumu ve bilgisayardan taşıma

Faz 2'nin 48 saatlik ve Faz 3'ün 3 günlük kabulü kiralık sunucuda (VPS) yapılacak. Bu rehber
sunucuyu sıfırdan kurmayı ve bilgisayardaki kurulumu (veritabanı, GRIB ve Parquet dosyaları)
sunucuya taşımayı anlatıyor. Faz 8'e kalan üretim işleri burada yok: sunucu dışı yedek, yedekten
geri yükleme denemesi ve sitenin HTTPS ile yayına açılması.

- Komutlar 2026-11-03'te birincil kaynaklardan alındı (en altta liste).
- Taşıma betikleri bu bilgisayarda gerçek veriyle denendi (bkz. "Deneme").
- **İş bölümü:** 1. adım proje sahibinde. 2. adımdaki anahtarı Claude oluşturabilir; panele
  eklemek proje sahibinde. 3–8. adımları Claude bu bilgisayardan SSH ile yapabilir.

## 1. Sunucu siparişi (Hetzner Cloud)

| Seçenek | Değer | Neden |
|---|---|---|
| Tür | **CX33** (4 vCPU, 8 GB RAM, 80 GB NVMe disk, 20 TB trafik), x86; ayda 8,99 € (KDV hariç, 2026-11-05) | Ölçüm: worker olağan çalışmada ~1,4 GB, 21 saatlik kesintiden sonra tüm modeller birlikte toparlanırken ~3,8 GB; ortalama ~2 çekirdek. ARM (CAX) türleri denenmedi; yeniden boyutlandırmada mimari değişmez |
| Konum | Nürnberg veya Helsinki | CX sayfasındaki Avrupa konumları; konum sonradan değiştirilemez |
| İşletim sistemi | Ubuntu 24.04 LTS | Docker'ın desteklediği sürümlerden |
| Ağ | Genel IPv4 **açık** ve IPv6 | Bazı veri kaynakları IPv6 desteklemeyebilir |
| SSH anahtarı | 2. adımdaki `.pub` dosyasının içeriği | Şifreyle giriş kullanılmayacak |
| Güvenlik duvarı | Yeni Cloud Firewall: gelen TCP 22. TCP 80 ve 443 yalnız alan adı bağlanınca | Ücretsiz; kural yoksa gelen trafik kapalı |
| Yedek | Önerilir (ücretli, günlük disk kopyası; faturalama SSS'ine göre sunucu fiyatının %20'si) | Faz 8'deki sunucu dışı yedek kurulana kadar arşivi korur |

Disk yetmezse **CX43**'e (8 vCPU, 16 GB RAM, 160 GB disk, ayda 16,49 €) geçilebilir. Disk büyütme geri
alınamaz ve bölüm Rescue System'den elle büyütülür. Faturalama saatliktir, aylık tavanı vardır;
kapalı sunucu da ücretlidir, silinen sunucu için yalnız kullanılan saatler ödenir.

Docker'ın açtığı portlar sunucudaki `ufw` kurallarını atlar. Bu yüzden asıl koruma Hetzner'in
sunucu dışındaki güvenlik duvarı. Üretim ayarı (`docker-compose.prod.yml`) zaten yalnız Caddy'nin
80/443 portlarını dışarı açıyor; veritabanı ve API dışarı açık değil.

## 2. SSH anahtarı (bilgisayarda)

Git Bash'te:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/istweather_ed25519 -C istweather-sunucu
```

- `~/.ssh/istweather_ed25519.pub` dosyasının içeriğini siparişte "SSH key" alanına yapıştırın.
  Bu açık anahtardır; paylaşılabilir.
- Gizli anahtar (`.pub` uzantısız) bilgisayardan çıkmaz.
- Şifre sorusu boş bırakılırsa Claude sunucuya kendi başına bağlanabilir. O zaman bilgisayara
  erişen herkes sunucuya da erişebilir. Bilgisayar kaybolursa anahtarı sunucudan ve Hetzner
  panelinden silin.

Sunucu açılınca `~/.ssh/config` dosyasına ekleyin (`<IP>` sunucunun IPv4 adresi):

```
Host istweather
    HostName <IP>
    User hava
    IdentityFile ~/.ssh/istweather_ed25519
```

## 3. İlk giriş ve temel ayarlar (sunucuda, root)

```bash
ssh -i ~/.ssh/istweather_ed25519 root@<IP>
```

Günlük işler için `hava` kullanıcısı. Şifresi yok, girişi yalnız anahtarla; `sudo` şifre sormaz:

```bash
adduser --disabled-password --gecos "" hava
usermod -aG sudo hava
echo 'hava ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/hava && chmod 440 /etc/sudoers.d/hava
install -d -m 700 -o hava -g hava /home/hava/.ssh
install -m 600 -o hava -g hava /root/.ssh/authorized_keys /home/hava/.ssh/authorized_keys
```

Root girişini ve şifreli girişi kapatın. `sshd` her ayarda ilk okuduğu değeri kullanır; `00-` öneki
bu dosyayı öteki ayar dosyalarından önce okutur:

```bash
cat > /etc/ssh/sshd_config.d/00-istweather.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
EOF
sshd -t && systemctl restart ssh
```

Root oturumunu kapatmadan **ikinci bir pencerede** `ssh istweather` ile girişi deneyin.

Takas alanı (bellek tepelerinde işlemin öldürülmemesi için, 4 GB):

```bash
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

Güvenlik güncellemeleri Ubuntu'da varsayılan olarak her gün otomatik kurulur, ancak sunucu kendiliğinden yeniden başlamaz.
`/etc/apt/apt.conf.d/20auto-upgrades` içinde iki satırın da `"1"` olduğunu kontrol edin.
`/var/run/reboot-required` dosyası çıkarsa uygun bir saatte `sudo reboot` yeterli: Docker açılışta
kendiliğinden başlar, servisler `restart: unless-stopped` ile geri gelir. Sunucu saati UTC kalır.

## 4. Docker (sunucuda, hava kullanıcısı)

Docker'ın resmî apt deposu:

```bash
sudo apt update
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker hava
```

Çıkıp yeniden girin, ardından `docker run --rm hello-world` ve `docker compose version` ile kontrol
edin. Üretim ayarındaki `!reset`/`!override` için Compose 2.24 veya üstü gerekir.

## 5. Kod ve `.env` (sunucuda)

```bash
git clone https://github.com/hsngllc/istweather.git ~/istweather
```

`.env`'i bilgisayardan kopyalayın (Git Bash, `C:\istweather`'da). Anahtarlar sohbetten geçmez:

```bash
scp .env istweather:~/istweather/.env
```

Sunucuda düzenleyin:

```bash
cd ~/istweather && chmod 600 .env
sed -i 's/^HAVA_ENV=.*/HAVA_ENV=prod/' .env
echo 'COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml' >> .env
# Sunucunun kendi veritabanı şifresi (değer ekrana yazılmaz)
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 24)/" .env
```

- `COMPOSE_FILE` sayesinde sunucuda her `docker compose` komutu üretim ayarıyla çalışır.
- Alan adı varsa `HAVA_DOMAIN=` satırına yazın (ör. `api.ornek.com`). Alan adının DNS A kaydı sunucunun
  IPv4'üne yönlenmeli ve güvenlik duvarında 80/443 açılmalı.
- Telegram ve e-posta ayarları bilgisayardakiyle aynı kalır.

## 6. Taşıma

**Bilgisayarda** (Git Bash, `C:\istweather`). Toplama burada durur; sunucu 7. adımda devralır:

```bash
docker compose stop worker api
scripts/tasima-paketle.sh ~/istweather-tasima
scp -r ~/istweather-tasima istweather:~/
```

Paket ~3,2 GB:

| Dosya | İçerik | Boyut |
|---|---|---|
| `hava.dump` | Veritabanı (`pg_dump -Fc`) | ~0,85 GB |
| `veri.tar` | GRIB ve Parquet volume'ları | ~2,4 GB |
| ek dosyalar | Satır sayıları, TimescaleDB sürümü, sağlama toplamları | küçük |

Paketleme ~3 dakika sürer. Yükleme süresi ev internetinin yükleme hızına bağlı: 20 Mbit/sn'de ~25 dk,
50 Mbit/sn'de ~10 dk.

`pg_dump` şu uyarıyı verir, bu beklenen durum: "circular foreign-key constraints on this table:
continuous_agg". Bu, TimescaleDB'nin kendi kataloğundaki bir tablo. Tam dökümde sorun çıkarmaz ve
geri yükleme hatasız geçti.

**Sunucuda:**

```bash
cd ~/istweather
scripts/tasima-yukle.sh ~/istweather-tasima
```

Betik sırayla:

1. Sağlama toplamlarını, üretim ayarını, veritabanının boş olduğunu ve TimescaleDB sürümünün
   aynı olduğunu denetler.
2. TimescaleDB'nin belgelediği sırayla geri yükler: `timescaledb_pre_restore()` → `pg_restore`
   (`-j` olmadan) → `timescaledb_post_restore()` → `ANALYZE`.
3. Volume'ları açar.
4. Her tablonun satır sayısını paketle karşılaştırır.

Bir şey tutmazsa durur ve servisleri başlatmaz.

## 7. Başlatma ve kontrol (sunucuda)

```bash
# Alan adı yokken (Caddy'siz; API dışarı açık değil)
docker compose up -d db migrate api worker backup
# Alan adı bağlıyken
docker compose up -d
```

Kontrol:

```bash
docker compose ps
docker compose logs --tail 50 worker
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').read().decode())"
```

Toplayıcılar her 10 dakikada bir çalışır ve kaçan çalıştırmaları en çok 72 saat geriye dönük
arar. Ancak DWD dosyaları ~24 saat durur. Bu yüzden bilgisayarda toplamanın durması ile sunucuda
başlaması arasında 20 saatten fazla geçmemeli. GDPS duyuruları bu arada broker'daki kalıcı kuyrukta
bekler.

## 8. Bilgisayarı kapatma ve geri dönüş

Sunucuda ilk model çalıştırmaları yüklenince bilgisayarda:

```bash
docker compose down
```

- Volume'lar silinmez. Faz 3 kabulüne kadar bilgisayarda yedek olarak durur.
- **Bilgisayarda worker'ı bir daha başlatmayın.** GDPS duyuru kuyruğunun adı pakette sunucuya geçti.
  İki worker aynı kuyruğu paylaşırsa duyurular bölünür ve bildirimler iki kez gelir.
- Bilgisayarda geliştirme için yalnız `docker compose up db api` yeterli.
- **Geri dönüş:** sunucuda bir sorun çıkarsa sunucuda `docker compose stop worker` çalıştırın,
  bilgisayarda `docker compose up -d`. Sorun giderilince taşımayı yeni bir paketle tekrarlayın.
- Taşıma doğrulanınca paket klasörlerini iki tarafta da silin: `rm -rf ~/istweather-tasima`.

## 9. Kabul ölçümleri

Faz 2'de 48 saat kesintisiz toplama, Faz 3'te her model için 3 gün eksiksiz çalıştırma gerekiyor.
Ölçülecekler:

- `model_runs` durumları
- RAM ve işlemci: `docker stats --no-stream`
- Disk: `df -h /` ve `docker system df -v`

Loglar üretimde Docker'ın `local` sürücüsüyle döner (kapsayıcı başına 5 × 20 MB, sıkıştırılmış).

## Deneme (2026-11-03, bu bilgisayarda)

Gerçek kurulum (`hava`) paketlendi ve ayrı bir Compose projesine (`havatest`) üretim ayarıyla
yüklendi:

- **Paketleme:** 2 dk 54 sn. Worker ve API bu süre boyunca durdu.
- **Geri yükleme:** 4 dk, `pg_restore` hatasız.
- **Satır sayıları:** 15 tablonun hepsi aynı. Örnek: `point_forecasts` 9.380.406,
  `ensemble_stats` 156.450, `observations` 150.032, `model_runs` 3.028.
- **TimescaleDB:** 4 hypertable, parça sayıları, sıkıştırma ayarları ve 6 arka plan işi aynı.
  Alembic sürümü `0003`.
- **Dosyalar:** Parquet'te 5.896, GRIB'de 93 dosya; ad ve boyut listeleri aynı. Tek fark, paketten
  sonra büyümeye devam eden GDPS duyuru dosyası.
- **Sonrası:** `migrate` hatasız çalıştı (şema güncel, referans verisi idempotent). API sağlık ucu
  veritabanına bağlandı.
- **Güvenlik kontrolleri:** dolu veritabanına ikinci yükleme reddedildi; worker çalışırken
  paketleme reddedildi; üretim ayarı yokken yükleme reddedildi.
- Deneme projesi ve volume'ları ardından silindi.

## Kaynaklar

- Docker Engine, Ubuntu kurulumu ve güvenlik duvarı notu: https://docs.docker.com/engine/install/ubuntu/
- Docker, açılışta başlama ve kullanıcıyı `docker` grubuna ekleme: https://docs.docker.com/engine/install/linux-postinstall/
- Docker logları, `local` sürücüsü ve varsayılanları: https://docs.docker.com/engine/logging/configure/ ,
  https://docs.docker.com/engine/logging/drivers/local/
- Compose, `COMPOSE_FILE` ve `.env`: https://docs.docker.com/compose/how-tos/environment-variables/envvars/
- TimescaleDB mantıksal yedek ve geri yükleme: https://www.tigerdata.com/docs/self-hosted/latest/backup-and-restore/logical-backup
- Hetzner Cloud Firewall (ücretsiz; kural yoksa gelen trafik kapalı): https://docs.hetzner.com/cloud/firewalls/overview/
- Hetzner planları ve fiyatlar (2026-11-05): https://www.hetzner.com/cloud/cost-optimized/
- Hetzner yeniden boyutlandırma ve konum: https://docs.hetzner.com/cloud/servers/faq/
- Hetzner faturalama: https://docs.hetzner.com/cloud/billing/faq/
- Ubuntu otomatik güncellemeler: https://ubuntu.com/server/docs/how-to/software/automatic-updates/
