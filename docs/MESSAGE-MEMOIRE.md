# Message de reprise à transmettre au projet Mémoire

Le dépôt privé `MrJ-am/vps-infrastructure` reprend également PostgreSQL, en
complément de Nginx, HTTPS et NixOS. Lire son `docs/POSTGRESQL.md`, son
`docs/MIGRATION.md` et `patches/matheval-postgresql.patch`.

Reprendre la PR nº 8 / branche `infra/separer-nginx` du dépôt `MrJ-am/M-moire`.
Le patch est fondé sur `deploy/matheval.nix` au commit
`c83308ddfeefa03dfbb6692773c3d1274c867936`. Le comparer à la version actuelle
avant de l'appliquer ; les empreintes amont et adaptée figurent dans
`vendor/matheval/source.json` du dépôt VPS.

Modifications à reprendre côté Mémoire :

1. Retirer de `deploy/matheval.nix` les déclarations `services.postgresql` et
   `services.postgresqlBackup`. L'infrastructure gère l'instance PostgreSQL 17,
   la création de la base et du rôle `matheval`, les accès et les sauvegardes locales.
2. Conserver le service applicatif, ses comptes, chemins, secrets, publications,
   migrations et l'export chiffré `matheval-backup` avec son workflow Actions.
   Cet export utilise `config.services.postgresql.package` au lieu d'imposer
   `pkgs.postgresql_17`. Attendre aussi `postgresql-setup.service` avec `after`
   et `requires` dans le service Matheval.
3. Maintenir l'ancienne configuration complète reconstructible : conserver les
   anciens blocs PostgreSQL et sauvegardes locales dans un fichier
   `deploy/legacy-postgresql.nix`, conditionné par `services.matheval.enable`,
   importé uniquement par `deploy/hostinger/configuration.nix`, comme pour
   `legacy-nginx.nix`. Étendre le contrôle de syntaxe CI à ce fichier. Ce module
   historique ne doit jamais être importé dans la nouvelle infrastructure.
4. Actualiser `AGENTS.md`, `deploy/INFRASTRUCTURE.org`, `deploy/README.org` et
   `deploy/REPRISE.org` avec cette répartition et l'URL réelle du dépôt VPS.
   Le raccordement reste socket `/run/postgresql`, base/rôle/compte Unix
   `matheval`, et HTTP `127.0.0.1:3000`, préfixe `/matheval`.
5. Renvoyer au projet VPS le commit du module repris pour qu'il remplace sa
   copie adaptée par une copie amont identifiée, puis mette à jour ses empreintes.

La migration serveur reste préparée, **non activée**. Aucun déplacement de
données ni changement de version majeure n'est demandé. Les restrictions
HBA/SQL et le retour arrière de leurs ACL doivent être vérifiés côté VPS.
Ne pas copier isolément le nouveau module sur l'ancienne installation et ne
pas reconstruire NixOS depuis Mémoire. La bascule porte sur la configuration
complète et reste coordonnée par le projet VPS.
