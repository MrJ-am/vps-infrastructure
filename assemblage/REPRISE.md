# Reprise — mission et amendement du 11 octobre 2026

## Point de reprise actif — candidat Log scellé, promotion à lancer

Production toujours étape1 (9qv8n9gd/296b7), aucun courriel personnel envoyé.
Candidat métier construit77129dd, SHA256bc70c8225908dd0c566fdcb27a49d62e8b1e39d46c81862098a5221676e9fcbb.
Opérateurs scellés9fcf998, transport chiffrée895785 (182388105octets, cinq parties).
Descripteur central operations/log-candidat.json ; 51suites avec reçus exacts et
vérificateur du bundle privé réussi. Qualification complète puis réparation
ciblée (37preuves conservées,14suites affectées) ; sources Lisp inchangées depuis
construction17,7007s, HTTP/transactions/redémarrage20,2273s. Aucun nouveau build.
Visiondecf5f7, Signature1719408, Stylea998822 publiés avant manifeste ; autres
révisions inchangées. Inversion mesurée avec horloge installée avant Elm,
mêmes seuils/focus ; aucune modification du rendu. Restauration froide/autreUID,
OIDC/MFA/passkey natifs réels et51suites qualifiés. Les sources ASDF OIDC auditées
rejoignent la closure signée pour restauration, sans outillage MCP produit.

Image C saine conservée (marqueur reprise-20261012-552402 observé, pas PID fixé).
CL-MCP sans pool/Swank, Tron distinct ; aucun qualifier synthétique de santé.
Aucun REPL connecté à des données de production.

Suite immédiate : workflow manuel log-deploiement.yml, opération deployer sur
main. Il vérifie le bundle, construit les superpositions depuis l'installation
réelle, qualifie backup/restauration métier récent et retour, amorce Native sur
loopback puis rattache explicitement le propriétaire stable. Inventaire de tous
les realms et consommateurs IdP avant toute mutation ; identités supplémentaires
refusées. Admission native conservée, demandes en cours refusées sans fermeture
artificielle. API onboarding90j sans admin général, propriétaire protégé HP.
Snapshot identités seulement pour retour ; jamais ancienne base métier restaurée.
Intent personnel jamais sondé/consommé ; sondes artefact/ressources/données/restart
avant SMTP. Marque avant envoi ; pas de renvoi après issue incertaine.

Ne jamais répéter une bascule engagée sans constater son état privé. Lire le run
et sa phase réelle ; arrêt/timeout du client ne prouve pas annulation. Ce jalon
ne clôt pas toute l'étape2 : enrôlement/autorisation MCP personnels, panneau et
préférences individuels, fermetures communes définitives restent à terminer.
Après invitation réellement servie et SMTP accepté, attendre l'enrôlement demandé
par l'utilisateur avant la suite ; ne pas annoncer une réception en boîte non
observable. Le retour indépendant et les anciennes générations restent protégés.

## Historique conservé — autorisations propriétaire et constats précédents

Amendement propriétaire du12octobre : suppression des deux anciennes identités
autorisée, remplacement Keycloak par Kanidm confirmé. Préserver le compte métier
et ses données ; ne jamais déclencher effacer_identite_cycle. Récupérer l'adresse
du compte Keycloak par canal privé pour invitation personnelle expressément
autorisée ; nouvelle identité liée explicitement au propriétaire stable AVANT
ouverture de l'accès, sans fusion par mail. Aucun courriel encore envoyé.
Inscription sur invitation : mail nécessaire à la récupération du compte ; pseudo
facultatif, affichage du mail par défaut, jamais identifiant technique mutable.
Unicode et espaces requis pour pseudo/phrase de passe ; nom affiché distinct du
name Kanidm contraint. Phrase de passe longue et indication de force demandées.
Version native1.11.2 : force zxcvbn score4, blacklist et minimum15 sansMFA/10avecMFA,
maximum128 ; pas de composition majuscules/chiffres/symboles imposée. Ne pas
promettre une règle exclusivement fondée sur la force ni un indicateur live non
qualifié. Test natif étendu : pseudo Unicode/espaces intact ; phrase100caractères
Unicode/espaces enregistrée puis connexion TOTP avant/après restart,25assertions.
Image applicative absente du constat ps (seul Tron présent) : reconstruire la
cible C et vérifier son identité avant prochaine opération Lisp ; ne pas réutiliser
les références historiques. Aucun arrêt/reconstruction déclenché par ce constat.

Mission poursuivie, étape1 toujours acceptée en production : génération9qv8n9gd,
artefact296b7, opérateurs185f931. Aucune deuxième promotion. Vision, Matheval,
Logique et leurs données préservés ; Keycloak/Python mrj-auth encore provisoires.
Six sources exactes du manifeste, composants propres. Infrastructure publiée
4f94882 puis354ceb0 ; compléments actuels encore à publier. Rapport MCP historique
non suivi préservé, ne pas l'inclure dans un commit fonctionnel.

Préférence propriétaire amendée : conserver un seul compte commun issu de Vision,
email ajouté et mot de passe gardé ; nouvelle inscription/reconnexion acceptable
sinon, aucun double mécanisme permanent. Référence réelle38237108531/354ceb0
réussie : un compte métier actif/administrateur/propriétaire/identité, zéro
orphelin/lien croisé ; un compte historique éligible SHA512-crypt reconnu, zéro
doublon/format inconnu. Trois participations Matheval toujours ouvertes. Preuve
agrégée kanidm/reference-proprietaire-20261012.json, aucun hash/nom exporté.
Téléchargement artifact gh refusé403 ; journal obtenu via connecteur GitHub
existant, JSON réellement émis extrait, aucun second workflow ni mutation métier.

Import simple réellement qualifié sur Kanidm1.11.2 local : `{crypt}$6$`, rounds
implicites5000 ET explicites656000, UUID/email conservés, bon password accepté,
mauvais refusé, stockage réhaché Argon2id après connexion. Session native existante
et password conservés au redémarrage. Le fichier de migration ordinaire refuse
PasswordImport par AccessDenied : constat, sans correctif amont ni ACL élargie.
API officielle ponctuelle sync_account/token/Sync/_finalise utilisée ; capacité
ensuite401/403, parent de sync absent. Aucun `_terminate`, aucun service de sync
permanent. Les bases/clefs/comptes sont entièrement synthétiques et supprimés en
fin de test. Cela ne migre pas encore le propriétaire réel ni ne qualifie OIDC/MCP.
Vision comptes.id UUID/utilisateur textuel restent stables ; remplacer le seul
rattachement identites, sans fusion email ni effacer_identite_cycle destructif.

Correction déterminante après contrôle supplémentaire : restart AVANT premier
login refuse le BON password importé, pour5000 et656000rounds. Source officielle
libs/crypto/src/lib.rs487 convertit DbPasswordV1::CRYPT_SHA512 en Kdf::CRYPT_SHA256
au rechargement. Aucun patch/fork Rust ni maintien conditionnel de deux logins.
Choix de repli expressément autorisé par l'utilisateur : compte Log neuf unique,
rattaché explicitement aux données Vision existantes ; password saisi/enrôlé
personnellement, ancien password éventuellement choisi si sa politique l'accepte.
Qualification contient cette régression observée et import_password_retenu=false.
Les succès précédents après réhachage restent exacts, mais ne qualifient plus
l'import pour la production. Aucun compte réel n'a été migré/supprimé.

OIDC réel supplémentaire :15assertions passent viaCL-MCP dans image C et en image
froide, puis commande centrale. Discovery/JWK/ES256/S256/consentement, échange,
issuer/audience/nonce/at_hash/UUID, introspection, refresh signé, révocation→active
false et nouveau refresh400. Données/secrets uniquement synthétiques, diagnostics
privés0600, aucune credential admin dans Lisp. Catalogue43suites, raccordement
serveur métier et MCP utilisateur encore à réaliser. Un nom de renderer JSON
incorrect a échoué à la lecture avant échange ; export réel json-encode utilisé.

Politiques natives sondées sur bases indépendantes : les DEUX défauts
idm_all_accounts/idm_all_persons contraignent les durées. Tous deux90j + profil
7j donnent réellement604800s ; un seul défaut modifié laissait86400s, même après
restart. CredentialTypeMinimum concerne l'enrôlement, ne prouve pas l'usage MFA :
password seul encore accepté sous minimummfa, confirmé parTODO authsession/mod.rs.
Ne pas accorder de privilège métier administratif sur ce seul paramètre.
Qualification canonique supplémentaire23assertions : enregistrement password
seul non committable sous minimummfa, TOTP SHA256 généré/vérifié par Kanidm,
commit puis seul mécanisme passwordmfa offert, vraie connexion avant ET après
restart. Profils7/30/90j effectifs et rôle7j plus fort constatés. Passkey réelle
viaChromium154/authentificateur virtuel : registration/login UVrequired,
password absent, login conservé après restart, assertion signée sansUV refusée
malgré affaiblissement du paramètre navigateur. Certificat synthétique ignoré
dans ce seul contexte navigateur routé exclusivement vers loopback ; Curl TLS
strict séparé qualifié. Aucune clé/passkey/OTP personnels ni accès production.
Commandes centrales politiques2,2805s/passkey4,4917s passent ; catalogue45suites.
Premier raccordement de provenance browser cherchait le cache supprimé : profil
Chromium externe effectivement utilisé déclaré, aucun moteur réinstallé/guard désactivé.

Kanidm officiel5479338, Nixpkgs c5, vendor741crates conformes au lock et licences
déclarées inventoriées. Intégrité staging fixe ET vendor dérivé vérifiée ; cargoHash
porte sur staging, pas vendor décompressé. Source/compiler/options inchangés,
provisioning tiers désactivé. Paquet store0aqnq3k2 installé/vérifié/protégé :
kanidm/installation-locale.json, NAR175497328octets. Build release93m27s à un cœur,
Cargo offline. MSRV1.96→1.95 de la recette existante effectivement compatible.
Nix doCheck=false : scénarios réels sont des preuves séparées, limitées.
Premier build overlay ENOSPC : TMPDIR ne change pas build-dir Nix ; build-dir
explicite vers tmpfs existant corrigé. Compilation terminée code0, plus aucun
processus build ; tmpfs35Mio, overlay environ1,5Gio libre, zéro OOM observé.
Ne pas répéter précollecte/build. Aucun déport, aucun nouveau disque disponible.

Image C saine conservée depuis CL-MCP et Tron : même PID/marqueur/objet, mutations0,
debuggerNIL. Pool désactivé, aucune reconnexion ni qualifier synthétique de santé.
Transport OIDC Lisp écrit puis ASDF incrémental et tests ciblés, secrets sur pipe,
TLS/SNI Log/loopback fermés, aucune redirection/répétition de POST. Basic seulement
sur/token ; introspection/révocation par possession du jeton opaque selon API
native.32assertions/11requêtes passent dans image persistante et image propre.
Erreur de lecteur avant nouveaux exports corrigée par résolution de symboles
après LOAD ; mauvais nom ASDF transport/tests corrigé en transport-tests avant
requêtes. Aucun dépilage CL-MCP présenté comme restart encore disponible.

