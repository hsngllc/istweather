#!/usr/bin/env bash
# Sunucuya taşıma, 1. adım — bilgisayarda (Git Bash, repo kökünde) çalışır.
#
#   docker compose stop worker api
#   scripts/tasima-paketle.sh ~/istweather-tasima
#
# Çıktı klasörü:
#   hava.dump        veritabanı (pg_dump özel biçim; TimescaleDB sıkıştırılmış parçalar dahil)
#   veri.tar         /data/grib ve /data/parquet (ARPEGE geçici dosyaları hariç; GDPS kuyruk adı dahil)
#   tablolar.tsv     tablo başına satır sayısı (sunucuda yüklemeden sonra karşılaştırılır)
#   timescaledb.txt  TimescaleDB sürümü (sunucudaki sürümle aynı olmalı)
#   SHA256SUMS       aktarım bozulmasın diye sağlama toplamları
# Worker çalışırken paketlemez: veritabanı ve dosyalar aynı anı göstermeli.
set -euo pipefail
export MSYS_NO_PATHCONV=1

out=${1:?"Kullanım: $0 <çıktı klasörü>"}
mkdir -p "$out"
if [ -n "$(ls -A "$out")" ]; then
  echo "Çıktı klasörü boş değil: $out" >&2
  exit 1
fi
# Windows'ta Docker'a C:/... biçiminde yol verilir; Linux'ta olduğu gibi kalır.
host_out=$(cd "$out" && { pwd -W 2>/dev/null || pwd; })

# stdin kapalı: döngü içinde çağrılınca okunan listeyi tüketmesin.
psql_db() {
  docker compose exec -T db sh -c \
    'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atq "$@"' sh "$@" </dev/null
}

if [ -n "$(docker compose ps -q --status running worker api)" ]; then
  echo "worker veya api çalışıyor; önce durdurun: docker compose stop worker api" >&2
  exit 1
fi

echo "Satır sayıları..."
for t in $(psql_db -c "select tablename from pg_tables where schemaname = 'public' order by 1"); do
  printf '%s\t%s\n' "$t" "$(psql_db -c "select count(*) from public.\"$t\"")"
done >"$out/tablolar.tsv"
psql_db -c "select extversion from pg_extension where extname = 'timescaledb'" >"$out/timescaledb.txt"

echo "Veritabanı dökümü..."
docker compose exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/hava.dump'
docker compose cp db:/tmp/hava.dump "$host_out/hava.dump"
docker compose exec -T db rm -f /tmp/hava.dump

echo "GRIB ve Parquet volume'ları..."
docker compose run --rm --no-deps --user root -v "$host_out:/out" worker \
  tar -C /data --exclude=grib/_tmp -cf /out/veri.tar grib parquet

(cd "$out" && sha256sum hava.dump veri.tar tablolar.tsv timescaledb.txt >SHA256SUMS)
echo "Paket hazır: $out"
du -sh "$out"/*
