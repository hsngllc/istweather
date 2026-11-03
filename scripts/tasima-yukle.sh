#!/usr/bin/env bash
# Sunucuya taşıma, 2. adım — sunucuda (repo kökünde, .env hazırken) çalışır.
#
#   scripts/tasima-yukle.sh ~/istweather-tasima
#
# tasima-paketle.sh paketini BOŞ bir kuruluma yükler: sağlama toplamlarını denetler, veritabanını
# TimescaleDB'nin belgelediği sırayla geri yükler (pre_restore → pg_restore, -j olmadan →
# post_restore → ANALYZE), GRIB/Parquet volume'larını açar ve tablo satır sayılarını paketle
# karşılaştırır. Veritabanında tablo varsa hiçbir şey yapmadan çıkar. Servisleri başlatmaz.
set -euo pipefail
export MSYS_NO_PATHCONV=1

src=${1:?"Kullanım: $0 <paket klasörü>"}
host_src=$(cd "$src" && { pwd -W 2>/dev/null || pwd; })

# stdin kapalı: aşağıdaki while döngüsünde okunan tablo listesini tüketmesin.
psql_db() {
  docker compose exec -T db sh -c \
    'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atq "$@"' sh "$@" </dev/null
}

if ! docker compose config --services | grep -qx caddy; then
  echo "Üretim katmanı etkin değil: .env'e COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml" >&2
  exit 1
fi

echo "Sağlama toplamları..."
(cd "$src" && sha256sum -c --quiet SHA256SUMS)

docker compose build
docker compose up -d --wait db

if [ "$(psql_db -c "select count(*) from pg_tables where schemaname = 'public'")" != 0 ]; then
  echo "Veritabanı boş değil; yükleme yapılmadı." >&2
  exit 1
fi
want=$(tr -d '\r\n' <"$src/timescaledb.txt")
have=$(psql_db -c "select default_version from pg_available_extensions where name = 'timescaledb'")
if [ "$want" != "$have" ]; then
  echo "TimescaleDB sürümü farklı (paket $want, sunucu $have); yükleme yapılmadı." >&2
  exit 1
fi

echo "Veritabanı geri yükleniyor..."
docker compose cp "$host_src/hava.dump" db:/tmp/hava.dump
psql_db -c "create extension if not exists timescaledb" -c "select timescaledb_pre_restore()" \
  >/dev/null
docker compose exec -T db sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner /tmp/hava.dump'
psql_db -c "select timescaledb_post_restore()" -c "analyze" >/dev/null
docker compose exec -T db rm -f /tmp/hava.dump

echo "GRIB ve Parquet volume'ları açılıyor..."
docker compose run --rm --no-deps --user root -v "$host_src:/in:ro" worker \
  tar -C /data -xf /in/veri.tar

echo "Satır sayıları karşılaştırılıyor..."
fail=0
while IFS=$'\t' read -r t n; do
  got=$(psql_db -c "select count(*) from public.\"$t\"")
  if [ "$got" = "${n%$'\r'}" ]; then
    printf '  %-22s %12s  tamam\n' "$t" "$got"
  else
    printf '  %-22s %12s  FARKLI (paket %s)\n' "$t" "$got" "$n"
    fail=1
  fi
done <"$src/tablolar.tsv"
if [ "$fail" != 0 ]; then
  echo "Satır sayıları tutmuyor; servisleri başlatmayın." >&2
  exit 1
fi
echo "Yükleme tamam. Başlatma: docs/sunucu-kurulumu.md, adım 7."
