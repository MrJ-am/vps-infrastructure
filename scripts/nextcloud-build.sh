#!/bin/sh
# Préparation non activante sur le Nixpkgs réellement installé.
set -eu
export LC_ALL=C
revision=${1:?révision complète requise}
case "$revision" in *[!0-9a-f]*|'') exit 2;; esac
test "${#revision}" -eq 40
preparation="/root/nextcloud-preparations/$revision"
source="$preparation/source"
test -f "$source/hosts/hostinger/nextcloud-acme.nix"
test -f "$source/hosts/hostinger/logique.nix"
test ! -e "$preparation/termine"

actif=$(readlink -f /run/current-system)
demarrage=$(readlink -f /nix/var/nix/profiles/system)
test "$actif" = "$demarrage"
test "$actif" = /nix/store/g24p3rvq97s1x66wiaw29z5kwqgw0ksl-nixos-system-nixos-26.05.8639.c5c4a43b0e80
test "$(sha256sum /etc/nixos/configuration.nix | cut -d ' ' -f 1)" = 57cfbe6ac09438eab9a535e5618d2dfe510da3905d51d6eb32313a6c31b8b88d
test "$(readlink -f /srv/matheval/current)" = /srv/matheval/releases/04168b68723322afe18b51d20e8089121348b8b3
test "$(readlink -f /srv/vision/current)" = /srv/vision/releases/3cbd57ff8d05798e3766fd0d6c93087739d8b608
test "$(readlink -f /srv/logique/current)" = /srv/logique/releases/2e2dd6a48cbdad20bbc8d0ac34a9ace67f111a0f
for unit in sshd nginx postgresql matheval vision mrj-auth; do systemctl is-active --quiet "$unit"; done
test "$(df -Pk / | awk 'NR==2 {print $4}')" -gt 20000000
test "$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)" -gt 3000000
test ! -e /var/lib/nextcloud
test ! -e /var/lib/acme/cloud.mrj.am
printf 'PRECONDITIONS_ACTIVES_OK\n'

nixpkgs=$(nix-instantiate --find-file nixpkgs)
test "$nixpkgs" = /nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos
test "$(sha256sum "$source/modules/postgresql.nix" | cut -d ' ' -f 1)" = 2de21683bcecdc95e36d0357fb42fc2a8c84db465bd3a35cb6454e0032c8b9f9
jq -e 'keys == ["matheval","nextcloud","vision"] and
  .matheval.name == "matheval" and .vision.name == "vision" and
  .nextcloud.name == "nextcloud"' "$source/databases.json" >/dev/null
installe="/etc/nixos/vps-infrastructure/$revision"
if test -e "$installe"; then
  if ! diff -qr "$source" "$installe" >/dev/null; then
    printf 'La copie candidate diffère de la source exacte ; arrêt.\n' >&2
    exit 1
  fi
else
  cp -a "$source" "$installe"
fi
printf 'SOURCES_CANDIDATES_IDENTIQUES\n'
racines="/nix/var/nix/gcroots/nextcloud/$revision"
mkdir -p "$racines"
for lien in avant nixpkgs; do
  case "$lien" in avant) cible="$actif";; nixpkgs) cible="$nixpkgs";; esac
  if test -L "$racines/$lien"; then
    test "$(readlink "$racines/$lien")" = "$cible"
  else
    ln -s "$cible" "$racines/$lien"
  fi
done
printf 'RACINES_NIX_CONSERVEES\n'

evaluer() {
  nix-instantiate --eval --strict --json "$installe/scripts/logique-config.nix" \
    --argstr configuration "$1" -I "nixpkgs=$nixpkgs"
}
evaluer /etc/nixos/configuration.nix > "$preparation/reference.json"
printf 'REFERENCE_SYSTEME=%s\n' "$(jq -r .systeme "$preparation/reference.json")"
test "$(jq -r .systeme "$preparation/reference.json")" = "$actif"

for phase in acme https; do
  case "$phase" in
    acme) config="$installe/hosts/hostinger/nextcloud-acme.nix";;
    https) config="$installe/hosts/hostinger/logique.nix";;
  esac
  evaluer "$config" > "$preparation/$phase.json"
  if ! jq -e --slurpfile reference "$preparation/reference.json" \
    'def garder_existant: .invariant | .services = ([.services[0]] + .services[3:]);
      garder_existant == ($reference[0] | garder_existant)
      and .systeme != $reference[0].systeme' \
    "$preparation/$phase.json" >/dev/null; then
    jq -n --slurpfile a "$preparation/reference.json" --slurpfile b "$preparation/$phase.json" \
      '{clesModifiees: [($a[0].invariant|keys[]) as $k | select($a[0].invariant[$k] != $b[0].invariant[$k]) | $k],
        indicesServices: [range(0;($a[0].invariant.services|length)) as $i | select($a[0].invariant.services[$i] != $b[0].invariant.services[$i]) | $i]}'
    printf 'Invariant modifié en phase %s ; construction interrompue.\n' "$phase" >&2
    exit 1
  fi
  nix-build '<nixpkgs/nixos>' -A system -I "nixpkgs=$nixpkgs" \
    -I "nixos-config=$config" --out-link "$racines/$phase" > "$preparation/$phase.systeme"
  test "$(jq -r .systeme "$preparation/$phase.json")" = "$(cat "$preparation/$phase.systeme")"
done

# Seule la phase ACME ne dépend pas encore d'un certificat absent.
nginx_command=$(jq -r .nginx "$preparation/acme.json")
nginx_bin=$(printf '%s\n' "$nginx_command" | cut -d ' ' -f 1)
nginx_conf=$(printf '%s\n' "$nginx_command" | sed -n 's/.* -c \([^ ]*\).*/\1/p')
case "$nginx_bin:$nginx_conf" in
  /nix/store/*/bin/nginx:/nix/store/*) "$nginx_bin" -t -c "$nginx_conf";;
  *) printf 'Commande Nginx candidate inattendue\n' >&2; exit 1;;
esac
touch "$preparation/termine"
printf 'CANDIDAT_CONSTRUIT=%s\nACME_SYSTEME=%s\nHTTPS_SYSTEME=%s\n' \
  "$revision" "$(cat "$preparation/acme.systeme")" "$(cat "$preparation/https.systeme")"
printf 'ACTIF_INCHANGE=%s\n' "$(readlink -f /run/current-system)"