Commandes centrales : OIDC681, transactions40, transport32 ; STARTTLS courriel
réel, intégration-sécurité60tests, sélection25 et éditorial passent. Import natif
avec deux formats rounds passé4,4618s ; transport final13,9169s. Catalogue42suites.
Les suites aux clés/états éphémères ne réutilisent pas automatiquement leurs reçus :
garde-fou testé par un compteur réellement exécuté, cache déterministe conservé,
valeur non booléenne refusée. Provenance exécute/empreinte Curl et Kanidm réellement
configurés. Reçus complets privés, résumés/empreintes publics, aucune attestation
CI fabriquée. Anciennes preuves restent historiques et ne qualifient pas Kanidm.

Ménage antérieur achevé :4,82Go nets récupérés,1,10→5,92Go avant téléchargements
Rust/Kanidm ; assemblage/nettoyage-20261012.json. GC normal161objets avec40racines
utiles protégées, caches navigateurs/npm/pip/candidats redondants vérifiés retirés.
Sources, imageC, Git, modèles/embeddings, candidat actif et retour gardés. Ancien
SBCL2.5 retiré ; SDK Playwright Python/npm1.61.0/Pillow12.3/Node24.19 communs,
Chromium154 système et Firefox151 uniques qualifiés. Quatre composants publiés
avant manifeste, aucun backend Node réactivé et aucun CI de développement.

Suite immédiate : publier preuves natives/commandes et conserver cette image.
Exercer les clients OIDC sur le vrai Kanidm local (discovery/JWK/signatures/PKCE,
state/nonce/audiences/expiration/révocation), puis politiques/invitations/durées/
email et parcours MCP. Porter seulement raccordement/session/OAuth provisoires
dans Lisp ; aucun credential admin global dans le monolithe. Préparer propriétaire
réel/enrôlement/récupération, qualification propre, sauvegarde/retour avant promotion.
Passkey/OTP personnels ne peuvent être simulés. Aucun accord architectural demandé.
Les documents ci-dessous sont l'historique, pas des blocages actifs de stockage.

## État précédent — étape1 acceptée, préparation OIDC, blocage disque avant nettoyage

Déploiement38200204066/29c3f39 réussi ; opérateurs185f931 et binaire296b7.
Génération active ET défaut9qv8n9gd ; une image métier, Node Matheval et anciens
processus arrêtés, Keycloak/mrj-auth provisoires conservés. Restauration récupérable,
retour code avec données actuelles, RLS/ACL36tables, artefact réel, ressources,
falsification refusée, données invariantes et persistance après restart passent.
Référence38200479116 : un compte/administrateur/identité, zéro orphelin/lien croisé,
trois participations toujours ouvertes. MCP historique : politique/séances identiques,
lecture62items possible, recherche hybride retrouve un item réellement existant,
aucun contenu/séance/participation créé. Pages publiques réelles Vision/Matheval/
Logique rendues, zéro erreurJavaScript ; HTML exacts qualifiés, session anonyme.

Preuve : assemblage/qualification-production-etape1.json,36reçus locaux exacts.
RSS principaux métier320270336→138428416octets (somme avec pages partagées,
pas RAM physique libérée). Latences après mesurées/cadencées ; pas de gain promis.
Navigateur initial sans proxy : délais ; pont réseau existant configuré explicitement.
Sonde wait_for_function par chaîne refusée par CSP ; observation par locators,
CSP non affaiblie, rendu complet attendu. Ces erreurs de sonde ne sont pas
présentées comme des succès ; contrôle final effectivement exécuté.

Kanidm stable1.11.2/revision5479338 officiel inspecté (correctif LDAP sécurité).
Source et Cargo.lock774packages/741registre verrouillés ; précollecte vendor
échouée sur espace : overlay32Go plein, substituts Cargo/Rust requis2,5Go.
Aucun serveur installé/démarré ni changement production. Extension de disque
d’au moins20Go demandée ; poursuivre travaux indépendants. Pour retrouver une
marge d’écriture : caches f981717 et0e3f999 seulement retirés après vérification
SHA256/octet exacte contre leurs trois blobs Git, transports publiés et tous
manifestes/sources/preuves conservés ; candidat actif185f931 gardé intégralement.
Ces caches se reconstituent par concaténation des parties de transport.json
via git cat-file blob, puis vérification cipher_sha256 de soumission.json.
Nix --delete sans forçage a retiré quatre substituts nouveaux de cette tentative
(1016,31MiB), aucune collecte globale ; marge retrouvée1,125Go. Archive source
Kanidm redondante retirée après SHA vérifié ; source extraite et provenance gardées. Provisioning
non officiel Nix explicitement désactivé. Licences transitives/compatibilitéRust
restent à qualifier avant compilation. Image83928 saine : identité/marqueur/objet
identiques depuis CL-MCP et Tron, poolNIL, debuggerNIL, sans mutation/scénario.
Client OIDC préparé et qualifié localement : mrjam-oidc, ES256 via Ironclad0.61
(tag officiel identique à sourceNix), six bibliothèques communes réutilisées,
NAR/licences/effets verrouillés. JOSE écarté car sans ES256. Après correction du
remplissage URI cl-base64,681cas/assertions passent, signatures OpenSSL indépendantes,
mutations et huit sujets concurrents ; image persistante puis image propre sans cache.
Transactions PKCE durables additives : consommation unique sous huit connexions,
36contrôles passent : refus client/hôte/binding/expiration/rejeu, répertoire0700/
fichier0600 et colonnes exactes ; table classée.
Aucune activation de ces bibliothèques ni nouvelle identité en production.

PaquetKanidm1.11.2 verrouillé avec hashvendor officiel, Nixpkgs c79f172 source de
ce hash seulement ; recette/toolchain c5 conservées sans mise à niveau générale.
Nix path-info code0 avec valeursnull ne prouve pas un cache : narinfo paquet et
vendor effectivement404. Module préparatoire Nix : serveurUIDkanidm/statemode0700,
loopback8443, TLSLoadCredential horsstore, Unix/LDAP/provisioningtiers désactivés ;
non importé dans configuration active. Installation/démarrage/échangesKanidm réels
restent bloqués par disque (1,1Go disponible, extension≥20Go déjà demandée).
Connexion par email : lecture source confirme name/SPN/UUID, nom interdit@ et email
absent de name2uuid ; adaptation sûre requise, aucun retrait de l’exigence autorisé.
Politiques individuelles, révocation et preuve MFA récente restent à qualifier
sur Kanidm réel, sans credential d’administration générale dans le monolithe.
Catalogue39suites, nouveaux reçus locaux : OIDC681cas4,9888s, transactions36contrôles
1,6318s, configurationKanidm8,8789s ; sélection21tests1,2095s et éditorial0,2906s.
Dernier contrôle depuis Tron : fonctionsOIDC/transactions visibles dans la même
image83928, poolNIL, marqueur conservé, debuggerNIL, mutationsregistre0.
Preuve préparatoire : assemblage/oidc/qualification-locale.json ; productionnonautorisée.
Commandes locales : suites oidc-es256, oidc-transactions, kanidm-configuration ;
CLIoidc-qualifier.py --sans-cache [--transactions] pour qualification de référence.
Les reçus du jalon1 restent historiques sur leurs sources exactes, pas preuves
pour ce nouveau client. Ne relancer ni ancien déploiement ni qualifier synthétique.

Prochaine étape autorisée : Kanidm stable/officiel/verrouillé, lire configuration
identité et exigences actuelles, préparer intégration/récupération et qualification
réelle hors production avant seconde bascule. Ne pas réactiver l’ancien métier.
Accès personnel/passkey à préparer sans inventer d’enrôlement. GitHub administration
403 reste une limite exacte, pas une prétendue correction des réglages distants.
Image de développement C conservée ; aucun qualifier synthétique/reconnexion.
Rapport MCP non commité conservé. Retour applicatif185f931 utilisable avec données
actuelles ; ne jamais restaurer une ancienne SQL pour un retour de code.

## État précédent — historique conservé

# Reprise — mission et amendement du 11 octobre 2026

## Point de reprise actif — routage Vision qualifié localement

Production ancienne r6s7ags3 après retour38196244219 enregistré/timer arrêté.
Préparation/restauration/RLS-ACL passent ; sonde précise Matheval200 puis Vision404.
Nginx index de la location exacte /= redirigeait vers /index.html, qui partait au
routeur métier. Cause reproduite avec vrai Nginx verrouillé et même binaireSBCL,
sans SQL/SMTP/IdP. Accueil conservé dans routeVision / : mêmes octets qualifiés,
CSP et no-store conservés ; aucun nouveau parcours ou changement de présentation.
Manifeste public /interface-manifest.json raccordé au fichier qualifié manifest.json.

Nouvelle suite centrale routage-nginx1,7222s, sécurité9,8278s,
migration50,7521s, sélection1,2065s passent. Catalogue36suites.
Nginx existant autorisé réutilisé pour test local, sourceofficiellec5c4a43 vérifiée,
paquet/closure verrouillés dans assemblage/nginx-qualification.json ; aucun profil
système ni produit modifié. Diagnostic38197483752 : paquet Nginx1.30.4 et SHA256 exacts identiques au VPS.
Même image de travail C et mêmes sources métier/frontends ; outil de test froid
Nginx/SBCL arrêté proprement après fixtures, aucun qualifier synthétique.

Candidatf981717 scellé et transport chiffré publié,109146518octets, SHA256
e23c41731a28fa744ce774eb00de0797ddb23d5fb6bed46a85a1562eed8968ce.
Bundle complet36reçus vérifié. Déploiement38197714319/90be33f déclenché
02:55:37UTC ; issue à constater avant toute répétition. Constater
issue avant répétition ; MCP réel/référence après activation avant jalon1/Kanidm.
Kanidm non commencé ; rapport MCP non commité conservé.



# Reprise — mission et amendement du 11 octobre 2026

## Point de reprise actif — sondes cadencées qualifiées

Production ancienne r6s7ags3, retour38195473395 enregistré/timer arrêté, données
actuelles conservées. Restauration complète et RLS/ACL actifs ont passé ; vue
historique désormais possédée par vision_migration, aucun rôle applicatif privilégié.
Bascule8576390 refusée ensuite sur une sonde publique ; ancien rapport ne précise
ni laquelle ni ses codes, cause exacte non attribuée. Nouveau rapport fermé par
nom/code et disponibilité, sans URL/corps/secret. Dix lectures désormais espacées
250ms sous limite commune5r/s, attente explicite45s seulement pour429/502/503/504
avant mesure ; 403/404/500 immédiats et toute erreur mesurée restent refusés.

Tests HTTP locaux réels :503 puis disponibilité200, dix lectures réellement
espacées, pauses hors latence ;429 mesurée et erreurs permanentes refusées.
Deadline unitaire bornée : ancienne fixture échouait car time.monotonic partagé
avec thread serveur ; substitution limitée au test de borne, trois scénarios HTTP
réels conservés. Sécurité10,065s, migration38,057s, sélection0,9849s passent.
Autres reçus inchangés ; ne rejouer ni interface ni calcul métier. Même binaire296b7,
Visioncd05b702/frontend3c00e4fd, image interactive C préservée.

Candidatb3a552f scellé et transport chiffré publié,109135992octets, SHA256
deb7fb67eed0695b1c1370e7d51a1bd81826477d724f69d2fa18d9a3f4c2cf0a.
Bundle complet vérifié. Déploiement38196244219/23845c1 déclenché02:33:20UTC ;
issue à constater avant toute répétition. Constater issue, puis MCP réel et référence mémoire/comptes/
latences/services avant jalon1 et Kanidm automatique. Kanidm non commencé.
Rapport MCP non commité conservé. Aucun qualifier synthétique ni reconnexion.




