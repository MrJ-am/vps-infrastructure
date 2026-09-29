#!/bin/sh
# Exerce une restauration de la sauvegarde locale dans un espace isolé.
set -eu
revision=${1:?révision requise}
case "$revision" in *[!0-9a-f]*|'') exit 2;; esac
test "${#revision}" -eq 40
test "$(readlink -f /run/current-system)" = "$(cat "/root/nextcloud-preparations/$revision/https.systeme")"
backup=$(find /var/backup/nextcloud -mindepth 1 -maxdepth 1 -type d -name '20*Z' | sort | tail -n 1)
test -n "$backup"
(cd "$backup" && sha256sum -c SHA256SUMS >/dev/null)
test ! -e "/root/nextcloud-preparations/$revision/restauration-test"
test "$(runuser -u postgres -- psql -Atqc "SELECT count(*) FROM pg_database WHERE datname='nextcloud_validation'")" = 0
runuser -u postgres -- createdb nextcloud_validation
nettoyer() {
  runuser -u postgres -- dropdb --if-exists nextcloud_validation >/dev/null 2>&1 || true
  rm -rf -- "/root/nextcloud-preparations/$revision/restauration-test"
}
trap nettoyer EXIT
runuser -u postgres -- pg_restore --no-owner --no-acl -d nextcloud_validation < "$backup/base.dump" >/dev/null
tables=$(runuser -u postgres -- psql -Atqc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" nextcloud_validation)
test "$tables" -gt 10
mkdir "/root/nextcloud-preparations/$revision/restauration-test"
tar -C "/root/nextcloud-preparations/$revision/restauration-test" -xpf "$backup/fichiers.tar"
test -f "/root/nextcloud-preparations/$revision/restauration-test/config/config.php"
test -d "/root/nextcloud-preparations/$revision/restauration-test/data"
printf 'RESTAURATION_ISOLEE=oui TABLES=%s\n' "$tables"
