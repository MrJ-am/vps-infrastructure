# Préparation de Vision multi-utilisateur

Cette opération est distincte des anciennes publications de présentation et de
la migration sémantique. Les modules sont **désactivés par défaut**. Ce dossier
ne revendique ni une activation NixOS ni une conformité globale en production.

## Architecture candidate

Keycloak 26.7.3 porte `https://compte.mrj.am/realms/mrjam`. Vision demeure
Common Lisp/ElmUI/PostgreSQL 17/pgvector ; aucune réécriture du moteur métier.
Keycloak utilise une base `mrjam_identite` et un rôle `keycloak` distincts,
JDBC sur socket Unix avec junixsocket. PostgreSQL ne reçoit aucun port TCP.
Le service IdP écoute uniquement 127.0.0.1:8085, avec un plafond de 2 Go.
Le serveur de gestion 127.0.0.1:3024 utilise `vision_administration`, dont les
droits SQL se limitent aux fonctions de gestion de métadonnées.

Nginx réserve les routes de vérification internes, écrase les en-têtes
d'identité et transmet l'origine, le CSRF et la méthode du POST original aux
vérificateurs. L'API d'administration et la console maître Keycloak restent
inaccessibles depuis Internet. Aucun compte administrateur Vision n'obtient
`realm-management`, impersonation ou réinitialisation d'identité.

Les comptes OIDC sont associés par `iss`/`sub`. Chaque application future
doit avoir un client confidentiel propre, des redirections exactes, ses cookies
sur son hôte et son admission. Le compte commun ne confère pas un accès
automatique à toutes les données de tous les outils. Les sessions en cours et
tokens MCP consultent le statut Vision vivant ; la déconnexion IdP signée
révoque aussi les autorisations MCP du compte concerné.

En mode nouveau, Basic utilise un **secret MCP nommé** de 256 bits, jamais
le mot de passe IdP. Les tokens Bearer et OAuth MCP restent séparés de REST
et du navigateur. Les mots de passe historiques ne doivent plus servir à
l'API. L'association des comptes historiques, des principaux OIDC persistants
et des tokens encore valides est une migration explicite. Aucun rattachement
par simple ressemblance de nom ou de courriel n'est autorisé.

## État connu et capacité

Audit Actions `37806601018`, infrastructure `c0a78e693c302ca3c274e2b18fda3b4ce803d192` :
PostgreSQL 17.11, socket `/run/postgresql`, données `/var/lib/postgresql/17`,
listen_addresses vide ; environ 7 942 Mio RAM totaux, 6 092 Mio disponibles,
80 Gio disque disponibles. Ce constat permet de préparer un IdP de 2 Go.
Il ne prouve pas la capacité après charge réelle, ni la région contractuelle
d'hébergement, ni les sauvegardes hors machine.

Validation locale Nixpkgs `4c7870105e7f1fdf9c48688c8d7efc21abf0688a` ; construire
le candidat sur le VPS avec le Nixpkgs réellement installé. La réussite d'une
évaluation Nix locale n'est pas une reconstruction ou une activation serveur.

## Décisions d'exploitation après entretien

Le propriétaire retient un compte commun MrJ.am, avec droits propres à chaque
outil. Le rôle administrateur Vision ne peut ni lire les contenus tiers,
ni usurper une identité, ni réinitialiser un mot de passe. L'accès potentiel
de l'exploitant et de l'hébergeur avec des droits techniques privilégiés est
annoncé ; la version retenue traite les contenus en clair et ne promet pas
de chiffrement de bout en bout. La notice déconseille les données personnelles
sensibles concernant des personnes identifiables.

Le responsable agit en France. Le 8 octobre 2026, il confirme que hPanel
Hostinger affiche l'Allemagne comme emplacement de son VPS. La source est
cette confirmation de l'exploitant. La localisation des sauvegardes et les
accès des fournisseurs sont à documenter séparément. Un futur changement
de VPS impose de mettre à jour ces informations.

Les inscriptions sont mondiales et réservées aux liens d'invitation. Pour les
mineurs nécessitant un accord parental, prévoir confirmation par courriel puis
vérification manuelle avant admission ; définir les règles selon le pays et
la base juridique. En France, le propriétaire retient cet accord avant quinze
ans comme règle d'admission, sans en déduire un âge minimum légal universel.
La création directe d'une identité ne doit pas contourner
invitations, limites, contrôles parentaux ou fermeture des admissions. L'inscription
native Keycloak reste désormais toujours fermée, même avec l'option d'ouverture.
Le service privé d’[admission contrôlée](ADMISSIONS-MRJAM.md) réserve les places, exige les confirmations et le contrôle manuel applicable, puis crée une identité désactivée. Le rattachement SQL doit réussir avant son activation. Tous les cas mineurs ou hors France restent en contrôle manuel au lancement.

