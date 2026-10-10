# Corps incorporé dans un opérateur root privé, avec ses chemins épinglés.
# Aucun paramètre, réseau, Python, secret ou ancien dump Vision n'est requis.
set -euo pipefail
umask 077
unset PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD PGOPTIONS PGSERVICE PGSERVICEFILE PGPASSFILE
export PATH="$outils:/run/wrappers/bin"
exec 9>"$d/finalisation.lock"
"$outils/flock" 9
test ! -e "$d/enregistre" || exit 0

prive() {
  test ! -L "$1" && test -f "$1"
  test "$("$outils/stat" -c '%u:%a:%h' "$1")" = '0:600:1'
}
marquer() {
  local temporaire
  temporaire=$("$outils/mktemp" "$d/marque.XXXXXXXX")
  printf '1\n' > "$temporaire"
  "$outils/sync" -f "$temporaire"
  "$outils/mv" -Tf "$temporaire" "$d/$1"
  "$outils/sync" -f "$d"
}
nettoyer_copie() {
  "$outils/rm" -f "$d/identite-courante-retour.dump" "$d/identite-retour-avant" "$d/identite-retour-apres"
  "$outils/sync" -f "$d"
}
if test -e "$d/retour-termine"; then nettoyer_copie; exit 0; fi
exec 3>&1
test ! -L "$d/retour-diagnostic-prive.log"
if test ! -e "$d/retour-diagnostic-prive.log"; then : > "$d/retour-diagnostic-prive.log"; fi
prive "$d/retour-diagnostic-prive.log"
exec >>"$d/retour-diagnostic-prive.log" 2>&1

gater() {
  local repertoire="$unites/$1.d" fichier
  test ! -L "$repertoire"
  "$outils/mkdir" -p "$repertoire"
  test "$("$outils/stat" -c '%u' "$repertoire")" = 0
  fichier="$repertoire/$gate"
  test ! -L "$fichier"
  printf '[Unit]\nConditionPathExists=!/\n' > "$fichier"
  "$outils/sync" -f "$fichier"
}
degater() { "$outils/rm" -f "$unites/$1.d/$gate"; }
arreter() {
  local charge actif
  charge=$("$outils/systemctl" show "$1" --property=LoadState --value)
  if test "$charge" = not-found; then return; fi
  "$outils/systemctl" stop "$1"
  actif=$("$outils/systemctl" show "$1" --property=ActiveState --value)
  case "$actif" in inactive|failed) ;; *) return 1 ;; esac
}
secours() {
  local code=$?
  trap - EXIT HUP INT TERM
  if test "$code" != 0; then
    # Les autres sites restent disponibles même si l'accès ancien est refusé.
    # Vision/auth/les deux Keycloak conservent leur condition fermée.
    for unite in vision.service mrj-auth.service keycloak.service mrjam-amorcage-identite.service; do
      gater "$unite" || true
    done
    "$outils/systemctl" daemon-reload || true
    for unite in vision.service mrj-auth.service keycloak.service mrjam-amorcage-identite.service; do
      arreter "$unite" || true
    done
    degater nginx.service
    "$outils/systemctl" daemon-reload || true
    "$outils/systemctl" start nginx.service || true
    printf '{"retour_effectif":false,"acces_vision_ferme":true}\n' >&3
  fi
  exit "$code"
}
trap secours EXIT
trap 'exit 1' HUP INT TERM
marquer retour-commence
if test -n "$worker"; then arreter "$worker"; fi
exec 8>"$verrou_deploiement"
"$outils/flock" 8
for unite in nginx.service vision.service mrj-auth.service keycloak.service mrjam-amorcage-identite.service; do
  gater "$unite"
done
"$outils/systemctl" daemon-reload
for unite in nginx.service vision.service mrj-auth.service keycloak.service mrjam-amorcage-identite.service \
  vision-purge.timer mrjam-sauvegarde.timer mrjam-amorcage-sauvegarde.timer \
  vision-cycle.service mrjam-admission.service mrjam-fermeture.service mrjam-courriel.service \
  vision-gestion.service vision-purge.service mrjam-sauvegarde.service; do
  arreter "$unite"
done

