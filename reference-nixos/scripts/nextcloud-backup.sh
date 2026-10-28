set -euo pipefail
umask 077
destination=/var/backup/nextcloud
mkdir -p "$destination"
chmod 0700 "$destination"
horodatage=$(date -u +%Y%m%dT%H%M%SZ)
temporaire="$destination/$horodatage.tmp"
final="$destination/$horodatage"
mkdir "$temporaire"
maintenance=0
restaurer_service() {
  if test "$maintenance" -eq 1; then
    runuser -u nextcloud -- nextcloud-occ maintenance:mode --off || true
  fi
}
trap restaurer_service EXIT
trap 'exit 1' HUP INT TERM
runuser -u nextcloud -- nextcloud-occ maintenance:mode --on
maintenance=1
runuser -u postgres -- pg_dump --format=custom --no-owner --no-acl nextcloud > "$temporaire/base.dump"
tar -C /var/lib/nextcloud -cpf "$temporaire/fichiers.tar" config data
(cd "$temporaire" && sha256sum base.dump fichiers.tar > SHA256SUMS)
runuser -u nextcloud -- nextcloud-occ maintenance:mode --off
maintenance=0
mv -T "$temporaire" "$final"
find "$destination" -mindepth 1 -maxdepth 1 -type d -name '20*Z' -mtime +7 -exec rm -rf -- {} +
printf 'Sauvegarde locale cohérente créée : %s\n' "$horodatage"
