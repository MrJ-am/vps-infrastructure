# Reconnexion Vision depuis ChatGPT

## Constat du 19 octobre 2026 — incident encore ouvert

La vidéo Android montre le consentement Vision puis le retour à la fenêtre
« Reconnecter Vision ». Le correctif du 14 octobre est toujours exécuté : le
binaire actif possède la même empreinte SHA256, et les 29 clients historiques
sont conservés. À l'heure de la vidéo, les codes ont été échangés contre de
nouveaux jetons ; aucune demande ni aucun code ne reste en attente. Cela ne
prouve pas que l'application mobile a repris l'appel avec ces nouveaux jetons.

Deux appels réels en lecture seule depuis le connecteur ChatGPT distinguent les
étapes : `tutoriel` dépasse le délai à 21:14 UTC, tandis que `lire_politique`
réussit à 21:18 UTC. Les traces montrent une erreur JSON-RPC `parse_error` pour
le premier, et `tools/call result=ok` pour le second, après authentification
HTTP réussie dans les deux cas. Aucun contenu métier n'est publié dans les
diagnostics ; seuls des comptes, statuts, minutes et empreintes sont conservés.

Une cause du délai est reproduite localement avec Vision `a3cb6be` et SBCL 2.6.4 :
le serveur commun ne définit pas `VISION_PUBLIC_MCP_URL`. Le tutoriel essaie
d'encoder `NIL` dans son résultat ; la gestion d'erreur renvoie alors
`-32700 / id:null` malgré une requête valide avec un identifiant. Avec l'adresse
configurée, le même appel réussit et conserve son identifiant. Cette reproduction
explique l'échec du tutoriel ; son lien avec la boucle de la vidéo reste à établir.

Le correctif source `c3adad9` transmet l'adresse publique depuis la configuration
Nix au serveur commun. La suite `vision-configuration-mcp` évalue ce véritable
environnement puis exécute le tutoriel dans une image SBCL propre, sans base ni
contenu de production. Elle échoue sur l'ancien module et passe sur le correctif.
Les 7 tests de confidentialité/agrégation du diagnostic, les 22 tests de
l'assembleur et les 4 tests de sélection d'impact passent également.

