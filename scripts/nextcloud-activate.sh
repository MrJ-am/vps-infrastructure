#!/bin/sh
# Phases fixes, révision construite et vérifiée. Aucun argument de commande libre.
set -eu
export LC_ALL=C
phase=${1:?phase requise}
revision=${2:?révision requise}
case "$revision" in *[!0-9a-f]*|'') exit 2;; esac
test "${#revision}" -eq 40
case "$phase" in preparer|acme|https|enregistrer|retour|constater) ;; *) exit 2;; esac
dossier="/root/nextcloud-preparations/$revision"
racines="/nix/var/nix/gcroots/nextcloud/$revision"
ancien=/nix/store/g24p3rvq97s1x66wiaw29z5kwqgw0ksl-nixos-system-nixos-26.05.8639.c5c4a43b0e80
premier_timer="nextcloud-retour-$(printf '%s' "$revision" | cut -c 1-12).timer"
timer="$premier_timer"
if test -f "$dossier/retour-effectue" || test -d "$dossier/essai-1"; then
  timer="${premier_timer%.timer}-2.timer"
fi
test -f "$dossier/termine"
test "$(readlink -f "$racines/acme")" = "$(cat "$dossier/acme.systeme")"
test "$(readlink -f "$racines/https")" = "$(cat "$dossier/https.systeme")"

verifier_anciens() {
  for service in sshd nginx postgresql matheval vision mrj-auth; do
    systemctl is-active --quiet "$service"
  done
  test "$(readlink -f /srv/matheval/current)" = /srv/matheval/releases/04168b68723322afe18b51d20e8089121348b8b3
  test "$(readlink -f /srv/vision/current)" = /srv/vision/releases/3cbd57ff8d05798e3766fd0d6c93087739d8b608
  test "$(readlink -f /srv/logique/current)" = /srv/logique/releases/2e2dd6a48cbdad20bbc8d0ac34a9ace67f111a0f
}

case "$phase" in
preparer)
  # Une tentative antérieure peut avoir installé les données puis été annulée.
  # Archiver les marqueurs de retour ; ne jamais effacer base, certificat ou fichiers.
  if test -e /var/lib/nextcloud; then
    test -f "$dossier/retour-effectue"
    test -f /var/lib/nextcloud/config/config.php
    test ! -e "$dossier/essai-1"
    systemctl stop "$premier_timer"
    test "$(systemctl is-active "$premier_timer" || :)" != active
    mkdir "$dossier/essai-1"
    for trace in retour-arme retour-effectue retour.sh configuration-avant.nix bascule.lock; do
      if test -e "$dossier/$trace"; then mv "$dossier/$trace" "$dossier/essai-1/$trace"; fi
    done
  fi
  test ! -e "$dossier/retour-arme"
  test "$(readlink -f /run/current-system)" = "$ancien"
  test "$(readlink -f /nix/var/nix/profiles/system)" = "$ancien"
  test "$(sha256sum /etc/nixos/configuration.nix | cut -d ' ' -f 1)" = 57cfbe6ac09438eab9a535e5618d2dfe510da3905d51d6eb32313a6c31b8b88d
  verifier_anciens
  cp -a /etc/nixos/configuration.nix "$dossier/configuration-avant.nix"
  sh_bin=$(command -v sh)
  flock_bin=$(command -v flock)
  cp_bin=$(command -v cp)
  mv_bin=$(command -v mv)
  touch_bin=$(command -v touch)
  nix_env_bin=$(command -v nix-env)
  cat > "$dossier/retour.sh" <<EOF
#!$sh_bin
set -eu
exec 9>"$dossier/bascule.lock"
"$flock_bin" -x 9
test ! -e "$dossier/enregistre" || exit 0
"$cp_bin" -a "$dossier/configuration-avant.nix" /etc/nixos/configuration.nextcloud-retour
"$mv_bin" -Tf /etc/nixos/configuration.nextcloud-retour /etc/nixos/configuration.nix
"$nix_env_bin" --profile /nix/var/nix/profiles/system --set "$ancien"
"$ancien/bin/switch-to-configuration" switch
"$touch_bin" "$dossier/retour-effectue"
EOF
  chmod 0700 "$dossier/retour.sh"
  "$sh_bin" -n "$dossier/retour.sh"
  systemd-run --unit="${timer%.timer}" --on-active=60m "$sh_bin" "$dossier/retour.sh"
  systemctl is-active --quiet "$timer"
  touch "$dossier/retour-arme"
  printf 'RETOUR_ARME=%s\n' "$timer"
  ;;
