# Nextcloud sur cloud.mrj.am

## Version choisie

L'infrastructure conserve NixOS 26.05 et son Nixpkgs installé. Nextcloud est
explicitement épinglé en **34.0.4**. Le Nixpkgs actif contient 34.0.3 ; la
révision stable 26.05 déjà utilisée par la CI du dépôt contient 34.0.4 avec le
même module NixOS. Seule la source du paquet Nextcloud est donc rétroportée,
avec l'empreinte publiée par Nixpkgs, sans mise à jour générale du système.

Nextcloud 35 n'est pas introduit tant qu'il exige de sortir de ce couple
NixOS/Nixpkgs stable.

## Architecture

- Nginx commun, certificat ACME pour `cloud.mrj.am`.
- PHP-FPM et tâches cron gérés par le module NixOS Nextcloud.
- Redis local dédié au cache et au verrouillage.
- PostgreSQL 17 partagé par socket Unix, base/rôle/compte `nextcloud`.
- sauvegarde logique PostgreSQL quotidienne par l'infrastructure.
- données Nextcloud persistantes sous `/var/lib/nextcloud`.

La sauvegarde PostgreSQL ne sauvegarde pas les fichiers utilisateurs. Une
sauvegarde hors VPS du répertoire de données doit être mise en place avant
d'utiliser cette instance comme stockage unique de documents importants.

## DNS

Créer un enregistrement **A** :

- nom/hôte : `cloud`
- valeur : `187.77.95.158`
- TTL : valeur automatique ou valeur par défaut du fournisseur.

Ne pas créer d'AAAA avant vérification explicite de l'accessibilité IPv6.

## Première activation

La première génération utilise `hosts/hostinger/nextcloud-acme.nix` pour
laisser HTTP disponible au challenge ACME. Une fois le certificat émis, la
configuration finale `hosts/hostinger/configuration.nix` impose HTTPS.

Aucun mot de passe administrateur n'est stocké dans Git ou dans le Nix store.
Après activation finale, créer le premier administrateur depuis un terminal
root interactif avec :

```sh
nextcloud-occ user:add --admin <identifiant>
```

La commande demande le mot de passe interactivement.