**Le correctif de configuration n'est pas déployé.** Le
[diagnostic 39327919219](https://github.com/MrJ-am/vps-infrastructure/actions/runs/39327919219)
constate une génération active `lddfg6bb` et une génération enregistrée `jzvmg8sf`,
avec sept unités différentes, dont Nginx. L'entrée enregistrée importe la
configuration Nextcloud Contacts du 17 octobre. Les préconditions existantes de
sauvegarde et de promotion exigent une référence cohérente ; ne pas effacer cet
écart, rejouer l'ancienne promotion ou activer ces autres changements avec le
correctif Vision. Aucun déploiement, aucune réinitialisation de jeton ou de compte,
ni aucune écriture de contenu métier n’a été effectué ici.

La vérification Android demandée reste en attente : fermer le dialogue, ouvrir
une nouvelle conversation texte avec Vision et demander la lecture des réglages.
Une lecture réussie dans ce fil ne prouve pas la reprise du dialogue mobile.
Preuve synthétique : `operations/mcp-reconnexion-diagnostic-20261019.json`.

## Incident du 14 octobre 2026

Depuis une conversation audio ChatGPT, le bouton « Se reconnecter » ouvre son
navigateur intégré et affiche immédiatement `{"error":"invalid_request"}`.
Le navigateur et l'URL exacte de l'incident ne sont pas connus. Ne pas collecter
de code OAuth, cookie, jeton ou URL complète pour compléter ce constat.

Le [diagnostic central en lecture seule](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38541683112)
retrouve les 29 clients historiques dans le registre actif. Il ne reproduit pas
la perte du registre corrigée le 13 octobre. Il ne permet pas d'attribuer avec
certitude cet incident à une requête précise.

Une cause compatible est reproduite sur les sources antérieures : le cookie
Vision existe encore, mais le jeton Native est inactif et son renouvellement
renvoie `invalid_grant`. `session-digest` levait alors une erreur 401, convertie
par le transport en `invalid_request`, avant toute redirection vers Log.

## Comportement corrigé

- Une session absente, expirée ou définitivement révoquée reprend la connexion,
  en conservant la demande OAuth, son état et son challenge PKCE.
- Une panne d'introspection ou de renouvellement retourne 503 avec
  `temporarily_unavailable` et `Retry-After`, et conserve la session.
  Elle n'est pas assimilée à une révocation ou à une requête invalide.
- Chaque connexion possède son cookie de transaction ; deux onglets ne
  s'écrasent plus. Un retour déjà commencé avec l'ancien cookie reste accepté.
- L'absence de `scope` sélectionne l'unique portée annoncée ; une portée
  explicitement étrangère reste refusée.
- Un grant expiré, révoqué ou déjà consommé est signalé au client par
  `invalid_grant`, afin qu'il demande une nouvelle autorisation.
- Le consentement cesse d'afficher « Enregistrement » après une erreur. Une
  reprise explicite est proposée après expiration ou perte de réponse, avec
  nouvelle vérification de session et nouvelle décision. Aucun consentement
  n'est accordé automatiquement.

## Preuve automatisée

`tests/mcp-reconnexion-serveur.lisp` charge une image SBCL propre et le serveur
HTTP livré. Les tests traversent TLS, le parseur HTTP, les routes Log, SQLite,
les signatures ES256, les contrôles de session/CSRF/PKCE, le consentement Elm
compilé, l'échange OAuth et les méthodes MCP `initialize`/`tools/list`.
Ils n'écrivent aucune fiche ni séance pédagogique.

Le fournisseur OIDC et la page de retour ChatGPT sont des doubles explicites.
Leur rôle est de provoquer les expirations, révocations, pannes et réponses
perdues. Aucune fonction applicative d'authentification n'est remplacée. Le proxy
de test n'accepte que trois noms, tous reliés à la boucle locale. Les bases,
clés et comptes synthétiques sont éphémères.

| Famille | Cas vérifiés |
| --- | --- |
| État de connexion | Profil neuf, session Vision valide, session Log seule, session locale expirée, accès Native expiré avec renouvellement valide, renouvellement révoqué |
| Cookies et fenêtres | Cookies inconnus/malformés/dupliqués, cookies effacés au retour, ancien cookie de transaction, deux onglets ouverts avant connexion avec retours inversés |
| Consentement | Autoriser/refuser au clavier, double clic, rechargement/retour arrière, demande expirée, session expirée pendant la décision |
| Réseau | Erreur avant envoi, réponse perdue après écriture réelle, fournisseur indisponible puis rétabli, introspection incomplète, renouvellement 400/401/429/500/503 |
| OAuth/MCP | Portée omise, état Unicode et encodé, PKCE, code à usage unique, six échanges concurrents, rotation et rejeu du renouvellement, révocation de famille, déconnexion, redémarrage avec base conservée |
| Refus nécessaires | Mauvais compte, compte désactivé, CSRF/origine étrangers, mauvais client, mauvais retour/audience, paramètres dupliqués ou mal encodés, transaction expirée/rejouée |

Les 24 tests HTTP et les 16 parcours exécutés dans chacun des trois moteurs
forment 72 tests, avec des sous-cas supplémentaires. Les parcours commencent
avec des contextes isolés et incluent des dimensions mobile et bureau ; Firefox
utilise un viewport étroit sans émuler un système mobile. Les cookies réels et
l'absence de connexion supplémentaire lorsqu'une session suffit sont vérifiés.

Quatre régressions échouent sur l'ancienne révision infrastructure
`ff303d8ebb640ee9c47b68ae3a6d3e140631a98c` : ancien cookie avec renouvellement
révoqué, portée omise, transactions parallèles et panne d'introspection. Ce
contrôle utilise les anciennes définitions applicatives dans une image propre.

## Commandes locales

Dans l'atelier central outillé conformément à `assemblage/DEVELOPPEMENT.md`,
construire le candidat exact puis lancer la suite :

```sh
python3 scripts/frontends.py construire --composant vision
python3 scripts/assemblage.py tester --suite mcp-reconnexion
```

La suite exige le candidat Vision du manifeste, les trois moteurs, SBCL,
OpenSSL, curl, libcrypto, SQLite et le profil Python `navigateur` verrouillé.
Elle vérifie la provenance par l'assemblage et ne réutilise pas un ancien reçu.
Un moteur absent ou un test en échec arrête la commande ; aucun fallback, skip
ou retry automatique. Elle est sélectionnée quand l'identité, le transport ou
le consentement Vision changent. Aucun workflow au push n'est ajouté.

Pour reproduire hors de l'atelier Nix, avec une interface déjà compilée :

```sh
python scripts/mcp-reconnexion-qualifier.py --interface /chemin/vision/interface/dist
```

Ce Python doit contenir Playwright 1.61.0. Les variables `CHROMIUM`,
`PLAYWRIGHT_NODEJS_PATH`, `MRJAM_LIBCRYPTO`, `MRJAM_LIBSQLITE` désignent les outils
locaux. Les adaptations explicites `SBCL`, `MRJAM_CHARGEUR_TESTS` et
`WEBKIT_EXECUTABLE` sont permises pour cette reproduction, mais refusées par
`--candidat`. Elles ne constituent pas une qualification de promotion.

La reproduction du 14 octobre utilise SBCL 2.6.4, Chromium 154.0.8037.57,
Firefox 151.0 (révision Playwright 1532), WebKit 26.5 (révision 2311) et
Playwright 1.61.0. WebKit utilise son binaire verrouillé avec un lanceur local
qui lui fournit les bibliothèques système manquantes. Les sources OIDC ont été
vérifiées contre les empreintes verrouillées. Elm a été compilé avec le style
exact du composant, contrôlé par les règles centrales elm-review sans
suppression, puis testé dans les navigateurs.

## Limites et vérification sur appareil

Cette matrice ne prouve pas le comportement de toutes les versions de
navigateurs, de Safari iOS, d'Android WebView ou de l'application ChatGPT. Elle
ne remplace pas `log-parcours` avec Kanidm réel. Les refus de sécurité et les
pannes externes doivent rester des refus ou erreurs récupérables, jamais des
connexions accordées pour faire passer un test.

Après promotion du même artefact qualifié, vérifier sur iPhone et Android :
conversation audio → demande de séance → « Se reconnecter » → navigateur
intégré → connexion/consentement → retour à la conversation → appel Vision.
Répéter avec session existante et session expirée ; constater seulement
l'étape, l'OS/version, l'heure, le statut et la réussite de l'appel, sans
exporter les URL ni les secrets. Un appel de catalogue suffit pour la sonde
automatique ; aucune séance fictive en production.

À l'étape de reproduction initiale, aucun déploiement n'était attesté. La
promotion ci-dessous est maintenant constatée ; l'essai ChatGPT sur appareil
reste distinct des tests automatisés.


## Qualification du candidat de production — 14 octobre 2026

Le candidat Nix `v2zss0pfglkl8ba1g6lwxwkx5az29jbq-mrjam-metier-fb5b7e217822`
est construit une seule fois (SHA256
`2e72ea810fb58f75441fe0c9493c5072b91d4939bdff379f4878e4e1c324f0df`).
Ses 40 tests réels HTTP/PostgreSQL passent. Vision `a3cb6be` est construit par
`frontends.py`, elm-review central sans suppression ; ensemble
`c1072e9e8d93267a42ba8a43ca60104d990399a6634dc2ce19735132ae54eebb`.
Les 72 parcours passent sur ce candidat frontend avec les outils Nix canoniques,
le profil Python verrouillé et WebKit original, sans lanceur de remplacement.
Le profil Debian13-x64 sélectionne explicitement la révision WebKit2311 ; une
variante incompatible ou forcée est refusée et les moteurs sont empreintés.

`mcp-reconnexion-native` complète cette matrice : Kanidm1.11.2 exact de production,
export chiffré par la CI existante et empreinte NAR vérifiée, serveur local isolé,
MFA initiale, SSO sans formulaire, pages déjà connectées, ancienne session Vision,
client historique et nouveau consentement PKCE. Processus Lisp propre ; aucune
qualification en image persistante n'est revendiquée.

`mcp-reconnexion-promotion` vérifie l'évaluation Nix comparative et le retour sans
restauration des bases. Le changement se limite au binaire et au document Vision,
sans changement de configuration Native, PostgreSQL ou des autres sites. Un port
supplémentaire fait échouer les invariants. Le canal central reçoit le même NAR,
compare ses empreintes et refuse une production différente. Avant bascule :
sauvegarde actuelle chiffrée, restauration isolée, timer indépendant réellement
exercé ; après : ressources HTTPS, MCP anonyme401, découverte200, clients OAuth,
invariants métier et persistance après redémarrage. Retour du code uniquement.
Les commandes fermées sont `reconnexion-preparer`, `reconnexion-deployer`,
`reconnexion-diagnostic` et `reconnexion-retour` dans le workflow central.


## Production constatée

Activation le14octobre2026 à15:29:58UTC, génération
`az22hgl8xp9sab6incdcnhbj7ljang78-nixos-system-nixos-26.05.8639.c5c4a43b0e80`.
[Préparation38589166917](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38589166917),
[déploiement38589625866](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38589625866)
et [diagnostic38589943881](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38589943881)
réussis. Binaire et site correspondent aux empreintes qualifiées ci-dessus.
Les29clients OAuth restent identiques après activation et redémarrage, de même
que les données métier ; Native, PostgreSQL et services tiers sont préservés.
La sauvegarde actuelle a été déchiffrée et restaurée dans un cluster isolé avec
empreintes identiques. Le témoin de retour indépendant fonctionne. Aucun compte,
consentement ou contenu fictif n'a été créé en production.

Le document et le JavaScript publics ont aussi été téléchargés depuis l'atelier :
leurs empreintes correspondent au candidat. La preuve synthétique est conservée
dans `operations/mcp-reconnexion-production.json`. Ces sondes ne prétendent pas
exécuter une conversation audio dans l'application ChatGPT.

[Référence38590095562](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38590095562)
réussie : génération active et démarrage identiques, serveur métier RSS180.7Mio,
cgroup avec cache172.1Mio. Les latences de dix lectures publiques par route
sont conservées dans la preuve ; elles ne mesurent pas un appel authentifié ni
le réseau du téléphone.
