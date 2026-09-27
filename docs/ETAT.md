# État attesté au 26 septembre 2026

## Vision 2.3 — items autonomes et observations, 26 septembre 2026, 23:19 UTC

Serveur et interface `c797c92be8c7a774e5566d5f8182442f52d609da` actifs,
source VPS `886105f5f5b926fd7eb6f2d1391bcae973617661`.
CI applicative 36278489471, interface 36278489466, infrastructure
36278717893 ; préparation 36278887497, activation 36278976906 et constat
indépendant 36279153941 réussis. Migration 013 : **58 items historiques
reformulés**, **49 observations horodatées reprises**, une séance ouverte
conservée, états mémoriels identiques. Les autres applications et la génération
NixOS active et au démarrage sont restées inchangées.

Quatorze outils MCP, Basic, Bearer, OAuth, sessions/CSRF, navigateur et artefact
exact ont été vérifiés après bascule. Le retour autonome est désarmé. Une lecture
réelle après finalisation confirme « Paris est la capitale de la France »,
« Prague est la capitale de la République tchèque », les observations sur
l'item TSD et les suggestions par fiche avec nombres à réviser. Les clients
MCP doivent recharger leur catalogue pour voir `ajouter_observation`.
Détails : [VISION-REFONTE.md](VISION-REFONTE.md) et
[vision-refonte-publication.json](../operations/vision-refonte-publication.json).

## Interfaces documentaires communes publiées le 26 septembre à 17:10 UTC

Les trois sites servent le style `3aab7233465ac0abe49464fa26a360765ccb4004`.
Vision serveur/interface : `b33ce9f0c20f4b8af5790831b59217408b496fc0` ;
Matheval : `fc3c2fcd36d920142de946b41154cc6f3a67d76e` ;
Logique : `2e2dd6a48cbdad20bbc8d0ac34a9ace67f111a0f`.

[CI 36257590715](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36257590715)
(132 tests, NixOS et PostgreSQL),
[préparation 36257753511](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36257753511)
et [activation 36257831262](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36257831262)
réussies, sources `d363b178b1f1c33fb8b73c518e20a480411c5985`.
Une nouvelle connexion après finalisation confirme les quatre liens et fichiers,
les services/sauvegardes et le retour automatique désarmé. La génération active
et par défaut `g24p3rvq97s1x66wiaw29z5kwqgw0ksl` et l’entrée NixOS sont conservées.

Les 32 sondes HTTP/TLS, les ressources exactes des trois sites, seize vues publiques,
les sessions/CSRF, Basic, Bearer, OAuth et treize outils MCP ont été vérifiés.
Les captures publiques ont été examinées. La première tentative a été annulée
et corrigée : permissions npm trop restrictives, contrôlées maintenant sous le
compte réel avant bascule. Aucun nouveau schéma ni restauration de données ;
les démarrages gardent leurs vérifications SQL idempotentes existantes.