# Reprise — mission et amendement du 11 octobre 2026

## Point de reprise actif — propriété de la vue historique corrigée

Production ancienne r6s7ags3 après retour38194338389, monolithe inactif.
Préparation et restauration77c7f82 entièrement réussies ; commun démarré puis
refus du contrôle SQL. Retour enregistré, timer arrêté, aucune base ancienne
restaurée. Diagnostic38194819102 : vue public.vision_browser_sheets encore
possédée par vision, donc rôle applicatif propriétaire. pg_tables ne listait
pas cette vue. Visioncd05b702 publié : transfert au rôle sans connexion
vision_migration, ACL existantes révoquées ; aucun changement de définition/donnée.

Régression PostgreSQL réelle : ancienne propriété reproduite/refusée, réparation
idempotente, définition/données/séance ouverte inchangées, accès direct refusé.
35 reçus exacts passent,28 réutilisés et7 rejoués : PostgreSQLVision112,051s,
interface59,6562s, navigateur/MCP28,4359s, migration41,1296s,
SQLnative14,8583s, sélection1,0693s, éditorial0,3216s.
Diagnostic fermé sécurité1,3513s qualifié séparément. Binaire296b7 inchangé ;
frontend Vision3c00e4fd : seul manifest.json de révision diffère, fichiers servis
identiques. Retour précédent explicitement77c7f82 dans manifeste.

Candidat8576390 scellé et transport chiffré publié,109131832octets, SHA256
33d0a52d4d01478697769b0c414a408a326fcfb6d83cf9610625b4112cd1e063.
Bundle complet vérifié localement. Déploiement38195473395/af32431 déclenché
02:21:36UTC ; issue à constater avant toute répétition. Constater l'issue avant répétition,
puis MCP réel/données/restart/services/mesures avant jalon1 et Kanidm automatique.
Kanidm non commencé. Image interactive C/interfaces conservées, aucun qualifier
synthétique ni nouvelle connexion. Rapport MCP non commité préservé.




# Reprise — mission et amendement du 11 octobre 2026

## Point de reprise actif — capture complète de la simulation Nix qualifiée

Production ancienne r6s7ags3 ; retour38190627348 finalisé, monolithe inactif,
agrégats préservés. Kanidm non commencé. Image interactive C/interfaces préservées.
Candidat8d44379 scellé et publié, mais déploiement38193221173/f5f64af refusé
pendant préparation AVANT restauration/activation : simulation absente sur stdout.
Source officielle verrouillée c5c4a43/switch-to-configuration-ng/src/main.rs vérifiée :
« would activate » et actions sont écrits par eprintln!, donc stderr.

Correction canonique : rapport_complet=True uniquement pour dry-activate, stdout/
stderr réunis ; sorties SQL/JSON ordinaires inchangées. Régression réelle shell :
rapport sur stderr capturé, restart protégé réellement refusé. Sécurité1,2728s
passe ; autres entrées inchangées, seuls contrôles affectés rejoués. Publier cette
source puis nouveau scellement exact35reçus, même binaire296b7 et mêmes interfaces.
Ne pas redéployer8d44379. Historique des corrections utiles conservé ci-dessous.

Corrections qualifiées conservées : attente exacte du binaire après lanceurBash,
reprise explicitement liée au retourdbd5b19, sources historiques récentes
prioritaires, états nouveaux conservés, fichiers communs supplémentaires chiffrés,
retour partiel sans recopie après redémarrage. PG17 réel : hba_file/ident_file
postmaster, restartPG/Keycloak précisément déclaré, versions/données conservées,
autres protections inchangées ; rôle étroit après setupPG. Essai reload abandonné
archivé, aucun succès prétendu. Migration41,0322s/sélection0,9335s passent après ajout du préparateur réel
aux dépendances de migration ; reçus vérifiés sur disque après fin du processus.

Candidat77c7f82 scellé : mêmes35reçus/binaire296b7/interfaces, bundle complet
vérifié ; transport e2d6910 publié,109128533octets chiffrés, SHA256
5e4436ee75d40558a5649e4e4e8da74836e720b8e0d806d62ef8275ebf4ebf9a.

Déploiement38194338389/b9eeb068 échoué : préparation et restauration complète
réussies, service commun démarré puis contrôle rôles SQL refusé (verifier-tables40).
Retour ancien système enregistré, seul PIDKeycloak différent, aucun SQL ancien
restauré. Diagnostic fermé des rôles à relever avant correction/nouveau candidat.

Prochain : constater ce déploiement central
préparer/restaurer/activer/contrôler, constater son issue avant répétition, puis
MCP réel, données/restart/mesures/services avant jalon1 et Kanidm automatique.




## Point de reprise antérieur — correction RLS avant bascule

Candidat courant4e6dba37bdb5da246b439b876164c50aed21b950 : scellement complet
réussi, transport0bc7abddb0ed1b8056fadfef87b4cb901af9e755 publié,
109109871octets chiffrés, SHA256c7a46d4e78bdf6520c557948a5804e96b2565fe29b7788480e7ab6526ef2f6df.
Le descripteur central remplace9a063b8 ; préparation/restauration/activation
conditionnelle sont exécutées dans le run38187899380 sur0528f41. Issue à
constater après interruption ; ne pas supposer arrêt, retour ou activation.

Production ancienne conservée ; étape 1 non activée, Kanidm non commencé.
Préparation 38184214522 réussie, déploiement 38184424703 arrêté pendant la
restauration isolée, avant activation. Diagnostic 38185217273 : les 14 tables
privées public.vision_* ont leur politique, mais ENABLE/FORCE RLS sont désactivés.
Le pg_dump/restore local conserve ces attributs : dérive déjà présente en
production, pas une perte à la restauration. Métadonnées privées dans
state/reference-rls-active-38185217273.json ; aucun contenu métier journalisé.

Correction qualifiée et publiée : migration Vision 027 explicite/idempotente, limitée aux
14 tables classées. Elle rétablit les prédicats de propriétaire et ENABLE/FORCE,
refuse une autre politique et ne rejoue ni la 019 ni les compteurs. Qualification
PostgreSQL isolée : dérive réelle, échec atomique, données/observations/séance
ouverte inchangées, idempotence et isolation. Opérateurs restauration/activation
adaptés à 25/26/27. Aucun SQL exécuté en production pour cette correction.

Vision18c52cdd publié ; migration13,4831s, PostgreSQL145,7859s, SQLnative16,6193s,
recherche CPU réelle36,871s, sécurité0,8142s, sélection1,0072s passent. Nouveau
frontend Vision37871df2, présentation76,2795s et navigateur/MCP26,9502s passent.
Les35reçus sont valides (34réutilisations exactes/éditorial rejoué). Opérateurs
9a063b8e4c38de5fbfcb11208df67fd1d259d370 publiés ; scellement complet local réussi.
Transportb02d22d74d531168a6e2523077ddf167497663b2 publié (trois parties),
109027873octets chiffrés, SHA256e8ad8f2832590e8a99c13f0d3186b23e5a9e5737c52c6490224437a3b3e2b659.
Descripteur central publié23aa0d14edf5f7e15a957f642988095dce77b694.
Préparation38186573658 réussie : binaire296b7, générationNix9rsmp9wrp9vid4dk85cn30fckjszywwp,
activationfalse, sondes des services existants réussies. Preuve dans
state/preparation-38186573658.json. Déployer est la prochaine opération fermée :
restauration fraîche/ACL/retour avant activation. Déploiement38186728742 sur23aa0d14 arrêté en restauration isolée avant activation.
RLS/ACL passent ; diagnostic38186824686 situe le refus au lancement SBCL128.
Diagnostic38187150992 : Vision ne peut pas traverser /var/lib/postgresql.
Le sous-répertoire ouvert au groupe Vision reste inaccessible sous ce parent.
Démarrage local avec env vidé réussi. Correction qualifiée localement : répertoire
éphémère sous /var/lib, permissions privées inchangées, aucun droit élargi sur
PostgreSQL. Régression Docker/Nix sans réseau sous un autre UID, cas parent
interdit et démarrage réel depuis le parent accessible. Migration et régression Unix passent29,4132s ; autres entrées inchangées. Contrôler les reçus avant un
nouveau scellement ; ne pas rejouer9a063b8. Production ancienne conservée.

Le candidat c5548b3 reste historique et ne doit pas être redéployé : préparer un
nouvel assemblage après qualification/publication des sources corrigées. Conserver
le même binaire Nix 296b7c89 (graphe Lisp inchangé) et les interfaces qualifiées ;
rejouer les suites réellement affectées. Sauvegarde fraîche/restauration/retour
restent obligatoires avant activation. Aucun assouplissement du contrat SQL.

Constat de reprise : six dépôts préservés ; seuls les changements ci-dessus sont
nouveaux, rapport MCP non commité conservé. Image SBCL/CL-MCP/Swank et Tron existants
écoutent toujours localement ; aucune reconnexion ni qualifier synthétique.
L'accès CLI GitHub est de nouveau fonctionnel (lecture du compte réussie).

Après correction : publier Vision avant manifeste, qualification centrale exacte,
sceller et promouvoir le même artefact, préparation/restauration/bascule par CI
centrale uniquement, accès MCP réel/invariants/redémarrage/services voisins.
Passer à Kanidm seulement après constat personnel de l'étape 1 en production.

## États de promotion antérieurs — historique conservé

## Point de reprise antérieur — restauration isolée à corriger

Run38184424703 terminé en échec pendant restauration isolée (message générique),
avant tout appel activer. Préparation réutilisée, ancien service non basculé.
Erreur détaillée conservée privée sur VPS ; diagnostic fermé étendu aux seules
classes/lignes, sans message de condition/source/SQL. Constat exact à lire avant
nouvelle restauration ; aucun re-déclenchement aveugle de l’opération.

Préparation réelle38184214522/afbe6f6 réussie : paquet296b7, candidatNix
r4czzy6icdfc14jiqs93kk6jc83cc1p1, dry-activate/Nginx/invariants/IdentMap validés,
sondes des services existants réussies ; aucune activation à cette étape.
Déploiement38184424703/afbe6f6 déclenché23:28:45UTC, état à constater avant toute
nouvelle opération. Il réutilise la préparation, restaure une sauvegarde fraîche
isolément avec ACL/retour puis active seulement si tout passe. Ne pas supposer
qu’une interruption arrête ce run ni redéclencher sans voir son issue.

Candidat actif c5548b354839db1f8875ec28a3ce7a8c810c42a4, bundle complet vérifié
localement. Transport8c57d52d0a54f0fe0aa1d2ee320483ddc4523edb, trois parties,109014944octets,
chiffrée710a430e8dbb6e62d7506ed05cd40949e6b201f496ccd292bfa1d4cffd09475.
Ordre Nix corrigé, ancien préfixe IdentMap conservé ; candidats métier/frontend
inchangés. Nouvelle préparation fermée à constater avant restauration/bascule.
Production ancienne, étape1 non déployée, Kanidm non commencé.

