# État de la migration à transmettre au projet Mémoire

La migration complète VPS / Mémoire est autorisée et en cours de préparation,
mais **la bascule serveur n'a pas été exécutée**.

VPS a intégré la provenance exacte de `deploy/matheval.nix` au commit amont
`0bcdaf101cbdacb85694ca217fd21ab3f2eac828`, sans modifier ses octets. Le commit
VPS est `e0f0c33a312708a54babdbfca00bd958682845b0` ; sa CI NixOS et PostgreSQL
a réussi. Ne plus appliquer le patch PostgreSQL au module : il est déjà repris.

La PR nº 8 de Mémoire a été actualisée au commit
`fdd71f8ea63da9e65f40cd59f4e6d5ea3ba942ad` avec les consignes d'accès via GitHub
Actions. Elle reste en brouillon et non fusionnée jusqu'à la bascule vérifiée.

Le premier [diagnostic administratif GitHub Actions](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35324107274)
s'est arrêté avant toute connexion : le secret `VPS_ADMIN_SSH_KEY` n'est pas
disponible au workflow du dépôt VPS. La clé administrative existante est dans
l'archive privée ; la configuration du secret attend la connexion GitHub à
deux facteurs. Aucun changement système, SQL, de données ou de sauvegarde
n'a été exécuté lors de cette reprise.

Depuis Work, les opérations distantes passent par GitHub Actions. Ne pas
retenter SSH directement. VPS peut désormais déclencher son audit en publiant
une demande `operations/audit-request.json`, puis lire les résultats du commit.

Mémoire conserve les données, le schéma, les migrations, les publications et
l'export chiffré. VPS prend en charge Nginx, HTTPS, NixOS, PostgreSQL, les bases,
les rôles, les accès et les sauvegardes locales. La configuration historique
reste reconstructible. Ne pas copier isolément le module adapté sur le VPS,
importer les modules `legacy-*` dans la nouvelle infrastructure ni reconstruire
NixOS depuis Mémoire. Les prochaines étapes côté VPS sont l'audit, la
construction avec le Nixpkgs installé, les sauvegardes et le retour arrière,
puis l'activation et ses contrôles avant la finalisation de la PR nº 8.