acme)
  test -f "$dossier/retour-arme"
  test ! -e "$dossier/retour-effectue"
  systemctl is-active --quiet "$timer"
  "$(cat "$dossier/acme.systeme")/bin/switch-to-configuration" test
  verifier_anciens
  test "$(readlink -f /run/current-system)" = "$(cat "$dossier/acme.systeme")"
  test "$(readlink -f /nix/var/nix/profiles/system)" = "$ancien"
  test "$(curl -sS -o /dev/null -w '%{http_code}' --resolve cloud.mrj.am:80:127.0.0.1 http://cloud.mrj.am/)" = 503
  systemctl start acme-cloud.mrj.am.service
  test -s /var/lib/acme/cloud.mrj.am/fullchain.pem
  test -s /var/lib/acme/cloud.mrj.am/key.pem
  printf 'ACME_CERTIFICAT_PRESENT=oui\n'
  ;;
https)
  test -f "$dossier/retour-arme"
  test ! -e "$dossier/retour-effectue"
  systemctl is-active --quiet "$timer"
  test -s /var/lib/acme/cloud.mrj.am/fullchain.pem
  test "$(readlink -f /run/current-system)" = "$(cat "$dossier/acme.systeme")"
  nginx_command=$(jq -r .nginx "$dossier/https.json")
  nginx_bin=$(printf '%s\n' "$nginx_command" | cut -d ' ' -f 1)
  nginx_conf=$(printf '%s\n' "$nginx_command" | sed -n "s/.* -c '\\([^']*\\)'$/\\1/p")
  case "$nginx_bin:$nginx_conf" in /nix/store/*/bin/nginx:/nix/store/*) ;; *) exit 1;; esac
  "$nginx_bin" -t -c "$nginx_conf"
  "$(cat "$dossier/https.systeme")/bin/switch-to-configuration" test
  verifier_anciens
  test "$(readlink -f /run/current-system)" = "$(cat "$dossier/https.systeme")"
  test "$(readlink -f /nix/var/nix/profiles/system)" = "$ancien"
  systemctl is-active --quiet phpfpm-nextcloud redis-nextcloud nginx
  test "$(systemctl show nextcloud-setup --property=Result --value)" = success
  runuser -u nextcloud -- nextcloud-occ status --output=json | jq -e \
    '.installed == true and .maintenance == false and .needsDbUpgrade == false and .versionstring == "34.0.4"' >/dev/null
  printf 'NEXTCLOUD_INSTALLE=34.0.4\n'
  ;;
retour)
  if test -f "$dossier/retour-arme" && test ! -f "$dossier/enregistre"; then
    "$dossier/retour.sh"
  fi
  ;;
enregistrer)
  test -f "$dossier/retour-arme"
  test ! -e "$dossier/retour-effectue"
  systemctl is-active --quiet "$timer"
  test "$(readlink -f /run/current-system)" = "$(cat "$dossier/https.systeme")"
  test "$(readlink -f /nix/var/nix/profiles/system)" = "$ancien"
  verifier_anciens
  systemctl is-active --quiet nextcloud-backup.timer nextcloud-cron.timer
  entry="$dossier/configuration-apres.nix"
  printf '{ imports = [ /etc/nixos/vps-infrastructure/%s/hosts/hostinger/logique.nix ]; }\n' "$revision" > "$entry"
  nixpkgs=$(nix-instantiate --find-file nixpkgs)
  resultat=$(nix-instantiate --eval --strict --json "$dossier/source/scripts/logique-config.nix" \
    --argstr configuration "$entry" -I "nixpkgs=$nixpkgs" | jq -r .systeme)
  test "$resultat" = "$(cat "$dossier/https.systeme")"
  exec 9>"$dossier/bascule.lock"
  flock -x 9
  test ! -e "$dossier/retour-effectue"
  cp -a "$entry" /etc/nixos/configuration.nextcloud-final
  mv -Tf /etc/nixos/configuration.nextcloud-final /etc/nixos/configuration.nix
  nix-env --profile /nix/var/nix/profiles/system --set "$resultat"
  touch "$dossier/enregistre"
  systemctl stop "$timer"
  test "$(readlink -f /nix/var/nix/profiles/system)" = "$resultat"
  printf 'GENERATION_ENREGISTREE=%s\n' "$resultat"
  ;;
constater)
  test -f "$dossier/enregistre"
  test ! -e "$dossier/retour-effectue"
  test "$(readlink -f /run/current-system)" = "$(cat "$dossier/https.systeme")"
  test "$(readlink -f /nix/var/nix/profiles/system)" = "$(cat "$dossier/https.systeme")"
  test "$(systemctl is-active "$timer" || :)" != active
  verifier_anciens
  systemctl is-active --quiet phpfpm-nextcloud redis-nextcloud nginx
  test "$(systemctl show nextcloud-setup --property=Result --value)" = success
  printf 'CONSTAT_FINAL=oui\n'
  ;;
esac
