#!/bin/sh
# Nouvel audit, sans rejouer les garde-fous de la migration de septembre 18.
# Lecture seule ; aucun secret, contenu applicatif privé ou changement système.
set -eu
actif=$(readlink -f /run/current-system)
demarrage=$(readlink -f /nix/var/nix/profiles/system)
test "$actif" = "$demarrage"
systemctl is-active sshd nginx postgresql matheval vision mrj-auth >/dev/null
systemctl is-active postgresqlBackup-matheval.timer postgresqlBackup-vision.timer >/dev/null
jq -n --arg date "$(date -u +%FT%TZ)" \
  --arg actif "$actif" --arg demarrage "$demarrage" \
  --arg nixpkgs "$(nix-instantiate --find-file nixpkgs)" \
  --arg entree "$(cat /etc/nixos/configuration.nix)" \
  --arg empreinte "$(sha256sum /etc/nixos/configuration.nix | cut -d ' ' -f 1)" \
  --arg matheval "$(cat /srv/matheval/current/RELEASE)" \
  --arg vision "$(cat /srv/vision/current/RELEASE)" \
  --arg cheminMatheval "$(readlink -f /srv/matheval/current)" \
  --arg cheminVision "$(readlink -f /srv/vision/current)" \
  --argjson certificat "$(if test -f /var/lib/acme/logique.echos.systems/fullchain.pem; then echo true; else echo false; fi)" \
  --argjson publication "$(if test -e /srv/logique/current || test -L /srv/logique/current || test -e /srv/apprendre-a-demontrer/current || test -L /srv/apprendre-a-demontrer/current; then echo true; else echo false; fi)" \
  '{date:$date,actif:$actif,demarrage:$demarrage,nixpkgs:$nixpkgs,entree:$entree,empreinteEntree:$empreinte,matheval:$matheval,vision:$vision,cheminMatheval:$cheminMatheval,cheminVision:$cheminVision,certificatLogiquePresent:$certificat,publicationLogiquePresente:$publication}'
