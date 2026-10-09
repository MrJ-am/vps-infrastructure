#!/bin/sh
# Cluster distinct : aucune variable PG héritée ni cible de production.
set -eu
umask 077
test "$#" = 4
action_mrjam=$1
bin_mrjam=$2
donnees_mrjam=$3
socket_mrjam=$4
test "$donnees_mrjam" = /var/lib/mrjam-amorcage-postgresql
test "$socket_mrjam" = /run/mrjam-amorcage-postgresql
test "$(id -un)" = postgres
case "$action_mrjam" in
  initialiser)
    if ! test -f "$donnees_mrjam/PG_VERSION"; then
      test -z "$(ls -A "$donnees_mrjam")"
      "$bin_mrjam/initdb" -D "$donnees_mrjam" --username=postgres \
        --auth-local=peer --auth-host=reject --encoding=UTF8 --no-locale >/dev/null
    fi
    test "$(cat "$donnees_mrjam/PG_VERSION")" = 17
    cat > "$donnees_mrjam/pg_hba.conf" <<'EOF'
local all postgres peer
local mrjam_identite keycloak peer
local all all reject
EOF
    chmod 0600 "$donnees_mrjam/pg_hba.conf"
    ;;
  configurer)
    # Les arguments fixes désignent le seul socket du cluster privé.
    for variable_mrjam in PGHOST PGHOSTADDR PGPORT PGDATABASE PGUSER PGPASSWORD \
      PGSERVICE PGSERVICEFILE PGPASSFILE PGOPTIONS; do
      unset "$variable_mrjam"
    done
    sql_mrjam() {
      "$bin_mrjam/psql" -XAtq --set=ON_ERROR_STOP=1 --host="$socket_mrjam" \
        --port=5432 --username=postgres --dbname=postgres --command="$1"
    }
    test "$(sql_mrjam "SELECT current_setting('server_version_num')::int BETWEEN 170000 AND 179999 AND current_setting('server_encoding')='UTF8' AND current_setting('listen_addresses')=''")" = t
    if test "$(sql_mrjam "SELECT count(*) FROM pg_roles WHERE rolname='keycloak'")" = 0; then
      sql_mrjam 'CREATE ROLE keycloak LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT'
    fi
    test "$(sql_mrjam "SELECT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls AND NOT rolinherit AND rolpassword IS NULL FROM pg_authid WHERE rolname='keycloak'")" = t
    test "$(sql_mrjam "SELECT count(*) FROM pg_auth_members WHERE roleid=(SELECT oid FROM pg_roles WHERE rolname='keycloak') OR member=(SELECT oid FROM pg_roles WHERE rolname='keycloak')")" = 0
    if test "$(sql_mrjam "SELECT count(*) FROM pg_database WHERE datname='mrjam_identite'")" = 0; then
      sql_mrjam 'CREATE DATABASE mrjam_identite OWNER keycloak'
    fi
    test "$(sql_mrjam "SELECT pg_get_userbyid(datdba)='keycloak' FROM pg_database WHERE datname='mrjam_identite'")" = t
    sql_mrjam 'REVOKE ALL ON DATABASE mrjam_identite FROM PUBLIC'
    test "$(sql_mrjam "SELECT count(*) FROM pg_database WHERE datname NOT IN ('postgres','template0','template1','mrjam_identite')")" = 0
    ;;
  *) exit 1 ;;
esac