Préparation38183623725/8b9d7be échoue avant activation sur l’ordre IdentMap.
Diagnostic fermé38183852193/563c0ed réussi : assertions Nix vraies, aucun invariant
préservé modifié, seuls les7ajouts attendus ; lignes existantes2/après9, aucune
activation. PostgreSQL officiel ajoute sa ligne native à mkAfter1500 ; nos
7entrées étaient intercalées avant celle-ci. Module métier passe à mkOrder1600,
ancien préfixe exact et refus des autres accès conservés. Régression de cet ordre
ajoutée ; module Nix inclus dans entrées/impact de la suite sécurité. Pas de
modification des données, du binaire ou des interfaces. Nouvelle préparation
après qualification/scellement des opérateurs corrigés ; ne pas rejouer l’ancienne.

Opérateurs qualifiés56b6ef7be73acaf90d7fe2ece3335100873f6ff0.
Scellement et verifier_bundle COMPLET réussis localement, mêmes35reçus/sources
et même image296b7. Archive109013762octets, chiffré80ee4b46c3866150213f8a3265edf9a53e57ac1a3212b1f0e4491e896fff62da.
Transport publiébbc2aee495fbe1982884dfefaba1600a503b1fba, brancheartefacts/monolithe-56b6ef7be73a.
Descripteur central actualisé. Nouvelle préparation fermée à lancer ; production
ancienne conservée, aucune activation/restauration de données effectuée.
Les préparations précédentes ci-dessous sont historiques, sans effet applicatif.

Préparation38183043781/c7da012 terminée en échec avant toute activation :
verifier_bundle refusait le verrou historique Logique (objets Git SHA-1 comparés
à SHA-256).75fichiers vérifiés réellement avec leur format historique ; aucun
fichier consommé différent. Format déclaré dans le manifeste, contrôleur corrigé,
quatre régressions (acceptation, altération, format absent/inconnu) ajoutées ;
integration-securite et editorial passent. SHA-256 du bundle/reçus inchangé.
Scelleur applique désormais le même verifier_bundle complet localement avant
transport. Contrôle complet local05d1ade a refusé le .pyc créé par son import après scellement ;
aucun transport effectué. Contrôle déplacé dans un processus Python-B de lecture,
sans bytecode et avec ses modules propres. Nouveau sceau/opérateurs à publier ;
anciens stages/chiffrés conservés,
aucune tentative aveugle ni modification des données. Interfaces/binaire inchangés.

Sources qualifiées publiées b0140de44c761f202271a436882cd05195b18fd3.
Scellement réussi vers state/candidats-scelles/b0140de-transport :109011960octets,
chiffré8f338e0f2cd166aab2e56a8ccfb4c41f46f408b8df2fe5a83d1ba12f3f3611f2.
Transport publié1d64b9ac20af91cdcb61b11b01b2a7d59e8ce5db, trois parties40Mio,
branche artefacts/monolithe-b0140de44c76. Descripteur central lié aux sources et
qualification d’amendement réussie. Première tentative locale de scellement :
Nix absent du PATH, dossier vide conservé ; reprise réussie avec le Nix existant
/home/agent/.nix-profile/bin, aucune installation ni reconstruction.
Prochaine opération fermée : préparation centrale sans activation, puis
restauration fraîche/retour/bascule et sondes réelles. Production toujours ancienne.

Même tâche et architecture C ; image interactive saine conservée, aucun nouveau
qualifier MCP synthétique, aucune reconnexion. Production encore ancienne,
Keycloak conservé ; étape 1 non déployée, Kanidm non commencé.

Révisions publiées : Vision649122b, Math68df529 (master), Style27111a9,
Logiqued76f007, Signaturee9d9d34 ; hashes complets dans manifest.json.
Vision/Math consomment Style271 ; Logique conserve son verrou fbdb qualifié.
Les interfaces exactes passent : Math base14,7407s et96/96477,2098s ; Vision
interface62,7724s/navigateur-MCP23,7191s ; Stylebase131,6359s/logo264,5806s
(94parcours,2cas spécifiques à l’autre moteur) ; Logique119,9275s/correcteur14,6842s ;
Signature3,9372s. Typographie réellement peinte et contextes aux trois tailles,
contrôles AST208 et fixtures négatives exécutés. Anciennes traces conservées.

Session67854 terminée0. Elle a cependant reconstruit le fichier candidat local
au début de matheval-postgresql, faute de MRJAM_CONSTRUCTION_NIX. Reconstruction
d7c4cb1 conservée séparément dans state/artefacts, sans promotion. L’original Nix
296b7c89 reste intact dans son store ; sources Lisp inchangées. Fichier local
rétabli depuis ce store, puis qualifier_existant exécuté (21,1274s) avec provenance
originale. Qualificateur corrigé : sidecar Nix détecté, reconstruction directe
refusée ;2régressions passent. Aucun résultat d7c4 présenté comme preuve296b7.
Session56680 terminée0 : MathevalPostgreSQL22,565s/VisionPostgreSQL117,2998s/
sélection1,0666s réussis. SQLnative original16,8229s passe (session83150 terminée0).
Les35suites finales passent :34réutilisations exactes/éditorial seul rejoué.
Puis reçu MathevalPostgreSQL explicitement lié à296b7 et sélection requalifiés.
Scelleur : dernier contrôle exact avant soumission ; aucune preuve de production.
Ancien résumé archivé exactement, nouveau résumé local sans attestation CI.

Environnement exact non secret : state/qualification-env.sh ; SBCL_HOME et trois
DSOs Nix, venv navigateur existant, outils PDF inchangés. Aucun navigateur en
parallèle ni empreinte Firefox pendant son exécution. Rapport MCP non commité
préservé. Ancien résumé archivé exactement, état local consolidé ; publier les sources
centrales puis sceller le
même binaire296b7 et les quatre candidats frontend ; soumission chiffrée par Git,
préparation centrale sans activation puis restauration fraîche/retour et bascule.
Référence VPS récente38178534125 ; accès MCP réel lecture politique/séances obtenu
avant bascule, aucune écriture production. Comparer après déploiement.

## Qualification intermédiaire conservée — avant contrôle final des reçus

Infra publiée7ad2dbe (main vérifié) ; sources centrales complémentaires non
commitées préservées. Sources actuelles publiées :
Style27111a95d0222c634e55fb2e3ff8e45041b40b16,
Vision649122bb45eeaf558caa626c85b8a52b35fe8c73,
Math68df529042609561329e757145a187ca079a5cea,
Logiqued76f0074efa066098ec95c89cbf6d14da8c296cd,
Signaturee9d9d34d353422c2993cd1bc7c3c626f503bb5e0. Manifeste exact actualisé,
amendement NON qualifié. Production inchangée, étape1 non déployée, Kanidm non
commencé. Seule référence VPS en lecture seule38178534125 déclenchée ; pas SQL
mutant ni activation.

Session88512 terminée : Style271 base131,6359s ; Vision649 navigateur23,7191s
et interface62,7724s réussis. Construction Mathd817 refusée par le garde sources
(tracea98d9f111d69) : cinq amorçages suivis avaient des empreintes Elm anciennes.
Générateur existant build:main exécuté depuis l’atelier central, diff uniquement
cinq références ?v= (ni corpus ni autre source), publié68df529.

Session67854 à constater (observation, aucun PID constant) : Math68df construit,
candidat matheval-68df52904260-d69249b0/ensemble53e0fb3dfafcc9ba8791c7fa3510244be08a5d1fad1c450b5b3ebb4a45d38a01.
Caméra : 6/6 réussis (trois répétitions par moteur),51,5s ; trace ciblée privée
matheval-diagnostic-359dd4dfa881, ne remplace pas campagne complète. Base/96 en
cours puis Stylelogo271 puis12suites SBCL natives/VisionPostgreSQL/référence
historique indépendante. Tous les anciens shells12668/8233/64118/38282/88512 ont
terminé ; aucune reprise aveugle. STRICTEMENT séquentiel/set-e. Logs
state/rapports-frontends/{matheval-qualification-68df529,
style-logo-qualification-27111a9,qualification-native-nix-finale}.txt.
Environnement final : SBCL_HOME explicite vers outilsNix/sbcl/lib/sbcl et PATH
navvenv/SBCLNix/original ; trois MRJAM_LIB* Nix explicites. Les anciens reçus SBCL
empreintaient le SBCL_HOME exploratoire : contrôle natif final assumé sur la
toolchain Nix. Ne remplacer ni les PDF actuels ni l'image interactive saine.

Nouvelle correction justifiée : le test Vision visait .mrjam-ecran puis la
police du conteneur natif non peint ; il mesure maintenant texte/commande réels.
Le socle avait deux listes de polices différentes entre racines/lecteur/dialogue.
Theme.typographie mutualise la liste historique Inter/Aptos/SegoeUI/sansSerif,
police principale et fontes d'identité inchangées ; régression clavier/champ
modale aux trois tailles. Vision/Math consomment exactement271 ; Logique reste à
son verrou qualifiéfbdb, sans adoption non nécessaire. Aucun corpus/métier/modèle
ni bibliothèque tierce/toolchain modifié. Ces nouveaux candidats sont à qualifier.

Les essais intermédiaires ci-dessous sont conservés avec leurs anciennes entrées ;
ils ne sont pas des preuves de la nouvelle typographie.

C et image saine conservées : SBCL83928/Tron129399 constatés, jamais constantes
routées ; ancien79777 distinct/idle préservé. Aucun chargement/reconnexion/debug
nouveau pour le frontend. Contrôleurs MCP ciblés et usages documentés ; aucune
refonte du pont. Preuve historique réelle0,8033s/22appels vérifiée offline sans
réinitialiser fixture ; noyau/bibliothèques/lanceurs/trace inchangés, effets1,
resultat42. Nouveau routage/parser testé séparément8cas. Empreinte preuve dans
reçu, références privées copiées au bundle/préparateur ; aucune nouvelle connexion
ou scénario exécuté prétendu. Rapport MCP historique non commité préservé.

Socle/consommateurs portés : ElmUI/Animator/contextes, lecteur/note/scène/axes,
quatre entrées Math. Corpus/graines/Survey.Model/backend inchangés. Espace/Axes/
GraphiqueSpatial et événements ont des adaptateurs privés bornés ; Tableaux
flex-basis:auto constant corrige hauteur0Firefox (AST/doc/tests). Références
JSgéométriques déplacées verbatim dans docs/tests/references, hors produit.

Candidats propres construits une fois par révision :
Style30c6087e6975-16136a76 ensemble02f4216d, base138,5239s réussie ;
Logiqued76f0074efa0-cd66ef05 ensemble42954783, base139,1341s/correcteur12,8117s réussis ;
Vision2d9f31b existant conservé ; Math0b277f02800e-73b22d87 ensemble093fc670.
Math0b et8f02 assets identiques, seul interface.json change (révision identifiée).
Math8f base16,4047s ; Math0b base14,9149s et 96/96 navigateur477,8515s réussis.
Aucune source canonique modifiée par le harnais corrigé.

Campagnes Math :96pass mais garde sources refuse le harnais534,0746s ; correction
vers copie privée .central-tests-*/e2e,3tests source intacte/chemins/no-overwrite.
Surcharge4CPU/16Gio par3campagnes simultanées : timeouts clavier/Yatelier, seuls
runners arrêtés proprement ; tracesd27518040481/03933b67e84b conservées. Pas de hausse
des timeouts. Cible4scénarios passe63,4647s après sérialisation. Campagne seule8f :
95pass/1échec497,7386s : helper tactile retournait avant retrait aide/rerenduaxes ;
trace72a69aad4d47. Fix canonique helper attend count0 (état, aucun délai fixe),
publié0b277f0. Régression réelle CDPtouch3répétitions passe43,99s, traceafab2d0ebc7f.
Tous anciens résultats restent datés, aucun reçu de réussite fabriqué.

