#!/bin/sh
# Le cluster entier est éphémère, synthétique, peer et sans écoute TCP.
set -eu
umask 077
test "$#" = 3
pg_mrjam=$1
runtime_mrjam=$2
utilisateur_mrjam=$3
mkdir "$runtime_mrjam/socket"
chmod 0755 "$runtime_mrjam/socket"
"$pg_mrjam/initdb" -D "$runtime_mrjam/data" --auth-local=peer --auth-host=reject --no-locale --encoding=UTF8
printf 'local all postgres peer\nlocal identite_unix keycloak peer map=qualification\nlocal all all reject\n' > "$runtime_mrjam/data/pg_hba.conf"
printf 'qualification %s keycloak\n' "$utilisateur_mrjam" > "$runtime_mrjam/data/pg_ident.conf"
exec "$pg_mrjam/postgres" -D "$runtime_mrjam/data" -c listen_addresses= \
    -c unix_socket_directories="$runtime_mrjam/socket" -c unix_socket_permissions=0777
