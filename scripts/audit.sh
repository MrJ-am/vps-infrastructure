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
