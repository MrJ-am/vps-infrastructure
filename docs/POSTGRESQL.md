# PostgreSQL partagé : contrat d'infrastructure

**Activé et vérifié le 18 septembre 2026**, dans
[l'exécution de migration](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395320446).
La gestion de PostgreSQL appartient désormais à l'infrastructure. PostgreSQL
17.11, son répertoire de données et les lignes existantes sont conservés ;
les restrictions d'accès et la restauration d'une sauvegarde ont été vérifiées.

## Responsabilités et raccordement

| Infrastructure VPS | Projet applicatif |
|---|---|
| Version, paquet, extensions disponibles et réglages du serveur | Besoins de compatibilité et d'extensions |
| Création des bases/rôles, authentification et droits de connexion | Tables, index, données, migrations du schéma |
| Sauvegardes PostgreSQL locales quotidiennes | Validation fonctionnelle des restaurations et exports hors VPS convenus |
| Mise à jour NixOS et coordination d'une maintenance collective | Publication du code avec un compte sans administration PostgreSQL |

`databases.json` associe un identifiant de projet à un nom commun de **base,
rôle SQL et compte système**. Le nom contient au maximum 63 caractères parmi
les lettres minuscules, chiffres et `_`, et commence par une lettre. Les noms
réservés, les doublons et le préfixe `pg_` sont refusés. Cette convention
permet l'authentification `peer` sans mot de passe ni fichier de secrets SQL.

| Paramètre | Matheval | Vision, exemple non activé |
|---|---|---|
| Socket | `/run/postgresql` | `/run/postgresql` |
| Port logique du socket | `5432` | `5432` |
| Base, rôle, utilisateur Unix | `matheval` | `vision` |
| Dépendance du service | `postgresql-setup.service` | `postgresql-setup.service` |

L'application utilise un client PostgreSQL configuré pour ce socket, cette
base et ce rôle. Matheval possède déjà ces valeurs dans `server/src/database.mjs` ;
aucune modification du code Node.js n'est nécessaire. Auditer néanmoins un
éventuel `DATABASE_URL` dans son environnement réel, sans afficher ses secrets.

Le compte système est créé par le module applicatif. L'infrastructure vérifie
son existence, crée son rôle sans privilèges globaux et lui attribue sa base.
Le service applicatif doit déclarer `after` et `requires` pour
`postgresql.service` et `postgresql-setup.service`, afin d'attendre la création
des bases/rôles et l'application des droits. La publication applicative ne
peut pas reconstruire NixOS, créer d'autres bases ou administrer les rôles.

## Accès et limites

Les règles HBA autorisent le compte Unix `postgres` à administrer les bases,
puis chaque compte applicatif à ouvrir sa propre base sous son propre rôle.
Toutes les autres connexions sont refusées, y compris en TCP. Les droits
PUBLIC sont retirés sur les bases déclarées et leur schéma `public`, puis les
droits nécessaires sont accordés au propriétaire. Ces opérations sont
réappliquées par `postgresql-setup` sur un cluster existant ; elles ne sont pas
limitées au premier démarrage. Elles ne suppriment aucune table ni donnée.

L'administrateur Unix root reste administrateur de la machine et passe par
`runuser -u postgres -- psql ...`. Les applications ne disposent pas de cet
accès. Avant migration, contrôler les appartenances et droits supplémentaires
des rôles existants : le module ne purge pas aveuglément des droits historiques.

Les bases partagent toujours mémoire, CPU, disque, journal WAL et maintenance.
Les noms de certaines ressources globales restent visibles. Ce modèle ne
fournit pas une isolation entre locataires hostiles. Une version incompatible
ou un besoin d'isolation renforcée demandera une instance séparée.

## Sauvegardes

Chaque base du registre reçoit une sauvegarde locale quotidienne via
`services.postgresqlBackup`, dans `/var/backup/postgresql`, avec le compte
`postgres`. Pour Matheval, le nom du service, l'horaire `daily` et le chemin
sont conservés. La mécanique NixOS conserve le dump courant et le précédent ;
ce n'est pas un historique hors serveur.

L'export chiffré existant `matheval-backup`, sa clé publique age, ses droits
sudo limités et le workflow Actions de Mémoire restent en place. Le client
`pg_dump` suit désormais le paquet PostgreSQL choisi par l'infrastructure.
Le retrait de `services.postgresqlBackup` du module applicatif ne doit donc
pas supprimer cet export. Pour Vision ou un nouveau projet, définir une copie
chiffrée hors VPS et sa rétention avant d'y collecter des données importantes.

Un dump logique peut être restauré dans une base isolée pour vérification.
Une sauvegarde physique ou une restauration temporelle concerne le cluster
entier et nécessite une procédure distincte. Un retour de génération NixOS
ne restaure ni les données SQL, ni les ACL, ni les attributs de rôles.

## Ajouter une base

1. Vérifier le besoin, la compatibilité PostgreSQL 17, les extensions et les
   modalités de sauvegarde. Une application peut fonctionner sans PostgreSQL.
2. Adapter `examples/vision-database.json` et fusionner l'entrée dans
   `databases.json`. Déclarer le compte système dans le module applicatif.
3. Configurer le client et les dépendances de démarrage décrites plus haut.
4. Vérifier la configuration complète et les tests, puis suivre
   [MIGRATION.md](MIGRATION.md). L'ajout de rôles et la modification du HBA
   peuvent affecter les unités PostgreSQL : relire l'activation prévue.
5. Contrôler les connexions autorisées/refusées, les applications et leurs
   sauvegardes ; enregistrer le résultat et le contrat du projet.

Retirer une entrée n'efface pas automatiquement sa base ni son rôle. La
connexion et sa sauvegarde planifiée disparaissent : traiter un retrait comme
une opération de conservation des données à organiser explicitement.

Références : [séparation des bases](https://www.postgresql.org/docs/17/manage-ag-overview.html),
[authentification peer](https://www.postgresql.org/docs/17/auth-peer.html),
[module NixOS PostgreSQL](https://github.com/NixOS/nixpkgs/blob/nixos-26.05/nixos/modules/services/databases/postgresql.nix).