La synchronisation finale de Mémoire sur `master`,
[36258073154](https://github.com/MrJ-am/M-moire/actions/runs/36258073154),
a également réussi : 56 tests navigateur et 107 fichiers servis identiques.

Procédure et limites : [INTERFACES-DOCUMENTAIRES.md](INTERFACES-DOCUMENTAIRES.md).
Références, preuves et empreintes : [interfaces-publication.json](../operations/interfaces-publication.json).
La page `/auth/mcp` conserve son interface propre. Les anciennes versions restent
disponibles ; un retour ultérieur constitue une nouvelle opération applicative.

## Vision 2.2 publiée et séances ouvertes préservées

Serveur et interface `5c92e0827c13cddaeb0bac852e57b3b26491670a` actifs ;
source VPS `35718a7ba5cbaf14132aab990dabd8f6a08e4509`.
CI applicative `36198122892`, interface `36198122897`, infrastructure
`36198498811`, préparation `36198681603`, activation `36198786537`
et constat indépendant `36198944200` réussis le 25 septembre UTC
(26 septembre à Paris). La migration additive 012 a été testée sur une
restauration isolée puis activée sans modifier les données : **deux séances
ouvertes conservées**, aucune séance fictive créée. Treize outils MCP, Basic,
Bearer, OAuth, interface et sites ont été contrôlés. Le retour autonome est
désarmé ; la génération NixOS est inchangée. La clôture des séances reste
à l'initiative de la personne.

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

Les états datés ci-dessous sont historiques.

## Rétablissement des tokens et OAuth Vision, 23 septembre à 02:11 UTC

La génération active et de démarrage `sz7w3lqm1lspcdzrqisi23xb6lv9886d`
importe les sources `96dc1e8e95b091dd0f13cc9d99002f0cd932210a`.
La [préparation 35809113793](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35809113793)
et l'[activation 35809202327](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35809202327)
ont réussi. Le [contrôle après finalisation 35809360397](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35809360397)
confirme le service actif, la page multi-tokens et la lecture de
`access_tokens` ; deux tokens préexistants restent actifs. Le retour autonome
est désarmé. Les 32 contrôles des sites et services, Basic, Bearer, les cinq
outils, lecture MCP, CSRF, révocation et rendu mobile ont réussi. La sonde
OAuth a vérifié découverte, enregistrement, consentement, code PKCE,
initialisation MCP et révocation du jeton temporaire sans écrire de fiche.

La précédente publication de tokens avait été annulée après coup par un
ancien timer de retour issu d'une tentative échouée, alors que la nouvelle
génération utilisait le même dérivé Nix. Le retour immédiat arrête désormais
son propre timer et refuse de remplacer une génération enregistrée par une
opération ultérieure ; deux tests couvrent le cas. La base SQLite n'a pas été
restaurée et le token Mistral est conservé. Le test de connexion dans le compte
Mammouth du propriétaire reste à refaire. Détails : [VISION-OAUTH.md](VISION-OAUTH.md).

L'essai initial de cette nouvelle publication,
[35808794433](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35808794433),
a été annulé correctement par son retour. Il échouait dans la sonde qui ne
lisait que le premier en-tête `WWW-Authenticate` ; Nginx émet plusieurs défis.
La sonde corrigée vérifie l'ensemble et a réussi sur le candidat final.

## Tokens Vision indépendants et menu publiés

La gestion des tokens par nom, historique et révocation individuelle est active sur
`https://vision.mrj.am/auth/mcp`. Le token Mistral préexistant a été conservé.
La [préparation 35804593654](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35804593654)
et l’[activation 35804717827](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35804717827)
ont validé Basic, Bearer, cinq outils, lecture, CSRF, rendu mobile et révocation
du seul token temporaire. Sources d’authentification `d71dff5858b221a4eb91655674ab1db74893a5a0` ;
génération active et enregistrée `qd9nkmq2yv55zdb5wfhab1sdy4w1hxvv`.
Les versions du serveur Vision, de Matheval et de Logique ont été conservées.

L’artefact de l’interface Vision `cb92ffa7e4ea5b547e09c9ad1d6dbe01c7e93ccf`,
validé par les CI applicatives 35801855474 et 35801855496, a été préparé par
l’[exécution 35805254157](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35805254157)
puis [publié et vérifié en production par 35805299046](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35805299046).
Le manifeste, les fichiers servis, la connexion réelle, la lecture PostgreSQL,
les protections CSRF et le lien du menu vers `/auth/mcp` ont été contrôlés.
La publication statique remplace uniquement le lien de l’interface ; un retour
autonome à quinze minutes était armé pendant les vérifications et a été désarmé
après leur réussite. Aucune fiche de test n’a été créée.

## Historique attesté au 22 septembre 2026

## Journal HTTP : activé le 22 septembre 2026

La [bascule 35792035605](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35792035605)
a réussi, commit opérateur `c2c3cf2e1073fb17113eabe26798e9862de0eb0f`.
Sources `4345e4ef59765c156aec937fd3a2d4f646f188eb`,
[CI 35791604558](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35791604558),
[préparation 35791837515](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35791837515).

Génération active et par défaut :
`/nix/store/dr7qkvrabfp62qqrc064pr99c9gjvjn6-nixos-system-nixos-26.05.8639.c5c4a43b0e80`.
Entrée conservant tous les sites et le token MCP :
`/etc/nixos/vps-infrastructure/http-4345e4ef59765c156aec937fd3a2d4f646f188eb/hosts/hostinger/logique.nix`.
Ancienne génération `h4rv6sn1izf1hv53qihsgrvkg1hy0j28` protégée. Retour autonome
armé avant l'essai et désarmé après validation et enregistrement.

Journal JSON Nginx dans `journalctl --namespace=http -t http_acces`, catégories
de routes sans paramètres, corps, cookies ou Authorization. Budget persistant
128 Mio (hors marge des fichiers actifs journald), rétention maximale 14 jours,
rotation/compression et limitation de journalisation. L'espace séparé préserve
les journaux système ; des pertes sont possibles sous saturation. Erreurs
natives Nginx limitées à `crit` pour éviter de recopier les URL des refus usuels.
Les anciennes traces ne sont pas supprimées.

Preuves : sondes HTTP 200/401/429 présentes et marqueurs confidentiels absents
du journal structuré ; 32 contrôles HTTP/TLS, huit unités actives, nouvelle
connexion SSH, lecture Basic. Aucun token permanent remplacé ou révoqué,
aucune écriture métier, restauration SQL ou modification applicative. Seul
Nginx a redémarré ; Nixpkgs et PostgreSQL sont conservés.

Audit réel : limites par IP 5/s et connexions sur REST/MCP Vision ; pas de
plafond global ni limite explicite sur Matheval/statique. SYN cookies actifs.
La configuration ne constitue pas une protection DDoS complète ; aucune
protection réseau du fournisseur n'est attestée. Les limites HTTP existantes
n'ont pas été modifiées. Rapport et modalités : [JOURNAL-HTTP.md](JOURNAL-HTTP.md),
preuve machine : `operations/http-publication.json`.

## Token MCP Vision : activé le 22 septembre à 21:22 UTC

L’authentification Bearer fonctionne sur `https://vision.mrj.am/mcp`, en plus
de Basic. Après connexion, `https://vision.mrj.am/auth/mcp` permet de créer,
remplacer ou révoquer son token. Le token de contrôle a été révoqué ; aucun
secret permanent n’a été enregistré dans Git ou affiché dans les journaux.

Sources : `b389fb7002ba4bd62e9585b98a9d0a5b89c4b92d`,
[CI réussie](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35785539670).
[Préparation 35785801163](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35785801163),
[activation 35786083939](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35786083939),
commit opérateur `64ac2c7009c6295987db45a02956d4eee01d2fba`.

Génération active et par défaut :
`/nix/store/h4rv6sn1izf1hv53qihsgrvkg1hy0j28-nixos-system-nixos-26.05.8639.c5c4a43b0e80`.
Entrée NixOS :
`/etc/nixos/vps-infrastructure/mcp-b389fb7002ba4bd62e9585b98a9d0a5b89c4b92d/hosts/hostinger/logique.nix`.
L’ancienne génération `y35z1d3l6882ylrz7glrq7q7yp4zyks7` reste protégée.
Le retour autonome a été armé avant l’essai puis désarmé après les contrôles.

Seuls mrj-auth et Nginx ont été remplacés/redémarrés. Serveur Lisp, interfaces,
Matheval, Logique, données et versions Nixpkgs/PostgreSQL conservés. Vérifications :
32 contrôles HTTP/TLS, services et sauvegardes actifs, nouvelle connexion SSH
du runner, Basic/Bearer, initialize, cinq outils, notification, lecture MCP,
CSRF, refus hors MCP, rendu mobile/bureau, absence de stockage navigateur et
révocation. Les écritures MCP passent en PostgreSQL isolé dans la
[CI Vision 35785184379](https://github.com/MrJ-am/vision/actions/runs/35785184379).
Aucune fiche ou observation de test n’a été créée en production.

Détails : [VISION-MCP-TOKEN.md](VISION-MCP-TOKEN.md) ; preuve machine :
`operations/mcp-publication.json`. Le raccordement dans le compte Mistral du
propriétaire reste à faire avec le token qu’il générera ; aucun test dans son
compte Mistral n’est revendiqué.

## Correction Logique et interfaces communes

Logique et l'interface Vision sont publiés depuis le 22 septembre à 11:13 UTC.
La [préparation 35719822363](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35719822363)
et l'[activation 35720088997](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35720088997)
ont réussi sur les sources d'infrastructure
`273139f1e66e7284af185fde66bf442cf7c9da03`, CI `35719627664` réussie.
Le commit opérateur d'activation est `436b0019fd10f4ad37c0bc030511f568a80411b2`.

| Élément | Référence réellement servie |
|---|---|
| Logique | `615439c841db1934ffaddc1dee64c85ff6c56cf2` |
| Interface Vision | `dbf5fcb3b1c70ec8ee1717db8e17527619840245` |
| Matheval | `ebae2c9d358e4b76d120b85e12afb4193cc37967` |
| Style commun | `b2177c0fd2c46c6f528266d30f7b933d3add1566` |
| Signature | `17495b13cefa24473e37434b98336b27caec8cdf` |
| Serveur Vision inchangé | `151ab64bd5c9c5c54297e88dbe4d548343cc4928` |
| Génération active et par défaut | `/nix/store/y35z1d3l6882ylrz7glrq7q7yp4zyks7-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Génération précédente protégée | `/nix/store/bbp9i9c94l8f4lvkr23qlgghhlw29qdd-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |

[Logique](https://logique.echos.systems/?accueil=1) sert l'application avec son
vrai certificat. Les 80 ressources et le manifeste servi ont été vérifiés,
ainsi que quatre formats d'écran et les cinq lecteurs Vimeo réels. Les anciennes
adresses `/matheval/` sur ce domaine sont récupérées vers une URL distincte de la
racine anciennement mise en cache. Les hôtes inconnus sont refusés par Nginx.
Aucune intervention sur un éventuel domaine `logic.ecos.systems` n'est revendiquée.

Les 13 ressources et le manifeste de Vision correspondent à l'artefact testé.
Le rendu, les polices, deux formats, la connexion avec le compte existant,
le cookie, CSRF, l'origine, la lecture PostgreSQL, Basic et la révocation
ont été contrôlés sans écriture métier. Les captures ne montrent que la connexion vide.
Les 22 contrôles HTTP/TLS précédents, les six services, les deux sauvegardes
et une nouvelle connexion du runner ont réussi. Le retour autonome de vingt
minutes a été armé avant l'essai, puis désarmé après enregistrement du démarrage.
Les bases n'ont pas été restaurées ; les anciennes versions restent conservées.

Matheval est publié à 11:23 UTC par son
[workflow 35720485951](https://github.com/MrJ-am/M-moire/actions/runs/35720485951).
Les 56 tests Firefox/Chromium/tactiles et les 16 tests API PostgreSQL 17 ont
réussi, puis les 107 fichiers réellement servis ont été comparés à l'artefact.
Le service est actif et les accès administratifs anonymes sont refusés.
La migration additive des sessions accompagne cette version ; les réponses
collectées et l'ancien déploiement `9ad544dfc7ce546a851e01b6c8f9a2a8334ca616`
sont conservés. La version précédente ne serait restaurée que par retour
applicatif, sans restauration de la base.

L'entrée NixOS active importe
`/etc/nixos/vps-infrastructure/273139f1e66e7284af185fde66bf442cf7c9da03/hosts/hostinger/logique.nix`.
Ce point d'entrée complète `projects.json` avec `operations/logique-site.json`.
Conserver ce domaine, les routes Vision et le refus des hôtes inconnus dans
les prochaines générations : la configuration de base seule ne représente pas
cette publication. Toute nouvelle opération reprend l'état réellement actif.

Preuves durables : `operations/corrections-publication.json`,
[procédure](CORRECTIONS-SITES-20260922.md),
[audit de sécurité](AUDIT-AUTHENTIFICATION-20260922.md), registre de coordination.
Les états antérieurs ci-dessous sont conservés comme historique.

## Historique au 21 septembre

## Vision ElmUI : publiée et enregistrée le 21 septembre à 22:32 UTC

L'[activation nº 35663052741](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35663052741)
a réussi sur [vision.mrj.am](https://vision.mrj.am/), depuis le commit opérateur
`12d9765413501c9911728bc3ca7a9220b6325e9b`. Les 13 fichiers du manifeste sont
identiques à l'artefact applicatif testé. Chromium a vérifié le rendu à 375 et
1280 pixels, la police exacte, la connexion avec le compte permanent, le cookie
commun, CSRF et l'origine, la lecture PostgreSQL, Basic et la révocation.
Les captures conservées montrent uniquement la connexion vide.

| Élément | Référence active |
|---|---|
| Interface Vision | `9a4c395b24e6eb8938a3246c96f5d80c030c2d2d` |
| Style partagé | `c7b4d6e00cd0014a0a05e5a4e77627357498faa9` |
| Signature | `17495b13cefa24473e37434b98336b27caec8cdf` |
| Sources du candidat d'infrastructure | `d224ab32928c43ef7f9445804077a2dbfb0fdfba` |
| Génération active et par défaut | `/nix/store/bbp9i9c94l8f4lvkr23qlgghhlw29qdd-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Génération précédente protégée | `/nix/store/ppx3gxdx4rw36wah3wdz9lfdkl7z72ln-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Serveur Vision conservé | `151ab64bd5c9c5c54297e88dbe4d548343cc4928` — 1.3.0 |
| Matheval conservé | `0c2758f5a1df6821903a684e9a3c41f600acf02c` |

La [préparation nº 35662657824](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35662657824)
a conservé les sources et générations, produit les sauvegardes chiffrées des
deux bases, comparé les invariants, testé Nginx et déclenché le timer indépendant.
La [simulation complète nº 35662944719](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35662944719)
annonçait seulement le redémarrage de Nginx. La bascule a vérifié une nouvelle
connexion SSH, les six services, les deux timers de sauvegarde et les 22 contrôles
HTTP/TLS. La génération testée est enregistrée ; le timer de retour est désarmé.
Aucune écriture métier, migration SQL, rotation de compte ni mise à jour NixOS.

L'entrée NixOS importe
`/etc/nixos/vps-infrastructure/vision-interface-d224ab32928c43ef7f9445804077a2dbfb0fdfba/configuration-interface.nix`.
Elle assemble l'entrée antérieure et le nouveau module de fichiers statiques.
`/srv/vision-interface/current` pointe vers la révision applicative ci-dessus.
L'import `apps/vision-interface.nix` est également intégré à la configuration
principale du dépôt pour que les prochaines générations conservent cette desserte.
Les preuves et le mécanisme de publication sont décrits dans
[VISION-INTERFACE.md](VISION-INTERFACE.md).

**Relais pour Logique :** toute préparation calculée avant cette bascule utilise
une génération antérieure. La refaire depuis l'état actif et les sources intégrant
le module Vision, en conservant ses cinq routes ; ne pas réutiliser aveuglément
un ancien candidat ACME/HTTPS. La publication parallèle de Logique reste une
opération distincte. Aucun redémarrage du VPS n'a été effectué.

## Préparation Logique du 21 septembre : aucune activation à cette date

Le site `logique.echos.systems` est préparé sur `preparation/logique-vps`.
L'[audit nº 35637628338](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35637628338),
commit `ba66dfcf939f299f9a296658aeaab938366b719e`, a réussi à 18:19 UTC :
22 contrôles HTTP/TLS existants, DNS A `187.77.95.158` sans AAAA, générations
identiques et seconde connexion du runner. Aucun certificat Logique ni
publication au chemin alors contrôlé (`/srv/apprendre-a-demontrer/current`)
n'était présent ; le nouveau précontrôle examine aussi `/srv/logique/current`.

Le nouveau lot ajoute les candidats ACME puis HTTPS, les contrôles statiques
et une préparation distincte de toute activation, intégrée sur `main`.
L'archive applicative `10667157261`, révision `7a356ca3ec3682c95aa841c968822c24dc683dbe`,
a été vérifiée : ZIP et 75 fichiers `dist` conformes, ressources identiques
à la référence fonctionnelle initiale. La CI publique `35661154380` a réussi.
La [validation typographique privée nº 35661307369](https://github.com/MrJ-am/Signature/actions/runs/35661307369)
a également réussi : deux fontes originales, géométrie, huit contextes HTTP,
sélection et copier-coller natif, puis examen des captures à 320 et 1280 pixels.
Le rapport durable figure dans `operations/logique-typographie.json`.
L'archive de préparation exclut les fontes et reste non publiable ; le candidat
complet devra être contrôlé et conservé par le mécanisme privé collectif.
La [construction VPS nº 35659924636](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35659924636)
a réussi le 21 septembre à 21:57 UTC. Le commit opérateur
`d659dde6034056dac2be73519804ce2ee33cb436` a construit les sources testées
`e9a4ed68fa71a072ff0815d28e7e3ffd3e9517ae` avec le Nixpkgs déjà installé.
Les invariants sont identiques, Nginx ACME passe son test réel, les six services
et les deux timers restent actifs. Les 22 contrôles HTTP/TLS réussissent avant
et après, avec une nouvelle connexion du runner.
Le relevé final conserve exactement génération, profil, entrée et versions
Matheval/Vision ; certificat et publication Logique sont toujours absents.
Le rapport est conservé dans `operations/logique-construction.json` et sur
le VPS. Le retour est écrit et vérifié syntaxiquement, sans timer armé.
HTTPS attend son vrai certificat ; aucune bascule n'est effectuée.
La [CI nº 35656506154](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35656506154)
a réussi au commit `b722165485e9b3b325b150f05ae7da5919a57984` : 55 tests,
Nginx réel, évaluations NixOS complètes des deux phases et des invariants,
ainsi que PostgreSQL 17 et ses restaurations isolées.
Lire [LOGIQUE.md](LOGIQUE.md) pour les références, les preuves et les étapes restantes.

## Historique : Vision web et sessions mrj.am, 20 septembre

Vision 1.3.0 est **activé et enregistré depuis 22:32 UTC** sur
`https://vision.mrj.am/`. La [bascule nº 35541957332](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35541957332)
atteste la nouvelle génération après une nouvelle connexion SSH, six services
actifs, les deux timers de sauvegarde et 22 contrôles HTTP/TLS depuis le VPS,
puis 22 depuis le runner GitHub. La connexion web, CSRF, le refus anonyme,
la lecture PostgreSQL et la révocation de session ont réussi. Les identifiants
de sonde ont été retirés et les identifiants antérieurs conservés.

| Élément | Référence vérifiée le 20 septembre |
|---|---|
| Sources d'infrastructure installées | `d3699cd829bf996540a53085fe2c0539d9552ebc` |
| Sources Vision | `151ab64bd5c9c5c54297e88dbe4d548343cc4928` — version `1.3.0` |
| Répertoire installé | `/etc/nixos/vps-infrastructure/d3699cd829bf996540a53085fe2c0539d9552ebc` |
| Génération active et par défaut | `/nix/store/ppx3gxdx4rw36wah3wdz9lfdkl7z72ln-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Génération précédente protégée | `/nix/store/nndnndfac30p7rnwrxbk8sr6hljk5y5b-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Services actifs | `sshd`, `nginx`, `postgresql`, `matheval`, `vision`, `mrj-auth` |
| Sauvegardes quotidiennes actives | `postgresqlBackup-matheval.timer`, `postgresqlBackup-vision.timer` |
| Compte permanent | Activé le 21 septembre 2026 à 05:18 UTC ; accès API vérifié |

La [préparation nº 35541853819](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35541853819)
a contrôlé la génération, les invariants, les sauvegardes chiffrées des deux
bases et le retour complet de l'essai précédent. Nixpkgs, PostgreSQL, les
certificats et les paramètres de Matheval sont conservés. Le timer de retour
de cette bascule est désarmé après enregistrement ; les anciennes générations
et les preuves restent protégées. Aucun redémarrage du VPS n'a été effectué.

Lors de la bascule, le compte permanent n'était pas encore défini.
Le propriétaire a ensuite enregistré les deux secrets de compte dans
`vps-production`. Le [renouvellement nº 35564114945](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35564114945),
exécuté au commit `65cedea8e71c157aafdf341e6894d4185b5ed651`, a réussi le
21 septembre 2026 à 05:18 UTC : validation des secrets, installation du compte,
accès HTTPS authentifié à l'API et nettoyage des fichiers temporaires.
Le compte est commun au navigateur et à l'API générale ; le service de sessions
lit ce même fichier d'identifiants. Aucun secret n'est conservé dans ce rapport.
Les prochaines rotations suivent [VISION-WEB.md](VISION-WEB.md).
Le navigateur de la session Work reçoit encore une erreur 502 au 21 septembre ; le rendu
visuel n'a donc pas été vérifié depuis ce navigateur. Ce constat est distinct
des contrôles HTTP/TLS réussis sur le VPS et sur le runner GitHub.

La [CI d'infrastructure nº 35541763449](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35541763449)
et la [CI Vision nº 35540278729](https://github.com/MrJ-am/vision/actions/runs/35540278729)
ont réussi. Les fonctionnalités et les reprises des deux premiers essais
sont détaillées dans [VISION-WEB.md](VISION-WEB.md).

## Historique : migration du 18 septembre 2026

La migration de l'infrastructure est **activée et enregistrée depuis 21:10 UTC**.
Nginx, HTTPS, NixOS et PostgreSQL sont gérés par ce dépôt. Matheval conserve
son application, ses données, son schéma, ses publications et ses exports chiffrés.

## Références installées le 18 septembre

| Élément | Référence vérifiée |
|---|---|
| VPS | `187.77.95.158`, Hostinger `1982677` |
| Sources VPS installées | `fa059d61acfc8cf5c5bd7f3f9c83600787f2c6eb` |
| Commit opérateur de la bascule | `49d82f8167b8121fb03c7d95da02169bb6409e28` |
| Répertoire des sources | `/etc/nixos/vps-infrastructure/fa059d61acfc8cf5c5bd7f3f9c83600787f2c6eb` |
| Génération active et par défaut | `/nix/store/8cbhcffxr0xhybz2va6yz8rrxfgqgzy9-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Ancienne génération protégée | `/nix/store/5840x51nc7d2s7gw0zfyy6my47j6nh1i-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Nixpkgs conservé | `/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos` |
| PostgreSQL | `17.11`, données `/var/lib/postgresql/17`, socket `/run/postgresql`, aucune écoute TCP |
| Matheval pendant la bascule | `d8d0f17f37f030d58c152d5e57ca2e2c5b5814ea` ; version de l'API `0.3.0` |
| Matheval après le relais | `841317fb87c8f81867ad884ca19ef93e8308838b` sur `master` |

`/etc/nixos/configuration.nix` importe la configuration de l'hôte dans le
répertoire des sources installé. Le module Matheval est la copie exacte du
commit amont `0bcdaf101cbdacb85694ca217fd21ab3f2eac828`, SHA-256
`8959538472392c6bff39cf91e3eeaa125b6814f0af15d63381258a51baf20086`.
Sa provenance figure dans `vendor/matheval/source.json`. Le patch historique
n'est plus à appliquer. Vision reste un exemple, sans service ni base activés.

## Contrôles et sauvegardes

- [Audit final nº 35396774874](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35396774874),
  commit `30decc1ab1deb39cd147dd289bd6a836e7a6c925`, réussi à 21:26 UTC après
  la publication de Mémoire : génération active et par défaut attendue,
  entrée NixOS persistante, retour désarmé, anciennes générations protégées,
  quatre services actifs, PostgreSQL et ses droits conformes, version applicative
  `841317fb87c8f81867ad884ca19ef93e8308838b` et onze contrôles HTTP/TLS réussis.
- [Préparation nº 35395032430](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395032430) :
  sauvegarde des sources et de la base, construction avec le Nixpkgs installé,
  comparaison des invariants, restauration isolée et retour ciblé des ACL testé
  deux fois. Seules les unités Matheval, PostgreSQL et son provisionnement
  changent ; Nginx, le réseau, SSH, le noyau et les certificats sont conservés.
- [Plan nº 35395215119](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395215119) :
  précontrôle exécuté depuis systemd avec l'environnement explicite, dry-run
  limité à PostgreSQL et Matheval, déclenchement du timer indépendant vérifié.
- [Bascule nº 35395320446](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395320446) :
  essai sous verrou de publication avec retour à quinze minutes, nouvelle
  connexion SSH, services actifs, onze contrôles HTTP/TLS et empreintes publiques
  identiques, refus anonymes 401, connexions SQL autorisées/refusées vérifiées.
  Les lignes antérieures et l'identité du stockage PostgreSQL sont conservées.
  La sauvegarde locale a été déclenchée puis restaurée dans une instance isolée ;
  l'export chiffré hors VPS a réussi. La même génération a ensuite été enregistrée
  pour le démarrage, et le timer a été désarmé après validation.
- [CI VPS nº 35395320531](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395320531) :
  vingt tests Python, syntaxe Nix, évaluations NixOS, isolation PostgreSQL 17 et
  restaurations dans un conteneur jetable réussis.

Les copies chiffrées de migration sont conservées trente jours dans les artefacts
[avant](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395032430/artifacts/10567635113)
et [après](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395320446/artifacts/10567442831).
Les sauvegardes locales quotidiennes restent dans `/var/backup/postgresql`.
Le workflow Mémoire conserve son export chiffré quotidien et sa rétention de
quatorze jours ; la clé privée age reste hors du VPS et hors Git.

Le dossier privé `/root/vps-migrations/fa059d61acfc8cf5c5bd7f3f9c83600787f2c6eb/`
conserve `etc-nixos-before.tar`, `configuration.nix.before`, `rollback-acl.sql`,
les sauvegardes privées et `committed.json`. Les racines de GC sous
`/nix/var/nix/gcroots/vps-migrations/fa059d61acfc8cf5c5bd7f3f9c83600787f2c6eb/`
protègent l'ancienne génération, le candidat, Nixpkgs et Python.

Le retour autonome de l'essai est volontairement inopérant après enregistrement.
Un retour ultérieur doit faire l'objet d'une nouvelle opération VPS, après
examen des changements intervenus depuis. Ne pas restaurer un dump de production
pour revenir à une configuration ; le retour NixOS ne restaure pas les droits SQL.

Aucun redémarrage du VPS n'a été effectué. Le profil et le menu de démarrage
sont enregistrés ; le comportement après un redémarrage réel reste un contrôle
distinct à planifier dans une fenêtre appropriée.

## Relais Mémoire

Les consignes, le contrat et les références du serveur ont été actualisés au
commit `3896f94bd129a197c904c08e5544108b5c0a7c68`, dans la
[PR nº 8](https://github.com/MrJ-am/M-moire/pull/8). Elle inclut le déclenchement
du workflow de sauvegarde existant par `deploy/backup-request.json` sur `master`,
avec le compte `matheval-deploy` et les secrets existants. La
[CI de la PR](https://github.com/MrJ-am/M-moire/actions/runs/35395609673) a réussi,
dont quatorze tests API et trente-deux tests navigateur. La PR est fusionnée
sur `master`, commit `841317fb87c8f81867ad884ca19ef93e8308838b`.

La [sauvegarde Mémoire nº 35396161367](https://github.com/MrJ-am/M-moire/actions/runs/35396161367)
a réussi depuis `matheval-deploy` après la bascule, et son artefact chiffré
`matheval-backup-35396161367` est disponible jusqu'au 2 octobre 2026.
La [publication applicative](https://github.com/MrJ-am/M-moire/actions/runs/35396161100)
a réussi sur `master` : tests, déploiement avec `matheval-deploy` et comparaison
des fichiers servis avec le manifeste de la version vérifiée. L'intégration
de Mémoire est terminée ; ses publications ne reconstruisent pas NixOS.

## Accès et reprise de la tentative interrompue

Depuis ChatGPT Work, **toutes les opérations VPS passent par GitHub Actions**.
Work ne dispose pas de connexion SSH directe. L'environnement `vps-production`
contient la clé administrative existante, enregistrée avec l'autorisation du
propriétaire, et autorise uniquement la branche `main`, sans tag. Les workflows
applicatifs conservent leur compte de publication sans accès root général.

La première tentative [nº 35351617482](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35351617482)
a échoué avant l'activation : son service systemd ne recevait pas `NIX_PATH`.
Le retour a rétabli l'ancienne génération mais n'a pu lire le fichier SQL privé
sous le compte `postgres`. L'[audit de reprise](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35394636820)
a confirmé l'ancienne génération, les anciens droits, les quatre services actifs
et onze contrôles publics réussis. Aucune activation du candidat n'avait eu lieu.

Les corrections fixent l'environnement du service et font ouvrir le fichier
SQL par root avant de le transmettre à `psql`. La première reprise de l'unité
ancienne a constaté qu'elle avait été collectée par systemd ; une nouvelle unité
a exécuté le [retour complet nº 35394938751](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35394938751)
avec succès, droits SQL et contrôles publics compris. La nouvelle préparation
puis la bascule réussie ci-dessus utilisent un dossier distinct. Les preuves
de l'ancienne tentative restent conservées sous son identifiant `088d36c15f2f…`.


## Vision 2.4 — 27 septembre 2026

Vision serveur et interface : `d5d6217b95b7548af7b7ed9009321a413f1c998b`, candidat VPS `be2b7fdd81a64b2f7aea02da106401da93789e68`. Préparation 36338925947, activation 36338989951, constat après finalisation 36339153877 réussis. Migration 013/014, états mémoriels et une séance ouverte préservés ; retour inactif, NixOS inchangé. Détails et incident corrigé dans [VISION-REFONTE.md](VISION-REFONTE.md) et [le rapport](../operations/vision-refonte-publication.json).