Le service SMTP retenu est Proton SMTP Submission, déjà compris dans le service
de courriel du propriétaire : `smtp.protonmail.ch`, port 587, STARTTLS obligatoire,
certificat vérifié, expéditeur `Automath@MrJ.am`. Le jeton dédié est fourni,
conservé hors des dépôts et à provisionner dans un fichier privé ou credential
systemd hors store Nix. Ne pas utiliser le mot de passe du compte Proton. Aucun
test d'authentification SMTP ni envoi réel n'est encore attesté. La réception du
domaine reste distincte ; ne pas changer les MX pour configurer l'envoi.

La récupération de mot de passe a été qualifiée sur Keycloak 26.7.3 et un relais
local synthétique : courriel natif, usage unique, nouveau mot de passe, OTP
conservé et nouvelle connexion obligatoire. Proton SMTP réel reste à qualifier.
La connexion par lien magique reste à
réaliser dans l'identité commune : jeton aléatoire à usage unique, courte durée,
aucun secret dans les journaux, validation du parcours et protection contre
l'énumération et le rejeu. L'administration garde son authentification forte
récente ; une preuve de connexion par courriel ne vaut pas mot de passe et OTP.

Le candidat implémente la suppression administrative à préavis de trente jours : suivi de
l'envoi, échéance et annulation, export personnel accessible, effacement aveugle
par une fonction dédiée. Un échec de courriel doit être visible et ne pas être
traité silencieusement comme une notification réussie. Aucune suppression
automatique des comptes pour inactivité n'est retenue. L'effacement Vision et
la fermeture de l'identité commune sont des opérations distinctes à qualifier.

Le choix de rétention est trente jours pour les événements applicatifs de
sécurité et d'administration, appliqué dans le SQL et le realm candidats et à constater sur le VPS. Le journal HTTP
commun garde sa limite existante de quatorze jours ; les historiques personnels
d'apprentissage relèvent de leur propre finalité.

Les sauvegardes payantes Hostinger sont exclues du budget actuel. Le propriétaire
dispose d'un PC Linux et d'un disque externe ; il accepte une copie complète
chiffrée **mensuelle**, avec le risque annoncé de perdre jusqu'à un mois de
données si la machine entière disparaît et que la copie est à jour. Préparer
une récupération simple par les opérations autorisées, vérifier les empreintes
et une restauration isolée, protéger la clé hors Git et hors store. Définir
la rétention et la purge du disque ; une fréquence mensuelle n'établit pas
une durée maximale de conservation de trente jours.

À **chaque effacement**, l'envoi automatique à la boîte Proton de l'exploitant
d'une copie chiffrée du registre minimal est autorisé : identifiants techniques
et dates, sans contenu de fiche ou d'item. Réaliser et qualifier ce canal externe
avant ouverture. Vérifier l'ordre intention durable, dépôt externe, effacement
SQL, reprises et idempotence. La réponse positive d'un relais SMTP n'est pas
à elle seule une preuve de réception et de conservation durable dans la boîte.
Si la preuve externe manque, ne pas annoncer qu'une suppression confirmée
survivra à la perte de la machine ; ne pas réouvrir une restauration dépourvue
du registre le plus récent. Les coordonnées privées de destination et la clé
de restauration sont des paramètres d'exploitation, jamais des valeurs publiques.

## Préparation obligatoire avant activation

1. Figer les trois révisions testées et relire la coordination. Faire un nouvel
   audit actuel ; conserver source, génération active, releases, manifestes,
   ACL PostgreSQL et état des rôles. Vérifier DNS/ACME de compte.mrj.am et SMTP.
2. Qualifier une restauration **isolée** du dump chiffré Vision. Mesurer poids
   initial, nombre de propriétaires historiques et toutes les copies ; un
   propriétaire historique ambigu bloque la migration plutôt que deviner.
   Exécuter les migrations 019–024 et `scripts/roles.sql` uniquement dans ce
   staging, par l'exploitation. Vérifier refus croisés et rapprochement des
   compteurs avec toutes les lignes. Ne jamais lancer un script d'une release
   modifiable par le déployeur comme root/PostgreSQL.
3. Préparer l'import privé avec `scripts/identite-preparer.py` dans un staging
   root 0700. Le JSON public ne contient aucun secret ; le fichier privé et
   `oidc-client.secret` sont 0600 et ne sont jamais envoyés aux logs Actions.
   Les options `importInitial`/`secretClient` pointent vers ces fichiers hors
   store, chargés avec les credentials systemd. Le premier import garde les
   inscriptions fermées. Un realm existant est ignoré par l'import : un
   changement ultérieur exige une opération API locale vérifiée via Actions,
   et non une simple réimportation supposée mettre à jour le realm.
4. Créer ou vérifier l'identité commune du propriétaire par une procédure
   technique réservée. Associer explicitement son sujet signé à son ancien
   identifiant Vision, sans changer l'identifiant des données. Vérifier sa
   possession du compte et son MFA ; créer le premier administrateur par
   l'exploitation, pas par un paramètre d'invitation. Insérer le principal
   OIDC correspondant avant de préserver les accès MCP historiques. Ne
   réhabiliter ni tokens révoqués ni fingerprints périmés. À ce stade, fermer
   les accès aux mutations et conserver l'ancien htpasswd privé uniquement
   pour retour/transfert des fingerprints, jamais pour authentification nouvelle.