Session12668 terminée : Math0b réussit ; Stylelogo échoue sur les deux premiers
démarrages Chromium simultanés (92pass/2fail/2skip,230,6843s, trace4a43b577abaa).
Traces : création/navigation prennent le budget initial, pas erreur de géométrie.
Le harnais central limite désormais l'atelier à --workers=1 ; délais/assertions
inchangés, régression de commande ajoutée. Dix tests frontend-sources réussis.
Session8233 terminée : Stylelogo94pass/2skip303,5335s, Stylebase137,6476s,
Visioninterface69,1729s, Signature3,9372s passent. Mathbase17,0834s ; navigateur
95pass/1fail478,4127s (tracec9b1b0cee044). La trace prouve __playwright_scroll_top_=3
après la première ArrowRight : la focalisation native défile la page entre les
mesures. Test canonique focalise la scène avant mesure initiale ; précision4 et
assertions inchangées, publié53c1cfa. Aucun produit/corpus/métier modifié.
Reprise séquentielle : construire le candidat Math53 exact → Logique/MCP métier
→ régression caméra trois répétitions → campagne Math entière → qualification
native avec SBCL/contrib/DSOs Nix explicites. Même image interactive conservée.
Aucun autre navigateur en parallèle ; échec analysé avant toute reprise.
Session64118 arrêtée normalement sur échec navigateur Vision49,2026s : ancien
sélecteur .mrjam-ecran absent, trace6f52d8bb6f7a ; pas erreur métier/SQL. Test utilise
le repère accessible main, assertions de police page/dialogue conservées ;
publié068a9c6. Logique119,9275s/correcteur14,6842s réussis avant cet arrêt.
Math53 construit (b294a025), seul interface.json différent de0b. La régression
caméra et campagne complète n'ont PAS encore été exécutées pour53.


Autres preuves :208AST/6ressources/3fixtures18,7958s, géométrie336cas40,2ms ;
sélection20/source9/transport/isolation/migration/classification privés passent.
VisionPostgreSQL289,8156s réussie ; SQLnative reçu réutilisé exact. Psycopg3.2.5
venv navigateur existant (même Python3.12.14/binaire), pas installation. Référence
historique Node sur base indépendante16,2075s après correction empreinteenv ;
aucun Nodebackend cible/production. Nativepures/Lisp inchangés à réutiliser exact.

Changements centraux : orchestration scientifique/lecture/note/géométrie, AST et
ressources ; dépendances inventoriées déjà autorisées (aucun ajout opportuniste).
Empreintes DSOs seulement suites natives,2régressions ; reçus frontend inchangés
réutilisables sous env Nix. Préparateur utilise Style réellement consommé par
Vision/Logique, archives immuables privées/3régressions ; garde sources conservée.
Sondes VPS vérifient les4ElmMath +interop, pas seulement enquete.js. Historique
qualification-locale.json non réécrit ; archiver exactement avant résumé actuel.

Après jobs : comparer35reçus dans env final (SBCLNix/navvenv/DSOs existants, PDF
actuels ; ne pas remplacer par popplerNix). Pas de lecture empreinteFirefox quand
il tourne : son verrou transitoire est refusé, attendre fin des campagnes.
Qualifier processus Lisp propre à étape pertinente, préserver imageinteractive.
Commiter/pousser composants avant manifeste, sceller mêmeNix296b7c89 déjà propre,
transportchiffré central puispréparer/restaurer/basculer/sondes/redémarrage/invariants.
Backup ancien02:40 doit être réévalué, pas restauré sur SQLrécent pour retour.
Référence centrale fraîche38178534125/7ad2dbe réussie en lecture seule21:58UTC :
générationr6s7ags3 inchangée ; Vision1compteactif/admin,1identité,0orphelin/0liencroisé,
0séanceouverte ; Math1admin/1corpus/3participations toutes ouvertes. Mémoire/latences
agrégées dans state/reference-38178534125/reference.json. Téléchargement artefact
refusé403 ; même JSON complet extrait du log du run, sans nouveau dispatch.
Connecteur Vision de cet agent réellement appelé : lire_politique et lister_seances
réussis/total0, aucune écriture ni contenu personnel journalisé. À comparer après
bascule ; cette lecture ne qualifie pas encore la nouvelle image en production.


Remote relu : maininfra15496df ; PagesMath workflow/dynamicbuiltinactive mais aucun
run depuis28septembre, malgré pushesOct11 ; workflowsStyle/Logique historiques
manuellementdisabled. Protectionsmain/master403 «Resource not accessible by
integration» ; environmentvps-production lisible/branchpolicy seulement. Pages
PUTdisable422 historique concerne builtin, ne pas le confondre avec suppression
site. Vérifier mécanisme autorisé après publicationcentrale sans réactivation
satellite. Ne prétendre aucun nettoyage inaccessible accompli. Ensuite étape1
réellement constatée avant Kanidm automatique. Références/histoire ci-dessous.

## Références et résultats historiques conservés

Même tâche, état conservé. Aucun reset/nettoyage, ni nouvelle bascule.
Production : génération r6s7ags3, ancienne architecture, Keycloak provisoire ;
étape 1 non terminée, Kanidm non commencé. Aucun contenu/compte/séance/participation
fictif créé, fermé ou effacé en production. Dernière référence38118876078 : un
compte Vision/une identité, liens cohérents, trois participations Matheval ouvertes.

État avant la publication de cette reprise : infrastructure ad98feb ; branche locale
reorganisation/assemblage-central-20261011. Vision 1ef7174, Matheval/master 5e234c0,
Logique 032b4f5, Style c9663ce (chronologie et adaptateur accessibles publiés ; autres vues encore à porter), Signature e9d9d34. Consignes/guides des cinq composants
publiés avec archives exactes ; root intègre les corrections Nix/préparateur et
le refus de promotion avant qualification de l’amendement. Aucun AGENTS imbriqué/override trouvé dans les sources
actives ciblées ; relecture des six fichiers effectuée. Aucun run de promotion
actif, ni build/migration locale en cours au constat.

Image de tâche SBCL2.6.4 PID83928/session27658 conservée et saine, métier chargé ;
contrôle de reprise court réussi. L’ancien PID79777/SBCL2.5 reste séparé et idle :
ne pas le présenter comme la session commune. Swank4105/cl-mcp4106 dans ce PID ; Tron4107/PID129399, processus outil seulement.
Sources officielles/35 bibliothèques Nix auditées/verrouillées. Connexion réelle
agent→pont HTTP local qualifiée : marqueur/PID/objet11→12, condition/pile/locaux40/2,
correction enregistrée compilée/restart42, effet1 avant/après. Scénario canonique
0,8729s ; trois assertions ASDF confirmées par marqueur, compte générique amont inconnu.
Ports loopback, aucun catalogue natif hébergé prétendu modifié. Limites backtrace
RPC et installation de skills documentées dans outils/audit-mcp.md.

Travail conservé : bibliothèques ASDF Matheval/Vision/auxiliaires, serveur commun,
contrats/isolation/SQL/états durables, catalogue/sélecteur/reçus, absence de CI
satellite. Candidat Nix propre296b7c89 (12486040octets), sources158e4a5, SBCL2.6.4/
ASDF3.3.1/Nixpkgs c5c4a43. Les 31suites antérieures passent, dont Matheval56/56,
Vision API/MCP40parcours multi-comptes, RLS30/6, recherche réelle existante et
interfaces. Ces preuves restent datées ; elles ne qualifient pas l’amendement.

Promotion : asset GitHub refusé401 ; repli Git chiffré108401335octets, trois parties,
commit transport29cde31, bundle/opérateurse522c2a. Transfert/import NAR réussis ;
préparation38126827329@2f1a7c2 refusée avant activation. Diagnostic38127124960@a209c00
réussi : toutes assertions et autres invariants identiques, seuls chemins générés
PG hba_file/ident_file changent pour le peer du compte commun. Correction locale :
comparer toutes autres propriétés et contrôler les seuls ajouts HBA/IdentMap exacts
sans modifier les règles antérieures ; 13 régressions passent, incluant le refus
d’un candidat antérieur/en attente avant transfert. Correction publiée c6ecf2d ; pas encore requalifiée sur VPS. Stage privé /root/mrjam-assemblages/e522c2a… ; aucune
preparation.json ou activation.json. Aucune opération à effets de bord incertaine.

Plan actualisé et critères de passage :

1. Consolider les consignes/guides/manifestes/reprise selon l’amendement ; relire
   explicitement, verrouiller la promotion en attente de nouvelle qualification.
2. MCP installé/verrouillé et scénario réel conservé dans le rapport historique.
   Maintenir C, contrôler la cible après reconnexion, borner les chemins distants.
   Ne pas rejouer le qualifier synthétique en contrôle de santé. Continuer dans
   l'image saine ; test final propre distinct lorsque pertinent.
3. Auditer/verrouiller elm-animator/elm-review ; règles mutualisées/testées,
   alias/exposing/frontières/adaptateurs, fixture interdite qui fait échouer
   la commande canonique, contrôles HTML/CSS/JS complémentaires.
4. Corriger le socle style et interfaces affectées ; Continuous UI réel,
   focus/clavier/reduced-motion/interruption/inversion/arrêt ; requalifier selon
   impact. Réutiliser les reçus Lisp dont les entrées sont inchangées.
5. Reprendre Nix réel puis backup/restauration isolée/ACL/retour, accès API/MCP,
   même binaire et nouvelles ressources qualifiées ; bascule courte/redémarrage/
   invariants/sondes. Ni ancienne DB restaurée ni séances ouvertes clôturées.
6. Constater étape 1 en production, puis Kanidm automatiquement : nouvel IdP réel,
   politiques/sessions/révocations/MCP/panneau et propriétaire métier stable.
   Enrôlement personnel distinct ; supprimer Keycloak après accès/récupération sûrs.

Références : manifest.json, DEVELOPPEMENT.md, FRONTENDS.md, PROMOTION.md,
SECURITE.md, JOURNAL.md, reference-production.json et sauvegarde-transition.json.
Ancien protocole/registres/résultats gardés historiques sans faux acquittements.
APIs protections/environments/deploy keys403 ; Pages intégré Matheval disable422.
Ne pas prétendre leur nettoyage distant achevé. Sauvegardes/tiers conservés.

Travail affecté en cours : elm-review Nix installé (paquet2.13.5, CLI annonce2.13.4),
règles/fixtures/contrôle de qualification à intégrer ; elm-animator1.1.1 existant
référence de Matheval. L’atelier logo emploie déjà2.0.0, confirmé officiel ;
API incompatible, cible commune2.0.0 après portage explicite et qualification. Présentation CSS/HTML existante dans
Matheval/Style et adaptateurs applicatifs à corriger ; aucune conformité annoncée.
Image métier296b7c89 et suites backend inchangées restent conservées.

elm-review : configuration unique2.15.0 + règle existante unused1.2.3 + règle
AST MrJam.Presentation. 21 cas réussis et commande canonique : fixture conforme
acceptée, H.div rejeté, dépendance inutilisée rejetée (noms de règles contrôlés).
Guards sur construction et qualification de candidats existants, aucune suppression.
Sources partagées effectivement consommées : 339 violations Style/330 Vision/
466 Matheval/406 Logique, principalement les mêmes échappatoires du socle à
corriger une fois puis adopter à révision exacte. Ces échecs bloquent la promotion.
L’atelier logo est un second projet Elm dans Style : étendre le contrôle à son
elm.json, conserver la géométrie et mutualiser son lecteur/horloge Animator.

