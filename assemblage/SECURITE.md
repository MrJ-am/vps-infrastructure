# Contrat de sécurité v1 — qualification en cours

Aucune conformité ASVS globale revendiquée. Les règles ci-dessous distinguent
la cible du mécanisme actuellement actif ; chaque preuve doit identifier code,
environnement et assemblage. Références officielles consultées le 11 octobre 2026 :
[ASVS 5](https://owasp.org/www-project-application-security-verification-standard/),
[RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html),
[OIDC Core errata 2](https://openid.net/specs/openid-connect-core-1_0.html),
[PostgreSQL 17 RLS](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).
La qualification Kanidm utilisera la documentation de la version retenue.

| Règle | Nature et source | Application et preuve attendue |
|---|---|---|
| Identité vérifiée avant tout accès privé | Normative OIDC §3.1.3.7 et OAuth BCP ; choix produit refus par défaut | Signature, issuer/audience, state/nonce/PKCE, expiration ; test réel IdP, identité forgée refusée |
| Autorisation par ressource/opération | Exigence mission ; ASVS contrôle d'accès | Fonctions métier, RLS/contraintes, Alice/Bob lectures/écritures/liens/caches/exports/tâches concurrents |
| Rôle SQL non propriétaire et non privilégié | Mission ; limite PostgreSQL RLS | Inventaire rôles/propriétaires/politiques ; tables privées classées, SQL isolé hostile et multi-comptes |
| Contexte borné à la transaction/requête | Mission ; PostgreSQL SET LOCAL | Établissement depuis identité vérifiée, transaction, réutilisation connexion Alice puis Bob, refus par défaut sans contexte |
| Recherche isolée avant candidats et dérivés | Mission, confidentialité/intégrité | RLS avant recherche vectorielle/texte et propriétaires des préparations ; tests multi-comptes |
| Sessions durables, révocation effective | Produit/OAuth BCP | Stockage hors tas, expiration/inactivité/rotation ; tests redémarrage, suspension/révocation/OAuth/MCP avec borne mesurée |
| Aucun secret en source/artefact/log | Mission ; ASVS gestion des secrets | Secrets acquis au démarrage, build propre, inspection bornée des artefacts, sentinelles synthétiques hors production |
| Propriétaire métier stable | Produit mission | Association explicite issuer/sub au compte métier ; aucun rattachement email, aucun hook d'effacement lors du retrait IdP |
| Matheval pseudonyme et résultats scientifiques | Produit mission | Secret de reprise indépendant, permissions dédiées résultats, zéro distinct de null, transactions/idempotence/conflits |
| Retour sans écraser données récentes | Mission exploitation | Sauvegarde restaurée en isolation, retour code/ACL ciblé, invariants avant/après et redémarrage réel |

Un `SET LOCAL vision.utilisateur` ne prouve pas l'authentification face à du SQL
arbitraire. Le rôle Vision peut établir ce contexte après vérification à l'entrée ;
une compromission du monolithe partage le niveau de confiance des bibliothèques.
Les packages Lisp et une variable SQL ne créent pas de frontière contre cette
compromission. Les droits SQL limités et les contraintes protègent les parcours
normaux et réduisent les capacités, sans promettre une isolation des bibliothèques
compromises entre elles. Le monolithe ne reçoit jamais l'administration globale IdP.

L'interface locale actuelle par en-têtes Nginx doit être qualifiée et remplacée
par une entrée effectivement bornée (socket Unix avec accès restreint ou preuve
authentifiée) avant le passage du monolithe. Aucun simple en-tête falsifiable ne
sera assimilé à une vérification. Les campagnes hostiles restent en environnement
isolé, jamais sur les données réelles.

Preuves locales Matheval : `tests/matheval-composant.mjs` exécute le serveur Node
de référence et le composant Lisp sur deux bases indépendantes PostgreSQL 17.
Le rôle applicatif est non propriétaire, NOSUPERUSER/NOCREATEROLE/NOBYPASSRLS.
39 parcours comparent les contrats et les empreintes ; le test Lisp ajoute une
course de révision, huit retransmissions concurrentes et un secret étranger.
`tests/native-differentiel.mjs` compare SHA-256/scrypt et 8003 cas JSON binaire64 à
Node. Ces preuves ne qualifient ni l'isolation Vision ni le déploiement complet.
Les buffers de paramètres SQL et de scrypt sont effacés avant libération ; les
chaînes Lisp d'entrée peuvent demeurer jusqu'au GC. Aucune promesse de purge
générale du tas ou de résistance à une compromission du processus n'en découle.
