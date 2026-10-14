# Reconnexion Vision depuis ChatGPT

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
- Une panne d'introspection ou de renouvellement retourne 503 et conserve la
  session. Elle n'est pas assimilée à une révocation.
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

Au moment de cette correction, la matrice est locale : aucun déploiement ni
essai sur l'application ChatGPT réelle n'est attesté par ces tests.
