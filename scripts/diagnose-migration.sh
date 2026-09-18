#!/bin/sh
# Lecture ciblée de la tentative interrompue ; aucun secret ni donnée applicative.
set -u
state=/root/vps-migrations/088d36c15f2fff9cecc4f25ff1b303fc29955042
printf '%s\n' 'Générations actuellement active et par défaut'
readlink -f /run/current-system /nix/var/nix/profiles/system
printf '%s\n' 'État des quatre services'
systemctl is-active sshd nginx postgresql matheval || true
printf '%s\n' 'Marqueurs de la tentative'
for name in started worker-failed rollback-started rolled-back tested committed; do
    if test -f "$state/$name"; then
        printf '%s\n' "$name"
        if test "$name" = worker-failed; then cat "$state/$name"; fi
    fi
done
printf '%s\n' 'Unités indépendantes et journaux ciblés'
systemctl show vps-test-088d36c15f2f.service vps-rollback-088d36c15f2f.service vps-rollback-088d36c15f2f.timer --property=Id,ActiveState,SubState,Result,ExecMainStatus,NextElapseUSecMonotonic
journalctl -u vps-test-088d36c15f2f.service -u vps-rollback-088d36c15f2f.service --no-pager -n 160
