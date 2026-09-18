#!/bin/sh
# Lecture seule de la migration enregistrée ; aucun secret ni donnée applicative.
set -eu
commit=fa059d61acfc8cf5c5bd7f3f9c83600787f2c6eb
state=/root/vps-migrations/$commit
candidate=/nix/store/8cbhcffxr0xhybz2va6yz8rrxfgqgzy9-nixos-system-nixos-26.05.8639.c5c4a43b0e80
printf '%s\n' 'Migration enregistrée et génération attendue'
test -f "$state/committed"
for marker in rollback-started rolled-back worker-failed; do
    test ! -e "$state/$marker"
done
test "$(readlink -f /run/current-system)" = "$candidate"
test "$(readlink -f /nix/var/nix/profiles/system)" = "$candidate"
test "$(cat /etc/nixos/configuration.nix)" = "{ imports = [ /etc/nixos/vps-infrastructure/$commit/hosts/hostinger/configuration.nix ]; }"
cat "$state/committed.json"
printf '%s\n' 'Essai terminé et retour automatique désarmé'
for unit in vps-test-fa059d61acfc.service vps-rollback-fa059d61acfc.timer; do
    test "$(systemctl show "$unit" --property=ActiveState --value || true)" = inactive
    systemctl show "$unit" --property=Id,ActiveState,SubState || true
done
printf '%s\n' 'Racines protégeant les générations et source Nixpkgs'
for root in previous candidate nixpkgs python; do
    test -e "/nix/var/nix/gcroots/vps-migrations/$commit/$root"
    readlink -f "/nix/var/nix/gcroots/vps-migrations/$commit/$root"
done
printf '%s\n' 'Dernière sauvegarde locale et provisionnement SQL'
systemctl show postgresqlBackup-matheval.service postgresql-setup.service --property=Id,Result,ExecMainStatus
stat --format='%n : %s octets, modification %y' /var/backup/postgresql/matheval.sql.gz
