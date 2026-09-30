#!/bin/sh
# Installation bornée de Talk ; aucun changement de canal ou d'identifiants.
set -eu
export LC_ALL=C
phase=${1:?phase}
revision=${2:?revision}
case "$phase" in construire|activer|constater) ;; *) exit 2;; esac
case "$revision" in *[!0-9a-f]*|'') exit 2;; esac
test "${#revision}" -eq 40
ancien=/nix/store/c06sq9vp17l36j8xp2apyfav1nribpwc-nixos-system-nixos-26.05.8639.c5c4a43b0e80
dossier="/root/nextcloud-talk/$revision"
source="/etc/nixos/vps-infrastructure/talk-$revision"
racines="/nix/var/nix/gcroots/nextcloud-talk/$revision"
timer="nextcloud-talk-retour-$(printf '%s' "$revision" | cut -c1-12).timer"

verifier_sites() {
  for service in sshd nginx postgresql matheval vision mrj-auth phpfpm-nextcloud redis-nextcloud; do
    systemctl is-active --quiet "$service"
  done
  test "$(readlink -f /srv/matheval/current)" = /srv/matheval/releases/04168b68723322afe18b51d20e8089121348b8b3
  test "$(readlink -f /srv/vision/current)" = /srv/vision/releases/3cbd57ff8d05798e3766fd0d6c93087739d8b608
  test "$(readlink -f /srv/logique/current)" = /srv/logique/releases/2e2dd6a48cbdad20bbc8d0ac34a9ace67f111a0f
  runuser -u nextcloud -- nextcloud-occ status --output=json |
    jq -e '.installed and (.maintenance|not) and (.needsDbUpgrade|not) and .versionstring == "34.0.4"' >/dev/null
}

verifier_talk() {
  verifier_sites
  runuser -u nextcloud -- nextcloud-occ app:list --output=json |
    jq -e '.enabled.spreed == "24.0.4"' >/dev/null
  test "$(curl --fail -sS https://cloud.mrj.am/status.php | jq -r .versionstring)" = 34.0.4
  code=$(curl -sS -o /dev/null -w '%{http_code}' -H 'OCS-APIRequest: true' 'https://cloud.mrj.am/ocs/v2.php/apps/spreed/api/v4/room?format=json')
  test "$code" = 401
  runuser -u postgres -- psql nextcloud -Atqc "SELECT count(*) FROM information_schema.tables WHERE table_name LIKE 'oc_talk_%'" |
    awk '{ if ($1 < 5) exit 1 }'
  systemctl is-active --quiet nextcloud-backup.timer nextcloud-cron.timer
  test "$(systemctl show nextcloud-setup --property=Result --value)" = success
  printf 'TALK_ACTIVE=24.0.4\nAPI_TALK_ANONYME=401\n'
}

