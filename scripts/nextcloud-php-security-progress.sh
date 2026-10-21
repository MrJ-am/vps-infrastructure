#!/usr/bin/env bash
# Observation exclusivement en lecture seule, parallèle à l'opération centrale.
set -euo pipefail
printf 'DATE_UTC=%s\nACTIF=%s\nDEMARRAGE=%s\n' "$(date -u +%FT%TZ)" \
  "$(readlink -f /run/current-system)" "$(readlink -f /nix/var/nix/profiles/system)"
printf 'BLOCKED=%s\n' "$(test -f /var/lib/nextcloud-php-security/blocked && echo true || echo false)"
printf 'FPM_PID=%s\n' "$(systemctl show phpfpm-nextcloud -p MainPID --value)"
systemctl show phpfpm-nextcloud -p ExecStart -p ActiveState -p ConditionResult
systemctl --failed --no-legend --plain --no-pager
for state in /root/mrjam-corrections/nextcloud-php-security/*/state.json; do
  test -f "$state" || continue
  jq '{revision, baseline, contained, patched, complete, backupPresent:has("backup")}' "$state"
  dir=${state%/state.json}
  for log in "$dir"/*-build-private.log; do
    test -f "$log" || continue
    stat --printf='BUILD_LOG=%n SIZE=%s MODIFIED=%y\n' "$log"
  done
done
ps -C nix-build,gcc,cc1,cc1plus,make,ld -o pid=,comm= || true
df -Pk / | tail -1
free -m | head -2
