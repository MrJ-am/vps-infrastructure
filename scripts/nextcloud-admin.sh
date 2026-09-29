#!/bin/sh
# Le secret arrive par SSH sur stdin, jamais en argument ou dans les journaux.
set -eu
revision=${1:?révision requise}
case "$revision" in *[!0-9a-f]*|'') exit 2;; esac
test "${#revision}" -eq 40
dossier="/root/nextcloud-preparations/$revision"
test "$(readlink -f /run/current-system)" = "$(cat "$dossier/https.systeme")"
test -f "$dossier/retour-arme"
test ! -e "$dossier/retour-effectue"
test -s "$dossier/admin-password"
umask 077
if ! runuser -u nextcloud -- nextcloud-occ user:info admin >/dev/null 2>&1; then
  OC_PASS=$(cat "$dossier/admin-password")
  export OC_PASS
  runuser -u nextcloud -- nextcloud-occ user:add --password-from-env --group=admin admin >/dev/null
  unset OC_PASS
fi
runuser -u nextcloud -- nextcloud-occ user:info admin --output=json |
  jq -e '.enabled == true and (.groups | index("admin") != null)' >/dev/null
printf 'ADMIN_CREE=oui\n'
