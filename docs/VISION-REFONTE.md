# Publication Vision 2 — état et procédure

## Publication réelle du 25 septembre 2026, 14:14 UTC

Serveur et interface `ad0fbd80401c0d2aed77b12d11e3f1b3e8397367` actifs ;
source de migration `951e80e1a66c1240541655a3eca6b435e62e4165`.
[Préparation 36145808884](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36145808884),
[activation 36146012682](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36146012682)
et [constat après finalisation 36146366039](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36146366039)
réussis. L’activation s’est terminée et le constat confirme le retour inactif.

Migration : **2 fiches, 58 items, 58 liens, 18 observations archivées**,
45 items sans évaluation attribuable. Stabilité initiale : 45 à −15 dB,
8 à −12, 4 à −17, 1 à −20 ; heuristique prudente documentée, aucune conversion
des paramètres FSRS. Le dump frais après arrêt des écritures a été restauré,
simulé et importé deux fois en base isolée avant l’import réel atomique.
Les sources historiques et les écritures v2 restent conservées.

Les 32 sondes HTTP/TLS, services/sauvegardes, nouvelle connexion runner,
neuf outils MCP, instructions 2.0.0/db-1, Basic/Bearer/OAuth/Origin null,
CSRF, tokens préexistants, artefact exact et navigateur ont été vérifiés.
Les contrôles n’ont créé aucune donnée métier fictive en production.

La génération active/par défaut reste
`g24p3rvq97s1x66wiaw29z5kwqgw0ksl-nixos-system-nixos-26.05.8639.c5c4a43b0e80`.
Matheval `f6706f8a6b6b08d797340e26f917a6cdc3bb9e5c` et Logique
`615439c841db1934ffaddc1dee64c85ff6c56cf2` restent actifs.
Sources identité `cb0294c8b78402de1566f54ea3009fbe6ee221c7`.
Les chiffres et empreintes sont dans
[vision-refonte-publication.json](../operations/vision-refonte-publication.json).

Les clients MCP doivent recharger leur catalogue si les cinq anciens outils
restent visibles. Aucun essai dans les comptes personnels des clients n’est
revendiqué. Le [rapport applicatif](https://github.com/MrJ-am/vision/blob/main/rapports/REFONTE-20260925.md)
décrit les contrôles, le modèle et ses limites.

## Procédure de l’opération initiale

Cette opération sépare l’identité authentifiée de la migration applicative.
Les workflows historiques ne sont pas réutilisés avec leurs anciens garde-fous.

`vision-identite.yml` construit le candidat NixOS avec le Nixpkgs réellement
installé. Le comparateur conserve les services, réseau, certificats, comptes,
sauvegardes et tous les sites ; seule la transmission de X-Mrj-User depuis Basic
et MCP évolue. Les en-têtes clients sont écrasés. Le code mrj-auth renvoie le
propriétaire déjà authentifié ; ses sessions, tokens et OAuth sont conservés.
Préparation `36142255046` réussie : 32 sondes HTTP/TLS, construction, invariants,
Nginx et timer de retour. La simulation ne prévoit que mrj-auth et Nginx.
Activation `36142629501` réussie, sources `cb0294c8b78402de1566f54ea3009fbe6ee221c7` :
génération active et de démarrage `g24p3rvq97s1x66wiaw29z5kwqgw0ksl`.
Basic, Bearer, OAuth/Origin null, CSRF, préservation des tokens et 32 sondes
HTTP/TLS vérifiés. Retour autonome désarmé après enregistrement.

`vision-refonte.yml` référence une révision infrastructure exactement vérifiée.
Son `operations/vision-refonte-candidat.json` fige l’archive applicative, l’artefact
interface et leurs SHA-256, avec les exécutions de CI d’origine. Aucune source
applicative courante n’est téléchargée implicitement. Le serveur est recompilé
sur le VPS ; le navigateur reprend l’artefact réellement testé par Playwright.

Le préparateur relève les générations et quatre publications, vérifie les
services et construit les deux candidats sans changer les liens actifs. Un dump
PostgreSQL frais est restauré dans une base temporaire dédiée, sous le rôle
Vision. Les migrations y installent `pg_trgm` (extension de recherche fournie par
PostgreSQL 17), sans modification de l’instance ni de la version majeure.
L’import métier y est simulé, appliqué puis rejoué. Les dates, sources et traces
historiques restent dans le plan privé ; seuls les agrégats sortent du VPS.
L’import exige un propriétaire historique univoque dans le fichier des comptes.

Lors de l’activation, un timer indépendant est armé avant l’arrêt de Vision.
Une nouvelle sauvegarde et une nouvelle restauration isolée relisent les données
au dernier moment. Le plan est reconstruit depuis cette source fraîche, puis
appliqué atomiquement après vérification de son empreinte sous verrou. Les
liens du serveur et de l’interface basculent ensemble pendant la maintenance.
Les autres applications ne sont pas arrêtées. Les sondes HTTPS valident ensuite
le binaire 2.0.0, l’artefact exact, Basic, sessions/CSRF, Bearer/OAuth et les neuf
outils réellement servis. Aucun item fictif n’est créé en production.

Le retour rétablit uniquement les deux publications. Il ne restaure jamais la
base et préserve les nouvelles écritures. Après l’import, les tables 1.x sont
figées : un ancien client ne peut pas créer une collection divergente. Un retour
complet en écriture passe par une version corrective 2.x ou une conciliation
explicite des nouvelles données avant toute restauration manuelle. Les dumps
0600, plans privés et anciennes publications sont conservés sur le VPS ; aucun
contenu utilisateur ni secret ne doit entrer dans Git ou les artefacts Actions.

Les rapports finaux et les identifiants des exécutions terminées seront ajoutés
après les contrôles. Une préparation réussie ne prouve pas une activation.
