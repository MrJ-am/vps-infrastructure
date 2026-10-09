# État attesté au 9 octobre 2026

La tentative2 de l'[opération37997821227](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37997821227),
0f8b9f3/PR70, job114048714100, a passé la correction du flux puis refusé
`compte_et_courriel`. Le diagnostic privé n'a pas encore été projeté ; ce stade
ne prouve ni création ni envoi. Six services/SSH/25sites finaux conservés.
La première tentative avait seulement dépassé le délai du relevé public ;
extraction et opérateur étaient restés non exécutés avant la relance ciblée.

L'enveloppe autorisait un identifiant interne de deux caractères, alors que le
profil immuable exige trois. [Reproduction native](../operations/vision-proprietaire-profil-qualification.json) :
refusHTTP400 sans création pour deux caractères, succès201 avec l'identifiant
corrigé sans mot de passe opérateur. Le minimum est corrigé avant API/intention
et seul l'identifiant interne du contact chiffré change ; adresse commune,
issuer, profil et realm restent identiques.
La reprise demeure conditionnelle à la preuve root d'un uniqueHTTP400 au
POST de création de0f8, aux sources/AST exacts, à la liste humaine vide, à
l'absence de sujet reçu et de toute intention de courriel, aux contacts qui
ne diffèrent que par ce nom, et au profil actuel minimum3. Une preuve fsync
précède l'archivage privé de l'intention explicitement refusée. Cet usage
unique ne permet jamais d'archiver une nouvelle intention ambiguë. Autres
codes/étapes, réponse perdue, sujet ou courriel présent refusent la reprise.
Cette préparation ne prouve toujours pas un compte ni un envoi réels.

L'[enrôlement37996158121](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37996158121),
f8343fb/PR69, job114042717040, s'est arrêté à `methodes_pwd_otp`, avant le
contact, l'état durable, la création et le courriel. HTTPS/issuer/refus/sources,
SSH/six services et25sites réussis ; génération réservée conservée.
Le lecteur exigeait à tort `REQUIRED` pour le mot de passe : l'import privé
courant prévoit `ALTERNATIVE` avec le lien magique dans un sous-flux obligatoire.
La correction compare toute la hiérarchie native à cet import immuable,
y compris exigences, providers, niveaux, priorités, UUID et configurations.
L'API masque les valeurs ; une requête en lecture seule sur le seul cluster
privé vérifie les trois configurations exactes. La preuve sensible reste
mot de passe ET OTP réellement exécutés depuis moins de300secondes.
[Qualification native26.7.3/PG17](../operations/vision-proprietaire-flux-qualification.json)
et325tests locaux, dont huit refus ciblés. Aucun changement de realm, de
méthode, de secret, de génération ou de SQL Vision. La relance demeure
réservée au sujet initial, après CI exacte, avec intentions durables et refus
de rejeu ; cette correction seule ne prouve pas un compte ou un envoi réel.

L'[activation37994597242](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37994597242),
opérateurac3d8e0ab466a536c9ac3190d360e163d364b8fb, job114037335784,
a réussi tous les contrôles natifs, copies chiffrées, SSH/six services,
25HTTP/TLS, certificat/issuer/refus/sources. La génération réservéek4q
est enregistrée, le retour neutralisé ; l'ancienne générationy1 reste conservée.
[Preuve exacte](../operations/vision-identite-amorcage-activation.json).
Aucun compte humain, OIDC Vision, migration SQL de production ou inscription.
La phase propriétaire suivante exige ce reçu égal au privé et l'état actif,
déchiffre le contact seulement en RAM, conserve des intentions privées
avant création/courriel, interdit tout rejeu ambigu et admin d'identité.
Le propriétaire choisira son mot de passe et son second facteur via lien natif ;
SMTP accepté ne prouve pas réception. L'observation ultérieure reste limitée
au sujet durable exact et ses méthodes pwd/otp fraîches, aucun contenu personnel.
Cette préparation ne prouve pas encore une création ou un courriel réel.

Le [diagnostic37993555900](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37993555900),
opérateur5dcfb0484599d8b74cedfc0c36217e8563337b74, job114033697403,
identifie HTTP503 au premier GET de découverte verifier34/api24 dans c527.
Les contrôles boucle locale/PG17/rejet peer ont précédé ce refus.
Source/cadres exacts, cluster sain arrêté, retour/six services/SSH/25 sites
conservés ; aucune activation ou personne.
[Projection fermée](../operations/vision-amorcage-diagnostic-c527.json).
Une attente monotone120s, réseau borné et pauses1s, retente seulement
le GET de découverte sur503 ou connexion refusée. Aucun credential envoyé
pendant cette attente, aucun rejeu de POST ; autres codes/redirections,
réponses invalides ou issuer différent refusés. Après disponibilité,
tous les contrôles initiaux restent exigés. Reprise gardée sur ce seul
HTTP503/source/cluster, avec nouvel audit/copie froide/retour avant essai.

L'[essai37992389053](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37992389053),
opérateurc527fcfd64dc5478da1011aafc28ce6e3d3fd199, job114029672958,
a réussi préparation/audit/copie froide/empreinte/dry/timer et démarrage,
puis rencontré une exception non classée à controles_locaux.
Le retour et le diagnostic automatique ont réussi ; clusterPG17 sain arrêté,
socle/six services/SSH/25HTTP/TLS conservés. Génération non enregistrée,
aucune migration SQL de production, personne ni inscription.
Le diagnostic suivant vérifie la source exacte de c527 et projette seulement
les classes Python fermées, codes HTTP d'exceptions réelles et cadres AST
connus ; aucun message, URL, corps ou valeur privée. Aucune reprise avant
constat réel de cette cause, aucun redémarrage ou SQL dans le diagnostic.

Le [diagnostic37991412168](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37991412168),
opérateur6dbdb2f6123142145ba6077ed3d6ca38ed39222c, job114026288555,
identifie le seul refus de f763 : contrôle de boucle locale verifier_local:301,
après essai_generation puis controles_locaux. Source/cadres vérifiés ; worker
arrêté, clusterPG17 privé sain et proprement arrêté, import/credential valides.
Socle/six services/SSH/25HTTP/TLS conservés ; aucune activation.
[Projection fermée réelle](../operations/vision-amorcage-diagnostic-f763.json).
Le parseur qualifié accepte maintenant la même adresse127.0.0.1:8085 en IPv4
ou IPv6 mappée, avec une seule écoute LISTEN. Il refuse les autres adresses,
ports, scopes et écoutes multiples. Le même Keycloak26.7.3 local emploie
une écoute mappée ; sa sortie ss réelle, avec seul port de fixture normalisé,
est refusée par l'ancien contrôle et acceptée par le parseur strict.
L'ancienne notation VPS n'a pas été enregistrée.
La reprise est gardée sur ce seul diagnostic, unités privées arrêtées et
cluster sain ; audit et copie froide chiffrée frais avant démarrage.
Le correctif ne constitue pas encore une preuve d'activation.

L'[essai37987992248](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37987992248),
opérateurf7634858fa7a7fbfe33f4c00ecc0047bc48b811f, job114014731892,
a préparé et vérifié une copie froide chiffrée du cluster réservé,
puis échoué aux contrôles locaux. Le retour a rétabli le socle et les
25HTTP/TLS passent à20:38:09 UTC. La génération n'est pas enregistrée ;
aucun compte humain ni inscription, aucune migration SQL de production.
[Rapport de retour](../operations/vision-amorcage-reprise-retour.json).
Le motif initial reste inconnu. Le diagnostic automatique était limité
aux anciennes révisions ; il accepte désormais la révision exacte du
contrôleur déjà lié à son dossier root. Le diagnostic suivant lit seulement
les fichiers bornés de f763, ses cadres de source vérifiés et les motifs
fermés des exceptions réelles. Aucun redémarrage ou SQL, aucune reprise
avant constat du motif et de l'état du cluster retourné.

La [construction37985768542](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37985768542),
opérateur25f685900a9b65cb7cef872f0b55bcb21e35567d, job114007309842,
réussit le test Nginx natif complet sous UID/groupe vérifiés, capacité native,
réseau privé et trois tmpfs privés. L'ancien refus542 était l'ouverture du
PID Nginx sur un système de fichiers readonly. Socle/six services/SSH et
25HTTP/TLS avant-après passent, fin20:17:27 UTC ; aucune activation.
[Preuve de construction exacte](../operations/vision-identite-amorcage-qualification.json)
et [contrôles natifs](../operations/vision-amorcage-nginx-native.json).
La génération k4q4i4m9r4070xwwpnd24hpi9g6zngyn reste retenue pour l'essai.
La reprise réservée du seul cluster arrêté f9 est préparée avec audit,
copie à froid chiffrée, empreinte vérifiée avant démarrage, retour indépendant
et diagnostic automatique après retour. Cette préparation ne prouve encore
ni son activation, ni le déchiffrement d'une sauvegarde réelle.

Le contrôle [37984167434](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37984167434),
opérateur542c15e87573f9f3d948fe0a5f9b5b2717df3e1f, refuse une ouverture
avec errno30 dans le confinement readonly du test. Les six services/SSH,
le socle et25HTTP/TLS restent conservés, aucune activation.
[Rapport du refus](../operations/vision-amorcage-nginx-lecture-seule.json).
Le test emploie ensuite trois tmpfs privés pour PID/cache/logs, appartenant
aux UID/GID Nginx évalués et vérifiés ; aucune écriture sur leurs équivalents
du service actif. Un test natif sous UID non root reproduit le refus RO,
puis valide nginx -t avec ces répertoires privés dans un conteneur readonly.

La construction [37982527127](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37982527127),
opérateur6072227fdae8d7f8b8ebd8476405073cef8960bb, établit que runuser
est présent et que la syntaxe Nginx complète est valide. Le test refuse
l'ouverture du port80 sans CAP_NET_BIND_SERVICE ; diagnostic chiffré,
déchiffré en privé dans Work, clé/diagnostic éphémères ensuite supprimés.
Socle/six services/SSH/25HTTP restent vérifiés, aucune activation.
[Rapport factuel](../operations/vision-amorcage-nginx-capacite.json).
Le test suivant emploie seulement cette capacité native, sous UID/groupe
nginx avec NoNewPrivileges, dans une unité transitoire au réseau privé.
Il conserve les permissions et utilise uniquement nginx -t, sans daemon.

La construction réservée [37979390241](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37979390241),
opérateur f27c4d1e1f0b731da9e16116d584293599ee10d4, a construit sa génération,
puis refusé le contrôle Nginx natif avant activation. Sa cause n'est pas encore
établie. Socle, six services, nouvelle SSH et 25 HTTP/TLS restent vérifiés.
Le [rapport du refus](../operations/vision-amorcage-construction-refus.json)
ne qualifie aucune nouvelle génération. Le contrôle suivant lit ce seul refus
privé et utilise util-linux explicitement évalué depuis le Nixpkgs installé.
En cas d'échec, seul le stderr de cette commande fixe est chiffré vers une clé
Work éphémère ; aucune erreur privée n'est publiée en clair.

## Vision — regroupement des opérations

