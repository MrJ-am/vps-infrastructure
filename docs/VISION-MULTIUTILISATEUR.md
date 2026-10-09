# Préparation de Vision multi-utilisateur

Cette opération est distincte des anciennes publications de présentation et de
la migration sémantique. Les modules sont **désactivés par défaut**. Ce dossier
ne revendique ni une activation NixOS ni une conformité globale en production.

La qualification réelle du 9 octobre
[37909401754](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37909401754),
opérateur `48f40f3eebbbd18eb9048c7036284185a56050e9`, réussit : snapshot
restauré en UTF-8, migrations 019–025 sans perte et retour des ACL/owners/RLS
rejoué deux fois. Six services, nouvelle connexion SSH et 25 sondes HTTP/TLS
passent avant et après. Le doublon `37909419903` est refusé car la préparation
est déjà terminée, avec contrôles réussis.
[Preuve technique sans données](../operations/vision-multiutilisateur-qualification.json).
Le schéma de production, la génération et les inscriptions restent inchangés.

Le workflow manuel `vision-identite-construire.yml` prépare maintenant le
paquet configuré par le module NixOS, avec ses cinq plugins JDBC Unix, SPI et
systemd. Le Nixpkgs installé fournit 26.7.2 ; `services/keycloak-mrjam/paquet.nix`
épingle seulement l'archive officielle 26.7.3 et son hash, avec la recette et
les dépendances installées. Aucune mise à jour de canal. La CI vérifie que
l'override ultérieur des plugins conserve cette source et que le garde-fou
d'activation reste fermé. La construction exige la preuve privée de la
qualification précédente et les mêmes candidats ; elle conserve des racines
GC et vérifie la version et les plugins, sans démarrer Keycloak ni créer de
compte. Son premier lancement réel `37912940648`, opérateur
`226a928a58121b25a3c097c8d32b6843a05e19e6`, passe les invariants et la preuve
de préparation, puis échoue pendant `construction_paquet`. Les six services,
nouvelle connexion SSH et 25 sondes passent après échec. Le diagnostic
`vision-identite-construction-auditer.py` classe seulement ce journal privé,
borné à 256 Kio, en catégories constantes ; le workflow d'audit reste en
lecture seule. L'audit `37914413033` confirme `permission_refusee` pendant le
build du SPI, sans publier le journal. Une reproduction sur Nixpkgs installé,
avec un utilisateur `nixbld` sans privilège et des sources privées, échoue lors
du nettoyage de `classes/META-INF/services` : `cp -R` conserve les permissions
de répertoires en lecture seule du store. Le compilateur rend maintenant sa
seule copie temporaire inscriptible avant de créer le jar et de l'effacer.
La source du store reste intacte. Le test natif `keycloak-compilation.py`
impose un utilisateur sans privilège, des ressources en lecture seule, un jar
valide et aucun temporaire restant. Le diagnostic précis est complété par
des catégories de contexte et de nettoyage, sans restituer de chemin.
La confirmation de ce contexte sur le VPS et sa construction corrigée restent
à constater ; aucune permission de fichier de production n'est modifiée.
L'essai JDBC Unix natif sur ce VPS, l'identité initiale/MFA et le retour autonome
constituent les étapes suivantes.

### Diagnostic préalable résolu

Le 9 octobre, l’audit réel [37903503795](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37903503795)
confirme la reproduction exacte du socle actif après épinglage de son fournisseur
avec `builtins.storePath` (PR34, opérateur `bb26c11a3afd5b924b91c579cc5fc5cd7841d3df`).
La préparation [37904714100](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37904714100)
passe ce contrôle, le relevé transactionnel privé, le dump et son chiffrement age,
puis échoue à `restauration_isolee`. Les migrations isolées n’ont pas commencé.
Six services, nouvelle connexion SSH et 25 sondes HTTP/TLS passent après échec.
Le second lancement du même commit, `37904735624`, refuse la source déjà extraite ;
ses contrôles après échec passent également. Ne pas relancer ce même dossier.

Le diagnostic `vision-restauration-auditer.py` lit seulement le journal privé
de cette opération, borné à 256 Kio, sans suivre de lien symbolique. Il publie
une liste fermée de catégories et des booléens de présence, jamais le stderr,
les identifiants de rôles arbitraires ou du SQL. Le workflow d’audit reste en
lecture seule ; une catégorie inconnue ne justifie aucun assouplissement du
contrôle de restauration. Aucune modification des données de production.

Les audits réels `37906264873` et `37907271873` passent : le refus vient de
`pg_restore`, pendant `COPY`, et ne correspond pas aux premières catégories.
Ils confirmaient le dump age présent et l’absence du dump temporaire en clair ;
aucun rapport de préparation ni retour ACL n’était alors produit.

La reproduction synthétique révèle un défaut du nouveau préparateur : avec
`--no-locale` seul, PostgreSQL choisit SQL_ASCII. Un titre de 180 « é », accepté
par la limite de 200 caractères dans la source UTF-8, est compté comme
360 octets et refusé lors de la copie. Le démarrage impose désormais UTF-8 et
vérifie réellement l’encodage, PostgreSQL 17 et l’absence de TCP avant copie.
Le test `vision-preparation-utf8.py` reproduit le refus initial, utilise le
véritable démarrage corrigé, restaure le schéma 18 et ses textes multioctets,
applique 19–25, puis rejoue deux fois le retour ACL/owners/RLS. Empreintes
historiques et attributs du rôle sont préservés. Le diagnostic est complété
par des catégories de contrainte et de valeur invalide pour confirmer le
refus réel. L'audit `37908917349` confirme une contrainte de longueur d'item ;
la qualification réelle corrigée ci-dessus établit ensuite le succès.

## Architecture candidate

Keycloak 26.7.3 porte `https://log.mrj.am/realms/mrjam`. Vision demeure
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

Audit Actions `37858455559`, infrastructure `9fda3ad29ed2312311c84684c441a8490351517e` :
PostgreSQL 17.11, socket `/run/postgresql`, données `/var/lib/postgresql/17`,
listen_addresses vide ; environ 7 942 Mio RAM totaux, 6 170 Mio disponibles,
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
La connexion par lien magique est qualifiée sur la même version native :
jeton d'action signé à usage unique, dix minutes, navigateur d'origine et
confirmation expresse avant reprise de l'OTP. Aucun secret dans les journaux.
Le fournisseur SMTP natif impose TLS et la vérification du nom du serveur ;
voir [preuves et plafonds](IDENTITE-FERMETURE.md). L'administration garde son
authentification forte récente ; une preuve par courriel ne vaut pas pwd et otp.

Le candidat implémente la suppression administrative à préavis de trente jours : suivi de
l'envoi, échéance et annulation, export personnel accessible, effacement aveugle
par une fonction dédiée. Un échec de courriel doit être visible et ne pas être
traité silencieusement comme une notification réussie. Aucune suppression
automatique des comptes pour inactivité n'est retenue. L'effacement Vision et
la fermeture de l'identité commune sont des opérations distinctes, qualifiées
localement avec registre age et reprise ; leur activation reste séparée.

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
   ACL PostgreSQL et état des rôles. Vérifier DNS/ACME de log.mrj.am et SMTP.
2. Qualifier une restauration **isolée** du dump chiffré Vision. Mesurer poids
   initial, nombre de propriétaires historiques et toutes les copies ; un
   propriétaire historique ambigu bloque la migration plutôt que deviner.
   Exécuter les migrations 019–025 et `scripts/roles.sql` uniquement dans ce
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
   les sept migrations présentes. Préparer un retour des ACL, des owners
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
