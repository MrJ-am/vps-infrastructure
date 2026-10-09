#!/bin/sh
# Répertoire runtime privé et paquet optimisé exact ; aucun import de realm réel.
set -eu
umask 077
test "$#" = 3
paquet_mrjam=$1
runtime_mrjam=$2
socket_mrjam=$3
mkdir -p "$runtime_mrjam/conf"
ln -s "$paquet_mrjam/lib" "$runtime_mrjam/lib"
ln -s "$paquet_mrjam/providers" "$runtime_mrjam/providers"
ln -s "$paquet_mrjam/themes" "$runtime_mrjam/themes"
cp "$paquet_mrjam/conf/keycloak.conf" "$runtime_mrjam/conf/keycloak.conf"
chmod 0600 "$runtime_mrjam/conf/keycloak.conf"
export KC_HOME_DIR="$runtime_mrjam" KC_CONF_DIR="$runtime_mrjam/conf"
export KC_DB_URL="jdbc:postgresql://localhost/identite_unix?socketFactory=org.newsclub.net.unix.AFUNIXSocketFactory\$FactoryArg&socketFactoryArg=$socket_mrjam/.s.PGSQL.5432&sslMode=disable"
export KC_DB_USERNAME=keycloak
export KC_HTTP_HOST=127.0.0.1 KC_HTTP_PORT=8085 KC_HOSTNAME=http://127.0.0.1:8085
export KC_BOOTSTRAP_ADMIN_USERNAME=qualification
KC_BOOTSTRAP_ADMIN_PASSWORD=$(cat "$CREDENTIALS_DIRECTORY/bootstrap")
export KC_BOOTSTRAP_ADMIN_PASSWORD
export JAVA_OPTS_APPEND='-Xms256m -Xmx1200m'
exec "$paquet_mrjam/bin/kc.sh" start --optimized