À la demande du propriétaire, les lancements techniques passent par
[un point d'entrée Actions unique](VISION-MISE-EN-SERVICE.md). L'agent peut
déposer une demande sur `operations/vision`, pour le seul commit intégré et
validé par la CI exacte. Les publications ordinaires ne déploient pas.
L'essai réservé devient une étape réutilisable ; les preuves et le retour
autonome sont conservés. Ce regroupement ne prouve aucune activation : l'état
VPS constaté reste celui décrit ci-dessous tant qu'une exécution n'est pas citée.

Le déclenchement par l'agent est réellement vérifié : signal37953863382,
orchestration37953882332, job113899388028, opérateurb82f1eba3bf8b8de102b0e1568978f085ef721ca.
Demande/CI exactes et état initial passent ; l'entrée reproduit la génération
préparée. Arrêt en `dry_activate` avant toute activation ; contrôle du socle
et25HTTP/TLS finaux réussis. Vision reste historique, aucune identité humaine.
Le diagnostic en lecture seule est préparé dans ce même point d'entrée.
[Rapport de tentative](../operations/vision-amorcage-tentative.json).

Le [diagnostic37955815952](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37955815952),
job113906002350, opérateurc849613768fdcd7868c4a38b6e44bc0ec9d3ffbd,
réussit à16:00UTC : arrêt prévu de tmpfiles-resetup et d'une unité ACME,
redémarrage Nginx, aucune unité inconnue/systemd/swap. Socle, six services,
nouvelle SSH et25HTTP/TLS avant/après passent, aucune activation.
La correction ajoute une comparaison stricte des fichiers/règles immuables
avant d'autoriser ce seul arrêt.
[Rapport du diagnostic](../operations/vision-amorcage-diagnostic.json).

La [reprise37958354048](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37958354048),
opérateur88dc20580cbfc3e790eb19f366794b8b94f87e9d, job113914603028,
passe réellement comparaison des règles/unité, simulation, copie chiffrée
et répétition du timer. Retour autonome armé, worker demandé ; les contrôles
locaux ne terminent pas dans les dix minutes. Le retour est attesté terminé
à16:31:54, socle rétabli ;25HTTP/TLS finaux passent à16:32:11.
Aucun enregistrement, personne, mode commun ou inscription. Le diagnostic
en lecture seule examine désormais ce worker arrêté, pas une nouvelle reprise.
[Rapport de reprise](../operations/vision-amorcage-reprise.json).

Le [diagnostic37961581194](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37961581194),
opérateur49ac1e7d9b86e454056d12abb3be1b1fd219411e, job113925573398,
réussit à16:47:59 : retour terminé, worker arrêté, aucune étape du worker
et aucun cluster réservé présent. Six services/nouvelle SSH et25sondes passent.
L'examen local identifie `self.worker` masquant la méthode `worker` ; le test
échoue sur l'ancien code et passe après renommage de l'attribut. La prochaine
reprise exige d'abord cette trace précise dans le journal privé, puis conserve
la même génération et tous les contrôles/retour. Toute autre cause bloque.
[Rapport du worker](../operations/vision-amorcage-worker-diagnostic.json).

La [reprise37963555297](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37963555297),
opérateurf9dae92a39f350d5aa5b5795f74b04f6827d60ff, job113932183678,
confirme réellement la trace d'action masquée puis délai dans88dc ; aucune
étape ni cluster présents à ce contrôle, reprise conditionnée autorisée.
Préflight/copie/timer passent et le worker corrigé est engagé. Un nouveau
refus de commande bloque les contrôles locaux ; retour terminé à17:06:10,
socle rétabli et25sondes finaux réussis à17:06:25. Aucun enregistrement/personne.
Le diagnostic courant examine cette tentative retournée avec cadres Python
validés contre le code exact et états/journaux des seules unités d'identité.
Aucun argument ou fragment privé n'est publié ; aucune reprise/effacement.
[Rapport de reprise corrigée](../operations/vision-amorcage-dispatch-reprise.json).

Le [diagnostic37966437838](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37966437838),
opérateurd8a974efefa8141f8e52e737936c4778d82d25db, job113941899050,
refuse sa lecture à17:28:36 ; la cause et l'état privé de f9 restent inconnus.
Six services/nouvelle SSH et25HTTP/TLS avant/après passent à17:28:52.
La préparation suivante conserve les préconditions strictes, indique la
sous-étape d'un refus et marque les relevés secondaires indisponibles sans
supprimer le rapport principal. Une indisponibilité ne prouve aucun état sûr
et n'autorise aucune reprise. Aucun changement de génération demandé.
[Rapport du refus de diagnostic](../operations/vision-amorcage-commande-diagnostic.json).

Le [diagnostic37967591960](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37967591960),
opérateur55309e2f0f232f084139e0f27579103229338e8b, job113945795441,
réussit à17:38:21. Socle/retour et worker arrêté sont vérifiés ; il a atteint
`essai_generation`, le cluster privé est présent. Les états actuels des trois
unités sont inactifs/success, sans cause classée ; cadres indisponibles.
Six services/nouvelle SSH et25HTTP/TLS avant/après passent à17:38:34.
La suite prépare un relevé de métadonnées du cluster arrêté et des journaux
des unités dans les deux namespaces. Aucun SQL, lancement ou effacement.
[Rapport du cluster présent](../operations/vision-amorcage-cluster-present.json).

Le [diagnostic37969887755](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37969887755),
opérateura006fdc48acc58b333f8e5b2fee9f3a8fd3d7f49, job113953556759,
réussit à17:58:16 : cadres f9 vérifiés, refus au `worker` ligne291
(switch-to-configuration test). Le cluster17 est privé et proprement arrêté,
aucun PID/socket ; journal privé PostgreSQL disponible sans motif d'erreur.
Seule l'unité d'identité présente un échec historique classé. Socle/retour,
six services/nouvelle SSH et25HTTP/TLS avant/après passent à17:58:40.
Le complément préparé classifie les codes de sortie/exceptions connus et le
namespace réservé complet ; contrôle de l'import et du format du credential,
sans valeur, lancement, SQL ou reprise.
[Rapport du cluster arrêté](../operations/vision-amorcage-cluster-arrete.json).

Le [diagnostic37971727525](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37971727525),
opérateur1f9ad7a2d1c778a3d5bb4b2420c4e291ba841fd3, job113959828149,
réussit à18:13:55 : sortie historique143 du service d'identité, aucun motif
d'exception/étape ; import et format du credential vérifiés. Le code143
correspond à un arrêt par signal et n'identifie pas le refus initial du switch.
Cluster17 privé proprement arrêté, socle/retour, six services/nouvelle SSH et
25HTTP/TLS avant/après passent à18:14:09. La projection suivante classe le
bilan d'unités échouées déjà conservé sur stderr par le gestionnaire NixOS ;
noms techniques connus seulement, compteur pour les inconnus, aucune reprise.
[Rapport de sortie](../operations/vision-amorcage-sortie-identite.json).

## Vision — génération d'amorçage construite sans activation

[Actions37941066602](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37941066602),
job113855262092, opérateur765ce372ccd61ad623e33bf8bb476a5c3be21fba,
réussit à14:03UTC. Génération39b7g3x42qp2q58idfv7nl6w5j3y78np construite,
anciennes unités/tous les hôtes/PostgreSQL de production conservés. Inventaire
privé en lecture seule : un propriétaire, quatorze tables, aucun contenu lu.
Six services/nouvelle SSH et25HTTP/TLS passent avant/après. Aucun compte humain,
switch ou inscription. Rapport exact : operations/vision-identite-amorcage-qualification.json.

L'[essai réservé](IDENTITE-AMORCAGE-ESSAI.md) est préparé avec ancien socle,
entrée réversible, copie locale age, dry-activate et répétition du timer,
worker indépendant de SSH et retour autonome. HTTPS/issuer/refus et25sites
doivent passer avant l'enregistrement de cette seule génération. L'essai
réel, ACME, possession/MFA et association historique ne sont pas encore constatés.

## Vision — composants construits sur le VPS

La [construction 37930689913](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37930689913),
job `113820359864`, opérateur `296e4d159544f01af1345ea844871d11f17897f7`,
réussit à 12:33 UTC. Sept unités, six imports Python sans privilèges et sources
AGPL sont vérifiés ; le paquet Keycloak qualifié est conservé. Le garde empêche
toujours une génération du mode commun, aucune identité humaine n'est créée.
Socle et release inchangés, six services/nouvelle SSH et 25 HTTP/TLS avant/après.
[Rapport technique](../operations/vision-mrjam-composants-qualification.json).
PR44 intégrée ; CI `37929201747`/`37929205485` réussie, 238 tests Python.

La [phase réservée d'amorçage](IDENTITE-AMORCAGE.md) prépare une génération
distincte à partir du socle actif, avec un cluster indépendant et un futur
enrôlement du seul propriétaire. Sa construction et toute activation restent
à constater. Le mode commun, l'association historique et l'admission
ne sont pas activés.

## Vision — import initial privé préparé sur le VPS

La [préparation 37927013329](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37927013329),
job `113808266809`, opérateur `ce847e1519eac78b37352cd070eb949346d61a47`,
réussit à 11:59 UTC. Les cinq secrets clients/hook et le realm sont créés
et vérifiés dans le dossier root privé, hors Git/store et sans rotation.
SMTP est configuré mais non contacté. Aucun compte humain, import en base,
migration de production ou activation. Socle inchangé ; six services, nouvelle
connexion SSH et 25 contrôles HTTP/TLS passent avant et après.
[Preuve sans données](../operations/vision-identite-import-qualification.json).
PR43 intégrée, CI `37926200637`/`37926204998` réussies, 232 tests Python.

La [construction des composants](VISION-COMPOSANTS-MRJAM.md) réussit réellement
dans l'exécution consignée ci-dessus, sans lever l'assertion ni démarrer les
services. L'identité du propriétaire, son MFA, le rapprochement historique et
l'activation demeurent des étapes séparées.

## Vision — identité native Unix qualifiée sur le VPS

La [qualification 37924485219](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37924485219),
job `113800035423`, opérateur `64402023f6ec4d0a733df3ad09f7663d789a4737`,
réussit à 11:35 UTC. Le paquet optimisé Keycloak 26.7.3 démarre réellement dans
une unité systemd DynamicUser avec réseau privé ; version, SPI et API
synthétiques passent. JDBC utilise le socket Unix du cluster PostgreSQL 17
isolé et peer sans mot de passe ; un autre UID est refusé, aucune écoute TCP.
Les runtimes sont retirés. Génération et release restent inchangées ; six
services, une nouvelle connexion SSH et 25 sondes HTTP/TLS passent avant/après.
[Rapport technique](../operations/vision-identite-unix-qualification.json).

L'audit `37923766983` confirme que le premier échec ci-dessous venait de la
traversée refusée du dossier root des lanceurs. PR42 rend uniquement ce dossier
de scripts publics traversable ; le refus des fichiers root privés est testé.
CI `37923202540` et `37923206284` réussies, 220 tests Python.

L'[import privé initial](IDENTITE-IMPORT-INITIAL.md) est maintenant préparé dans
le code et son workflow manuel distinct. Sa création effective sur le VPS est
constatée ci-dessus. Aucun compte humain, migration SQL de production, activation
NixOS ou inscription n'a été réalisé pendant cette qualification.

## Vision — copie réelle et retour des droits qualifiés le 9 octobre 2026

La [qualification 37909401754](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37909401754),
opérateur `48f40f3eebbbd18eb9048c7036284185a56050e9`, réussit à 09:10 UTC :
restauration du snapshot réel dans le seul cluster privé UTF-8, migrations
019–025 sans modification des empreintes historiques et retour ciblé des
ACL/owners/RLS rejoué deux fois. Le cluster isolé est retiré après le test.
Les six services, une nouvelle connexion SSH et 25 sondes HTTP/TLS passent.
Le second lancement `37909419903` est refusé à « Préparation déjà terminée » ;
ses contrôles passent également. Aucune migration de production ni activation.

Le socle actif est reproduit exactement en conservant sa source fournisseur
immuable avec `builtins.storePath` ; la divergence décrite ci-dessous est
résolue pour cette préparation. Le défaut SQL_ASCII du cluster de test est
corrigé et sa régression multioctet passe.
Vision `a9c51acac81510d7dc896f5daf4e6fb28a36b979` et Style
`96fa28ac564b9492768837d4087608e83acc721b` restent les candidats.
[Rapport technique](../operations/vision-multiutilisateur-qualification.json).

Le paquet Keycloak 26.7.3 avec ses plugins est préparé pour une construction
manuelle distincte sur le Nixpkgs installé (qui fournit 26.7.2). Cette
construction réelle `37912940648`, opérateur
`226a928a58121b25a3c097c8d32b6843a05e19e6`, passe le socle et la preuve de
préparation, puis échoue à `construction_paquet`. Six services, nouvelle
connexion SSH et 25 sondes passent après échec. Le diagnostic privé sera
classé en lecture seule par l'audit `37914413033`, qui confirme un refus de
permission dans le build du SPI ; 25 sondes réussissent. La reproduction
locale avec `nixbld` identifie la copie des ressources en lecture seule et
son nettoyage refusé. Le correctif ne rend inscriptible que cette copie
temporaire, avec une régression native sans privilège. Le contexte précis
du refus VPS est confirmé par l'audit `37916043224` : nettoyage SPI refusé.
La [construction corrigée 37916844094](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37916844094),
opérateur `6a3f3d56d7a63795674fd243859b3d689340005c`, réussit ensuite :
Keycloak 26.7.3 et cinq plugins dans le paquet
`/nix/store/v3g29yfxvp9bdnjgw3p91zvh4jggvk45-keycloak-26.7.3`.
Les six services, nouvelle connexion SSH et 25 sondes HTTP/TLS passent.
[Preuve de construction](../operations/vision-identite-construction.json).
Le paquet n'avait pas encore été démarré sur le VPS : le workflow distinct
`vision-identite-unix-qualifier.yml` prépare seulement un essai synthétique
avec PostgreSQL peer/Unix et systemd DynamicUser dans un réseau privé.
Son [essai réel 37921899243](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37921899243),
opérateur `ebf5a5bfb65fdb0e479e1bc3717d8e6e0d3986d7`, s'arrête au démarrage
du cluster synthétique : indisponible. Keycloak n'est pas démarré. Le socle
inchangé et le retrait des runtimes sont constatés ; six services, nouvelle
connexion SSH et 25 sondes passent après échec. Le diagnostic privé est classé
en lecture seule, sans afficher ses journaux. Une reproduction locale relève
que `mkdir(mode=0711)` sous umask 077 laisse le dossier des lanceurs root 0700.
Le correctif rend explicitement ce seul dossier de deux scripts publics
traversable et teste un UID distinct, avec refus du fichier root privé. La
cause réelle et la qualification corrigée sont désormais constatées ci-dessus.
Préconditions d'activation, identité initiale,
contrats, clé et copie externe demeurent à établir.

## Vision — qualification isolée arrêtée avant dump, 9 octobre 2026

La relance [37897757438](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37897757438),
opérateur `8c3721c5fc25724c409a5f9e2b56e0bccfdd702b`, vérifie les invariants
actifs et l'archive Vision `a9c51acac81510d7dc896f5daf4e6fb28a36b979`, puis
refuse le socle NixOS recalculé à `evaluation_nixos`. Aucun dump, migration ni
activation ne commence. Après arrêt : nouvelle connexion administrative,
six services actifs et 25 contrôles HTTP/TLS réussis. Le constat privé du
premier essai `37893102123` retrouve seulement la source extraite, sans
évaluation conservée, ACL ni dump. La cause précise de la divergence reste
à établir par le diagnostic technique du workflow d'audit existant ; le
garde-fou du préparateur reste strict.

L'audit [37899364733](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37899364733),
opérateur `98ab45e24b2b82fec512fe046681830092919531`, réussit ensuite.
Génération active et démarrage restent conformes, PostgreSQL 17 sans TCP.
Les trois évaluations des sources installées produisent toutes la génération
`mvgw1a0cy7mmf1fq2ji02zynafmg604m`, différente de l'active ; 25 sondes passent.
La comparaison des unités et du fournisseur reste à constater. Le diagnostic
est en lecture seule ; aucune correction du système n'est encore appliquée.

L'audit [37900599245](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37900599245),
opérateur `99d355bc12c11d3eb48a6af8014e138ab2e62e57`, retrouve dix unités
identiques et les deux unités du fournisseur d'embeddings différentes. La
comparaison des fichiers ne termine pas et l'épinglage n'est pas encore
qualifié. La génération active reste inchangée et les 25 sondes réussissent.

L'audit [37901569064](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37901569064),
opérateur `566b279f15c9042d4b8f31906318d3cdf56fdf7b`, confirme les deux scripts
présents dans la source active `20nds4zvi1pcnljpwnwzcsysvyk15g11`. La source
recalculée n'est pas réalisée par `--eval`. L'essai `toPath` ne conserve pas
le contexte Nix ; un test local reproduit cet écart et vérifie que `storePath`
rétablit la génération exacte. Le candidat prépare cet épinglage explicite,
sans modifier le brut, en conservant tous les contrôles de génération et PG.
Son audit réel et la préparation isolée restent à réaliser.

## Vision — courrier Proton qualifié le 9 octobre 2026

L'exécution [37891204452](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37891204452),
commit opérateur `48aa2fa6d05388d48bc6e7ef3625b358bdb53905`, a réussi.
Le jeton est installé dans le fichier privé root 0600 hors Git et store Nix.
La connexion réelle à Proton exige STARTTLS et vérifie le certificat ;
l'authentification réussit et le relais accepte le témoin avec pièce jointe age.
Le témoin ne contient aucune donnée d'usager. L'exploitant confirme le 9 octobre
sa réception dans Proton et le format age de la pièce jointe. La lecture du
fichier chiffré n'est pas son déchiffrement : ce dernier et la possession de
la clé privée restent à vérifier à son retour au PC. La préparation isolée
peut continuer ; aucune rotation de clé n'est effectuée.

Les 25 contrôles HTTP/TLS réussissent avant et après l'installation, ainsi
qu'une nouvelle connexion administrative et les états actifs de sshd, nginx,
PostgreSQL, Vision et Matheval. Cette opération ne lance aucune activation
NixOS, migration SQL de production ou ouverture des comptes. Le propriétaire
retient ensuite `log.mrj.am` pour l'identité commune ; son A vers
`187.77.95.158` est observé le 9 octobre. Le certificat et les autres
préconditions du dossier restent à établir.
[Rapport technique](../operations/vision-courriel-qualification.json).

## Logique — correction de la prise tactile publiée le 7 octobre 2026

Code servi `808483d4789172113b120b44fe5767d9cd3cc983` : prise sur les surfaces
jaunes et marges vertes, dépôt sur le fond libre du canevas. Le défaut reproduit
était une source limitée au petit libellé. Les gestes sur les anciennes poignées,
le clavier, les boutons et le défilement sont conservés. Le téléphone physique
du signalement n’est pas testé ; validation tactile automatisée CDP sur deux
formats et essai Firefox à la souris, sans confondre ces niveaux de preuve.

CI application `37603672723`, opérateur `47d24ecb676c57ac1fa51b42a61d5fc9e9f08bc3`,
CI infrastructure `37603994825` ; préparation `37604334515`, activation
[37604573774](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37604573774)
et constat indépendant [37604902304](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37604902304)
réussis. Les 84 fichiers, 83 ressources HTTPS, trois formats et gestes existants
sont contrôlés, ainsi qu’un geste tactile CDP hors libellé sur le site servi.
Captures de production examinées. Ancienne release `fb21030ca35fed6a82f65729e6f91e8562760e9f`
conservée, retour désarmé ; autres publications, NixOS et données conservés.
Style `eaee86024ac2d158f507bfe798cee3af3a923930`, Signature et formats inchangés.
[Rapport final](../operations/logique-atelier-publication.json).

## Logique — refonte graphique publiée le 7 octobre 2026

L’[atelier](https://logique.echos.systems/#/atelier) présente désormais une palette
à gauche et un canevas à droite. Les règles sont des pièces jaunes à encoches et
cavités ; les propositions vertes s’emboîtent directement dans les paramètres.
Zoom, défilement indépendant, gestes tactiles et historique sont vérifiés.
Code servi `fb21030ca35fed6a82f65729e6f91e8562760e9f`, style
`eaee86024ac2d158f507bfe798cee3af3a923930`, Signature originale conservée.

CI application `37597158853`, style `37596804467` et infrastructure
`37597525950` réussies : 97 cas Elm de l’atelier, treize parcours, six formats,
non-régression des cours, huit contextes typographiques et 145 tests de
l’infrastructure, avec NixOS et PostgreSQL jetable dans la CI.

Opérateur `95e4fa1af48b0dce5e473510b9f7180cfa65a8c5` ; préparation
[37597865546](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37597865546),
activation [37598028422](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37598028422)
et constat indépendant [37598302049](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37598302049)
réussis. Les 84 fichiers de la release et 83 ressources HTTPS sont vérifiés,
ainsi que les 35 sondes, trois formats, la disposition, les couleurs, le dépôt
direct et son annulation, l’extraction d’un théorème et sa restauration.
Captures de production examinées ; tactile automatisé CDP, sans appareil physique.

L’ancienne release `63f8a7fe940f3384e76ab8fb4764f033a49f02ca` est conservée.
Le retour autonome est désarmé ; seul `/srv/logique/current` change. Le relevé
confirme les mêmes générations système, empreinte de configuration et releases
Vision/Matheval. Aucun changement SQL ni reconstruction NixOS. Les formats de
sauvegarde et certificats restent compatibles. [Preuve durable](../operations/logique-atelier-publication.json).

## Logique — première publication de l’atelier le 7 octobre 2026

L’[atelier de preuves](https://logique.echos.systems/#/atelier) est réellement
servi à la révision `63f8a7fe940f3384e76ab8fb4764f033a49f02ca`, avec le style
`90ced00b49bf1e26bea0c8b8477b630c966e2082` et Signature originale conservée.
Il permet de composer des preuves, d’en extraire des théorèmes paramétriques et
de les réutiliser à deux niveaux. Noyau Elm, gestes Pointer Events, stockage
local et export JSON ; aucune démonstration transmise à un serveur.

Opérateur `94f48f49efcfaa05fdc77af54fe036a5363e5ee6`, CI infrastructure
`37554642021` réussie : 145 tests, évaluations NixOS, PostgreSQL et restauration
dans un conteneur jetable. Préparation
[37554886674](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37554886674),
activation [37555013283](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37555013283)
et constat indépendant [37555292312](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37555292312)
réussis. [Révisions, état réel et empreintes](../operations/logique-atelier-publication.json).
[Procédure](ATELIER-PREUVES.md).

Les 84 fichiers de la release sont intègres ; les 83 ressources hors manifeste
sont identiques en HTTPS. Deux contrôles des 35 sondes et des parcours sur trois
formats réussissent, avec extraction puis rechargement d’un théorème. Captures
de production examinées. CI application `37554360513` et style `37553448100`
réussies ; 91 cas du noyau, parcours souris/clavier/tactile CDP et non-régression.
Aucun appareil tactile physique n’est revendiqué.

Seul `/srv/logique/current` change. Ancienne release `2e2dd6a48cbdad20bbc8d0ac34a9ace67f111a0f`
conservée, retour autonome testé puis désarmé. Générations active et de démarrage,
empreinte de configuration, Vision, interface Vision, Matheval et sauvegardes
conservés. Aucune migration SQL, restauration de production ou reconstruction
NixOS. Le module de style additionnel n’est adopté que par Logique.

## Vision 2.6.1 — vitrine publiée et constatée le 6 octobre 2026, 11:42 UTC

Accueil visuel, cinq illustrations et captures fictives, marque Vision.MrJ.am,
pictogrammes communs et suppression de la signature de bas de page. Tutoriel
commun de onze chapitres avec procédures ChatGPT, Claude, Gemini CLI et Codex.
La confidentialité et le tutoriel excluent les détails d’hébergement.

Application `166fce94afa84d1dd9b786f756a1e958eecc764e`, style
`ed6e4af0c1c0080862b6f6f6e6417849cf8c84fb`, opérateur
`633471aa3a2f00a354ac2341c3b1292bb2321a03`.
Préparation [37456998498](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37456998498),
activation [37457545367](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37457545367)
et constat indépendant [37457922254](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37457922254)
réussis. [État complet et empreintes](../operations/vision-vitrine-publication.json).
[Procédure](VISION-VITRINE.md).

Aucune migration ni restauration de production. Les vingt tables, les contrats
SQL 7/1, les générations NixOS, la configuration, les autres applications et le
fournisseur local sont préservés. La sauvegarde est restaurée dans une base
jetable et le serveur candidat y démarre sans écrire. Le retour applicatif
est désarmé après contrôles ; anciennes releases et sauvegardes privées conservées.

Les 35 sondes HTTP/TLS, vingt outils, OAuth PKCE, Basic, Bearer, sessions/CSRF,
liens privés, rapports, révocations et artefact exact sont vérifiés. Les cinq
visuels, les fontes, la copie de l’adresse MCP, les onze chapitres web et MCP,
la confidentialité et quatre formats ont aussi passé le constat indépendant.
Les connexions à des comptes personnels OpenAI, Anthropic ou Google ne sont
pas simulées : leurs procédures reposent sur les guides officiels vérifiés.


## Vision 2.6 — publication et constat indépendant, 6 octobre 2026, 08:24 UTC

Application `c747ad881849ffbc9bd7caa6c24e9934e75ce9a2`, source opérateur
`88b72ae8e5deb9eb1db6152f0eda910d555d58c1`. Préparation
[37435153077](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37435153077),
activation [37435297652](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37435297652)
et constat indépendant [37435615890](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37435615890)
réussis. Source, interface et empreintes :
[preuve complète](../operations/vision-autonomie-publication.json).
[Procédure et limites](VISION-AUTONOMIE.md).

Vision sert 2.6.0, vingt outils MCP et les contrats SQL 7/1. Migrations
additives 017/018 appliquées ; 19 tables historiques préservées. Sauvegarde
restaurée, essais annulés et vrai retour SQL testés avant activation.
Aucune séance fictive ni restauration de la base de production.
Publication enregistrée ; timer de retour autonome désarmé.
Les 35 sondes HTTP/TLS, Basic/Bearer/OAuth PKCE, sessions/CSRF, révocation,
accueil public, politique, tutoriel, liens privés, rapports et interface
exacte ont réussi, puis ont été contrôlés une seconde fois après finalisation.

Générations active et de démarrage conservées :
`/nix/store/y1azkcagkf54nq5vjn4j16g5v1c61c4c-nixos-system-nixos-26.05.8639.c5c4a43b0e80`.
Matheval `04168b68723322afe18b51d20e8089121348b8b3` et Logique
`2e2dd6a48cbdad20bbc8d0ac34a9ace67f111a0f` conservent leurs publications.
PostgreSQL 17.11, pgvector 0.8.2, fournisseur local, routage, secrets et style
partagé conservés. Les anciennes releases et sauvegardes privées restent disponibles.

Le contrat prescrit le comportement du LLM ; les tests ne certifient pas
l'application de ces règles par tous les modèles. Les dates anciennes
incertaines ne sont pas reconstituées. Les sauvegardes restent locales au VPS.


## Talk installé et vérifié le 30 septembre 2026 à 22:17 UTC

Talk **24.0.4** (`spreed`) est installé et activé sur Nextcloud 34.0.4.
Accès : https://cloud.mrj.am/index.php/apps/spreed/

- Source : `cb55b9ce71acefe0686f23b5159150f2fe9d5f94`.
  CI exacte [36783983804](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36783983804) réussie.
- Audit en lecture seule [36783613726](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36783613726).
- Construction réelle sans activation [36784323831](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36784323831).
- Activation et constat indépendant [36784621012](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36784621012),
  commit opérateur `df52b749ddfdcb8d0d100aa50d78b39653f80b92`.
- Génération active et de démarrage :
  `/nix/store/mabshi6mmisnabl5qb5hwldnkxiz2s25-nixos-system-nixos-26.05.8639.c5c4a43b0e80`.
  Ancienne génération `c06sq9vp17l36j8xp2apyfav1nribpwc` conservée et protégée.
  Retour autonome armé pendant la bascule puis désarmé après enregistrement.

Le paquet provient de `nextcloud34Packages.apps.spreed` dans le Nixpkgs
installé `c5c4a43b0e80`, archive officielle
`https://github.com/nextcloud-releases/spreed/releases/download/v24.0.4/spreed-v24.0.4.tar.gz`,
empreinte `sha256-puSnXtbKLtKX2EgXGoqCPB8n98cf+vvUXoEAGrn3FkY=`.
L'installation est déclarative (`extraApps`, activation automatique) ;
l'App Store et ses mises à jour automatiques restent désactivés.
Aucune mise à jour générale NixOS ni modification de PostgreSQL, SSH,
pare-feu, domaines ou comptes administrateurs.

Contrôles exécutés : sauvegarde cohérente avant bascule réussie ; invariants
des autres services identiques ; Nginx candidat valide ; Talk activé en
version 24.0.4, tables Talk présentes, API des conversations anonyme refusée
avec HTTP 401, Nextcloud installé hors maintenance et sans migration en
attente. Comparaison privée des comptes et des métadonnées de fichiers
avant/après identique. Les publications Matheval, Vision et Logique ont gardé
leurs chemins exacts. Les 25 sondes HTTP/TLS ont réussi avant et après ;
une nouvelle connexion runner a confirmé les deux générations et Talk.

**Périmètre de vérification :** installation, activation et API protégée.
Aucun appel audio/vidéo entre deux navigateurs, partage d'écran ou parcours
invité complet n'a été testé. Aucun serveur TURN ni High Performance Backend
n'a été ajouté. La sauvegarde reste locale au VPS.


## Vision 2.4.1 — clôtures et cohérence SQL, 27 septembre 2026, 22:46 UTC

Application `3cbd57ff8d05798e3766fd0d6c93087739d8b608`, source VPS
`4af66c01941887e04152d012579bf7f65b35d161`. CI backend `36355860960`,
interface `36355860951`, infrastructure `36356051235` ; préparation
`36356230474`, activation `36356320005`, constat indépendant `36356465429`
réussis. Le retour autonome est désarmé.

La migration additive 015 corrige la validation des sens et la clôture. Les
références techniques manquantes sont fournies par Vision ; déroulement et
retour sont facultatifs, sans invention. Un rejeu ne double pas les résultats.
Le démarrage contrôle les empreintes des fonctions SQL et ne réexécute plus
les migrations enregistrées. Contrat SQL 6, version HTTP/MCP 2.4.1.

Les 58 items de la sauvegarde restaurée ont passé clôture et rejeu, essais
annulés en base isolée. Les données des 17 tables applicatives sont inchangées.
Aucune séance de test en production ; aucun résultat utilisateur rejoué.
Basic, Bearer, OAuth, sessions/CSRF, quatorze outils et interface exacte vérifiés.
Génération NixOS, autres applications et anciennes versions conservées.
Preuves : `operations/vision-refonte-publication.json` et rapport applicatif
`rapports/CLOTURES-20260928.md`.


## Vision 2.3 — items autonomes et observations, 26 septembre 2026, 23:19 UTC

Serveur et interface `c797c92be8c7a774e5566d5f8182442f52d609da` actifs,
source VPS `886105f5f5b926fd7eb6f2d1391bcae973617661`.
CI applicative 36278489471, interface 36278489466, infrastructure
36278717893 ; préparation 36278887497, activation 36278976906 et constat
indépendant 36279153941 réussis. Migration 013 : **58 items historiques
reformulés**, **49 observations horodatées reprises**, une séance ouverte
conservée, états mémoriels identiques. Les autres applications et la génération
NixOS active et au démarrage sont restées inchangées.

Quatorze outils MCP, Basic, Bearer, OAuth, sessions/CSRF, navigateur et artefact
exact ont été vérifiés après bascule. Le retour autonome est désarmé. Une lecture
réelle après finalisation confirme « Paris est la capitale de la France »,
« Prague est la capitale de la République tchèque », les observations sur
l'item TSD et les suggestions par fiche avec nombres à réviser. Les clients
MCP doivent recharger leur catalogue pour voir `ajouter_observation`.
Détails : [VISION-REFONTE.md](VISION-REFONTE.md) et
[vision-refonte-publication.json](../operations/vision-refonte-publication.json).

## Interfaces documentaires communes publiées le 26 septembre à 17:10 UTC

Les trois sites servent le style `3aab7233465ac0abe49464fa26a360765ccb4004`.
Vision serveur/interface : `b33ce9f0c20f4b8af5790831b59217408b496fc0` ;
Matheval : `fc3c2fcd36d920142de946b41154cc6f3a67d76e` ;
Logique : `2e2dd6a48cbdad20bbc8d0ac34a9ace67f111a0f`.

[CI 36257590715](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36257590715)
(132 tests, NixOS et PostgreSQL),
[préparation 36257753511](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36257753511)
et [activation 36257831262](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36257831262)
réussies, sources `d363b178b1f1c33fb8b73c518e20a480411c5985`.
Une nouvelle connexion après finalisation confirme les quatre liens et fichiers,
les services/sauvegardes et le retour automatique désarmé. La génération active
et par défaut `g24p3rvq97s1x66wiaw29z5kwqgw0ksl` et l’entrée NixOS sont conservées.

Les 32 sondes HTTP/TLS, les ressources exactes des trois sites, seize vues publiques,
les sessions/CSRF, Basic, Bearer, OAuth et treize outils MCP ont été vérifiés.
Les captures publiques ont été examinées. La première tentative a été annulée
et corrigée : permissions npm trop restrictives, contrôlées maintenant sous le
compte réel avant bascule. Aucun nouveau schéma ni restauration de données ;
les démarrages gardent leurs vérifications SQL idempotentes existantes.

La synchronisation finale de Mémoire sur `master`,
[36258073154](https://github.com/MrJ-am/M-moire/actions/runs/36258073154),
a également réussi : 56 tests navigateur et 107 fichiers servis identiques.

Procédure et limites : [INTERFACES-DOCUMENTAIRES.md](INTERFACES-DOCUMENTAIRES.md).
Références, preuves et empreintes : [interfaces-publication.json](../operations/interfaces-publication.json).
La page `/auth/mcp` conserve son interface propre. Les anciennes versions restent
disponibles ; un retour ultérieur constitue une nouvelle opération applicative.

## Vision 2.2 publiée et séances ouvertes préservées

Serveur et interface `5c92e0827c13cddaeb0bac852e57b3b26491670a` actifs ;
source VPS `35718a7ba5cbaf14132aab990dabd8f6a08e4509`.
CI applicative `36198122892`, interface `36198122897`, infrastructure
`36198498811`, préparation `36198681603`, activation `36198786537`
et constat indépendant `36198944200` réussis le 25 septembre UTC
(26 septembre à Paris). La migration additive 012 a été testée sur une
restauration isolée puis activée sans modifier les données : **deux séances
ouvertes conservées**, aucune séance fictive créée. Treize outils MCP, Basic,
Bearer, OAuth, interface et sites ont été contrôlés. Le retour autonome est
désarmé ; la génération NixOS est inchangée. La clôture des séances reste
à l'initiative de la personne.

## Révision séquentielle publiée le 25 septembre 2026

Application `608c34cacdd0040dd84c4507f26d7799d70d4f38`, source VPS
`766316cae5b71964c98e73bce476243087d0a2b5`. Préparation
[36164763326](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36164763326)
(réussie à la deuxième tentative après un délai SSH avant tout changement),
activation [36164997869](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36164997869)
et constat [36165233858](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36165233858)
réussis. Migrations additives 009 et 010 appliquées sans modification des données
existantes. Une préparation ciblée expose au plus un item ; son texte de retour
ordonne d’enregistrer chaque tentative par `evaluer_items` avant un nouvel appel
à `preparer_revision`. Basic, Bearer, OAuth, navigateur, services et 32 sondes
HTTP/TLS ont été contrôlés. L’état actif et de démarrage NixOS est conservé,
les deux publications Vision pointent vers cette application, et le retour
est désarmé après le constat.

## Publication réelle du 25 septembre 2026, 14:14 UTC

Serveur et interface `ad0fbd80401c0d2aed77b12d11e3f1b3e8397367` actifs ;
source de migration `951e80e1a66c1240541655a3eca6b435e62e4165`.
[Préparation 36145808884](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36145808884),
[activation 36146012682](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36146012682)
et [constat après finalisation 36146366039](https://github.com/MrJ-am/vps-infrastructure/actions/runs/36146366039)
réussis. L’activation s’est terminée et le constat confirme le retour inactif.

Migration : **2 fiches, 58 items, 58 liens, 18 observations archivées**,
45 items sans évaluation attribuable. Stabilité initiale : 45 à −15 dB,
8 à −12, 4 à −17, 1 à −20 ; heuristique prudente documentée, aucune conversion
des paramètres FSRS. Le dump frais après arrêt des écritures a été restauré,
simulé et importé deux fois en base isolée avant l’import réel atomique.
Les sources historiques et les écritures v2 restent conservées.

Les 32 sondes HTTP/TLS, services/sauvegardes, nouvelle connexion runner,
neuf outils MCP, instructions 2.0.0/db-1, Basic/Bearer/OAuth/Origin null,
CSRF, tokens préexistants, artefact exact et navigateur ont été vérifiés.
Les contrôles n’ont créé aucune donnée métier fictive en production.

La génération active/par défaut reste
`g24p3rvq97s1x66wiaw29z5kwqgw0ksl-nixos-system-nixos-26.05.8639.c5c4a43b0e80`.
Matheval `f6706f8a6b6b08d797340e26f917a6cdc3bb9e5c` et Logique
`615439c841db1934ffaddc1dee64c85ff6c56cf2` restent actifs.
Sources identité `cb0294c8b78402de1566f54ea3009fbe6ee221c7`.
Les chiffres et empreintes sont dans
[vision-refonte-publication.json](../operations/vision-refonte-publication.json).

Les clients MCP doivent recharger leur catalogue si les cinq anciens outils
restent visibles. Aucun essai dans les comptes personnels des clients n’est
revendiqué. Le [rapport applicatif](https://github.com/MrJ-am/vision/blob/main/rapports/REFONTE-20260925.md)
décrit les contrôles, le modèle et ses limites.

Les états datés ci-dessous sont historiques.

## Rétablissement des tokens et OAuth Vision, 23 septembre à 02:11 UTC

La génération active et de démarrage `sz7w3lqm1lspcdzrqisi23xb6lv9886d`
importe les sources `96dc1e8e95b091dd0f13cc9d99002f0cd932210a`.
La [préparation 35809113793](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35809113793)
et l'[activation 35809202327](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35809202327)
ont réussi. Le [contrôle après finalisation 35809360397](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35809360397)
confirme le service actif, la page multi-tokens et la lecture de
`access_tokens` ; deux tokens préexistants restent actifs. Le retour autonome
est désarmé. Les 32 contrôles des sites et services, Basic, Bearer, les cinq
outils, lecture MCP, CSRF, révocation et rendu mobile ont réussi. La sonde
OAuth a vérifié découverte, enregistrement, consentement, code PKCE,
initialisation MCP et révocation du jeton temporaire sans écrire de fiche.

La précédente publication de tokens avait été annulée après coup par un
ancien timer de retour issu d'une tentative échouée, alors que la nouvelle
génération utilisait le même dérivé Nix. Le retour immédiat arrête désormais
son propre timer et refuse de remplacer une génération enregistrée par une
opération ultérieure ; deux tests couvrent le cas. La base SQLite n'a pas été
restaurée et le token Mistral est conservé. Le test de connexion dans le compte
Mammouth du propriétaire reste à refaire. Détails : [VISION-OAUTH.md](VISION-OAUTH.md).

L'essai initial de cette nouvelle publication,
[35808794433](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35808794433),
a été annulé correctement par son retour. Il échouait dans la sonde qui ne
lisait que le premier en-tête `WWW-Authenticate` ; Nginx émet plusieurs défis.
La sonde corrigée vérifie l'ensemble et a réussi sur le candidat final.

## Tokens Vision indépendants et menu publiés

La gestion des tokens par nom, historique et révocation individuelle est active sur
`https://vision.mrj.am/auth/mcp`. Le token Mistral préexistant a été conservé.
La [préparation 35804593654](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35804593654)
et l’[activation 35804717827](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35804717827)
ont validé Basic, Bearer, cinq outils, lecture, CSRF, rendu mobile et révocation
du seul token temporaire. Sources d’authentification `d71dff5858b221a4eb91655674ab1db74893a5a0` ;
génération active et enregistrée `qd9nkmq2yv55zdb5wfhab1sdy4w1hxvv`.
Les versions du serveur Vision, de Matheval et de Logique ont été conservées.

L’artefact de l’interface Vision `cb92ffa7e4ea5b547e09c9ad1d6dbe01c7e93ccf`,
validé par les CI applicatives 35801855474 et 35801855496, a été préparé par
l’[exécution 35805254157](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35805254157)
puis [publié et vérifié en production par 35805299046](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35805299046).
Le manifeste, les fichiers servis, la connexion réelle, la lecture PostgreSQL,
les protections CSRF et le lien du menu vers `/auth/mcp` ont été contrôlés.
La publication statique remplace uniquement le lien de l’interface ; un retour
autonome à quinze minutes était armé pendant les vérifications et a été désarmé
après leur réussite. Aucune fiche de test n’a été créée.

## Historique attesté au 22 septembre 2026

## Journal HTTP : activé le 22 septembre 2026

La [bascule 35792035605](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35792035605)
a réussi, commit opérateur `c2c3cf2e1073fb17113eabe26798e9862de0eb0f`.
Sources `4345e4ef59765c156aec937fd3a2d4f646f188eb`,
[CI 35791604558](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35791604558),
[préparation 35791837515](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35791837515).

Génération active et par défaut :
`/nix/store/dr7qkvrabfp62qqrc064pr99c9gjvjn6-nixos-system-nixos-26.05.8639.c5c4a43b0e80`.
Entrée conservant tous les sites et le token MCP :
`/etc/nixos/vps-infrastructure/http-4345e4ef59765c156aec937fd3a2d4f646f188eb/hosts/hostinger/logique.nix`.
Ancienne génération `h4rv6sn1izf1hv53qihsgrvkg1hy0j28` protégée. Retour autonome
armé avant l'essai et désarmé après validation et enregistrement.

Journal JSON Nginx dans `journalctl --namespace=http -t http_acces`, catégories
de routes sans paramètres, corps, cookies ou Authorization. Budget persistant
128 Mio (hors marge des fichiers actifs journald), rétention maximale 14 jours,
rotation/compression et limitation de journalisation. L'espace séparé préserve
les journaux système ; des pertes sont possibles sous saturation. Erreurs
natives Nginx limitées à `crit` pour éviter de recopier les URL des refus usuels.
Les anciennes traces ne sont pas supprimées.

Preuves : sondes HTTP 200/401/429 présentes et marqueurs confidentiels absents
du journal structuré ; 32 contrôles HTTP/TLS, huit unités actives, nouvelle
connexion SSH, lecture Basic. Aucun token permanent remplacé ou révoqué,
aucune écriture métier, restauration SQL ou modification applicative. Seul
Nginx a redémarré ; Nixpkgs et PostgreSQL sont conservés.

Audit réel : limites par IP 5/s et connexions sur REST/MCP Vision ; pas de
plafond global ni limite explicite sur Matheval/statique. SYN cookies actifs.
La configuration ne constitue pas une protection DDoS complète ; aucune
protection réseau du fournisseur n'est attestée. Les limites HTTP existantes
n'ont pas été modifiées. Rapport et modalités : [JOURNAL-HTTP.md](JOURNAL-HTTP.md),
preuve machine : `operations/http-publication.json`.

## Token MCP Vision : activé le 22 septembre à 21:22 UTC

L’authentification Bearer fonctionne sur `https://vision.mrj.am/mcp`, en plus
de Basic. Après connexion, `https://vision.mrj.am/auth/mcp` permet de créer,
remplacer ou révoquer son token. Le token de contrôle a été révoqué ; aucun
secret permanent n’a été enregistré dans Git ou affiché dans les journaux.

Sources : `b389fb7002ba4bd62e9585b98a9d0a5b89c4b92d`,
[CI réussie](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35785539670).
[Préparation 35785801163](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35785801163),
[activation 35786083939](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35786083939),
commit opérateur `64ac2c7009c6295987db45a02956d4eee01d2fba`.

Génération active et par défaut :
`/nix/store/h4rv6sn1izf1hv53qihsgrvkg1hy0j28-nixos-system-nixos-26.05.8639.c5c4a43b0e80`.
Entrée NixOS :
`/etc/nixos/vps-infrastructure/mcp-b389fb7002ba4bd62e9585b98a9d0a5b89c4b92d/hosts/hostinger/logique.nix`.
L’ancienne génération `y35z1d3l6882ylrz7glrq7q7yp4zyks7` reste protégée.
Le retour autonome a été armé avant l’essai puis désarmé après les contrôles.

Seuls mrj-auth et Nginx ont été remplacés/redémarrés. Serveur Lisp, interfaces,
Matheval, Logique, données et versions Nixpkgs/PostgreSQL conservés. Vérifications :
32 contrôles HTTP/TLS, services et sauvegardes actifs, nouvelle connexion SSH
du runner, Basic/Bearer, initialize, cinq outils, notification, lecture MCP,
CSRF, refus hors MCP, rendu mobile/bureau, absence de stockage navigateur et
révocation. Les écritures MCP passent en PostgreSQL isolé dans la
[CI Vision 35785184379](https://github.com/MrJ-am/vision/actions/runs/35785184379).
Aucune fiche ou observation de test n’a été créée en production.

Détails : [VISION-MCP-TOKEN.md](VISION-MCP-TOKEN.md) ; preuve machine :
`operations/mcp-publication.json`. Le raccordement dans le compte Mistral du
propriétaire reste à faire avec le token qu’il générera ; aucun test dans son
compte Mistral n’est revendiqué.

## Correction Logique et interfaces communes

Logique et l'interface Vision sont publiés depuis le 22 septembre à 11:13 UTC.
La [préparation 35719822363](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35719822363)
et l'[activation 35720088997](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35720088997)
ont réussi sur les sources d'infrastructure
`273139f1e66e7284af185fde66bf442cf7c9da03`, CI `35719627664` réussie.
Le commit opérateur d'activation est `436b0019fd10f4ad37c0bc030511f568a80411b2`.

| Élément | Référence réellement servie |
|---|---|
| Logique | `615439c841db1934ffaddc1dee64c85ff6c56cf2` |
| Interface Vision | `dbf5fcb3b1c70ec8ee1717db8e17527619840245` |
| Matheval | `ebae2c9d358e4b76d120b85e12afb4193cc37967` |
| Style commun | `b2177c0fd2c46c6f528266d30f7b933d3add1566` |
| Signature | `17495b13cefa24473e37434b98336b27caec8cdf` |
| Serveur Vision inchangé | `151ab64bd5c9c5c54297e88dbe4d548343cc4928` |
| Génération active et par défaut | `/nix/store/y35z1d3l6882ylrz7glrq7q7yp4zyks7-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Génération précédente protégée | `/nix/store/bbp9i9c94l8f4lvkr23qlgghhlw29qdd-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |

[Logique](https://logique.echos.systems/?accueil=1) sert l'application avec son
vrai certificat. Les 80 ressources et le manifeste servi ont été vérifiés,
ainsi que quatre formats d'écran et les cinq lecteurs Vimeo réels. Les anciennes
adresses `/matheval/` sur ce domaine sont récupérées vers une URL distincte de la
racine anciennement mise en cache. Les hôtes inconnus sont refusés par Nginx.
Aucune intervention sur un éventuel domaine `logic.ecos.systems` n'est revendiquée.

Les 13 ressources et le manifeste de Vision correspondent à l'artefact testé.
Le rendu, les polices, deux formats, la connexion avec le compte existant,
le cookie, CSRF, l'origine, la lecture PostgreSQL, Basic et la révocation
ont été contrôlés sans écriture métier. Les captures ne montrent que la connexion vide.
Les 22 contrôles HTTP/TLS précédents, les six services, les deux sauvegardes
et une nouvelle connexion du runner ont réussi. Le retour autonome de vingt
minutes a été armé avant l'essai, puis désarmé après enregistrement du démarrage.
Les bases n'ont pas été restaurées ; les anciennes versions restent conservées.

Matheval est publié à 11:23 UTC par son
[workflow 35720485951](https://github.com/MrJ-am/M-moire/actions/runs/35720485951).
Les 56 tests Firefox/Chromium/tactiles et les 16 tests API PostgreSQL 17 ont
réussi, puis les 107 fichiers réellement servis ont été comparés à l'artefact.
Le service est actif et les accès administratifs anonymes sont refusés.
La migration additive des sessions accompagne cette version ; les réponses
collectées et l'ancien déploiement `9ad544dfc7ce546a851e01b6c8f9a2a8334ca616`
sont conservés. La version précédente ne serait restaurée que par retour
applicatif, sans restauration de la base.

L'entrée NixOS active importe
`/etc/nixos/vps-infrastructure/273139f1e66e7284af185fde66bf442cf7c9da03/hosts/hostinger/logique.nix`.
Ce point d'entrée complète `projects.json` avec `operations/logique-site.json`.
Conserver ce domaine, les routes Vision et le refus des hôtes inconnus dans
les prochaines générations : la configuration de base seule ne représente pas
cette publication. Toute nouvelle opération reprend l'état réellement actif.

Preuves durables : `operations/corrections-publication.json`,
[procédure](CORRECTIONS-SITES-20260922.md),
[audit de sécurité](AUDIT-AUTHENTIFICATION-20260922.md), registre de coordination.
Les états antérieurs ci-dessous sont conservés comme historique.

## Historique au 21 septembre

## Vision ElmUI : publiée et enregistrée le 21 septembre à 22:32 UTC

L'[activation nº 35663052741](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35663052741)
a réussi sur [vision.mrj.am](https://vision.mrj.am/), depuis le commit opérateur
`12d9765413501c9911728bc3ca7a9220b6325e9b`. Les 13 fichiers du manifeste sont
identiques à l'artefact applicatif testé. Chromium a vérifié le rendu à 375 et
1280 pixels, la police exacte, la connexion avec le compte permanent, le cookie
commun, CSRF et l'origine, la lecture PostgreSQL, Basic et la révocation.
Les captures conservées montrent uniquement la connexion vide.

| Élément | Référence active |
|---|---|
| Interface Vision | `9a4c395b24e6eb8938a3246c96f5d80c030c2d2d` |
| Style partagé | `c7b4d6e00cd0014a0a05e5a4e77627357498faa9` |
| Signature | `17495b13cefa24473e37434b98336b27caec8cdf` |
| Sources du candidat d'infrastructure | `d224ab32928c43ef7f9445804077a2dbfb0fdfba` |
| Génération active et par défaut | `/nix/store/bbp9i9c94l8f4lvkr23qlgghhlw29qdd-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Génération précédente protégée | `/nix/store/ppx3gxdx4rw36wah3wdz9lfdkl7z72ln-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Serveur Vision conservé | `151ab64bd5c9c5c54297e88dbe4d548343cc4928` — 1.3.0 |
| Matheval conservé | `0c2758f5a1df6821903a684e9a3c41f600acf02c` |

La [préparation nº 35662657824](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35662657824)
a conservé les sources et générations, produit les sauvegardes chiffrées des
deux bases, comparé les invariants, testé Nginx et déclenché le timer indépendant.
La [simulation complète nº 35662944719](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35662944719)
annonçait seulement le redémarrage de Nginx. La bascule a vérifié une nouvelle
connexion SSH, les six services, les deux timers de sauvegarde et les 22 contrôles
HTTP/TLS. La génération testée est enregistrée ; le timer de retour est désarmé.
Aucune écriture métier, migration SQL, rotation de compte ni mise à jour NixOS.

L'entrée NixOS importe
`/etc/nixos/vps-infrastructure/vision-interface-d224ab32928c43ef7f9445804077a2dbfb0fdfba/configuration-interface.nix`.
Elle assemble l'entrée antérieure et le nouveau module de fichiers statiques.
`/srv/vision-interface/current` pointe vers la révision applicative ci-dessus.
L'import `apps/vision-interface.nix` est également intégré à la configuration
principale du dépôt pour que les prochaines générations conservent cette desserte.
Les preuves et le mécanisme de publication sont décrits dans
[VISION-INTERFACE.md](VISION-INTERFACE.md).

**Relais pour Logique :** toute préparation calculée avant cette bascule utilise
une génération antérieure. La refaire depuis l'état actif et les sources intégrant
le module Vision, en conservant ses cinq routes ; ne pas réutiliser aveuglément
un ancien candidat ACME/HTTPS. La publication parallèle de Logique reste une
opération distincte. Aucun redémarrage du VPS n'a été effectué.

## Préparation Logique du 21 septembre : aucune activation à cette date

Le site `logique.echos.systems` est préparé sur `preparation/logique-vps`.
L'[audit nº 35637628338](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35637628338),
commit `ba66dfcf939f299f9a296658aeaab938366b719e`, a réussi à 18:19 UTC :
22 contrôles HTTP/TLS existants, DNS A `187.77.95.158` sans AAAA, générations
identiques et seconde connexion du runner. Aucun certificat Logique ni
publication au chemin alors contrôlé (`/srv/apprendre-a-demontrer/current`)
n'était présent ; le nouveau précontrôle examine aussi `/srv/logique/current`.

Le nouveau lot ajoute les candidats ACME puis HTTPS, les contrôles statiques
et une préparation distincte de toute activation, intégrée sur `main`.
L'archive applicative `10667157261`, révision `7a356ca3ec3682c95aa841c968822c24dc683dbe`,
a été vérifiée : ZIP et 75 fichiers `dist` conformes, ressources identiques
à la référence fonctionnelle initiale. La CI publique `35661154380` a réussi.
La [validation typographique privée nº 35661307369](https://github.com/MrJ-am/Signature/actions/runs/35661307369)
a également réussi : deux fontes originales, géométrie, huit contextes HTTP,
sélection et copier-coller natif, puis examen des captures à 320 et 1280 pixels.
Le rapport durable figure dans `operations/logique-typographie.json`.
L'archive de préparation exclut les fontes et reste non publiable ; le candidat
complet devra être contrôlé et conservé par le mécanisme privé collectif.
La [construction VPS nº 35659924636](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35659924636)
a réussi le 21 septembre à 21:57 UTC. Le commit opérateur
`d659dde6034056dac2be73519804ce2ee33cb436` a construit les sources testées
`e9a4ed68fa71a072ff0815d28e7e3ffd3e9517ae` avec le Nixpkgs déjà installé.
Les invariants sont identiques, Nginx ACME passe son test réel, les six services
et les deux timers restent actifs. Les 22 contrôles HTTP/TLS réussissent avant
et après, avec une nouvelle connexion du runner.
Le relevé final conserve exactement génération, profil, entrée et versions
Matheval/Vision ; certificat et publication Logique sont toujours absents.
Le rapport est conservé dans `operations/logique-construction.json` et sur
le VPS. Le retour est écrit et vérifié syntaxiquement, sans timer armé.
HTTPS attend son vrai certificat ; aucune bascule n'est effectuée.
La [CI nº 35656506154](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35656506154)
a réussi au commit `b722165485e9b3b325b150f05ae7da5919a57984` : 55 tests,
Nginx réel, évaluations NixOS complètes des deux phases et des invariants,
ainsi que PostgreSQL 17 et ses restaurations isolées.
Lire [LOGIQUE.md](LOGIQUE.md) pour les références, les preuves et les étapes restantes.

## Historique : Vision web et sessions mrj.am, 20 septembre

Vision 1.3.0 est **activé et enregistré depuis 22:32 UTC** sur
`https://vision.mrj.am/`. La [bascule nº 35541957332](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35541957332)
atteste la nouvelle génération après une nouvelle connexion SSH, six services
actifs, les deux timers de sauvegarde et 22 contrôles HTTP/TLS depuis le VPS,
puis 22 depuis le runner GitHub. La connexion web, CSRF, le refus anonyme,
la lecture PostgreSQL et la révocation de session ont réussi. Les identifiants
de sonde ont été retirés et les identifiants antérieurs conservés.

| Élément | Référence vérifiée le 20 septembre |
|---|---|
| Sources d'infrastructure installées | `d3699cd829bf996540a53085fe2c0539d9552ebc` |
| Sources Vision | `151ab64bd5c9c5c54297e88dbe4d548343cc4928` — version `1.3.0` |
| Répertoire installé | `/etc/nixos/vps-infrastructure/d3699cd829bf996540a53085fe2c0539d9552ebc` |
| Génération active et par défaut | `/nix/store/ppx3gxdx4rw36wah3wdz9lfdkl7z72ln-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Génération précédente protégée | `/nix/store/nndnndfac30p7rnwrxbk8sr6hljk5y5b-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Services actifs | `sshd`, `nginx`, `postgresql`, `matheval`, `vision`, `mrj-auth` |
| Sauvegardes quotidiennes actives | `postgresqlBackup-matheval.timer`, `postgresqlBackup-vision.timer` |
| Compte permanent | Activé le 21 septembre 2026 à 05:18 UTC ; accès API vérifié |

La [préparation nº 35541853819](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35541853819)
a contrôlé la génération, les invariants, les sauvegardes chiffrées des deux
bases et le retour complet de l'essai précédent. Nixpkgs, PostgreSQL, les
certificats et les paramètres de Matheval sont conservés. Le timer de retour
de cette bascule est désarmé après enregistrement ; les anciennes générations
et les preuves restent protégées. Aucun redémarrage du VPS n'a été effectué.

Lors de la bascule, le compte permanent n'était pas encore défini.
Le propriétaire a ensuite enregistré les deux secrets de compte dans
`vps-production`. Le [renouvellement nº 35564114945](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35564114945),
exécuté au commit `65cedea8e71c157aafdf341e6894d4185b5ed651`, a réussi le
21 septembre 2026 à 05:18 UTC : validation des secrets, installation du compte,
accès HTTPS authentifié à l'API et nettoyage des fichiers temporaires.
Le compte est commun au navigateur et à l'API générale ; le service de sessions
lit ce même fichier d'identifiants. Aucun secret n'est conservé dans ce rapport.
Les prochaines rotations suivent [VISION-WEB.md](VISION-WEB.md).
Le navigateur de la session Work reçoit encore une erreur 502 au 21 septembre ; le rendu
visuel n'a donc pas été vérifié depuis ce navigateur. Ce constat est distinct
des contrôles HTTP/TLS réussis sur le VPS et sur le runner GitHub.

La [CI d'infrastructure nº 35541763449](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35541763449)
et la [CI Vision nº 35540278729](https://github.com/MrJ-am/vision/actions/runs/35540278729)
ont réussi. Les fonctionnalités et les reprises des deux premiers essais
sont détaillées dans [VISION-WEB.md](VISION-WEB.md).

## Historique : migration du 18 septembre 2026

La migration de l'infrastructure est **activée et enregistrée depuis 21:10 UTC**.
Nginx, HTTPS, NixOS et PostgreSQL sont gérés par ce dépôt. Matheval conserve
son application, ses données, son schéma, ses publications et ses exports chiffrés.

## Références installées le 18 septembre

| Élément | Référence vérifiée |
|---|---|
| VPS | `187.77.95.158`, Hostinger `1982677` |
| Sources VPS installées | `fa059d61acfc8cf5c5bd7f3f9c83600787f2c6eb` |
| Commit opérateur de la bascule | `49d82f8167b8121fb03c7d95da02169bb6409e28` |
| Répertoire des sources | `/etc/nixos/vps-infrastructure/fa059d61acfc8cf5c5bd7f3f9c83600787f2c6eb` |
| Génération active et par défaut | `/nix/store/8cbhcffxr0xhybz2va6yz8rrxfgqgzy9-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Ancienne génération protégée | `/nix/store/5840x51nc7d2s7gw0zfyy6my47j6nh1i-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Nixpkgs conservé | `/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos` |
| PostgreSQL | `17.11`, données `/var/lib/postgresql/17`, socket `/run/postgresql`, aucune écoute TCP |
| Matheval pendant la bascule | `d8d0f17f37f030d58c152d5e57ca2e2c5b5814ea` ; version de l'API `0.3.0` |
| Matheval après le relais | `841317fb87c8f81867ad884ca19ef93e8308838b` sur `master` |

`/etc/nixos/configuration.nix` importe la configuration de l'hôte dans le
répertoire des sources installé. Le module Matheval est la copie exacte du
commit amont `0bcdaf101cbdacb85694ca217fd21ab3f2eac828`, SHA-256
`8959538472392c6bff39cf91e3eeaa125b6814f0af15d63381258a51baf20086`.
Sa provenance figure dans `vendor/matheval/source.json`. Le patch historique
n'est plus à appliquer. Vision reste un exemple, sans service ni base activés.

## Contrôles et sauvegardes

- [Audit final nº 35396774874](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35396774874),
  commit `30decc1ab1deb39cd147dd289bd6a836e7a6c925`, réussi à 21:26 UTC après
  la publication de Mémoire : génération active et par défaut attendue,
  entrée NixOS persistante, retour désarmé, anciennes générations protégées,
  quatre services actifs, PostgreSQL et ses droits conformes, version applicative
  `841317fb87c8f81867ad884ca19ef93e8308838b` et onze contrôles HTTP/TLS réussis.
- [Préparation nº 35395032430](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395032430) :
  sauvegarde des sources et de la base, construction avec le Nixpkgs installé,
  comparaison des invariants, restauration isolée et retour ciblé des ACL testé
  deux fois. Seules les unités Matheval, PostgreSQL et son provisionnement
  changent ; Nginx, le réseau, SSH, le noyau et les certificats sont conservés.
- [Plan nº 35395215119](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395215119) :
  précontrôle exécuté depuis systemd avec l'environnement explicite, dry-run
  limité à PostgreSQL et Matheval, déclenchement du timer indépendant vérifié.
- [Bascule nº 35395320446](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395320446) :
  essai sous verrou de publication avec retour à quinze minutes, nouvelle
  connexion SSH, services actifs, onze contrôles HTTP/TLS et empreintes publiques
  identiques, refus anonymes 401, connexions SQL autorisées/refusées vérifiées.
  Les lignes antérieures et l'identité du stockage PostgreSQL sont conservées.
  La sauvegarde locale a été déclenchée puis restaurée dans une instance isolée ;
  l'export chiffré hors VPS a réussi. La même génération a ensuite été enregistrée
  pour le démarrage, et le timer a été désarmé après validation.
- [CI VPS nº 35395320531](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395320531) :
  vingt tests Python, syntaxe Nix, évaluations NixOS, isolation PostgreSQL 17 et
  restaurations dans un conteneur jetable réussis.

Les copies chiffrées de migration sont conservées trente jours dans les artefacts
[avant](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395032430/artifacts/10567635113)
et [après](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395320446/artifacts/10567442831).
Les sauvegardes locales quotidiennes restent dans `/var/backup/postgresql`.
Le workflow Mémoire conserve son export chiffré quotidien et sa rétention de
quatorze jours ; la clé privée age reste hors du VPS et hors Git.

Le dossier privé `/root/vps-migrations/fa059d61acfc8cf5c5bd7f3f9c83600787f2c6eb/`
conserve `etc-nixos-before.tar`, `configuration.nix.before`, `rollback-acl.sql`,
les sauvegardes privées et `committed.json`. Les racines de GC sous
`/nix/var/nix/gcroots/vps-migrations/fa059d61acfc8cf5c5bd7f3f9c83600787f2c6eb/`
protègent l'ancienne génération, le candidat, Nixpkgs et Python.

Le retour autonome de l'essai est volontairement inopérant après enregistrement.
Un retour ultérieur doit faire l'objet d'une nouvelle opération VPS, après
examen des changements intervenus depuis. Ne pas restaurer un dump de production
pour revenir à une configuration ; le retour NixOS ne restaure pas les droits SQL.

Aucun redémarrage du VPS n'a été effectué. Le profil et le menu de démarrage
sont enregistrés ; le comportement après un redémarrage réel reste un contrôle
distinct à planifier dans une fenêtre appropriée.

## Relais Mémoire

Les consignes, le contrat et les références du serveur ont été actualisés au
commit `3896f94bd129a197c904c08e5544108b5c0a7c68`, dans la
[PR nº 8](https://github.com/MrJ-am/M-moire/pull/8). Elle inclut le déclenchement
du workflow de sauvegarde existant par `deploy/backup-request.json` sur `master`,
avec le compte `matheval-deploy` et les secrets existants. La
[CI de la PR](https://github.com/MrJ-am/M-moire/actions/runs/35395609673) a réussi,
dont quatorze tests API et trente-deux tests navigateur. La PR est fusionnée
sur `master`, commit `841317fb87c8f81867ad884ca19ef93e8308838b`.

La [sauvegarde Mémoire nº 35396161367](https://github.com/MrJ-am/M-moire/actions/runs/35396161367)
a réussi depuis `matheval-deploy` après la bascule, et son artefact chiffré
`matheval-backup-35396161367` est disponible jusqu'au 2 octobre 2026.
La [publication applicative](https://github.com/MrJ-am/M-moire/actions/runs/35396161100)
a réussi sur `master` : tests, déploiement avec `matheval-deploy` et comparaison
des fichiers servis avec le manifeste de la version vérifiée. L'intégration
de Mémoire est terminée ; ses publications ne reconstruisent pas NixOS.

## Accès et reprise de la tentative interrompue

Depuis ChatGPT Work, **toutes les opérations VPS passent par GitHub Actions**.
Work ne dispose pas de connexion SSH directe. L'environnement `vps-production`
contient la clé administrative existante, enregistrée avec l'autorisation du
propriétaire, et autorise uniquement la branche `main`, sans tag. Les workflows
applicatifs conservent leur compte de publication sans accès root général.

La première tentative [nº 35351617482](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35351617482)
a échoué avant l'activation : son service systemd ne recevait pas `NIX_PATH`.
Le retour a rétabli l'ancienne génération mais n'a pu lire le fichier SQL privé
sous le compte `postgres`. L'[audit de reprise](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35394636820)
a confirmé l'ancienne génération, les anciens droits, les quatre services actifs
et onze contrôles publics réussis. Aucune activation du candidat n'avait eu lieu.

Les corrections fixent l'environnement du service et font ouvrir le fichier
SQL par root avant de le transmettre à `psql`. La première reprise de l'unité
ancienne a constaté qu'elle avait été collectée par systemd ; une nouvelle unité
a exécuté le [retour complet nº 35394938751](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35394938751)
avec succès, droits SQL et contrôles publics compris. La nouvelle préparation
puis la bascule réussie ci-dessus utilisent un dossier distinct. Les preuves
de l'ancienne tentative restent conservées sous son identifiant `088d36c15f2f…`.


## Vision 2.4 — 27 septembre 2026

Vision serveur et interface : `d5d6217b95b7548af7b7ed9009321a413f1c998b`, candidat VPS `be2b7fdd81a64b2f7aea02da106401da93789e68`. Préparation 36338925947, activation 36338989951, constat après finalisation 36339153877 réussis. Migration 013/014, états mémoriels et une séance ouverte préservés ; retour inactif, NixOS inchangé. Détails et incident corrigé dans [VISION-REFONTE.md](VISION-REFONTE.md) et [le rapport](../operations/vision-refonte-publication.json).

## Vision — tableaux éditables et retards, 27 septembre 2026

Serveur et interface actifs : `3ff7f21f01fa63ed740672f9b331e46d50704b8c`, candidat VPS `94f2de6a8b00016e14b5494a58ef4f0226a830ae`. Préparation 36347688045, activation 36347783328 et constat 36348090796 réussis. Les données, 187 observations historiques et une séance ouverte sont préservées ; retour inactif, génération NixOS inchangée. Voir [VISION-REFONTE.md](VISION-REFONTE.md) et [le rapport](../operations/vision-refonte-publication.json).

## Nextcloud — 29 septembre 2026

`cloud.mrj.am` sert Nextcloud 34.0.4 en HTTPS. Candidat `43a8cd0f551b74b75583bb8aaf849d2a90560618`, intégré par PR 24. Construction réelle sur Nixpkgs installé : exécution 36623222464 ; activation et constat indépendant : 36624255776. Génération active et de démarrage `c06sq9vp17l36j8xp2apyfav1nribpwc` ; retour autonome désarmé. Certificat ACME, administrateur, WebDAV aller-retour, première sauvegarde, restauration isolée (131 tables) et 25 contrôles HTTP/TLS réussis. Matheval, Vision et Logique conservent leurs releases. Le premier essai 36623847704 a été retourné après défaut du validateur de registre ; audit de retour 36624180463. Sauvegarde cohérente locale quotidienne, sans copie chiffrée hors VPS. Voir [NEXTCLOUD.md](NEXTCLOUD.md).

## Vision 2.5 — création sémantique, 4 octobre 2026

Serveur et interface `c0bfcac66b9ee52e282bb895ec6aed3921a86266`, candidat VPS
`32a4c3d2ad0e39568fe16d7acdb2472a7f095fc2`. Audit 37182284525, CI 37200246228,
construction/restauration réelle 37200466652, activation 37200705574 et constat
indépendant 37200895774 réussis. Génération active et de démarrage
`y1azkcagkf54nq5vjn4j16g5v1c61c4c`, ancienne `mabshi6mmisnabl5qb5hwldnkxiz2s25`
protégée, retour désarmé. PostgreSQL reste 17.11 ; pgvector et fournisseur local
activés, migration 016/backfill terminés : 58 items et embeddings, dix-sept tables
historiques intactes. Basic, MCP, navigateur/sessions/CSRF, artefact exact et
25 sondes HTTP/TLS vérifiés. Aucun reboot ni restauration de production.
Le point d'entrée actif importe `vision-semantique.nix` sous la source privée
conservée ; ne pas reconstruire le seul `logique.nix` en supprimant le fournisseur.
Détails et limites : [VISION-CREATION-SEMANTIQUE.md](VISION-CREATION-SEMANTIQUE.md)
et [rapport](../operations/vision-semantique-publication.json).


## Vision — alignement de la marque, 6 octobre 2026

Serveur et interface : `ba19503113f94e2bd73cec27a09b2cf11a143cbe`, style
`3c87b98aa48a5f6a533d7f88de9faf57cff1706d`, opérateur
`412bbcb9ea9983a7f2b29c6bac277402f90d49b9`. Audit 37486943452, CI 37487971501,
préparation 37488460816 (tentative 2), activation 37488989857 et constat
indépendant 37489386224 réussis. Baseline commune et signature entière vérifiées
sur le rendu HTTPS à quatre largeurs et agrandie quatre fois. Vingt tables
préservées ; aucune migration, restauration de production ou modification
NixOS. Retour désarmé. Les autres releases et sauvegardes restent conservées.
Voir [le rapport](../operations/vision-alignement-publication.json).


## Vision — point Echo et AGPL, 6 octobre 2026

Serveur et interface : `ba6c9d8b1f4ef6ad6d0c78ef570d89bbe223eccf`, style
`4e8214970c22160059fe1024f854e8ecb0cbc59e`, opérateur
`f27ea81080d570bc2f905c7fcad4099ac245bc05`. Audit 37491350997, CI 37492890918,
préparation 37493315938, activation 37493485203 et constat indépendant
37493885562 réussis. Motifs des points identiques en HTTPS et marque alignée,
quatre formats et grossissement ×4 vérifiés. Code Vision sous AGPL-3.0-or-later ;
identité réservée, fontes OFL et licences externes conservées. Vingt tables
préservées, aucune migration ni restauration de production. Génération NixOS
et autres releases inchangées, retour désarmé, sauvegardes conservées.
Voir [le rapport](../operations/vision-point-licence-publication.json).

Le 9 octobre à 18:28:33 UTC, diagnostic autonome `37973425279`
(job `113965629376`, commit `239962e014c35c02ef4f4c5b2da96e0fb8e04fd2`,
PR57/281 tests, CI push `37972655858` et PR `37972660633`) : le bilan du
gestionnaire désigne uniquement `nginx.service`, sans unité inconnue.
Le cluster PostgreSQL17 privé reste proprement arrêté et préservé ; aucune
génération enregistrée ni compte humain. Six services/SSH et 25 contrôles
HTTP/TLS avant/après passent, fin 18:28:45 UTC. Voir
`operations/vision-amorcage-bilan-switch.json`. La sortie 143 de l’identité
ne constituait pas la cause initiale.

Le complément suivant lit uniquement `nginx.service` et
`nginx-validate-config.service` dans les namespaces `http` et par défaut,
sur la fenêtre fixe de cet essai (17:05:00–17:06:40 UTC). Le module actif
`journal-http.nix` dirige Nginx vers `http`. Sortie fermée : familles
d’erreurs, noms de directives prédéfinis, compteur d’inconnus, codes
numériques/étapes systemd connus. Aucun fragment, chemin, URL, IP ou valeur
n’est publié ; le journal HTTP général n’est jamais lu. Pas de réparation
ou de relance avant la cause précise, pas d’effacement du cluster.

Diagnostic réservé du 9 octobre à 18:39:40 UTC, exécution `37974721935`
(job `113970038399`, commit `717e9d378e96e63445691e220da6e57f56cc9826`,
PR58/283 tests, CI push `37974107919` et PR `37974111241`) : le journal
Nginx `http` classe le refus comme configuration/syntaxe/permissions ;
le journal par défaut donne une sortie 1. Aucun détail privé publié.
Le cluster17 reste proprement arrêté et préservé ; six services/SSH
et 25 contrôles HTTP/TLS avant/après passent, fin18:39:54 UTC.
Voir `operations/vision-amorcage-nginx-diagnostic.json`.

La précision suivante distingue les sous-familles de syntaxe, opérations
et errno techniques, types de chemins fermés. Seule la ligne numérotée
d’un fichier immuable `/nix/store/HASH-nginx.conf` référencé par l’erreur
est examinée en mémoire : sortie numéro, premier mot s’il est une
directive prédéfinie, mode/lecture publique. Aucun texte ou valeur.
Liens, fichier non régulier, propriétaire/droits invalides, taille excessive
ou chemin inconnu sont refusés. Aucune commande Nginx, relance, SQL,
modification ou effacement. Les mêmes unités/fenêtre/bornes restent imposées.

Complément confidentiel : les seules lignes commençant par
`nginx: [emerg]` de ce relevé sont sélectionnées (16 lignes/16Kio maximum)
et chiffrées en mémoire par AGE vers la clé publique éphémère Work épinglée.
Actions ne reçoit que le cryptogramme ASCII/base64 ; la clé privée reste
dans Work, mode0600, jamais sur VPS/Git/Actions, puis sera supprimée après
le diagnostic. Déchiffrement seulement dans Work en mémoire ou fichier
privé0600 ; toute publication ultérieure expurge les valeurs privées.
Les erreurs par requête, autres niveaux et journaux généraux sont exclus.
Nix-shell fournit AGE depuis le Nixpkgs installé. Ce diagnostic ne
lance pas Nginx et ne modifie ni configuration ni données.

Le 9 octobre à18:58:32 UTC, diagnostic autonome `37976909188`
(job `113977466748`, commit `c320f1b5562cddf11efcdafc3ccdd3d4e0765d44`,
PR59/286 tests, CI push `37976118015` et PR `37976123742` quatre jobs verts) :
jeton inattendu dans le fichier immuable Nginx, ligne215, directive `types`,
mode0444/publicement lisible. Le bloc `types {};` du téléchargement de
sources reproduit nativement `unexpected ";"` ; `types {}` passe.
Six services/SSH et25 HTTP/TLS avant/après passent, fin18:58:44 UTC ;
cluster17 privé proprement arrêté/préservé, aucune activation ou personne.
Voir `operations/vision-amorcage-nginx-cause.json`. Les erreurs ont un
préfixe daté : le canal temporaire ne sélectionne donc aucune ligne.
Aucun déchiffrement réel ; clé Work supprimée et canal retiré.

Les trois blocs analogues (amorçage et deux téléchargements Vision) sont
corrigés. Une régression native vérifie les extraConfig effectivement
présents, avec contrôle négatif du point-virgule. La nouvelle phase fermée
`construction` du point d’entrée main/CI exacte appelle le préparateur
sans saisie manuelle ni concurrence imbriquée. Il construit puis teste
la configuration complète avec le paquet Nginx produit, `nginx -t`,
sous le compte nginx. Paquet/configuration immuables et arguments fermés ;
aucun serveur lancé, stderr privé, rapport booléen. L’activation exige
désormais cette preuve native, absente de l’ancienne préparation765.
La nouvelle construction ne modifie pas le cluster existant ou la
génération active. Une reprise qualifiée avec sauvegarde chiffrée à froid
et retour indépendant sera une opération suivante, sans effacement.
