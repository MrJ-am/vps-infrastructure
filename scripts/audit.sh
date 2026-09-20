#!/bin/sh
# À exécuter sur le VPS. Lecture seule ; ne révèle pas les fichiers de secrets.
set -eu
printf '%s\n' 'Version NixOS et générations'
nixos-version
readlink -f /run/current-system
readlink -f /nix/var/nix/profiles/system
printf '%s\n' 'Source Nixpkgs installée, sans mise à jour'
nix-instantiate --find-file nixpkgs
printf '%s\n' 'Services existants'
systemctl is-active sshd nginx postgresql matheval vision
printf '%s\n' 'Ports en écoute'
ss -lntp
printf '%s\n' 'Configuration Nginx active'
nginx_command=$(systemctl show nginx --property=ExecStart --value)
printf '%s\n' "$nginx_command"
nginx_bin=$(printf '%s\n' "$nginx_command" | sed -n 's/.*path=\([^ ;]*\) ;.*/\1/p')
nginx_config=$(printf '%s\n' "$nginx_command" | sed -n 's/.*argv\[\]=[^;]* -c \([^ ;]*\).*/\1/p')
case "$nginx_bin:$nginx_config" in
    /nix/store/*/bin/nginx:/nix/store/*) ;;
    *) echo 'Commande Nginx non reconnue ; ne pas deviner sa configuration.' >&2; exit 1 ;;
esac
"$nginx_bin" -t -c "$nginx_config"
printf '%s\n' 'Publication Matheval'
readlink -f /srv/matheval/current
cat /srv/matheval/current/RELEASE
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:3000/matheval/api/health
printf '\n%s\n' 'Publication Vision'
readlink -f /srv/vision/current
cat /srv/vision/current/RELEASE
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:3001/healthz
printf '\n%s\n' 'Avertissements Vision récents, sans corps de requête'
journalctl --unit vision.service --unit vision-migrate.service \
  --since '-30 min' --priority warning --no-pager --output=short-iso --lines=200
printf '%s\n' 'Sonde locale en lecture seule du candidat Vision 1.1.0'
candidate=/srv/vision/releases/71e1dbf4add390b9039fa0273f76bddbe7397fda
test "$(cat "$candidate/RELEASE")" = 71e1dbf4add390b9039fa0273f76bddbe7397fda
psql_path=$(command -v psql)
case "$psql_path" in
    /nix/store/*/bin/psql|/run/current-system/sw/bin/psql) ;;
    *) echo 'Client PostgreSQL non reconnu.' >&2; exit 1 ;;
esac
runuser -u vision -- env \
  PGHOST=/run/postgresql PGDATABASE=vision PGUSER=vision \
  "$psql_path" --no-psqlrc --quiet --tuples-only --no-align \
  --command="SELECT count(*) FROM vision_memory_sheets" >/dev/null
diagnostic=$(mktemp -d)
candidate_pid=
cleanup_candidate() {
    if test -n "$candidate_pid"; then
        kill "$candidate_pid" 2>/dev/null || true
        wait "$candidate_pid" 2>/dev/null || true
    fi
    rm -rf -- "$diagnostic"
}
trap cleanup_candidate EXIT INT TERM
(
    cd -- "$candidate"
    exec runuser -u vision -- env \
      PATH="$(dirname -- "$psql_path"):/run/current-system/sw/bin" \
      IP=127.0.0.1 PORT=39003 VISION_VERSION=1.1.0 \
      VISION_DOCUMENT_ROOT="$candidate/docs" \
      PGHOST=/run/postgresql PGDATABASE=vision PGUSER=vision \
      PGOPTIONS='-c statement_timeout=5000' \
      "$candidate/vision"
) >"$diagnostic/server.log" 2>&1 &
candidate_pid=$!
for _attempt in $(seq 1 50); do
    if curl --fail --silent --max-time 1 \
      http://127.0.0.1:39003/healthz >/dev/null; then
        break
    fi
    sleep 0.1
done
status=$(curl --silent --show-error --max-time 10 \
  --output "$diagnostic/response.json" --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --header 'X-Vision-Authenticated: 1' \
  --data '{"jsonrpc":"2.0","id":"audit","method":"tools/call","params":{"name":"search_memory_sheets","arguments":{"query":"__vision_activation_probe_no_match__","limit":1}}}' \
  http://127.0.0.1:39003/mcp)
printf 'Statut MCP local : %s\n' "$status"
if test "$status" = 200 && grep -q '"isError":false' "$diagnostic/response.json"; then
    printf '%s\n' 'Lecture PostgreSQL MCP locale validée.'
else
    printf '%s\n' 'Lecture PostgreSQL MCP locale en échec ; journal du candidat :' >&2
    cat "$diagnostic/server.log" >&2
    exit 1
fi
cleanup_candidate
trap - EXIT INT TERM
printf '%s\n' 'Planification des certificats et sauvegardes'
systemctl list-timers --all --no-pager 'acme*' 'postgresqlBackup*'
printf '%s\n' 'Ressources et point d’entrée NixOS'
df -h / /nix/store /var/lib/postgresql
free -m
stat /etc/nixos/configuration.nix
printf '%s\n' 'Sources NixOS à comparer avec le candidat'
rg --files /etc/nixos -g '*.nix'
printf '%s\n' 'Empreintes des sources NixOS, sans afficher leur contenu'
while IFS= read -r source; do
    sha256sum -- "$source"
done <<EOF
$(rg --files /etc/nixos -g '*.nix')
EOF
