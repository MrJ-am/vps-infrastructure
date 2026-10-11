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

L'entrée cible utilise un socket Unix 0660, répertoire 0750 et SO_PEERCRED :
seul l'UID Nginx configuré peut envoyer une requête. Nginx impose les en-têtes de
service et d'identité après `auth_request`, sans reprendre ceux du navigateur.
`tests/serveur-artefact.py` refuse un autre UID portant des en-têtes forgés.
L'évaluation Nix vérifie le routage et les permissions de la configuration cible ;
la chaîne Nginx/IdP réellement activée reste à qualifier. Un Nginx compromis fait
partie de cette frontière de confiance, comme le monolithe compromis. Les
campagnes hostiles restent en environnement isolé, jamais sur les données réelles.

Preuves locales Matheval : `tests/matheval-composant.mjs` exécute le serveur Node
de référence et le composant Lisp sur deux bases indépendantes PostgreSQL 17.
Le rôle applicatif est non propriétaire, NOSUPERUSER/NOCREATEROLE/NOBYPASSRLS.
40 parcours comparent les contrats et les empreintes ; le test Lisp ajoute une
course de révision, huit retransmissions concurrentes et un secret étranger.
`tests/native-differentiel.mjs` compare SHA-256/scrypt et 8003 cas JSON binaire64 à
Node. Elles sont complétées par `tests/vision-sql-native.py` : RLS Alice/Bob, liens
croisés, contexte transactionnel et rôles auxiliaires réels sur PostgreSQL isolé.
Le déploiement complet et la chaîne réelle d'identité restent à qualifier.
Les buffers de paramètres SQL et de scrypt sont effacés avant libération ; les
chaînes Lisp d'entrée peuvent demeurer jusqu'au GC. Aucune promesse de purge
générale du tas ou de résistance à une compromission du processus n'en découle.

Auxiliaires : tokens de consentement à usage unique et durées bornées, refus de
rattachement à un profil IdP non vérifié, contrôle parental/manual conservé.
Les suppressions attendent le registre accepté ; retirer une identité IdP pour
la migration reste distinct de ces fonctions de fermeture personnelle.
`tests/courriel-smtp.py` vérifie STARTTLS/CA/hostname avant AUTH ; aucune
localisation certaine ni garantie de livraison finale ne découle d'un relais SMTP.
Age et restauration : run central 38105867103 sur eff80b8, données de production
copiées en READ ONLY puis restaurées dans un cluster Unix privé. Empreintes
sémantiques identiques ; mauvaise clé refusée, clé éphémère enveloppée pour le
destinataire déjà configuré, aucune clé personnelle utilisée. Le rapport
`sauvegarde-transition.json` distingue données, ACL/rôles et retour applicatif.
Les deux derniers restent à qualifier pour l'assemblage commun.

L'approbation manuelle utilise la migration Vision 026 et la même entrée
administrative ; SQL revalide actif/administrateur et conserve le verrou jusqu'à
l'écriture SQLite. La file courriel ne constitue pas une autorisation. Les calculs
scrypt sont limités à deux simultanés pour borner les allocations ; HTTP 503 si
le budget est épuisé. Cette borne n'est pas une mesure RSS de production.

`tables-privees.json` classe les 30 tables Vision et les 6 tables Matheval.
`scripts/verifier-tables.py` compare la liste effective, les propriétaires, RLS
forcée/politiques, droits de tables et colonnes et appartenances aux rôles élevés.
Toute table nouvelle est refusée sans classification. Les anciennes tables Vision
sans `utilisateur` n'ont aucun droit direct applicatif ; les métadonnées d'identité,
d'admission et de cycle passent par les fonctions bornées. Le compte courant
utilise RLS. Matheval conserve le schéma pseudonyme : autorisation par secret de
reprise et session scientifique, sans assimilation au propriétaire Log. Son rôle
SQL dispose des droits de collecte nécessaires ; une compromission de ce rôle
ne permet pas de promettre une isolation de participations par RLS inexistante.
Cette limite est distincte de l'isolation contrôlée par les parcours HTTP.
La fixture réelle PostgreSQL vérifie l'inventaire et les parcours Alice/Bob ;
six régressions refusent les omissions de table, RLS, politique, classe ou rôle,
les droits supplémentaires et l'héritage privilégié.

Les limites Matheval gardent les fenêtres historiques 30/h, 300/min et 8/15 min
(activation et connexion partagées), en-têtes draft-8 et Retry-After. L'adresse
est imposée par Nginx sur l'entrée Unix vérifiée ; IPv6 est regroupé par /56,
comme le middleware Node verrouillé. Origine et JSON sont contrôlés avant le
budget. Table bornée à 4096 entrées, verrou par serveur, horloge monotone et
HTTP 503 à saturation ; un redémarrage réinitialise ces seuls budgets en mémoire.
Les sessions et apprentissages restent durables en SQL/SQLite.
