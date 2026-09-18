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
systemctl is-active sshd nginx postgresql matheval
printf '%s\n' 'Ports en écoute'
ss -lntp
printf '%s\n' 'Configuration Nginx active'
nginx -t
printf '%s\n' 'Publication Matheval'
readlink -f /srv/matheval/current
cat /srv/matheval/current/RELEASE
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:3000/matheval/api/health
printf '\n%s\n' 'Planification des certificats et sauvegardes'
systemctl list-timers --all --no-pager 'acme*' 'postgresqlBackup*'
printf '%s\n' 'Sources NixOS à comparer avec le candidat'
rg --files /etc/nixos -g '*.nix'
printf '%s\n' 'Empreintes des sources NixOS, sans afficher leur contenu'
while IFS= read -r source; do
    sha256sum -- "$source"
done <<EOF
$(rg --files /etc/nixos -g '*.nix')
EOF
