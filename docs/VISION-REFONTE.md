# Publication Vision 2 — état et procédure

## Vision 2.3 publiée le 26 septembre 2026

Application `c797c92be8c7a774e5566d5f8182442f52d609da`, source
VPS `886105f5f5b926fd7eb6f2d1391bcae973617661`. CI backend
[36278489471](https://github.com/MrJ-am/vision/actions/runs/36278489471),
interface [36278489466](https://github.com/MrJ-am/vision/actions/runs/36278489466),
infrastructure [36278717893](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36278717893),
[préparation 36278887497](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36278887497),
[activation 36278976906](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36278976906)
et [constat indépendant 36279153941](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36279153941)
réussis. Le rapport d'activation confirme le retour désarmé et les deux
publications exactes.

La migration additive 013 a été essayée sur une restauration fraîche avant
l'arrêt puis sur une seconde sauvegarde après arrêt des écritures. Le
comparateur a conservé sans changement la stabilité, les références, les
épisodes et les séances. **58 items** ont reçu une formulation autonome et
**49 observations historiques** ont été reprises, avec date du fait quand elle
était connue et date de saisie serveur. Une séance ouverte a été préservée.
Les observations nouvelles sont immuables et transversales aux fiches pour
un item partagé ; les fiches ont leur propre historique. Les 14 outils MCP
incluent `ajouter_observation`, et `ouvrir_seance` fournit l'historique
structuré pour construire des questions difficiles mais faisables.

Les vérifications HTTPS ont couvert Basic, Bearer, OAuth, sessions/CSRF,
interface, artefact et l'item France reformulé. Une lecture MCP ultérieure
a confirmé les items France, République tchèque et Situation didactique et
les suggestions chiffrées. Aucune séance de contrôle ni réponse fictive
n'a été créée en production. Les clients doivent rafraîchir leur catalogue
MCP pour afficher le nouvel outil. Le retour applicatif ne restaure pas la
base ; les anciennes versions demeurent disponibles. Preuves agrégées :
[vision-refonte-publication.json](../operations/vision-refonte-publication.json).

## Reprise des séances et gain rapproché, publiée le 26 septembre 2026

Vision `5c92e0827c13cddaeb0bac852e57b3b26491670a` et son interface sont
actifs depuis la source VPS `35718a7ba5cbaf14132aab990dabd8f6a08e4509`.
Le contrat 2.2 ajoute `lister_seances` et `lire_seance` : pagination par
thème/date, reprise et clôture depuis toute conversation. Plusieurs séances
ouvertes coexistent sans limite ; une nouvelle ouverture demande le choix de
la personne. Un gain rapproché excessif est ramené à la borne admise, avec
valeur demandée et appliquée dans le rapport atomique.

CI Vision `36198122892`, interface `36198122897`, VPS `36198498811`,
préparation `36198681603`, activation `36198786537` et constat indépendant
`36198944200` réussis. La restauration isolée, puis la migration réelle 012
ont préservé les **deux séances ouvertes** et le reste des données. Les treize
outils, Basic/Bearer/OAuth, CSRF, navigateur et services ont passé les contrôles.
Le retour autonome est désarmé. Aucune séance n'a été clôturée d'office.

## Révision séquentielle publiée le 25 septembre 2026

Application `608c34cacdd0040dd84c4507f26d7799d70d4f38`, source VPS
`766316cae5b71964c98e73bce476243087d0a2b5`. Préparation
[36164763326](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36164763326)
(réussie à la deuxième tentative après un délai SSH avant tout changement),
activation [36164997869](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36164997869)
et constat [36165233858](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36165233858)
réussis. Migrations additives 009 et 010 appliquées sans modification des données
existantes. Une préparation ciblée expose au plus un item ; son texte de retour
ordonne d’enregistrer chaque tentative par `evaluer_items` avant un nouvel appel
à `preparer_revision`. Basic, Bearer, OAuth, navigateur, services et 32 sondes
HTTP/TLS ont été contrôlés. L’état actif et de démarrage NixOS est conservé,
les deux publications Vision pointent vers cette application, et le retour
est désarmé après le constat.

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

## Vision 2.4 publiée le 27 septembre 2026

L'application et l'interface `d5d6217b95b7548af7b7ed9009321a413f1c998b` ont été activées depuis le candidat VPS `be2b7fdd81a64b2f7aea02da106401da93789e68`. Les items exposent leur seul contenu autonome, sans titre ni directives de révision. La fiche fournit le contexte ; les observations horodatées des fiches et items accompagnent les séances. Les fenêtres qui ferment le plus tôt passent d'abord, puis les nouveaux items complètent le nombre demandé.

[CI serveur](https://github.com/MrJ-am/vision/actions/runs/36338596805), [CI interface](https://github.com/MrJ-am/vision/actions/runs/36338596798), [CI VPS](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36338767151), [préparation](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36338925947), [activation](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36338989951) et [constat indépendant](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36339153877) réussis. Les migrations 013/014 ont préservé 58 items autonomes, les états mémoriels et une séance ouverte. Aucun item de test ni restauration de production. Les liens serveur/interface sont exacts, le retour autonome inactif ; génération NixOS inchangée. Rapport chiffré dans [vision-refonte-publication.json](../operations/vision-refonte-publication.json).

Une première activation a révélé qu'un rejeu de 013 sous l'ancienne version dépassait la contrainte du titre interne TSD. Le service a été rétabli par workflow, puis 013 rendue relançable et testée. Un audit complémentaire a repéré 138 entrées historiques identiques sur 187 observations brutes. Elles restent conservées dans l'audit, une occurrence est exposée pour chaque fait historique identique, et les futurs replays n'en ajoutent plus. La dernière activation et le constat ont validé le correctif. Les observations explicites demeurent distinctes.

## Tableaux et révisions en retard — publication du 27 septembre 2026

Le serveur et l’interface `3ff7f21f01fa63ed740672f9b331e46d50704b8c` sont actifs depuis le candidat VPS `94f2de6a8b00016e14b5494a58ef4f0226a830ae`. Les rattachements d’une fiche présentent le contenu des items, les filtres de retard, de fenêtre et de nouveauté, ainsi que le tri par fermeture de fenêtre ou alphabet. Un crayon permet l’édition sur place de la fiche et des connaissances dans le tableau. Le style commun est verrouillé à `3691f0faa80cdcd03bdd7fc60418d0de331a945c` ; les autres applications gardent leur révision.

[CI serveur](https://github.com/MrJ-am/vision/actions/runs/36347303978), [CI interface](https://github.com/MrJ-am/vision/actions/runs/36347303976), [CI VPS](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36347509629), [préparation](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36347688045), [activation](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36347783328) et [constat indépendant](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36348090796) ont réussi. Le rapport dans `operations/vision-refonte-publication.json` confirme 58 items autonomes, 187 observations historiques et une séance ouverte préservés, sans restauration de production.