Socle de transitions publié0ea000d : lecteur Echo.Player déplacé sans doublon
vers MrJam.Transitions, utilisé par Main/abonnementLecteur. 82 anciens tests
passent ; 8 nouvelles propriétés ciblées passent (102ms), après constat que
Timeline.isRunning est vrai à init dans2.0.0 : le socle borne explicitement les
frames aux changements demandés. Réduction/inversion/continuité/cible immédiate
et durée nulle qualifiées en unités, navigateur encore requis. Consommateurs
Vision/Math/Logique restent sur leurs pins de style antérieurs jusqu'au portage.
Complément HTML/CSS/JS avec HTMLParser/Babel déjà dans Playwright1.58.2 : 3tests
(9casJS dont alias/calculé/optionnel) passent. Garde canonique branché sur build
et qualification ; rapports actuels restent en échec, dont atelier logo690
violations avant déplacement. Pas de promotion, pas de Kanidm commencé.

Style6f1a8eb publié : libellés accessibles portés vers Element.Region.description
et lienExterne vers Element.newTabLink (noopener/noreferrer natifs), galerie
compile incrémentalement. Travail suivant non commité : adaptateur DOM ID/ARIA
controls-expanded-describedby/tabindex strict et adopteurs, sans CSS. Classement
font/SVG/dialogue et portage Theme/CSS restent à poursuivre ; couleurs de marques
doit conserver leur sens avec contexte explicite, pas par CSS variables globales.
Raccordement MCP toujours sain PID83928/poolNIL/métierT ; aucun déploiement.

Progression conservée : Style c9663ce publie Accessibilite (ID, relations ARIA et
tabindex -1/0). Cinq tests DOM réussis247ms, aucune classe/style/nom arbitraire.
Règles AST26cas + fixtures canoniques + complément ressources3tests qualifiés
localement8,4137s ; assertions de test strictement bornées, renderers Animator
HTML/CSS interdits. Atelier/socle encore625violations, aucune conformité déclarée.
Image saine83928/poolNIL/métierT confirmée ; tentative de lecture d'un nom de
package incorrect refusée avant toute évaluation, corrigée à partir de la source.
Suite à poursuivre : contexte explicite de palette pour préserver les marques
sans cascade CSS, présentation elm-ui et adaptateurs manquants ; consommateurs
toujours verrouillés aux anciennes révisions, preuves frontend à renouveler.

## Interruption pour audit MCP — état historique du 11 octobre 2026, 11:55 UTC

**État historique : chantier suspendu pendant l’audit. Interruption close par
l’amendement ciblé de reprise ; voir l’état actuel ci-dessous.** Aucune consigne,
architecture, dépendance ou production modifiée par l’audit ; aucun commit,
nouvelle condition, compilation, restart ou suite de tests. Rapport autonome :
[RAPPORT-EXPERIENCE-MCP-20261011.md](RAPPORT-EXPERIENCE-MCP-20261011.md), onze
sections, preuves et plan exact de reprise. Constats privés et empreintes :
state/outils-mcp/audit-20261011.json ; état Actions dans audit-actions-20261011.json.

HEAD infra ad98feb812017391621a3533ca696b6137c456ee, branche locale
reorganisation/assemblage-central-20261011. Autres HEADs inchangés : Vision
1ef7174/main, Math 5e234c0/master, Logique 032b4f5/main, Style c9663ce/main,
Signature e9d9d34/main. Ces quatre composants hors Style sont propres.

Travail interrompu non commité, conservé :
- Infra : assemblage/elm-review/src/MrJam/Presentation.elm et
  assemblage/elm-review/tests/PresentationTest.elm.
- Style : src/MrJam.elm ; src/MrJam/{Theme,Controles,Disposition,Documents,
  Fenetres,Identite}.elm ; src/MrJam/Adaptateurs/Accessibilite.elm.
- Nouveaux fichiers Style : exemples/Contextes.elm, src/MrJam/Contexte.elm,
  src/MrJam/Adaptateurs/{Dialogue,Selection}.elm et tests/contextes.py.

Palette immuable explicite Theme.Contexte/MrJam.Contexte et MrJam.pour,
composants elm-ui colorés sans cascade, select/dialog natifs étroits,
focus explicitement rétabli après déplacement keyed. Tests ciblés Contextes
passés320/768/1440px (4,117659s), JS state/contextes.js SHA2b8e1951a4683953684a40f4d6b68c2ec7faca67948c456f2bb5b18ebab49bf7.
Nouveau test pas encore raccordé à la commande centrale, autres contextes/vues,
typographie et consommateurs à terminer. Règle AST37cas passent ; reçu canonique
frontend-regles9,5305s valide ces contrôles, pas la conformité des applications.
Dernière analyse réelle socle/atelier541violations/exit1. Aucun nouveau candidat
frontend qualifié ni changement des trois pins Style consommés. Les ajouts ARIA
suivants et les autres composants de contexte étaient prévus, pas encore écrits.

État Lisp lu sans mutation applicative : PID83928 SBCL2.6.4/ASDF3.3.1, métierT,
cl-mcp4106/Swank4105, poolNIL, pool-status0workers/0sessions affectées.
MCP_NO_WORKER_POOL="1" ; MCP_WORKER_SWANK/INIT_SYSTEM/INIT_ENTRY non définies.
TronPID129399/4107 connecté au Swank83928 ; ancienne image79777 séparée et
préservée. Objet12, effets1, résultat42 et même marqueur lus des deux côtés.
Aucun débogage suspendu : THREADNIL/LEVEL0. Les outils REPL/Swank visent
l’application ; les inspecteurs/mesures locaux Tron ne sont pas cette image
(frontière constatée dans le code, détaillée au rapport). Les outils natifs
ne sont pas enregistrés dans le catalogue hébergé ; pont HTTP réellement utilisé.

Trace synthétique antérieure22appels, empreinte canonique cd79880769a83adab908b5e25dc80040c8e0e159aff6dc821873d22b015eae9a
recalculée conforme ; toutes sources du reçu actuel inchangées. Ne pas en déduire
un total d’appels de session. Ne pas lancer qualifier-mcp.py comme simple sonde :
il réinitialise la fixture et provoque une condition. Aucune opération locale
de build/test/migration en cours ; API GitHub de l’assembleur0in_progress,
0queued,0waiting. Production non resondée pendant l’audit, dernière preuve
38118876078/ancienne générationr6s7ags3 ; aucune bascule/activation achevée.

Reprise après instructions seulement : constater mutations concurrentes/PID/
débogage ; conserver image saine ou reconstruire le seul environnement absent ;
appliquer les nouveaux choix explicitement, puis terminer le portage frontend et
ses commandes bloquantes. Publier composants avant manifeste, requalifier selon
impact ; reprendre Nix/HBA/promotion/backup/restauration/retour et sondes réelles.
Étape1 non terminée, Kanidm non commencé. Aucun reset ni répétition d’opération
à effets de bord incertaine nécessaire pour cet audit.

## Reprise actuelle après audit — architecture C conservée

Interruption levée par instruction explicite, même tâche reprise sans reset.
Image saine conservée, trois listeners loopback et identité croisée relus :
CL-MCP/Tron même PID83928, marqueur/objet12/effets1/résultat42 ; pool arrêté,
aucun débogage suspendu. Ces PID restent des observations, jamais paramètres fixes.
Les fichiers de chantier sont inchangés au constat ; aucune commande interrompue
encore active hormis les images. Aucune production modifiée ou campagne relancée.

Consignes centrales/AGENTS Lisp actualisés : architecture C, cibles distinctes,
édition structurelle facultative, sources canoniques, discipline DEBUG/restarts/
effets, revalidation après reconnexion et test propre distinct permis.
Pont HTTP borné aux cinq chemins Tron distants qualifiés, trois sondes et connexion
Swank explicitement locale ; locaux/fallbacks/inconnus refusés avant transport,
statut distant obligatoire avant opération. Garde de routage sans sandbox.
Cinq tests ciblés du pont passent0,012s, sans serveur Lisp ni mutation du calcul.
Ancienne qualification synthétique conservée historiquement ; son empreinte du
pont ne qualifie pas la modification actuelle, aucun scénario réinitialisé.

Plan actif : terminer le socle/contextes ElmUI et intégrer Contextes aux commandes
centrales ; corriger les violations réelles puis adopter les révisions dans les
consommateurs et qualifier les parcours affectés. Ensuite reprendre qualification
Nix/HBA/préconditions, promotion/sondes de l’étape1, puis Kanidm après constat réel.
Aucune nouvelle validation manuelle requise pour les décisions déjà arrêtées.

## Progression de la reprise ciblée — 11 octobre 2026

Consignes MCP publiées : Vision 9cb1fb145d6a, Math 78137b0a0e9e. Aucun code métier
modifié dans ces deux commits. Manifeste actualisé après leurs push, protection
amendement-en-cours conservée ; aucune promotion ni campagne distante lancée.
Pont : six tests isolés et reçu central outils-routage réussis0,3246s ; un diff
limité au pont sélectionne cette suite,33 évitées. Le qualifier vérifie le restart
actuel par nom/sens/position/thread/niveau et le relit après compilation ; contrôle
pur testé, scénario suspendu non rejoué. Rapport d'audit inchangé, preuve historique.

Socle frontend en sources, non encore publié/adopté : contextes explicites pour
MrJam, Documents, Donnees, Tableaux, Disposition et Pictogrammes ; rôles/états ARIA
bornés. Adaptateurs Saisie/Texte/Pictogramme sans nouvelle dépendance. Le nœud
texte échappé corrige le white-space normal imposé aux .t d'elm-ui. Le composant
Animations.deploiement impose minimum0, nécessaire au repli réel de sa hauteur.
Le raccord animations.js transmet uniquement matchMedia au port, sans animation
JS ni horloge ; corps de callback Playwright explicite pour éviter l'invocation
immédiate du disposer retourné (cause du second échec du test, pas bug du raccord).

56 cas AST passent459ms ; huit tests DOM d'accessibilité précédents conservés.
Contextes compile avec Galerie/Bibliotheque ; navigateur320/768/1440 réussi sur
JS SHA b3537d128fb954467baf10fb4ea3e96bfcd376b64765f2b48167d74007babce3 :
couleurs OKLCH de trois marques, isolation après réordonnancement/focus, select,
String/Int, tableau et palette, limite/Entrée unique, zéro/vide, dates, menu Échap/
focus, espaces/retours/mot long, SVG original, cibles44px, progression bornée,
inversions/interactions rapides/saisie pendant mouvement/arrêt des frames,
réduction pendant mouvement et au chargement, modale inerte/clavier/focus/deux
fermetures exactes. Nouveau test raccordé à la qualification centrale Style ;
package.json compile Contextes et fait partie des entrées de reçus.

