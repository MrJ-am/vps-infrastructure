# Nextcloud et Talk sur cloud.mrj.am

## Talk installé et vérifié le 30 septembre 2026 à 22:17 UTC

Talk **24.0.4** (`spreed`) est installé et activé sur Nextcloud 34.0.4.
Accès : https://cloud.mrj.am/index.php/apps/spreed/

- Source : `cb55b9ce71acefe0686f23b5159150f2fe9d5f94`.
  CI exacte [36783983804](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36783983804) réussie.
- Audit en lecture seule [36783613726](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36783613726).
- Construction réelle sans activation [36784323831](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36784323831).
- Activation et constat indépendant [36784621012](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36784621012),
  commit opérateur `df52b749ddfdcb8d0d100aa50d78b39653f80b92`.
- Génération active et de démarrage :
  `/nix/store/mabshi6mmisnabl5qb5hwldnkxiz2s25-nixos-system-nixos-26.05.8639.c5c4a43b0e80`.
  Ancienne génération `c06sq9vp17l36j8xp2apyfav1nribpwc` conservée et protégée.
  Retour autonome armé pendant la bascule puis désarmé après enregistrement.

Le paquet provient de `nextcloud34Packages.apps.spreed` dans le Nixpkgs
installé `c5c4a43b0e80`, archive officielle
`https://github.com/nextcloud-releases/spreed/releases/download/v24.0.4/spreed-v24.0.4.tar.gz`,
empreinte `sha256-puSnXtbKLtKX2EgXGoqCPB8n98cf+vvUXoEAGrn3FkY=`.
L'installation est déclarative (`extraApps`, activation automatique) ;
l'App Store et ses mises à jour automatiques restent désactivés.
Aucune mise à jour générale NixOS ni modification de PostgreSQL, SSH,
pare-feu, domaines ou comptes administrateurs.

Contrôles exécutés : sauvegarde cohérente avant bascule réussie ; invariants
des autres services identiques ; Nginx candidat valide ; Talk activé en
version 24.0.4, tables Talk présentes, API des conversations anonyme refusée
avec HTTP 401, Nextcloud installé hors maintenance et sans migration en
attente. Comparaison privée des comptes et des métadonnées de fichiers
avant/après identique. Les publications Matheval, Vision et Logique ont gardé
leurs chemins exacts. Les 25 sondes HTTP/TLS ont réussi avant et après ;
une nouvelle connexion runner a confirmé les deux générations et Talk.

**Périmètre de vérification :** installation, activation et API protégée.
Aucun appel audio/vidéo entre deux navigateurs, partage d'écran ou parcours
invité complet n'a été testé. Aucun serveur TURN ni High Performance Backend
n'a été ajouté. La sauvegarde reste locale au VPS.

## Résultat et preuves

Nextcloud **34.0.4** fonctionne en HTTPS sur `cloud.mrj.am`. Le DNS A a été
contrôlé vers `187.77.95.158` chez Google et Cloudflare avant la bascule.
Le certificat ACME a été obtenu pendant la phase HTTP réservée au challenge ;
l'instance finale ne sert les connexions et les fichiers que sous HTTPS.

- Source exacte : `43a8cd0f551b74b75583bb8aaf849d2a90560618`, intégrée dans `main`
  par la [PR 24](https://github.com/MrJ-am/vps-infrastructure/pull/24).
- [Construction sur le VPS, exécution 36623222464](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36623222464) : deux générations construites avec le Nixpkgs installé, sans activer le candidat.
- [Bascule et constat final, exécution 36624255776](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36624255776) : ACME, Nginx, Nextcloud, administrateur, WebDAV, sauvegarde, restauration isolée et contrôle indépendant réussis.
- Génération active et profil de démarrage : `/nix/store/c06sq9vp17l36j8xp2apyfav1nribpwc-nixos-system-nixos-26.05.8639.c5c4a43b0e80`.
  Le retour autonome a été désarmé après enregistrement. L'ancienne génération
  reste protégée par une racine Nix.
- 25 sondes HTTP/TLS après finalisation, dont les anciennes publications
  Matheval et Vision. Les releases Matheval, Vision et Logique ont gardé leurs
  chemins exacts, et leurs services sont restés actifs.

Une première activation s'est arrêtée après installation sur un défaut de
validateur du registre dans `main`. Le retour a rétabli l'ancienne génération ;
[l'audit 36624180463](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36624180463)
a vérifié cet état et la présence des données Nextcloud. La seconde activation
a conservé ces données, régénéré le secret administrateur et réussi.

## Configuration effective

Nginx commun avec ACME, PHP-FPM limité à quatre processus et 512 Mio par
processus, Redis dédié, PostgreSQL 17 par socket Unix avec rôle/base
`nextcloud`, cron Nextcloud et upload maximal de 2 Gio. L'App Store et les
mises à jour automatiques des applications Nextcloud sont désactivés.
L'entrée NixOS finale importe `hosts/hostinger/logique.nix` et conserve les
modules des sites existants. Nextcloud utilise le paquet 34.0.4 avec empreinte
SHA-256 de l'archive `00f226e6364f96e0918ab06157158f66601b8cedc25af777f5ee5a3056f42b83` ;
le reste du système demeure sur le Nixpkgs déjà installé.

L'administrateur `admin` a été créé par `nextcloud-occ` avec un secret généré
sur le runner, transféré par SSH et absent des arguments et journaux en clair.
L'aller-retour WebDAV a créé, relu avec comparaison exacte, puis supprimé un
fichier de test dédié. Le propriétaire reçoit le secret séparément et doit le
changer après sa première connexion.

## Sauvegarde et restauration

Le timer `nextcloud-backup.timer` exécute à 03:30 UTC une sauvegarde locale
cohérente sous `/var/backup/nextcloud` : maintenance temporaire, dump PostgreSQL,
configuration, données, sommes SHA-256 et rétention de sept jours. La première
exécution manuelle a réussi. L'archive a été vérifiée puis restaurée dans une
base distincte `nextcloud_validation` (131 tables) et un répertoire temporaire,
sans toucher la base en service. Les timers PostgreSQL historiques restent
actifs.

**Limite restante :** cette sauvegarde est sur le même VPS. Aucune destination
chiffrée hors serveur n'est configurée, donc la perte complète du VPS emporterait
l'instance et sa sauvegarde locale. Prévoir cette destination avant d'y déposer
des fichiers irremplaçables.

## Reprise

Le workflow d'activation est borné à la révision ci-dessus, conserve l'ancienne
génération et arme un retour systemd avant tout `switch-to-configuration test`.
Le profil de démarrage n'a été changé qu'après les contrôles HTTPS, WebDAV et
restauration. Les traces des deux essais se trouvent sous
`/root/nextcloud-preparations/43a8cd0f551b74b75583bb8aaf849d2a90560618`.
Un retour de génération ne réinitialise ni la base Nextcloud ni ses fichiers.
