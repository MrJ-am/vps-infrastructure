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

nixpkgs=$(nix-instantiate --find-file nixpkgs)
test "$nixpkgs" = /nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos
installe="/etc/nixos/vps-infrastructure/$revision"
test ! -e "$installe"
cp -a "$source" "$installe"
racines="/nix/var/nix/gcroots/nextcloud/$revision"
mkdir -p "$racines"
ln -s "$actif" "$racines/avant"
ln -s "$nixpkgs" "$racines/nixpkgs"

evaluer() {
  nix-instantiate --eval --strict --json "$installe/scripts/logique-config.nix" \
    --argstr configuration "$1" -I "nixpkgs=$nixpkgs"
}
evaluer /etc/nixos/configuration.nix > "$preparation/reference.json"
python3 - "$preparation/reference.json" "$actif" <<'PY'
import json,sys
assert json.load(open(sys.argv[1]))['systeme'] == sys.argv[2], 'Sources actives non reproductibles'
PY

for phase in acme https; do
  case "$phase" in
    acme) config="$installe/hosts/hostinger/nextcloud-acme.nix";;
    https) config="$installe/hosts/hostinger/logique.nix";;
  esac
  evaluer "$config" > "$preparation/$phase.json"
  python3 - "$preparation/reference.json" "$preparation/$phase.json" <<'PY'
import json,sys
reference,candidat = (json.load(open(p)) for p in sys.argv[1:])
assert reference['invariant'] == candidat['invariant'], 'Invariant existant modifié'
assert reference['systeme'] != candidat['systeme'], 'Candidat identique à la production'
PY
  nix-build '<nixpkgs/nixos>' -A system -I "nixpkgs=$nixpkgs" \
    -I "nixos-config=$config" --out-link "$racines/$phase" > "$preparation/$phase.systeme"
  python3 - "$preparation/$phase.json" "$preparation/$phase.systeme" <<'PY'
import json,sys
assert json.load(open(sys.argv[1]))['systeme'] == open(sys.argv[2]).read().strip(), 'Construction différente de l’évaluation'
PY
done

# Seule la phase ACME ne dépend pas encore d'un certificat absent.
python3 - "$preparation/acme.json" <<'PY'
import json,shlex,subprocess,sys
command=shlex.split(json.load(open(sys.argv[1]))['nginx'])
subprocess.run([*command,'-t'],check=True)
PY
touch "$preparation/termine"
printf 'CANDIDAT_CONSTRUIT=%s\nACME_SYSTEME=%s\nHTTPS_SYSTEME=%s\n' \
  "$revision" "$(cat "$preparation/acme.systeme")" "$(cat "$preparation/https.systeme")"
printf 'ACTIF_INCHANGE=%s\n' "$(readlink -f /run/current-system)"