Dernier contrôle réel complet de l'atelier+socle :421 violations, exit1 ; le
contrôle n'a pas atteint le second projet Style. Répartition : Echo.Render121,
Main23, Palette183, Philosophie7, Shared.Licorne2, Shared.Ui19, Blocs11,
Disposition26, Identite16, Vitrine13. Aucun écart dans les adaptateurs nouvellement
bornés, MrJam/Controles/Documents/Donnees/Lecture/Tableaux ; aucune suppression.
Cette analyse précède le nouveau composant Animations, à recontrôler ensuite.
Les pins Style des consommateurs restent historiques, aucune interface globale
qualifiée. À reprendre : typographie réservée, dialogues composés/companions,
Vitrine/Blocs, atelier ; adopter ensuite les nouvelles sources exactes, vérifier
les parcours existants et ressources, puis reprendre l'étape1 réelle et Kanidm.
Image Lisp persistante conservée, aucun DEBUG ouvert au constat, aucune cible
ni objet ancien réinventé. Production inchangée depuis les preuves précédentes.

Typographie ajoutée au socle après le reçu précédent : Typographie ne permet
que les classes littérales de la bibliothèque générée Signature et ses métriques
absentes de l'API elm-ui (1,183/baseline-.005em/synthèse/sélection). Les marqueurs
applicatifs deviennent data-mrjam-marque. Signature en ligne ne force pas une
seconde boîte d'interligne : cause du surplus42,621px trouvée en mode standards
(la sonde sans doctype en mode quirks ne reproduisait pas ce défaut). Variante
signatureEnLigne conserve la ligne commune. Fonte/contours/blobs inchangés.
Les validateurs peints précédents de Vision sont déplacés sans duplication dans
Style/tests/typographie.py ; Vision les importe depuis STYLE_MRJAM_SOURCE et
refuse une source verrouillée dépourvue du helper. Ce diff Vision est encore
non commité, pin Style non adopté : ne pas prétendre Vision qualifiée.
Contextes utilise Signature/web + Parisienne.ttf en FontFace, ressources originales
non copiées dans le bundle ; argument --signature central, entrées fonts/ttf et
helper commun ajoutées aux reçus. Nouveau navigateur complet réussi sur JS SHA
76f5d76e3694b92dd991212c92d2dccac2e8ff433778a6d1bef8eb3a4acb8dc5,
320/768/1440px, capitales et motifs de points agrandis identiques/interligne borné.
Reçu central frontend-regles9,8957s :60 tests AST +3 tests ressources et fixtures
conforme/interdite/inutilisée avec noms de règles vérifiés. Dernière analyse réelle
405 violations/exit1, Identite désormais conforme à cette règle ; reste du portage
bloquant. Consignes/pont publiés infra9801479 ; aucun déploiement. Prochaine étape
concrète : Vitrine (dimensions explicites et compléments contrôlés elm-ui), ses
consommateurs Galerie/Vision, puis dialogues/constructions/atelier. Préserver tous
les diffs Style ; publier composants avant le manifeste exact, promotion en attente.

## Chronologie frontend antérieure — historique, remplacée par le point actif

Infra publiée15496df ; lecteurs/notes communs publiés, géométrie pure en cours.
Style113169d (révision complète dans le manifeste) et
Logiqued76f007 (révision complète dans le manifeste) publiés.
Vision2d9f31bff90eed0dd330e4a568afaae92ce761f2, Math/master78137b0 et
Signaturee9d9d34 conservés. Production inchangée : étape1 non déployée,
Kanidm non commencé. Aucune CI ni opération de données déclenchée.
Rapport MCP historique non commité préservé. ArchitectureC et image saine
conservées (processus constatés83928/129399), sans reconnexion ni qualifier.

Style : socle/contextes/TeX/vidéo/gestes publiés ; iframe stable, générations,
façades publiques, frontière des adaptateurs privés. Candidat
state/frontends-candidats/style-fbdb9dbb0c72-78eef4b9,
ensemble59108d807326d74d1b58fa3e1c8d4d3b5d431ce2ab8a70d33b7e176d0db33a82.
Qualification base81,0367s, complément201,1529s :98tests Elm,
94parcours Chromium/Firefox,16comparaisons raster, géométrie/exports identiques.
Médias320/768/1440 : KaTeX réel, SDK synthétique, délai réel15s, focus/reprise,
source refusée et génération obsolète. Vidéo bornée à un lecteur visible par page.

Vision : candidat2d9f31bff90e-29425f7e / ensemble
a8e9f4e8186b194b09d7318aaea0cb94cb2f79b7d157680e4b041fda95a20198,
qualification48,3092s conservée, Style196ab46 effectivement consommé inchangé.
Les outils d'orchestration modifiés sont requalifiés au jalon final selon impact.

Logique : vues et atelier elm-ui, indice Animator mesuré, réductions initiale/live,
focus/historique/MCP et actions indépendants des animations. Geste hors Document,
fantôme commun inerte sans identifiants, horloge active seulement pendant geste.
JS limité aux pointeurs/hit-test/scroll/fichiers/reprise ; aucune CSS applicative.
Retarget tactile Chromium corrigé par prise géométrique ; scroll natif conservé.
Candidat7137ff286284-c36463f0 / ensemble
c604bd4d54cc35e9d0ff2574b1dc2adef262af61b437125fabad14ad0f6f1294,
qualification navigateur132,2951s :58exercices303TeX12bilans12vidéos,
3contrats WebMCP,4largeurs ;6ContinuousUI ;13atelier+2tactiles ;polices originales.
Deux tests historiques exigeaient CSS retirée/ancien hash du pont ; corrigés sans
changer corpus/correcteur. Autre ancien contrôle visait video.js supprimé : vise
maintenant les lecteurs communs et atelier.js. La révisiond76f007 ne change que
ce script ; unité centrale12,3742s réussie (190correcteur/299TeX/14Python/97atelier,
format), sans site navigateur artificiellement requis. Le reçu navigateur reste
celui de7137ff2 ; aucune qualification navigateur revendiquée pourd76f007.
Aligner candidat exact au jalon final avant promotion.

Contrôles centraux :136tests AST+6ressources+3fixtures réellement refusées,
10,5718s ;6tests de sources0,6622s ;18tests de sélection0,8401s.
Pas de suppressions/exclusions ni seuils abaissés. Reçus privés machine dans
state/recus, confiance locale non attestée, jamais autorisation de publication.
Stade exploratoire Logique et captures conservés dans state ; pas candidat.

Matheval en cours, non commité : lecteur scientifique commun Style48cb06a,
142tests AST11,9332s, qualification centrale Style91,9703s sur candidat
style-48cb06aaa08f-befceaca / ensemble
2514d258c02f6ae10da64f98153d67b7491596fef15f28c8e6aab55858b75ad9.
Huit cas scientifiques aux3largeurs320/390/1363 réussis, retraits comparés à
l'ancien rich-text, TeX réel/HTML échappé/Markdown/soumission bornée. Le reçu
Style-logo précédent reste historique ; additions hors logo pas encore finalisées.
Administration : Math.document, métadonnées publiques, soumission INPUT et
contexte Matheval, CSS locale retirée, compile incrémentale22puis2modules.
Trois parcours Chromium réussis8,4s sur binaire Nix296b7c89/PG jetable : accès,
activation/Entrée, corpus/statistiques/réponses avec zéro/absence et déconnexion.
Première fixture incomplète (assets absents) et environnement DSO distribution
au lieu de Nix : démarrage refusé avant parcours ; fixture préservée. Avec DSO
Nix, démarrage réussi mais instrumentation répétée dans la fixture réutilisée :
refus de tests. Nouvelle fixture neuve depuis sources canoniques, trois succès.
Aucune répétition d'effets production, aucun backend Node. Config Playwright
locale n'en lance plus ; la commande centrale possède le serveur SBCL isolé.
Prototype et DemoCard en cours, non commité : Main elm-ui/TableSpatiale/T.Transition,
mêmes BoardLogic/positions/miniscale/dimensions. Nouveau socle Spatial publié816b663,
167tests AST+6ressources+3fixtures11,3080s ; review intégral Style réussi.
Premier prototype5/7 : boîtes non peintes recouvraient les voisines en tactile,
ancrage transparent et surface transformée active corrigés ;2mobiles ciblés9,6s
réussis. Test long injecte le JSON scientifique avant chargement (aucune mutation
du vieux custom element retiré). Main et DemoCard compilés séparément, comme le
constructeur canonique ; bundle exploratoire combiné refusé à cause des ports
homonymes, conservé sans usage. Huit nouveaux parcours de continuité Firefox/
Chromium390/1280 normal/réduit passent1,2min : interruptions/inversions, Entrée/
Espace/Échap, nœud/focus préservés, préférence live et frames arrêtées au repos.
Le Demo recentre désormais une carte dans sa boîte elm-ui plutôt que le coin
absolu de l'ancien div ; aucune donnée scientifique concernée. Hauteurs explicites
compactes240desktop/360mobile, bornées par92% du viewport ; à vérifier avec le
reste des parcours avant qualification finale. test.html construit DemoCard actuel,
ancien bundle test.js retiré (histoire Git intacte). Survey encore ancien.
Math verrou Style816b663 local (SHA256 exact de tous modules/ressources utilisées),
Animator2/time existant/bezier2 transitif ; pas de mise à niveau d'outil.
Stage incrémental state/matheval-developpement-jbgia3ck (sources absolues canoniques),
pointeur matheval-developpement-courant.txt ; jamais candidat. Toutes opérations
citées locales ; rapport MCP/Image persistante et production conservés.

Avancement complémentaire : Survey lecteur elm-ui/Math.document, timeline commune,
notes facultatives avec aperçu distinct de la réponse, fermeture immédiate sans
WebAnimations ou attente "closed". Les aperçus/frames/mesures/préférences n'émettent
pas de checkpoints scientifiques. Question mesurée, lecteur placé sous l'énoncé
(cap32% viewport), commandes à droite en paysage compact. Aides à contenu défilant
borné pour conserver fermeture disponible. Stage même chemin ci-dessus, survey.js
incrémental ; Math non commité. Corpus, tirages, Model.point/S.move et serveur Lisp
inchangés. Bootstrap index/enquete identiques ; erreur de chargement rendue Elm.

Qualifications locales ciblées :181tests AST+6ressources+3fixtures12,0871s,
review Style intégral réussi. Notes : souris/clavier320/390/1363 dans Chromium143
et Firefox146 existants, un tactile Chromium réel (diagonale/annulation), sept
cas réussis depuis fixture actuelle (notes-ciblées-finales.txt).
Lecteur commun : huit formats normal/réduit, focus/défilement/changement de texte
et arrêt des frames réussis depuis sources finales (lecture-ciblee-finale.txt).
Style113169d publié : sources/correctifs/assets et tests conservés, aucune nouvelle
construction ou qualification globale Style revendiquée. Math verrou local113169d
avec tous modules et fenetres.js/notes.js supplémentaires ; manifeste Math garde
encore le verrou historique de78137b0, jusqu'au commit composant réellement publié.
Tests ajoutés à orchestration Style centrale, pas de CI déclenchée ni qualification
complète du nouveau Style revendiquée. Scénarios Math sur Nix SBCL/PG jetable :
fixture3 quatre succès17,9s avant nouveau placement ; fixture4 ciblée placement/aide
portrait un succès6,1s ; fixture5 deux portraits réussis, deux paysages échoués
(aide dépassait439px pour viewport390px), correction de hauteur de texte commune.
Fixture6 quatre succès15,0s : source exacte, zéro/absence/relecture, focus/clavier,
placement sous énoncé, aide accessible portrait/paysage, frames au repos.
Premières fixtures1/2 échouées avant lecteur : ressources puis index d'entrée ancien.
Leur trace est préservée ; index/enquete sources corrigés ensemble. Native DSOs Nix
exactes, aucune fixture instrumentée réutilisée ; copie suivante doit être neuve.
Logs/captures dans state/rapports-frontends et stage/lecteur-fixture-1..6.