case "$phase" in
construire)
  test "$(readlink -f /run/current-system)" = "$ancien"
  test "$(readlink -f /nix/var/nix/profiles/system)" = "$ancien"
  test "$(sha256sum /etc/nixos/configuration.nix | cut -d' ' -f1)" = 04fdd2382d474b7ea596c64cdaabe77e96cb08fc2edd6f23502bf9ea4057ebbc
  verifier_sites
  runuser -u nextcloud -- nextcloud-occ app:list --output=json | jq -e '.enabled.spreed == null and .disabled.spreed == null' >/dev/null
  test "$(df -Pk / | awk 'NR==2 {print $4}')" -gt 10000000
  mkdir -p "$racines"
  ln -s "$ancien" "$racines/avant"
  nixpkgs=$(nix-instantiate --find-file nixpkgs)
  test "$nixpkgs" = /nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos
  cp -a /etc/nixos/configuration.nix "$dossier/configuration-avant.nix"
  evaluer() {
    nix-instantiate --eval --strict --json "$source/scripts/logique-config.nix" --argstr configuration "$1" -I "nixpkgs=$nixpkgs"
  }
  evaluer /etc/nixos/configuration.nix > "$dossier/avant.json"
  test "$(jq -r .systeme "$dossier/avant.json")" = "$ancien"
  evaluer "$source/hosts/hostinger/logique.nix" > "$dossier/apres.json"
  jq -e --slurpfile a "$dossier/avant.json" '.invariant == $a[0].invariant' "$dossier/apres.json" >/dev/null
  nix-build '<nixpkgs/nixos>' -A system -I "nixpkgs=$nixpkgs" -I "nixos-config=$source/hosts/hostinger/logique.nix" --out-link "$racines/apres" > "$dossier/systeme"
  test "$(cat "$dossier/systeme")" = "$(jq -r .systeme "$dossier/apres.json")"
  candidat=$(cat "$dossier/systeme")
  "$candidat/bin/switch-to-configuration" dry-activate > "$dossier/plan.txt" 2>&1
  # Le plan complet reste privé ; refuser toute modification des services critiques.
  if sed -n '/stopping the following units:/p;/restarting the following units:/p' "$dossier/plan.txt" |
    grep -Eq '(sshd|postgresql|matheval|vision|mrj-auth|systemd-networkd)\.service'; then exit 1; fi
  nginx_command=$(jq -r .nginx "$dossier/apres.json")
  nginx_bin=$(printf '%s\n' "$nginx_command" | cut -d' ' -f1)
  nginx_conf=$(printf '%s\n' "$nginx_command" | sed -n "s/.* -c '\([^']*\)'$/\1/p")
  case "$nginx_bin:$nginx_conf" in /nix/store/*/bin/nginx:/nix/store/*) ;; *) exit 1;; esac
  "$nginx_bin" -t -c "$nginx_conf"
  test "$(readlink -f /run/current-system)" = "$ancien"
  touch "$dossier/construit"
  printf 'TALK_CONSTRUIT=%s\n' "$candidat"
  ;;
activer)
  test -f "$dossier/construit"
  test ! -e "$dossier/retour-arme"
  test "$(readlink -f /run/current-system)" = "$ancien"
  test "$(readlink -f /nix/var/nix/profiles/system)" = "$ancien"
  cmp /etc/nixos/configuration.nix "$dossier/configuration-avant.nix"
  verifier_sites
  systemctl start nextcloud-backup.service
  test "$(systemctl show nextcloud-backup --property=Result --value)" = success
  # Comptes et métadonnées des fichiers : contrôle privé, sans contenu personnel.
  runuser -u postgres -- psql nextcloud -Atqc 'SELECT row_to_json(u)::text FROM oc_users u ORDER BY uid' > "$dossier/comptes-avant"
  runuser -u postgres -- psql nextcloud -Atqc 'SELECT row_to_json(f)::text FROM oc_filecache f ORDER BY fileid' > "$dossier/fichiers-avant"
  chmod 0600 "$dossier/comptes-avant" "$dossier/fichiers-avant"
  sh_bin=$(command -v sh)
  flock_bin=$(command -v flock)
  cp_bin=$(command -v cp)
  mv_bin=$(command -v mv)
  nix_env_bin=$(command -v nix-env)
  runuser_bin=$(command -v runuser)
  occ_bin=$(command -v nextcloud-occ)
  touch_bin=$(command -v touch)
  cat > "$dossier/retour.sh" <<EOF
#!$sh_bin
set -eu
exec 9>"$dossier/bascule.lock"
"$flock_bin" -x 9
test ! -e "$dossier/enregistre" || exit 0
"$runuser_bin" -u nextcloud -- "$occ_bin" app:disable spreed >/dev/null || :
"$cp_bin" -a "$dossier/configuration-avant.nix" /etc/nixos/configuration.talk-retour
"$mv_bin" -Tf /etc/nixos/configuration.talk-retour /etc/nixos/configuration.nix
"$nix_env_bin" --profile /nix/var/nix/profiles/system --set "$ancien"
"$ancien/bin/switch-to-configuration" switch
"$touch_bin" "$dossier/retour-effectue"
EOF
  chmod 0700 "$dossier/retour.sh"
  "$sh_bin" -n "$dossier/retour.sh"
  systemd-run --unit="${timer%.timer}" --on-active=30m "$sh_bin" "$dossier/retour.sh"
  systemctl is-active --quiet "$timer"
  touch "$dossier/retour-arme"
  candidat=$(cat "$dossier/systeme")
  trap '"$dossier/retour.sh"' EXIT
  "$candidat/bin/switch-to-configuration" test
  verifier_talk
  runuser -u postgres -- psql nextcloud -Atqc 'SELECT row_to_json(u)::text FROM oc_users u ORDER BY uid' > "$dossier/comptes-apres"
  runuser -u postgres -- psql nextcloud -Atqc 'SELECT row_to_json(f)::text FROM oc_filecache f ORDER BY fileid' > "$dossier/fichiers-apres"
  cmp "$dossier/comptes-avant" "$dossier/comptes-apres"
  cmp "$dossier/fichiers-avant" "$dossier/fichiers-apres"
  touch "$dossier/teste"
  # L'enregistrement est une phase séparée exécutée après une nouvelle connexion.
  trap - EXIT
  printf 'TALK_TESTE_COMPTES_ET_FICHIERS_PRESERVES\n'
  ;;
constater)
  test -f "$dossier/teste"
  test ! -e "$dossier/retour-effectue"
  candidat=$(cat "$dossier/systeme")
  test "$(readlink -f /run/current-system)" = "$candidat"
  verifier_talk
  exec 9>"$dossier/bascule.lock"
  flock -x 9
  test ! -e "$dossier/retour-effectue"
  systemctl is-active --quiet "$timer"
  printf '{ imports = [ %s/hosts/hostinger/logique.nix ]; }\n' "$source" > /etc/nixos/configuration.talk-final
  mv -Tf /etc/nixos/configuration.talk-final /etc/nixos/configuration.nix
  nix-env --profile /nix/var/nix/profiles/system --set "$candidat"
  "$candidat/bin/switch-to-configuration" boot
  test "$(readlink -f /nix/var/nix/profiles/system)" = "$candidat"
  touch "$dossier/enregistre"
  systemctl stop "$timer"
  test "$(systemctl is-active "$timer" || :)" != active
  printf 'TALK_ENREGISTRE=%s\nRETOUR_DESARME=oui\n' "$candidat"
  ;;
esac
