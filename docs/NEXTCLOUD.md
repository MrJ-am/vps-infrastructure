# Nextcloud sur cloud.mrj.am — candidat non déployé

## Version proposée et état

La branche `nextcloud/installation-20260929` prépare Nextcloud **34.0.4**.
Cette préparation n'est pas une preuve d'installation. Une nouvelle exécution
Actions doit auditer le VPS, construire le candidat puis contrôler son activation.

Le dernier état documenté est NixOS 26.05.8639, Nixpkgs `c5c4a43b0e80`,
avec Nextcloud 34.0.3 disponible. La révision stable utilisée pour la CI,
`4c7870105e7f1fdf9c48688c8d7efc21abf0688a`, fournit 34.0.4 ; le module
Nextcloud consulté était identique entre ces deux révisions. Le candidat
rétroporte seulement cette maintenance et son empreinte, sans mettre à jour
le système entier. Revalider versions, provenance et support avant activation.

Aucune conversion vers les flakes n'est incluse : les opérations existantes
utilisent NIX_PATH et les modules NixOS classiques. Le choix de 34.0.4 n'est
pas une incompatibilité de principe entre les flakes et une autre majeure.

## Architecture préparée

- Nginx commun et certificat ACME pour `cloud.mrj.am`.
- PHP-FPM et tâches cron du module NixOS Nextcloud.
- Redis local dédié au cache et au verrouillage.
- PostgreSQL 17 partagé par socket Unix ; base/rôle/compte `nextcloud`.
- Sauvegarde logique PostgreSQL quotidienne par l'infrastructure.
- Données persistantes sous `/var/lib/nextcloud`.

Le registre réserve le domaine comme service `native`, sans port HTTP fictif.
`database.createLocally = false` évite de confier PostgreSQL au module applicatif.
Les dépendances de `nextcloud-setup` sur PostgreSQL et son setup sont explicites.

Le dump PostgreSQL ne sauvegarde pas les fichiers utilisateurs. Avant usage
comme stockage unique, il faut une sauvegarde cohérente base/configuration/
fichiers, chiffrée hors VPS, une rétention bornée et un essai de restauration.
Aucun tel dispositif complet n'est attesté par cette branche.

## DNS

Dans la zone de `mrj.am`, créer un A : nom `cloud`, valeur `187.77.95.158`,
TTL automatique ou valeur par défaut. Vérifier les réponses DNS réelles avant
ACME. Ne pas ajouter d'AAAA tant que le routage public IPv6 n'est pas vérifié.

## Entrées NixOS et préservation des sites

Le candidat d'amorçage `hosts/hostinger/nextcloud-acme.nix` importe désormais
`./logique.nix`, et non `./configuration.nix`, afin de conserver Logique.
L'entrée finale candidate est `hosts/hostinger/logique.nix`, qui conserve
Logique, Vision, Matheval et les modules communs. Il faut néanmoins comparer
ces candidats à l'entrée réellement active sur le VPS avant toute activation.

Ne jamais activer directement `configuration.nix` en oubliant le module Logique.
Le fichier d'amorçage n'est pas, à lui seul, une procédure sûre d'émission ACME :
le workflow doit réserver l'accès HTTP au challenge tant que HTTPS n'est pas
valide, tester Nginx avec les vrais certificats et prévoir un retour autonome.
Aucun accès utilisateur ni identifiant ne doit transiter en HTTP.

## Premier administrateur

Le candidat initialise sans administrateur (`adminuser` et `adminpassFile`
à null). Il faut donc prévoir sa création sécurisée, sans laisser un assistant
d'installation public permettant à un tiers de prendre possession de l'instance.
L'instance n'est pas livrée tant que son propriétaire ne peut pas s'y connecter.

La syntaxe documentée pour créer interactivement un administrateur est :

```sh
nextcloud-occ user:add --group=admin IDENTIFIANT
```

Le mot de passe doit être demandé interactivement ou transmis par une voie
secrète adaptée, jamais dans Git, le Nix store, les arguments visibles ou les
journaux Actions désormais publics. Ne pas réutiliser les identifiants Vision.
Référence : https://docs.nextcloud.com/server/stable/admin_manual/occ_users.html

## Validation nécessaire

Préparer une opération Nextcloud distincte des migrations historiques : audit
actuel, évaluation complète avec le Nixpkgs du serveur, comparaison des unités,
construction, retour indépendant de SSH, essai temporaire puis enregistrement
exact de la génération testée. Préserver toutes les anciennes générations et
les données. Un rollback NixOS n'annule pas les migrations SQL ni les ACL.

Contrôler les sites existants, les accès administratifs anonymes refusés,
Basic/Bearer/OAuth et sessions Vision, une nouvelle connexion SSH du runner,
les sauvegardes, HTTPS Nextcloud, cron, Redis et un aller-retour WebDAV avec
fichier de test dédié. Vérifier séparément l'état après finalisation.
