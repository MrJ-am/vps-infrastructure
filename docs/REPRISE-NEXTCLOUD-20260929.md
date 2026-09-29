# Reprise Nextcloud — 29 septembre 2026

## Bilan des opérations de cette reprise

Les outils GitHub d'écriture fonctionnent à nouveau. Le commit
`e566b5218b4798eeee03f56a5a7a090db6ee8ed7` corrige l'import du candidat
ACME : `hosts/hostinger/nextcloud-acme.nix` importe `./logique.nix`.
Sa CI complète est réussie :
https://github.com/MrJ-am/vps-infrastructure/actions/runs/36616997267
(job `109572461730`, Python, syntaxe Nix, évaluations NixOS et intégration
PostgreSQL/restaurations en environnement jetable).

Le commit `90fc3c10ee55eb97b0078f1fe9797571a780f42e` corrige
`docs/NEXTCLOUD.md` : état candidat, entrée finale conservant Logique,
création administrateur par `user:add --group=admin`, et préconditions.
Le commit `e3c5d5b6ba22d13238a2bb9a34291dc96cb4dd29` ajoute le contrôle
DNS non destructif `.github/workflows/nextcloud-dns.yml`.
Aucun de ces commits ne déploie le système. Main était toujours
`2c02d2704ac79843046a304531896cb15997ace6` lors de la reprise.

## Audit réel du VPS

Exécution `36599677941`, tentative 3, job `109572649737`, vers 19:08 UTC :
https://github.com/MrJ-am/vps-infrastructure/actions/runs/36599677941

La connexion administrative du runner réussit. Constats dans ses journaux :
- NixOS `26.05.8639.c5c4a43b0e80 (Yarara)`.
- Génération active et par défaut identiques :
  `/nix/store/g24p3rvq97s1x66wiaw29z5kwqgw0ksl-nixos-system-nixos-26.05.8639.c5c4a43b0e80`.
- Nixpkgs : `/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos`.
- Nginx actif ; test de sa configuration réussi.
- PostgreSQL 17.11, `/var/lib/postgresql/17`, socket `/run/postgresql`, sans écoute TCP.
- Bases applicatives présentes : Matheval et Vision ; aucune base Nextcloud.
- Vision : `/srv/vision/releases/3cbd57ff8d05798e3766fd0d6c93087739d8b608`.
- Matheval : `/srv/matheval/releases/04168b68723322afe18b51d20e8089121348b8b3`.
- 22 contrôles HTTP/TLS du registre main réussis. Cela ne couvre pas un test
  authentifié complet de Vision ni les futurs contrôles Nextcloud.

L'audit est globalement en échec : `diagnose-migration.sh` exige encore la
génération historique `8cbhcffx...` de la première migration ; `audit.sh`
cherche `/srv/vision/current/RELEASE`, absent dans le format actuel. Il faut
un audit contemporain, pas contourner ces gardes ni déclarer l'audit vert.

## DNS constaté

Exécution DNS `36617279797`, job `109573429800`, vers 19:10 UTC :
https://github.com/MrJ-am/vps-infrastructure/actions/runs/36617279797

Google et Cloudflare renvoient le statut DNS 3 (NXDOMAIN) pour A, AAAA et
CAA de `cloud.mrj.am`. L'enregistrement attendu n'est pas visible.
Le workflow a réussi à effectuer le diagnostic, pas à valider le domaine :
son journal indique `A_attendu_confirme=false` et un avertissement.
Créer dans la zone `mrj.am` : A, nom `cloud`, valeur `187.77.95.158`.
Aucun DNS n'a été modifié pendant cette reprise.

## Travaux restant à exécuter

Nextcloud n'a pas été installé ni activé. La branche n'est pas fusionnée.
Il manque une procédure Nextcloud de préparation/activation/retour dédiée,
la construction sur le Nixpkgs réellement installé, un audit complet et des
contrôles d'invariants, l'émission du certificat et la vérification HTTPS,
le premier administrateur utilisable, ainsi que la sauvegarde cohérente des
fichiers/configuration/base et son essai de restauration.

Préserver les anciennes générations, tous les sites et toutes les données.
Ne pas utiliser une migration historique comme un déploiement générique.
Ne pas considérer le succès de la CI comme preuve d'installation Nextcloud.
Le registre de coordination main doit être relu et informé avant publication
de changements partagés. Il n'a pas été modifié pendant cette reprise.