5. Vérifier le dossier RGPD du projet Vision : responsable/contact, région
   réelle, sous-traitance, transferts, mineurs, conservation, AIPD, incidents.
   Préparer la notice complète et son numéro de version, synchroniser
   `sauvegardes_jours` SQL avec `sauvegardesJours` Nix. L'option
   `preconditionsValidees` représente une preuve externe, pas un audit automatique.
6. Tester restauration, registre d'effacement durable et ancien état SQL,
   puis armer un retour autonome **avant** l'essai de génération. Le compte
   HTTP ne lance plus de DDL ; le service vision-migrate vérifie seulement
   les cinq migrations présentes. Préparer un retour des ACL, des owners
   et de RLS correspondant au relevé réel : revenir au seul binaire ancien
   ne restaure pas la base. Après admission de plusieurs personnes, le retour
   doit conserver une version compatible avec leurs données et l'isolation.
7. Essayer le candidat avec les inscriptions fermées, contrôler tous les
   sites, MCP Basic/Bearer/OAuth, sessions/CSRF, MFA récent, administration
   anonyme refusée, export/effacement, sauvegardes et nouvelle connexion SSH
   depuis le runner. Ne finaliser la génération qu'après réussite des contrôles.
8. Ouvrir l'admission contrôlée Vision, en gardant l'inscription native Keycloak fermée, après les
   preuves juridiques et techniques. La configuration SQL exige les champs
   d'information, mais ne certifie pas les contrats ni le droit applicable.

Depuis Work, toutes ces opérations serveur passent par **GitHub Actions**.
Les anciens workflows d'activation ne sont pas réutilisés en contournant leurs
invariants : préparer une opération propre à cette migration et ses preuves.

## Sauvegardes et suppression

Le nouveau module propose une sauvegarde quotidienne age de Vision, de la
base IdP, de SQLite mrj-auth et du registre externe d'effacement. La clé privée
de restauration demeure hors store et hors Git. Rétention initiale 30 jours,
borne 1–90 jours. Le timer PostgreSQL historique de Vision est retiré seulement
en mode multi-utilisateur ; les sauvegardes des autres bases gardent leur contrat.
Les anciens fichiers en clair et snapshots ne disparaissent pas par magie :
les traiter avec preuves, sans supprimer la dernière restauration utilisable.

Le registre `/var/lib/vision-effacements/demandes.jsonl` est privé (0600,
répertoire 0700) et hors de la base. Vision consigne une intention confirmée et
fsync le fichier/répertoire avant DELETE. Après panne, l'intention autorisée
prime même si la réponse n'a pas été reçue. Ne pas réattribuer l'identifiant
effacé. Protéger et répliquer ce registre hors machine indépendamment du dump.
Une copie journalière de ce registre ne suffit pas à garantir qu'une demande
effectuée après cette copie survivra à la destruction de la machine : définir
et vérifier cette protection avant ouverture.

`scripts/vision-effacements-rejouer.py` refuse une base de production. Il applique
le registre courant à une base `vision_restauration_*`, avec le rôle technique,
avant toute promotion de cette restauration. Il n'affiche aucun contenu.
Ne jamais ouvrir la restauration au réseau avant ce rejeu. Une purge du registre
n'est autorisée qu'après expiration vérifiée de toutes les copies pertinentes,
snapshots inclus ; ne pas supprimer le registre en se fondant uniquement sur
la table SQL restaurée. La preuve hors machine reste une condition ouverte.

## Sécurité et limites de preuve

Tests locaux : PG17 avec rôles réels non propriétaires, refus de lecture de
contenu par l'administration, RLS croisée, quotas Unicode/historiques, rollback
atomique, concurrence, dernière place d'invitation, rétroactivité/révocation,
export cohérent et suppression des observations. OIDC : véritables signatures
RSA, PKCE/nonce/issuer/audience/expiration, liaison hôte, rôles vivants, MFA récent
et backchannel signé/rejeu. Keycloak 26.7.3 a été importé et parcouru réellement
en conteneur jetable, avec mot de passe, OTP, PKCE, AMR et auth_time.

Cette qualification est reproductible par `tests/keycloak-integration.py` et
le job `keycloak` de la CI. Le conteneur est épinglé par digest ; le test crée
puis efface un realm synthétique issu du fichier versionné, vérifie la signature
RSA de l'ID token et n'affiche aucun jeton. La restauration age et le rejeu des
effacements sont reproductibles par `tests/vision-restauration.py --vision CHEMIN`,
avec un client PostgreSQL 17 et une copie exacte du code Vision candidat.

La qualification Keycloak locale utilise H2 et HTTP loopback pour le test,
pas la configuration de production. Il faut encore constater JDBC Unix,
TLS/DNS, SMTP, restauration et charge dans le staging VPS. L'accès privilégié
technique potentiel aux contenus en clair demeure déclaré ; l'exclusion des
administrateurs applicatifs n'est pas une promesse d'inaccessibilité par root.
