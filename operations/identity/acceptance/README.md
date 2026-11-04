# Acceptation indépendante du broker Log natif

Ces tests sont définis depuis les contrats publics historiques épinglés dans
`contract.json`, avant toute lecture ou exécution du candidat Rust. L'agent qui
les a écrits est distinct de l'agent d'implémentation. `frozen-tests.json` conserve
les empreintes du banc avant son premier passage sur le candidat.

Le banc crée exclusivement des données inventées : PostgreSQL temporaire sans
écoute TCP, schéma SQLite historique vide puis politiques de deux sujets fictifs,
CA locale temporaire, serveur OIDC TLS et jetons signés ES256. Aucun compte,
secret, certificat, cookie ou état de production n'est utilisé. Les seuls noms
réels apparaissant dans les protocoles sont les audiences et l'émetteur exigés
par le contrat ; les connexions du banc vont au loopback et au socket temporaire.

## Exécution

Lancer sous un utilisateur non privilégié, dans l'environnement de qualification
isolé retenu par l'opérateur. Python 3 avec sa bibliothèque standard, OpenSSL 3 et
les binaires PostgreSQL sont nécessaires. Le candidat reçoit seulement
`serve --config /chemin/absolu/config.json`, sans secret en argument ni variable
d'environnement. Les chemins du candidat et des outils doivent rester accessibles
dans cet environnement. Le lancement du banc n'établit pas lui-même une isolation
du programme candidat : le confinement externe reste requis.

```sh
python3 -B selftest_fixture.py \
  --postgres-bin /nix/store/POSTGRESQL/bin \
  --openssl /nix/store/OPENSSL/bin/openssl

python3 -B acceptance.py \
  --binary /nix/store/CANDIDAT/bin/mrjam-identity \
  --postgres-bin /nix/store/POSTGRESQL/bin \
  --openssl /nix/store/OPENSSL/bin/openssl \
  --output /chemin/nouveau/acceptance-001.json
```

Un chemin de résultat existant est refusé : conserver chaque premier échec et
utiliser un nouveau nom pour les passages suivants. Le reçu fournit les cas en
échec et les empreintes exactes du candidat et des sources de test. Il ne contient
pas les réponses ni les jetons. Les diagnostics détaillés de `unittest` utilisent
seulement les données inventées ; les conserver dans l'environnement de
qualification. Les bases et clés temporaires sont supprimées après les tests.

Le processus PostgreSQL est local, temporaire et lancé par le même utilisateur.
Son authentification Unix `trust` sert uniquement à ce banc synthétique ; elle
ne représente pas le contrôle `peer` de production. Le rôle `vision_identite`
est sans privilèges administrateur et ne peut lire directement la table des
principaux. Il peut seulement appeler la fonction métier convenue.

## Couverture figée

| Cas | Comportement contrôlé |
| --- | --- |
| 01 | Adoption du schéma et des politiques SQLite existants, sans création implicite quand l'état manque. |
| 02–05 | Refus anonyme et des faux en-têtes d'identité ; connexion ES256 positive ; séparation Vision/Audition ; PKCE serveur, cookies liés au navigateur, onglets concurrents, usage unique. |
| 06–08 | Mauvais issuer/audience/azp/nonce/signature/dates/at_hash ; JWK injectée et JSON ambigu ; JWKS privée ou kid dupliqué ; consommation durable avant panne et retour simultané. |
| 09–11 | Raccordement métier par issuer et sujet immuable ; retrait des droits et changement de nom ; CSRF et Origin ; administration avec politique MFA qualifiée et fraîcheur signée. |
| 12–15 | Pannes et réponse tronquée distinctes d'une révocation ; renouvellement signé et sujet constant ; déconnexion locale malgré panne, autre session préservée. |
| 16–20 | Métadonnées MCP par audience ; redirects HTTPS ; consentement lié à la session et CSRF ; refus ; PKCE/client/redirect ; code à usage unique ; rotation, rejeu et révocation familiale ; déconnexion du parent. |
| 21–22 | CA non fiable, redirection du fournisseur, en-têtes/formulaires/JSON ambigus, limites de corps et retours dangereux. |
| Tous | Absence de secrets natifs et de sujets dans les réponses ; absence de secrets dans les diagnostics ; aucun jeton client ou binding dans les erreurs. |

`selftest_fixture.py` comporte six contrôles indépendants du candidat : signature
vérifiée par OpenSSL, TLS/SNI et CA, PKCE et authentification des endpoints,
rotation/révocation, permissions PostgreSQL et ambiguïtés réellement produites.

## Limites explicites

Un passage vert ne qualifie ni une instance Kanidm réelle ni le SSO de production.
Le consentement est exercé par HTTP, sans interface graphique ni authentificateur
humain. La présence de `minimum=mfa` dans SQLite simule une décision opérateur :
elle ne démontre aucun enrôlement réel. Ce travail ne crée aucune politique
protégée dans la forge et n'accorde aucune approbation de déploiement.

Le banc ne qualifie pas l'isolation système, Nginx, PostgreSQL de production,
les sauvegardes, la reprise après crash/panne disque, la charge, les limites de
trafic ni une bascule réelle. L'adoption d'une session historique déjà active
sur disque n'est pas exercée ; l'adoption du schéma et des politiques est vérifiée.
Les invitations, l'inscription, les changements de politique opérateur, la page
de compte Kanidm, la compatibilité de l'ancien cookie transactionnel et la route
`/auth/revoquer-autres` restent hors couverture de ce premier banc. Les variations
cryptographiques exhaustives et l'expiration temporelle réelle des jetons MCP
restent également à qualifier séparément.
