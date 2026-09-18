# Message à transmettre au projet Mémoire

La migration du VPS est terminée : Nginx, HTTPS, NixOS et PostgreSQL sont
maintenant gérés par le dépôt privé
[MrJ-am/vps-infrastructure](https://github.com/MrJ-am/vps-infrastructure).
La configuration a été activée et enregistrée le 18 septembre 2026 à 21:10 UTC,
avec contrôles des services, SSH, HTTPS, droits SQL, conservation des données
et restauration d'une sauvegarde dans une instance isolée.
[Preuve de la bascule](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395320446).

La [PR nº 8](https://github.com/MrJ-am/M-moire/pull/8) est fusionnée dans
`master`, commit `841317fb87c8f81867ad884ca19ef93e8308838b`. Les consignes
`AGENTS.md`, `deploy/INFRASTRUCTURE.org`, `deploy/REPRISE.org` et
`deploy/README.org` sont actualisées. Repars de `master` et lis ces fichiers.
Les tests et la [publication de ce commit](https://github.com/MrJ-am/M-moire/actions/runs/35396161100)
ont réussi, avec vérification des fichiers servis après déploiement.
Le module Matheval adapté est déjà intégré côté VPS : ne réapplique pas le patch
PostgreSQL. Les modules `legacy-*` restent uniquement des archives reconstructibles.

Mémoire conserve l'application, les données, le schéma et ses migrations, les
publications et les exports chiffrés. VPS gère l'instance PostgreSQL, les bases,
les rôles, les règles d'accès et les sauvegardes locales. Le raccordement reste
`https://principiipetit.io/matheval/` vers `127.0.0.1:3000`, avec le socket
`/run/postgresql` et la base/rôle/compte Unix `matheval`. Toute évolution de ce
contrat ou du module NixOS doit être intégrée explicitement par VPS.

Depuis ChatGPT Work, tout accès distant passe par GitHub Actions ; aucun SSH
direct n'est disponible. Les publications et sauvegardes utilisent toujours
`matheval-deploy`, sans clé root dans Mémoire. La
[sauvegarde après migration](https://github.com/MrJ-am/M-moire/actions/runs/35396161367)
a réussi. Une modification de `deploy/backup-request.json` sur `master` permet
désormais de déclencher cet export depuis Work ; son horaire quotidien reste inchangé.

Les générations, sauvegardes de retour et preuves sont consignées dans
[ETAT.md](https://github.com/MrJ-am/vps-infrastructure/blob/main/docs/ETAT.md)
et `deploy/INFRASTRUCTURE.org`. Le VPS n'a pas été redémarré ; le démarrage de
la configuration est enregistré mais n'a pas été testé par un redémarrage réel.
Ne reconstruis pas NixOS depuis Mémoire et garde les tests de collecte dans des
bases isolées. Tu peux poursuivre le développement applicatif sur cette base.
