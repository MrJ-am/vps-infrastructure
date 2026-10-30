#!/run/current-system/sw/bin/bash
# Exécution personnelle uniquement ; cet emballage n'est pas une ACL.
# Sans argument : arrêt fermé avant toute connexion.
# --verify-only : vérification exclusivement locale des octets du paquet.
# Un argument : nom d'un compte EXISTANT NON PRIVILÉGIÉ confirmé par l'humain.
set +x
exec 2>/dev/null
set -u
umask 077
mrjam_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) || {
  printf '%s\n' '{"status":"failed","code":"LOCAL_EXECUTION_FAILED"}'
  exit 1
}
mrjam_python=/nix/store/jy00n3jp5xj8s40n1fbldmkcr5n7avxc-python3-3.13.15/bin/python3
if [[ ! -x "$mrjam_python" ]]; then
  printf '%s\n' '{"status":"failed","code":"LOCAL_PYTHON_311_REQUIRED"}'
  exit 1
fi
mrjam_result=$("$mrjam_python" -I -S "$mrjam_dir/remise_inventaire.py" "$@")
mrjam_status=$?
if [[ -z "$mrjam_result" ]]; then
  printf '%s\n' '{"status":"failed","code":"LOCAL_EXECUTION_FAILED"}'
  exit 1
fi
printf '%s\n' "$mrjam_result"
exit "$mrjam_status"
