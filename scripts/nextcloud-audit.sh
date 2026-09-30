#!/bin/sh
# Lecture seule. Ne jamais afficher de secrets, journaux HTTP ou données métier.
set -eu
export LC_ALL=C

printf 'DATE_UTC=%s\n' "$(date -u +%FT%TZ)"
printf 'NIXOS=%s\n' "$(nixos-version)"
printf 'ACTIF=%s\n' "$(readlink -f /run/current-system)"
printf 'DEMARRAGE=%s\n' "$(readlink -f /nix/var/nix/profiles/system)"
printf 'NIXPKGS=%s\n' "$(nix-instantiate --find-file nixpkgs)"
printf 'ENTREE_SHA256=%s\n' "$(sha256sum /etc/nixos/configuration.nix | cut -d ' ' -f 1)"
printf 'ENTREE_CIBLE=%s\n' "$(readlink -f /etc/nixos/configuration.nix)"
printf 'SOURCES_NIXOS\n'
find /etc/nixos -type f -name '*.nix' -print0 | sort -z | xargs -0 -r sha256sum
printf 'RESSOURCES\n'
df -hP / /nix/store /var/lib/postgresql /var/lib/nextcloud 2>/dev/null || df -hP / /nix/store /var/lib/postgresql
df -iP / /nix/store /var/lib/postgresql
free -m
printf 'SERVICES\n'
for unit in sshd nginx postgresql matheval vision mrj-auth redis-nextcloud nextcloud-setup nextcloud-cron; do
  printf '%s=%s\n' "$unit" "$(systemctl is-active "$unit" 2>/dev/null || :)"
done
printf 'PUBLICATIONS\n'
for app in matheval vision logique apprendre-a-demontrer; do
  if test -L "/srv/$app/current"; then
    printf '%s=%s\n' "$app" "$(readlink -f "/srv/$app/current")"
    for marker in RELEASE revision-application.txt; do
      if test -f "/srv/$app/current/$marker"; then
        revision=$(head -c 100 "/srv/$app/current/$marker")
        case "$revision" in
          *[!a-fA-F0-9]*|'') printf '%s_%s=non-hexadecimal\n' "$app" "$marker" ;;
          *) printf '%s_%s=%s\n' "$app" "$marker" "$revision" ;;
        esac
      fi
    done
  fi
done
printf 'BASES_APPLICATIVES\n'
runuser -u postgres -- psql -Atqc "SELECT datname FROM pg_database WHERE datname IN ('matheval','vision','nextcloud') ORDER BY datname"
printf 'ROLES_APPLICATIFS\n'
runuser -u postgres -- psql -Atqc "SELECT rolname FROM pg_roles WHERE rolname IN ('matheval','vision','nextcloud') ORDER BY rolname"
printf 'SAUVEGARDES_TIMER\n'
systemctl list-timers --all --no-pager 'postgresqlBackup*' 'acme*' | tail -n +2 | head -n 25
printf 'SAUVEGARDES_REPERTOIRES\n'
for dir in /var/backup/postgresql /var/lib/nextcloud /var/lib/acme/cloud.mrj.am; do
  if test -d "$dir"; then stat -c '%n owner=%U:%G mode=%a' "$dir"; else printf '%s absent\n' "$dir"; fi
done
printf 'PORTS_TCP\n'
ss -lntH | awk '{print $4}' | sort -u
printf 'NGINX_TEST\n'
nginx_exec=$(systemctl show nginx --property=ExecStart --value)
nginx_bin=$(printf '%s\n' "$nginx_exec" | sed -n 's/.*path=\([^ ;]*\) ;.*/\1/p')
nginx_conf=$(printf '%s\n' "$nginx_exec" | sed -n 's/.*argv\[\]=[^;]* -c \([^ ;]*\).*/\1/p')
case "$nginx_bin:$nginx_conf" in
  /nix/store/*/bin/nginx:/nix/store/*) "$nginx_bin" -t -c "$nginx_conf" 2>&1 | tail -n 2 ;;
  *) printf 'commande nginx inattendue\n'; exit 1 ;;
esac
printf 'REPRISE_NEXTCLOUD\n'
reprise=/root/nextcloud-preparations/43a8cd0f551b74b75583bb8aaf849d2a90560618
for marqueur in termine retour-arme retour-effectue enregistre; do
  if test -f "$reprise/$marqueur"; then printf '%s=oui\n' "$marqueur"; else printf '%s=non\n' "$marqueur"; fi
done
for chemin in /var/lib/nextcloud/config/config.php /var/lib/acme/cloud.mrj.am/fullchain.pem; do
  if test -s "$chemin"; then printf '%s=present\n' "$chemin"; else printf '%s=absent\n' "$chemin"; fi
done
printf 'RETOUR_TIMER=%s\n' "$(systemctl is-active nextcloud-retour-43a8cd0f551b.timer || :)"

printf 'NEXTCLOUD_ET_TALK\n'
runuser -u nextcloud -- nextcloud-occ status --output=json
runuser -u nextcloud -- nextcloud-occ app:list --output=json | jq '{spreed_enabled: .enabled.spreed, spreed_disabled: .disabled.spreed}'
nix-instantiate --eval --strict --json -E 'let p = import <nixpkgs> {}; a = p.nextcloud34Packages.apps.spreed; in { version = a.version; name = a.name; }'
printf 'ENTRY_IMPORT\n'
cat /etc/nixos/configuration.nix
