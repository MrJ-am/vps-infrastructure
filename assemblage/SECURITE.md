# Contrat de sécurité v2 — jalons de production et preuves ciblées

Aucune conformité ASVS globale revendiquée. Les règles ci-dessous distinguent
la cible du mécanisme actuellement actif ; chaque preuve doit identifier code,
environnement et assemblage. Références officielles consultées le 11 octobre 2026 :
[ASVS 5](https://owasp.org/www-project-application-security-verification-standard/),
[RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html),
[OIDC Core errata 2](https://openid.net/specs/openid-connect-core-1_0.html),
[PostgreSQL 17 RLS](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).
Kanidm1.11.2 est retenu : [support](https://kanidm.github.io/kanidm/stable/support.html),
[politiques](https://kanidm.github.io/kanidm/stable/accounts/account_policy.html).
Ces documents et le code officiel verrouillé ont été consultés le12octobre2026.
L'installation et la bascule Native sont attestées dans
[qualification-production-20261013.json](kanidm/qualification-production-20261013.json).
Les contrôles techniques ne prouvent pas une connexion personnelle effectuée.
Le jalon1 et ses limites sont attestés dans
[qualification-production-etape1.json](qualification-production-etape1.json).

| Règle | Nature et source | Application et preuve attendue |
|---|---|---|
| Identité vérifiée avant tout accès privé | Normative OIDC §3.1.3.7 et OAuth BCP ; choix produit refus par défaut | Signature, issuer/audience, state/nonce/PKCE, expiration ; test réel IdP, identité forgée refusée |
| Origine du formulaire natif vérifiée et liens de récupération privés | Choix produit/contrôles CSRF ASVS ; comportement navigateur constaté | Origin HTTPS exact dans log-login.lisp ; Referrer-Policy strict-origin unique dans log-referrer.nix, chemin/query jamais transmis ; suites log-connexion et log-routage-nix, origine étrangère refusée. Aucun assouplissement à Origin:null |
| Autorisation par ressource/opération | Exigence mission ; ASVS contrôle d'accès | Fonctions métier, RLS/contraintes, Alice/Bob lectures/écritures/liens/caches/exports/tâches concurrents |
| Rôle SQL non propriétaire et non privilégié | Mission ; limite PostgreSQL RLS | Inventaire rôles/propriétaires/politiques ; tables privées classées, SQL isolé hostile et multi-comptes |
| Contexte borné à la transaction/requête | Mission ; PostgreSQL SET LOCAL | Établissement depuis identité vérifiée, transaction, réutilisation connexion Alice puis Bob, refus par défaut sans contexte |
| Recherche isolée avant candidats et dérivés | Mission, confidentialité/intégrité | RLS avant recherche vectorielle/texte et propriétaires des préparations ; tests multi-comptes |
| Sessions durables, révocation effective | Produit/OAuth BCP | Stockage hors tas, expiration/inactivité/rotation ; tests redémarrage, suspension/révocation/OAuth/MCP avec borne mesurée |
| Aucun secret en source/artefact/log | Mission ; ASVS gestion des secrets | Secrets acquis au démarrage, build propre, inspection bornée des artefacts, sentinelles synthétiques hors production |
| Propriétaire métier stable | Produit mission | Association explicite issuer/sub au compte métier ; aucun rattachement email, aucun hook d'effacement lors du retrait IdP |
| Matheval pseudonyme et résultats scientifiques | Produit mission | Secret de reprise indépendant, permissions dédiées résultats, zéro distinct de null, transactions/idempotence/conflits |
| Retour sans écraser données récentes | Mission exploitation | Sauvegarde restaurée en isolation, retour code/ACL ciblé, invariants avant/après et redémarrage réel |
| Vérificateur Kanidm ES256 strict | OIDC §3.1.3.7, RFC7515/7518 ; profil produit ES256 seulement | `mrjam-oidc`, suites `oidc-es256` : signatures indépendantes OpenSSL, issuer par client, aud/azp, nonce, dates/auth_time, at_hash, clés dupliquées/injectées, mutations et huit sujets concurrents ; non activé |
| Transactions state/nonce/PKCE durables | OAuth BCP, choix produit600s et4096lignes | `mrjam-oidc/transactions`, SQLite privé, consommation atomique client/hôte/binding ; suite `oidc-transactions`, huit connexions concurrentes et refus de réutilisation ; non activé |

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
la chaîne Nginx/Keycloak du jalon1 a été qualifiée en production ; le remplacement
Kanidm reste à qualifier. Un Nginx compromis fait
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
Le déploiement du jalon1 est qualifié ; la nouvelle chaîne Kanidm reste à qualifier.
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
Les ACL/rôles et le retour applicatif ont ensuite été qualifiés pour l'assemblage
commun par le jalon1 ; leur historique initial reste dans ce rapport.

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

La nouvelle table privée SQLite `log_transactions` est classée dans
`oidc/tables-privees.json`, avec ses colonnes, accès et limites. Elle ne contient
aucun credential maître Kanidm. State/binding sont condensés, verifier/nonce
restent dans le fichier privé ; aucune sérialisation navigateur ou journal ne
doit les exposer. Le fichier n'est pas une frontière entre bibliothèques Lisp
compromises. Cette table additive ne modifie aucune donnée métier ou identité.
Le client ne mappe jamais un sujet par adresse, ne crée pas de compte applicatif
automatiquement et ne déduit pas une preuve MFA du seul `auth_time`.

## Raccordement Log du12octobre — qualification locale avant bascule

`mrjam-log` vérifie code/S256/state/nonce, ES256/issuer/audience/at_hash et le
rattachement UUID explicite. Sessions/refresh durables privés ; compte actif et
introspection native à chaque accès. Broker MCP : parent de session, consentement,
retour exact, code à usage unique, rotation et révocation de famille. Deux
personnes réelles d'IdP synthétique testées concurremment, aucune donnée réelle.
`assemblage/oidc/tables-privees.json` classe aussi toutes les tables Log.

Kanidm ne publie pas amr/acr. Le privilège administratif repose sur un sujet NEUF,
sans credential importé, dont le groupe natifMFA empêche tout commit de credential
password seul (même si une passkey existe : source credupdatesession.rs). Son
rattachement/politique sont établis par l'opérateur ; auth_time est réellement
signé et900s au plus. L'IdP réel exige TOTP puis password en réauthentification.
La politique n'est pas déduite d'un booléen du navigateur. NativeCLI bootstrap
idm_admin est désactivé après provisionnement ; pas de credential global produit.
Limite : compromission complète du monolithe peut changer sa propre SQLite et
ses contrôles ; ce n'est pas une frontière contre du Lisp/SQL arbitraire.

Alias de connexion au seul formulaire natif /ui/login/begin, pas de système de
mot de passe parallèle. Adresse indexée privée vers UUID ; nom affiché Unicode
séparé du nom technique. Aucun rattachement métier par email. Réponse/formulaires
Kanidm transmis tels quels ; cet adaptateur n'est pas une vue HTML/CSS applicative.
Nginx fixe cible/service/hôte et vérifie TLS du Kanidm loopback. Répertoires
identité/admin0700 et credentials séparés ; pas de debugger dans le produit.

La bascule conserve le réglage d'inscription existant. L'admission native crée une
personne après vérification de son adresse et des consentements existants, puis
rattache explicitement son UUID au compte métier. Une colonne SQLite privée
`demandes.enrolement` conserve l'intent pour reprendre sans nouvel envoi : même
protection que la file SMTP, nettoyage à trente jours. Ajout de schéma au démarrage
seulement, jamais au chargement ASDF. Tests : admission-kanidm.lisp, vrai PostgreSQL
et Kanidm isolés, scénario chaud et reproduction froide.

La capacité native d'onboarding et de lecture mail expire après90jours. Elle ne
permet ni modification de politique globale ni élévation administrateur ; le
propriétaire placé dans idm_high_privilege ne peut être réinitialisé ou suspendu
par cette capacité. Ces refus sont exercés sur Kanidm réel. Limite : cette capacité
peut agir sur les personnes ordinaires ; une compromission complète du monolithe
atteint ce niveau de confiance. Elle ne sert pas à modifier les préférences
individuelles. Rotation officielle du token par l'exploitation avant expiration,
sans credential idm_admin permanent dans le produit.

Zéro demande d'admission ou fermeture en cours exigé avant changement de sujets
IdP. Les fermetures communes définitives et le panneau complet restent à terminer.
Ce jalon n'est pas la clôture de toute l'étape2. L'intent personnel n'est jamais
consommé par une sonde : `/ui/reset` sans token seulement. EnvoiSMTP marqué avant
appel, aucun nouvel envoi automatique après résultat incertain. Les backups natifs
et SQLite Log rejoignent le timer chiffré existant avant manifeste/copie froide.
