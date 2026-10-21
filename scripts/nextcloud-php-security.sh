#!/usr/bin/env bash
# Opérations fermées, accès SSH central existant, aucune donnée privée imprimée.
set -euo pipefail
export LC_ALL=C
operation=${1:?operation}
revision=${2:?revision}
[[ $revision =~ ^[a-f0-9]{40}$ ]]
case "$operation" in audit|isolate) ;; *) exit 2;; esac
state=/var/lib/nextcloud-php-security
install -d -m 700 "$state"
exec 9>"$state/operation.lock"
flock -n 9

printf 'DATE_UTC=%s\nACTIF=%s\nDEMARRAGE=%s\n' "$(date -u +%FT%TZ)" \
  "$(readlink -f /run/current-system)" "$(readlink -f /nix/var/nix/profiles/system)"
printf 'NIXPKGS=%s\n' "$(nix-instantiate --find-file nixpkgs)"
printf 'ENTRY_SHA256=%s\n' "$(sha256sum /etc/nixos/configuration.nix | cut -d ' ' -f 1)"
systemctl list-unit-files --no-legend 'phpfpm*' 'php*' || true
ps -C php,php-fpm,php-cgi -o pid=,comm= || true
pid=$(systemctl show phpfpm-nextcloud.service -p MainPID --value)
version=unknown
if [[ $pid =~ ^[1-9][0-9]*$ ]] && test -e "/proc/$pid/exe"; then
  binary=$(readlink -f "/proc/$pid/exe")
  case "$binary" in /nix/store/*/bin/php-fpm|/nix/store/*/bin/.php-fpm-wrapped) ;; *) exit 3;; esac
  printf 'FPM_BINARY=%s\n' "$binary"
  version=$("$binary" -v | sed -n '1s/^PHP \([0-9][0-9.]*\).*/\1/p')
  printf 'PHP_VERSION=%s\n' "$version"
fi
patched=false
case "$version" in
  8.2.*) minimum=8.2.35;; 8.3.*) minimum=8.3.36;;
  8.4.*) minimum=8.4.27;; 8.5.*) minimum=8.5.12;; *) minimum=unknown;;
esac
if test "$minimum" != unknown && test "$(printf '%s\n' "$minimum" "$version" | sort -V | head -1)" = "$minimum"; then patched=true; fi
printf 'CVE_2026_109618_109619_PATCHED=%s\n' "$patched"
for unit in nginx postgresql kanidm mrjam-metier forgejo sshd; do
  printf '%s %s\n' "$unit" "$(systemctl show "$unit" -p MainPID --value)"
done > "$state/protected.before"

if test "$operation" = isolate && test "$patched" != true; then
  printf '%s\n' "$revision" > "$state/blocked"
  chmod 600 "$state/blocked"
  for unit in phpfpm-nextcloud nextcloud-cron; do
    install -d -m 755 "/run/systemd/system/$unit.service.d"
    dropin="/run/systemd/system/$unit.service.d/99-php-security.conf"
    printf '[Unit]\nConditionPathExists=!%s/blocked\n' "$state" > "$dropin"
    chmod 644 "$dropin"
  done
  systemctl daemon-reload
  systemctl stop nextcloud-cron.timer nextcloud-cron.service phpfpm-nextcloud.service
  # Une tentative de démarrage doit être refusée par la condition.
  systemctl start phpfpm-nextcloud.service
  test "$(systemctl show phpfpm-nextcloud.service -p MainPID --value)" = 0
  test "$(systemctl show phpfpm-nextcloud.service -p ConditionResult --value)" = no
  test "$(systemctl is-active phpfpm-nextcloud.service || :)" = inactive
  printf 'NEXTCLOUD_PHP_STOPPED=true\nRESTART_GUARD_VERIFIED=true\nRUNTIME_GUARD_REQUIRES_PERSISTENT_CORRECTION=true\n'
fi
for unit in nginx postgresql kanidm mrjam-metier forgejo sshd; do
  printf '%s %s\n' "$unit" "$(systemctl show "$unit" -p MainPID --value)"
done > "$state/protected.after"
cmp "$state/protected.before" "$state/protected.after"
printf 'PROTECTED_PIDS_UNCHANGED=true\n'
for path in /status.php /login /remote.php/dav/; do
  code=$(curl --silent --show-error --output /dev/null --max-time 20 --write-out '%{http_code}' \
    --resolve cloud.mrj.am:443:127.0.0.1 "https://cloud.mrj.am$path")
  printf 'HTTPS_%s=%s\n' "$path" "$code"
  if test "$operation" = isolate && test "$patched" != true; then
    case "$code" in 502|503) ;; *) exit 4;; esac
  fi
done