if test -e "$d/identite-migree" && test ! -e "$d/identite-retablie"; then
  prive "$d/identite-empreintes.sql"
  if test ! -e "$d/identite-retour-copie"; then
    # La base initiale reste intacte jusqu'à la première activation Keycloak.
    # Après cette marque, seule l'identité COURANTE peut être rendue à l'ancien cluster.
    "$runuser" -u postgres -- "$postgres/bin/psql" -XAtq -v ON_ERROR_STOP=1 \
      -h "$socket_nouveau" -U postgres -d mrjam_identite -f - \
      < "$d/identite-empreintes.sql" > "$d/identite-retour-avant"
    "$runuser" -u postgres -- "$postgres/bin/pg_dump" -Fc -h "$socket_nouveau" -U postgres mrjam_identite \
      > "$d/identite-courante-retour.dump.tmp"
    "$postgres/bin/pg_restore" --list "$d/identite-courante-retour.dump.tmp" >/dev/null
    "$outils/sync" -f "$d/identite-courante-retour.dump.tmp"
    "$outils/sync" -f "$d/identite-retour-avant"
    "$outils/mv" -Tf "$d/identite-courante-retour.dump.tmp" "$d/identite-courante-retour.dump"
    "$outils/sync" -f "$d"
    marquer identite-retour-copie
  fi
  prive "$d/identite-courante-retour.dump"
  prive "$d/identite-retour-avant"
fi

"$outils/cp" -a --no-dereference "$d/configuration-avant.nix" "$configuration.vision-retour"
"$outils/mv" -Tf "$configuration.vision-retour" "$configuration"
"$outils/sync" -f "$("$outils/dirname" "$configuration")"
"$outils/nix-env" --profile "$profil" --set "$ancien"
"$ancien/bin/switch-to-configuration" boot
# Les conditions natives empêchent les clients de démarrer pendant le transfert,
# sans les erreurs de démarrage que provoqueraient des masques systemd.
"$ancien/bin/switch-to-configuration" test
arreter mrjam-amorcage-identite.service
if test -e "$d/identite-migree" && test ! -e "$d/identite-retablie"; then
  "$outils/systemctl" start mrjam-amorcage-postgresql.service
  "$runuser" -u postgres -- "$postgres/bin/pg_restore" --single-transaction --exit-on-error \
    --clean --if-exists --no-owner --no-privileges --role=keycloak \
    -h "$socket_ancien" -U postgres -d mrjam_identite < "$d/identite-courante-retour.dump"
  "$runuser" -u postgres -- "$postgres/bin/psql" -XAtq -v ON_ERROR_STOP=1 \
    -h "$socket_ancien" -U postgres -d mrjam_identite -f - \
    < "$d/identite-empreintes.sql" > "$d/identite-retour-apres"
  "$outils/cmp" -s "$d/identite-retour-avant" "$d/identite-retour-apres"
  marquer identite-retablie
fi
if test -e "$d/sql-engage"; then
  prive "$d/retour-acl.sql"
  "$runuser" -u postgres -- "$postgres/bin/psql" -Xq -v ON_ERROR_STOP=1 \
    -h "$socket_nouveau" -U postgres -d vision -f - < "$d/retour-acl.sql"
fi
cible=$("$outils/readlink" -f "$d/backend-avant")
test -d "$cible" && test -f "$cible/vision"
"$outils/ln" -sfn "$cible" "$backend.vision-retour"
"$outils/mv" -Tf "$backend.vision-retour" "$backend"
"$outils/sync" -f "$("$outils/dirname" "$backend")"
test "$("$outils/readlink" -f "$courant")" = "$ancien"
test "$("$outils/readlink" -f "$profil")" = "$ancien"
"$outils/systemctl" is-active sshd nginx postgresql matheval >/dev/null || \
  "$outils/systemctl" is-active sshd postgresql matheval >/dev/null
for unite in vision.service mrj-auth.service mrjam-amorcage-identite.service nginx.service; do degater "$unite"; done
"$outils/systemctl" daemon-reload
"$outils/systemctl" start mrjam-amorcage-identite.service vision.service mrj-auth.service nginx.service
"$outils/systemctl" is-active sshd nginx postgresql vision matheval mrj-auth mrjam-amorcage-identite >/dev/null
marquer retour-termine
trap - EXIT HUP INT TERM
nettoyer_copie
printf '{"retour_effectif":true,"identite_courante_conservee":true,"ancien_dump_vision_restaure":false}\n' >&3
