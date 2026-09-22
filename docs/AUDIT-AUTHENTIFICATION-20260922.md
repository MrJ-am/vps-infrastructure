# Audit de l'authentification — 22 septembre 2026

## Périmètre et méthode

Revue des sources de Mémoire, Vision, Apprendre à démontrer, style-mrjam,
Signature et VPS Infrastructure ; revue des tests, configurations Nginx/NixOS,
schémas et mécanismes de provisionnement. Audit serveur en lecture seule par
[Actions 35712882397](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35712882397).
Les fichiers d'identifiants, mots de passe, réponses réelles et bases de sessions
n'ont pas été lus. Ce travail est une revue de conception et de code avec tests,
pas un test d'intrusion exhaustif ni une certification.

Les paramètres des condensats ci-dessous sont ceux des implémentations et du
provisionnement. Le fichier de secrets déployé n'a pas été ouvert pour contrôler
chaque ligne. Les références réellement publiées sont consignées séparément dans
les preuves de déploiement ; une branche corrigée ne prouve pas son activation.

## Méthodes par projet

| Projet et usage | Mot de passe / identité | Persistance de l'accès | Évaluation |
|---|---|---|---|
| Matheval, administration | PostgreSQL, `scrypt:N=131072,r=8,p=1`, sortie 64 octets, sel aléatoire de 16 octets ; comparaison à temps constant ; minimum 14 caractères à l'activation, maximum 256 | Jeton aléatoire de 32 octets ; seul SHA-256 stocké côté serveur ; cookie `matheval_admin`, HttpOnly, Secure en HTTPS, SameSite=Strict, chemin `/matheval/api/admin`, durée absolue 8 h | Stockage robuste, cohérent avec les paramètres scrypt OWASP. Limites : pas de MFA ni récupération/changement autonome du mot de passe. |
| Matheval, participation | Aucun compte, mot de passe ou champ email ; identifiant UUID et secret aléatoire de 32 octets | Secret et reprise en `localStorage` (`matheval-participation-v1`), SHA-256 du secret côté serveur ; transmission dans `X-Session-Token` ; pas d'expiration automatique définie | Accès par possession du secret. Persistant sur appareil partagé et lisible par un script de même origine ; risque supérieur à un cookie HttpOnly. Ce n'est pas une authentification nominative. |
| Vision, API Basic / MCP | Fichier htpasswd `root:vision-auth` 0640 ; provisionnement `openssl passwd -6` : SHA-512-crypt `$6$`, sel aléatoire et 5 000 tours par défaut ; secret configuré d'au moins 24 caractères | Identifiants transmis à chaque requête, uniquement sous HTTPS ; pas de session serveur pour Basic | HTTPS et limites de débit protègent le transport et les essais en ligne. SHA-512-crypt 5 000 tours est un point faible relatif contre le cassage hors ligne ; à moderniser. |
| Vision, navigateur / mrj-auth | Vérifie le même htpasswd avec passlib ; aucun second mot de passe en clair | Jeton aléatoire URL-safe de 32 octets, SHA-256 dans SQLite ; cookie `__Secure-mrj_session`, Secure, HttpOnly, SameSite=Lax, Domain=mrj.am, Path=/ ; 12 h absolues, 2 h d'inactivité, au plus 20 sessions/compte | Gestion des sessions correcte, mais hérite du hachage ancien de Basic. Une modification du fichier d'identifiants invalide toutes les sessions par empreinte du fichier. |
| Apprendre à démontrer | Site statique, sans compte, email ni mot de passe | Progression pédagogique et positions vidéo en mémoire JavaScript/Elm dans cette version ; pas de cookie propre ni localStorage repéré | Pas de base de comptes à protéger ; vigilance distincte pour les lecteurs externes. |
| style-mrjam / Signature | Bibliothèque de présentation et identité visuelle ; aucune authentification utilisateur propre | Aucune session propre ; accès aux dépôts délégué à GitHub | Ces projets ne doivent pas absorber les secrets ni la logique d'authentification des applications. |
| VPS Infrastructure | Accès administratif SSH par clé, uniquement via les runners autorisés ; secrets d'environnement GitHub | Clé temporaire sur runner, effacée après l'opération ; hôtes SSH épinglés ; comptes/services séparés | Compromettre un runner, son environnement GitHub ou root reste une compromission critique. Les politiques et réglages de compte GitHub n'ont pas été audités. |

Sources du constat : `M-moire/server/src/security.mjs`, `app.mjs`, `validation.mjs`,
`migrations/`, `docs/site/collection.js` ; `services/mrj-auth/server.py`,
`modules/mrj-auth.nix`, `lib/virtual-hosts.nix`, `vendor/vision/vision.nix` ;
`vision/interface/pont.js` ; `apprendre-a-demontrer/public/bridge.js`, `video.js`.

## Connexion, maintien de session et révocation

Matheval vérifie l'identifiant et le condensat scrypt, puis émet un jeton distinct
du mot de passe. L'API consulte la session à chaque accès administratif. Elle
exige l'origine exacte, le JSON et `X-Matheval-Request: 1` pour les écritures.
La limite est de huit tentatives en quinze minutes par IP. L'utilisateur inconnu
passe aussi par une vérification coûteuse, afin de réduire les différences de temps.
Le logout supprime la session en base. Aucun jeton de renouvellement n'est utilisé.

Le correctif du 22 septembre ajoute à Matheval une limite d'inactivité de deux
heures, le remplacement du jeton présenté à la reconnexion et au plus vingt
sessions par administrateur. La durée absolue reste huit heures. La migration
ajoute `last_seen` sans supprimer de données ; les anciennes sessions reçoivent
l'heure de migration comme point de départ d'inactivité. Le retour à l'ancien
code reste possible, mais rétablit son ancienne politique jusqu'à redéploiement.

