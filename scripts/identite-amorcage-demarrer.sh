#!/bin/sh
# Paquet optimisé qualifié ; credentials privés et socket du cluster séparé.
set -eu
umask 077
test "$#" = 4
paquet_mrjam=$1
runtime_mrjam=$2
socket_mrjam=$3
themes_mrjam=$4
test "$runtime_mrjam" = /run/mrjam-amorcage-identite
test "$socket_mrjam" = /run/mrjam-amorcage-postgresql
test "$(id -u)" -ne 0
mkdir -p "$runtime_mrjam/conf" "$runtime_mrjam/data/import"
ln -snf "$paquet_mrjam/lib" "$runtime_mrjam/lib"
ln -snf "$paquet_mrjam/providers" "$runtime_mrjam/providers"
ln -snf "$themes_mrjam" "$runtime_mrjam/themes"
ln -snf "$CREDENTIALS_DIRECTORY/realm-import" "$runtime_mrjam/data/import/mrjam-realm.json"
cp "$paquet_mrjam/conf/keycloak.conf" "$runtime_mrjam/conf/keycloak.conf"
chmod 0600 "$runtime_mrjam/conf/keycloak.conf"
export KC_HOME_DIR="$runtime_mrjam" KC_CONF_DIR="$runtime_mrjam/conf"
export KC_DB_URL="jdbc:postgresql://localhost/mrjam_identite?socketFactory=org.newsclub.net.unix.AFUNIXSocketFactory\$FactoryArg&socketFactoryArg=$socket_mrjam/.s.PGSQL.5432&sslMode=disable"
export KC_DB_USERNAME=keycloak
export KC_HTTP_HOST=127.0.0.1 KC_HTTP_PORT=8085 KC_HTTP_ENABLED=true
export KC_HOSTNAME=https://log.mrj.am KC_HOSTNAME_STRICT=true KC_PROXY_HEADERS=xforwarded
export KC_LOG_LEVEL=warn KC_METRICS_ENABLED=false
IFS= read -r KC_BOOTSTRAP_ADMIN_PASSWORD < "$CREDENTIALS_DIRECTORY/amorcage-admin"
test -n "$KC_BOOTSTRAP_ADMIN_PASSWORD"
export KC_BOOTSTRAP_ADMIN_USERNAME=amorcage-local KC_BOOTSTRAP_ADMIN_PASSWORD
export JAVA_OPTS_APPEND='-Xms256m -Xmx1200m'
exec "$paquet_mrjam/bin/kc.sh" start --optimized --import-realm