Géométrie pure en cours, non publiée : Style src/MrJam/GeometrieSpatiale.elm,
exemples/Geometrie.elm et tests/geometrie.cjs. Programme Elm sans navigateur pour
comparaison avec les références frontend historiques M-moire/docs/site/space-layout.js
et slider-layout.js.323cas (12séparations3D,30poignées dont10prises surélevées,
280déplacements relatifs et projection de référence caméra0) réussis46,5ms,
compile incrémentale2modules. Comparaison de toutes positions/ordres/valeurs ;
seul cout de tri interne historique, inutilisé par la vue, absent du nouveau DTO.
Deux défauts de fixture corrigés : champ cout inclus par spread JS ; poignée
surélevée pas nécessaire dans toutes les largeurs. Aucune assertion de position
relâchée. Coordonnées originales immuables. Nouvelle entrée compilateur et test
raccordés localement dans infrastructure, empreintes des deux références dans
suite Style. Sélection18cas0,9974s et review intégral Style réussis. Geometrie
n'est pas encore consommée par Survey ; aucune conformité de sa scène revendiquée.
Logs dans state/rapports-frontends/geometrie-differentielle-*.txt ; js exploratoire
state/geometrie-developpement.js. Publier seulement après raccordement utile ou
jalon ciblé, puis verrou exact ; dernier Style publié reste113169d.

Suite immédiate : publier lecteur/note communs et verrous exacts après résultats
ciblés, terminer Survey axes/scène/contextes/compagnons et JS de mesure/pointeurs.
L'ancienne projection/sliders/rich-text restent seulement à porter, pas qualifiés.
Les quatre entrées Math, règles/ressources et ContinuousUI doivent passer sur
sources/candidat exacts ; ne pas présenter les tests des règles comme conformité
Math. Ensuite qualification finale assemblage, Nix/HBA/préconditions actuelles,
backup/restauration/retour et étape1 réelle avant Kanidm. Promotion refusée tant
que l'ensemble reste incomplet. Image SBCL de tâche saine conservée ; aucun
rechargement/reconnexion/MCP artificiel pour ce travail Elm.

## Point frontend précédent — historique, remplacé par le point actif

### Observation antérieure des candidats frontend

Infrastructure publiée15496df ; Style30c6087 publié après03a7b7f ;
Matheval8f02f64 publié avec corrections finales et verrou Style30c6087 ;
Vision2d9f31b, Logiqued76f007, Signaturee9d9d34 inchangés. Révisions complètes
assemblées dans manifest.json. Production inchangée : étape1 non déployée,
Kanidm non commencé. Aucun déclenchement CI ni opération de données pendant
cette reprise. Rapport MCP historique non commité préservé.

ArchitectureC et image saine conservées, aucun chargement/reconnexion artificiel,
aucun qualifier synthétique. Processus83928/129399 constatés, non fixés dans les
scripts ; aucun débogage ouvert connu. Outillage hors graphe produit. Les consignes
centrales et renvois C sont en vigueur ; aucune refonte du pont nécessaire.

Conservés : socle ElmUI/Animator scientifique (lecteur, note, scène, axes), quatre
entrées Matheval, contextes, contrôles AST/ressources et géométrie différentielle.
Corpus/graines/Survey.Model/backend inchangés. Références géométriques historiques
moved verbatim vers docs/tests/references, hors site. Les résultats frontend
antérieurs restent historiques : aucune conformité déduite des seuls tests AST.

Qualification ciblée :208cas AST,6ressources et3fixtures conformes/interdites
vérifiées par commande canonique,18,7958s ; review Style intégral réussi. Sélecteur
18cas et sources6cas passent1,1624s/1,2019s. Géométrie336cas (323différentiels,
13séquences des machines Elm),40,2ms. Tableaux encadrés/actions/état/focus/Tab et
transitions/reduced-motion passent aux320/768/1440px dans Contextes actuel.

Campagnes globales exactes03a7b7f/8814b8e analysées, PAS qualifiées :
Style49,6087s échoue sur Tab (corrigé) ; Matheval343,6956s :49pass/5échecs/42non
exécutés sur96. Défauts réels corrigés : Firefox tableau réduit à0 (adaptateur
flex-basis:auto constant, AST strict/documenté), restitution de focus sans
interférer avec Tab, note tactile proxy clavier seulement, proportions des axes
et scène. Assertions de sauvegarde adaptées au texte visible, renforcées par un
vrai PUT200 portant la note2, sans masquer erreurs/conflicts. Fixture19 :8pass/
2échecs proportions ; fixture20 :2passFirefox/Chromium19,8s après hauteur scène450.
Fixtures17/18 : annulation tactile note et axes confirmée, aucune note commitée
par pointercancel ; capture native/prévisualisation séparées. Diagnostics privés
state/rapports-frontends, fixtures exécutées jamais réinstrumentées.

Matheval base exacte8814b8e passe15,297s. Candidats antérieurs conservés mais
supplantés par les fixes : Style03a7b7fac2fe-4efc0ce2, Math8814b8eb9ef3-68b51f4d.
Stade incrémental privé state/matheval-developpement-jbgia3ck, pointeur courant,
quatre sorties compilées séparément. Binaire métier Nix296b7c89/DSOs store audités,
PG17 jetable, aucun backend Node, aucune donnée production.


Qualification exacte conservée : Style30c6087 base138,5239s,
Math8f02f64 base16,4047s ; Logique candidat42954783 base139,1341s et correcteur
12,8117s. Nouveaux candidats : Style30c6087e6975-16136a76/02f4216d ;
Math8f02f64b578d-5c98bd2e/1916a502 ; Logiqued76f0074efa0-cd66ef05/42954783.
Math96parcours ont tous réussi534,0746s mais qualification refusée par garde
sources (harnais ajoutait quota aux tests suivis) : diagnosticmatheval-0a410bb62774,
aucun reçu vert fabriqué. Harnais corrigé vers copie privée .central-tests-*/e2e,
profondeurs/imports identiques,3tests : source intacte, chemins, refus réutilisation.
Frontend-sources9cas passent0,7902s.

Trois campagnes lourdes simultanées ont saturé4cœurs/16Gio : pression mémoire,
timeouts Matheval clavier13/14/15 et atelierY Chromium34. Arrêt SIGINT des seuls
runners265998/268010 constatés ; cleanupPG/SBCL/worktrees par harnais normal,
tracesmatheval-d27518040481/style-03933b67e84b conservées. Aucune hausse de timeout
ni affaiblissement d'assertion. Cible Math4scénarios sérialisés passent63,4647s,
source intacte et trace6e2c8a2048ab. Jobs suivants EXCLUSIVEMENT séquentiels :
Math96 → Stylelogo → Vision/Signature → MCP métier, shellset-e, session à constater
par processus/logs (pas PID constant). Logs *final-serialise.txt / mcp-metier-final.txt.

Visionpostgresql passe289,8156s sous contention, SQLnative reçu réutilisé exact.
L'absence psycopg Python global a été corrigée en utilisant le venv navigateur
existant3.2.5, même binairePython3.12.14/empreinte, aucune installation. Bibliothèques
Nix/runtime existants, pas popplerNix à la place des outils PDF déjà qualifiés.

Contrôles centraux source6+harnais3, sélection20, sauvegarde/migration/classes
privées, transport et isolation passent. Préparateur teste désormais Style
réellement consommé plutôt que HEAD,3cas acceptation/revision/fichier altéré ;
bundle privé inclut sources verrouillées immuables. Le scénario MCP historique
0,8033s/22appels reste intact : vérification offline sourcescoeur/trace/effet1/
resultat42. Contrôleurs Python amendés qualifiés séparément par8cas routage,
aucune condition ou nouvelle connexion prétendue. Reçu inclut empreinte preuve,
tracecopiée dans bundle privé, préparateur vérifie. Manifeste reste nonqualifié.

Suite immédiate : manifeste/empreinte actualisés ; construire UNE fois les
nouveaux candidats propres,
qualifier Style base et Math base/navigateur96parcours. Rejouer seulement suites
affectées, réutiliser reçus inchangés avec provenance exacte. Ne pas confondre
AST, parcours fonctionnels et production. Ensuite aligner toutes preuves requises,
validation Lisp propre distincte sans détruire image saine, Nix/HBA actuel,
backup/restauration isolée/retour, bascule réelleAPI/MCP/invariants/redémarrage.
Kanidm seulement après constat réel étape1. Accès GitHubsettings403/Pagesdisable422
historiques, aucun nettoyage distant prétendu réussi. Références ci-dessous.

## Point de reprise antérieur — activation, SQL privé transmis par stdin

Architecture C et travail frontend conservés ; image applicative saine encore
présente, aucun qualifier MCP synthétique ni reconnexion. Kanidm non commencé.

Déploiement 38189157223 / 109ff5b7 : restauration isolée entièrement réussie,
RLS/ACL, données, lectures temporelles, écritures croisées et redémarrage passent.
Activation engagée, arrêt avant transfert à monolithe-activer.py:201 : psql sous
Unix postgres ne peut pas lire le script privé situé sous /root. Retour du code
exécuté ; référence 38189544447 réussie confirme génération et profil r6s7ags3,
anciens services actifs, monolithe inactif, services tiers disponibles. Comptes
Vision 1 actif/admin, rattachements cohérents ; Matheval 3 participations toutes
ouvertes. Les migrations SQL 026/027 peuvent désormais être appliquées : ne pas
présumer le schéma 25 ni annuler leur protection pour revenir au code ancien.

Correction locale : SQL canonique lu par l'opérateur puis envoyé à psql par stdin,
comme en restauration ; socket/base explicites. Aucun droit de /root élargi.
Tests réels PostgreSQL/autre UID : fichier privé refusé, mêmes méta-commandes et
transaction réussissent via stdin, accès au parent toujours refusé. Migration
29,7892s et sécurité 0,9461s réussissent. Diagnostic fermé précise phase/retour/
qualification finale sans exposer le plan privé. Opérateurs dbd5b19814b88b6ddc4e033134fc5b9e595de90d publiés et scellés ;
transport 6eaa929fb433966043dfc6363c6e9dfc34124bb4 publié. Aucun rejeu de
dad8482 ayant déjà engagé une activation. Descripteur publié d1ce2f1f9969d642a519bc365b01363e585d954f. Déploiement
38189849220 en cours ; constater son issue réelle et son éventuel retour avant
toute répétition. Une interruption de conversation ne l’arrête pas.

Composants exacts du manifeste inchangés, Vision 18c52cdd. Même binaire Nix
296b7c89, graphe Lisp inchangé, mêmes interfaces qualifiées. Reçus affectés seuls
rejoués ; scellement doit vérifier les 35 reçus exacts avant transport. Sauvegarde
fraîche/restauration/retour et bascule centrale uniquement, puis MCP réel,
invariants, mémoire/latences, redémarrage et services tiers. Consigner le nouveau
run avant toute interruption, constater son issue avant répétition. Étape 1 reste
non livrée tant que sa version active et les critères ne sont pas constatés.