Vision consulte sa session SQLite, sa durée absolue, sa dernière activité et
l'empreinte du fichier d'identifiants. Il exige une origine autorisée et un jeton
CSRF pour les écritures. Le navigateur conserve le CSRF en mémoire et aucune
fiche ni secret en localStorage/sessionStorage. Les en-têtes internes sont effacés
puis réécrits par Nginx. Le service d'authentification écoute en boucle locale,
dispose d'un répertoire privé et de restrictions systemd. Les échecs de connexion
sont limités à dix par dix minutes et par IP, en plus des limites Nginx.

Le cookie partagé de Vision couvre `mrj.am` : les sous-domaines autorisés doivent
donc rester sous une même administration de confiance. Il ne peut pas être
partagé avec `principiipetit.io` ou `echos.systems`. La cohérence entre projets
signifie mêmes exigences de sécurité et révocation, pas copie d'un cookie entre
domaines différents. Un éventuel SSO transversal exigerait un protocole dédié.

## Peut-on lire les mots de passe ou les emails ?

Les mots de passe existants ne sont pas stockés en clair dans les bases et fichiers
examinés par leur schéma/code. Un condensat n'est pas un chiffrement réversible.
Un attaquant qui vole des condensats peut toutefois essayer des mots de passe
hors ligne ; le coût mémoire, le coût de calcul et la qualité des mots de passe
sont donc essentiels. Le sel est aléatoire, distinct par mot de passe et peut
être stocké publiquement avec le condensat. Il ne suffit pas d'ajouter un hash
en clair au mot de passe : il faut une fonction dédiée, telle que scrypt ou Argon2id.
[Recommandations OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

Je n'ai pas récupéré les mots de passe. Les outils GitHub ne permettent pas de
relire la valeur des secrets GitHub ; les workflows autorisés peuvent les utiliser
sans les afficher. Les serveurs voient nécessairement la saisie en mémoire pour
la vérifier après terminaison TLS. Un administrateur root, ou un attaquant ayant
ses privilèges, pourrait modifier le service pour capturer de futures saisies.
Le hachage protège le stockage ; il ne neutralise pas une compromission complète
du serveur. Aucune tentative de récupération ou cassage des condensats n'a été faite.

Aucun champ email distinct n'est collecté dans ces systèmes de comptes. Le nom
d'utilisateur Matheval peut contenir une adresse si son titulaire en choisit une :
il est alors stocké en clair comme identifiant. Le contenu libre de Vision peut
aussi contenir des données personnelles ; il ne s'agit pas d'un annuaire chiffré.
Un simple hash d'email est souvent devinable par dictionnaire et ne permet plus
d'envoyer un message. Si une future fonction a besoin de l'adresse, définir sa
finalité et sa rétention, puis envisager chiffrement au repos et index HMAC séparé.

## Cookies, traceurs et information

Un cookie strictement nécessaire à une connexion demandée, ou à sa sécurité,
peut être exempté de consentement préalable. L'exemption n'efface pas l'obligation
d'informer. La règle s'applique aussi aux mécanismes équivalents, dont localStorage.
Une bannière n'est donc pas imposée uniquement par les cookies d'authentification
décrits ici. Ce constat ne vaut pas exemption générale des services tiers ou de
la collecte de recherche. [CNIL](https://www.cnil.fr/fr/cookies-et-autres-traceurs/que-dit-la-loi).

Matheval conserve aussi la préférence d'aide `regards-help-v1`. Les réponses,
positions, temps et interactions de recherche sont pseudonymisés, pas garantis
anonymes. Il reste à fixer et présenter la durée de conservation, le responsable,
la base juridique et l'exercice des droits. Le secret de reprise n'a pas de durée
limite ni de bouton d'effacement autonome dans cette version : amélioration à prévoir
avec un mécanisme explicite de reprise/export, pour ne pas perdre l'accès aux réponses.

Logique chargeait des affiches depuis Vimeo avant le clic. Le correctif supprime
ces contacts anticipés, soumet tous les lecteurs externes à une activation informée,
et propose un arrêt du lecteur. `dnt=1` est conservé pour Vimeo. Cela ne prouve pas
l'absence de tous les cookies du fournisseur une fois le lecteur activé ; aucune
analyse réseau exhaustive des fournisseurs après activation n'est revendiquée.

## Améliorations et limites restantes

Appliquées dans les candidats : sessions Matheval bornées/révoquées, fenêtres
adaptatives, vidéo activable, refus des domaines inconnus par Nginx, tests de
navigation/collecte/3D, et publication soumise aux contrôles des trois applications.

À traiter ensuite en priorité : remplacer le hachage historique de Vision tout
en traitant simultanément Basic et le navigateur ; prévoir rotation ou migration
à la prochaine connexion avec le mot de passe disponible, et mesurer le coût sur
le VPS. Les condensats actuels ne peuvent pas être convertis en Argon2id sans
connaître le mot de passe. Ajouter uniquement un condensat fort en laissant une
copie faible du même secret n'améliorerait pas la résistance au vol de fichiers.
Cette migration n'est pas présentée comme réalisée et aucun mot de passe n'a
été changé ni accès Basic cassé silencieusement.

Autres suites : MFA et gestion de compte si l'administration s'élargit, politique
de conservation/reprise des participations, revue des sous-domaines de confiance,
et contrôle périodique des dépendances et permissions. Les sauvegardes chiffrées
et l'isolation PostgreSQL existent ; leurs règles sont décrites dans les contrats
VPS, sans lecture de données privées dans cet audit.
