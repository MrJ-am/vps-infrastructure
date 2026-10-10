# Mise en service Vision : un seul point d'entrée

Depuis le 9 octobre 2026, le propriétaire ne sert plus de relais entre chaque
contrôle technique. L'agent prépare, teste, demande et suit les opérations avec
[Vision — mise en service suivie](../.github/workflows/vision-mise-en-service.yml).
Le lancement manuel reste un secours, sur `main`, sans saisie de paramètres.

## Déclencher depuis les outils GitHub

Après intégration et réussite de la CI du commit **exact**, faire avancer la
branche `operations/vision` à ce commit, sans forcer, avec une comparaison de
son ancienne référence. Si elle n'existe pas, la créer depuis le parent du
commit intégré, puis l'avancer : une simple création de référence ne vaut pas
push et n'est pas une preuve de lancement. Lire ensuite le signal Actions
`Vision — demande d'opération`, puis l'exécution administrative `workflow_run`,
son SHA, les étapes et le rapport.

Cette branche contient exactement le code intégré, sans fichier de commandes,
adresse, mot de passe ou jeton. Elle sert de demande de lancement. Un push sur
`main`, une PR, un fork ou une autre branche ne déclenche pas cette opération.
Le signal n'extrait aucun code et ne reçoit aucun credential. Le workflow
administratif est chargé par GitHub depuis la branche par défaut et extrait
explicitement `main` : du code placé seulement sur la branche de demande ne
peut pas administrer le VPS. Le programme refuse un signal d'un autre dépôt,
d'un autre workflow ou dont le commit diffère du `main` actuel. Il exige la CI
réussie de ce commit avant tout credential VPS, puis revérifie la demande dans
l'étape réservée. La CI complète n'est pas répétée sur la branche de demande.

Les opérations restent exécutées depuis les runners, avec la clé existante,
la clé d'hôte épinglée, `vps-production` et l'exclusion `vps-administration`.
Aucun SSH depuis Work, aucun accès administratif supplémentaire et aucune
commande distante paramétrable. Publier du code et demander une opération
restent deux actions distinctes.

## Avancement et interventions

| Phase | Situation au regroupement | Suite |
|---|---|---|
| Courriels, restauration isolée, paquet et composants | Qualifications VPS réussies, références dans les documents correspondants | Réutiliser les preuves et vérifier les préconditions |
| Génération réservée | Génération réservée enregistrée par Actions `37994597242`, après contrôles natifs/SSH/25HTTP/TLS | Génération enregistrée, service et compte initial vérifiés ; préparer la bascule distincte |
| Compte commun du propriétaire | Compte/email/password/OTP et connexion pwd+otp fraîche vérifiés :0fbce8d/38002451652 | Étape humaine validée ; préparer association historique et bascule, sans considérer la session historique comme fraîche aujourd’hui |
| Rattachement historique et bascule Vision | Préparation complète réussie38045641408 : restaurations/association/admin/ACL isolés et dix composants construits ; production inchangée | Vérifier clé personnelle et copie extérieure, puis qualifier un essai distinct avec retour SQL/NixOS autonome et interface figée |
| Invitations à des tiers | Fermées | Vérifier séparément les préconditions juridiques et de sauvegarde avant ouverture |

Le premier enchaînement appelle la recette réservée déjà préparée : lecture
des preuves privées et du socle, copie locale chiffrée, simulation, répétition
du timer, retour autonome armé, essai indépendant de SSH, contrôles privés,
25 sondes HTTP/TLS et nouvelle SSH, HTTPS d'identité, puis enregistrement.
Les qualifications de construction précédentes ne sont pas refaites.

La phase courante vient uniquement de `operations/vision-mise-en-service.json`
sur le main qualifié : valeurs fermées `amorcage`, `diagnostic`, `construction`, `proprietaire`, `proprietaire-observer`, `vision-preparer` ou `vision-diagnostic`, sans paramètre libre.
Le diagnostic lit seulement les journaux privés de la tentative identifiée,
classe les refus et revérifie le socle. Il ne modifie ni génération ni base.
Les phases restent des jobs explicites du même point d'entrée.

Le déclenchement autonome est attesté par le signal `37953863382` puis
[l'exécution 37953882332](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37953882332).
Elle s'arrête pendant la simulation, avant l'essai ; l'entrée candidate
reproduit bien la génération construite, le contrôle final du socle et les
25 sondes passent. Le refus sera diagnostiqué par l'agent via ce même point
d'entrée, sans solliciter un nouveau lancement du propriétaire.

Le diagnostic `37955815952` établit l'arrêt prévu de
`systemd-tmpfiles-resetup.service`, d'une unité ACME et le redémarrage de Nginx,
avec aucune unité inconnue ; socle, six services/nouvelle SSH et25sondes passent.
La reprise ajoute un contrôle strict des répertoires avant d'autoriser ce seul
arrêt. Les règles anciennes et la commande de l'unité doivent être conservées ;
seule la création root0700 du répertoire de sauvegarde réservé est admise.
Les prochains refus seront aussi classés automatiquement dans l'exécution.

La reprise `37958354048`, commit88dc20580cbfc3e790eb19f366794b8b94f87e9d,
passe réellement ce contrôle, simulation, copie et répétition du timer. Le
worker est demandé avec le retour armé ; aucun résultat local complet n'arrive
dans les dix minutes. Le retour rétablit le socle et les25sondes passent.
Le diagnostic du même point d'entrée exige maintenant une tentative retournée
et un worker arrêté ; il classe aussi le journal privé et les états systemd.
Aucune boucle de relance ou suppression de cluster n'est autorisée.

Le diagnostic `37961581194` confirme un worker arrêté sans étape atteinte ni
cluster privé créé, socle et25sites conservés. L'attribut `self.worker` masque
la méthode à appeler : le contrôle de non-masquage échoue sur l'ancien code.
L'attribut devient `unite_essai`. Avant le prochain essai, le diagnostic doit
retrouver le TypeError à cet appel précis dans la seule tentative88dc retournée,
sans autre cause connue, étape engagée ou cluster présent. Il refuse toute
divergence ; la reprise qualifiée utilise un nouveau dossier de tentative,
avec la même génération et le retour autonome inchangé.

Cette preuve de dispatch est réellement passée dans `37963555297`. Le worker
corrigé démarre, mais une commande refuse la poursuite ; le retour rétablit
le socle et les25sites passent. Le diagnostic normal examine maintenant cette
seule tentativef9 retournée, avec cadres Python limités à son code connu et
états/journaux du namespace identite classés. L'ancienne preuve88dc reste
distincte et inchangée pour le contrôle de reprise antérieur. Aucun argument,
chemin privé, extrait ou donnée métier n'est transmis.

Le diagnostic `37966437838` refuse sa lecture complète ; six services et les
25sites sont vérifiés après ce refus. Un relevé secondaire indisponible doit
être marqué comme tel, sans masquer les cadres/classifications principales.
La sous-étape d'un refus est un nom fermé ; aucun message d'exception privé
ne sort. Le socle, le retour durable et l'arrêt du worker restent obligatoires.
Une donnée absente n'est jamais une preuve autorisant une reprise.

Le relevé `37967591960` établit la présence du cluster et l'étape
`essai_generation` avant le retour. Le contrôleur refuse toujours une reprise
sur ce cluster. Le diagnostic complémentaire lit les journaux techniques dans
les namespaces identite et par défaut, les attributs/PG_VERSION et
`pg_controldata` du seul cluster arrêté. Il ne lance ni service ni SQL.
Les cadres historiques sont liés aux trois SHA-256 publics de f9 dans un
dossier privé ; leur mode d'archive0664 est alors acceptable, sans droits monde,
lien ou contenu différent. Les nouvelles extractions respectent umask077.

Le diagnostic `37969887755` valide ces cadres historiques et le cluster17
privé proprement arrêté. L'échec classé concerne le service d'identité.
Les codes de sortie/étapes systemd sont des valeurs fermées, les classes
d'exception appartiennent à une liste prédéfinie. Le namespace identite
entier reste réservé à ces composants et sa sortie uniquement classifiée ;
aucun journal général du serveur. Le format des credentials et l'import
peuvent être contrôlés sans envoi ni restitution de leurs valeurs.

Le relevé `37971727525` donne une sortie143, import et credential valides,
aucune exception classée. La cause initiale reste inconnue : le gestionnaire
NixOS émet sur stderr son bilan d'unités échouées avant le retour4.
Le diagnostic privé contient déjà cette sortie ; seuls noms techniques
prédéfinis et nombre d'inconnus sont projetés. Aucun journal supplémentaire,
lancement ou relaxation des restrictions du service n'est nécessaire à cette
lecture. La sonde Java locale sans AF_NETLINK n'a pas confirmé cette piste.

Le résumé Actions explique l'avancement et la suite ; les rapports ne
contiennent que références et booléens. Un enregistrement déjà terminé pour
le même opérateur est recontrôlé, sans nouvel essai ni rotation de secret.
Une préparation entamée ou un essai échoué s'arrête pour diagnostic : aucune
boucle de relance, nettoyage de données ou réparation automatique.

Ce regroupement n'affirme pas que l'enrôlement ou la bascule sont déjà
implémentés dans l'orchestrateur. Ajouter ces phases demande leurs contrôles
et preuves propres, pas une nouvelle série de clics du propriétaire.
Le garde `preconditionsValidees` du mode commun reste fermé. Vision conserve
ses données et accès historiques pendant l'amorçage ; aucun autre outil ne
change de comptes, routage, release ou style.

## Retour et preuves

La [recette réservée](IDENTITE-AMORCAGE-ESSAI.md) conserve son retour autonome,
son verrou et son marqueur durable. Le workflow appelant possède l'exclusion
globale ; l'appelé n'en reprend pas une seconde, ce qui bloquerait son propre
parent. Sur échec, les contrôles et le retour restent visibles dans l'exécution.
Un succès CI local ne prouve jamais une activation VPS. Consigner l'URL, le
commit et les contrôles réels après chaque opération réussie.

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

La construction `37985768542` (25f685900a9b65cb7cef872f0b55bcb21e35567d,
job114007309842) réussit réellement le test natif complet et les contrôles
du socle/six services/SSH/25sites. La preuve exacte référence désormais
la génération k4q4i4m9r4070xwwpnd24hpi9g6zngyn, avec validation native vraie.

La phase `amorcage` reprend uniquement le cluster créé par f9 : audit de
retour et worker arrêté, seul échec Nginx connu, PostgreSQL17 arrêté proprement
sans PID/socket/erreur, import et secret existants conservés. Toute divergence
refuse la reprise. Une archive à froid passe directement de tar à AGE vers
le destinataire de sauvegarde existant ; ni archive ni dump en clair sur disque.
Objets spéciaux et liens externes refusés, fichier root0600 fsync et empreinte
contrôlée avant essai. Le test d'archive/AGE/restitution est synthétique ;
le déchiffrement de cette copie réelle reste une vérification distincte.

Entrée reproduite, règles/dry-activate, copie Vision, répétition du timer,
retour15min, contrôles locaux/25sites/HTTPS et copie d'identité précèdent
l'enregistrement. Une erreur déclenche le retour puis un diagnostic automatique
limité à la tentative courante et aux états/catégories fermés. Aucun effacement
de cluster, aucun humain, inscription ou migration Vision dans cette phase.

## Images de qualification

La CI du diagnostic5afe a rencontré le quota anonyme Docker Hub429,
y compris après relance. Les images PostgreSQL17, pgvector0.8.0-pg17
et Debian bookworm-slim proviennent désormais du miroir public Google,
[épinglées par digest OCI](../operations/vision-ci-images.json).
Les téléchargements et empreintes ont été vérifiés dans Work. La CI
précharge les mêmes images sous les noms attendus par les recettes ;
aucun test n'est omis. Cela ne modifie pas les paquets Nix ou images VPS.
La réussite du commit exact reste exigée avant toute demande administrative.

## Enrôlement initial

La phase `proprietaire` compare le reçu d'activation public au privé et
vérifie le système réellement enregistré. Le contact reste une enveloppe
chiffrée, ouverte seulement en RAM avec la clé d'hôte existante, sans export.
Un état root durable précède création et courriel ; une réponse ambiguë bloque
tout rejeu. Le compte reçoit uniquement UPDATE_PASSWORD et CONFIGURE_TOTP,
aucun mot de passe choisi par l'exploitation ni privilège d'administration
d'identité. Le lien dure30min ; SMTP accepté ne prouve pas sa réception.
La création et l'envoi réels seront attestés après exécution, pas par la CI.
L'ancien accès Vision reste actif, OIDC Vision et inscriptions tierces fermés.
L'observation ultérieure ne lit que les notes de session du sujet initial
exact et exige les méthodes pwd/otp fraîches≤300s. La simple présence des
credentials ne constitue pas une preuve de connexion. Le rattachement
historique et le statut administrateur applicatif restent une phase distincte.

La phase automatisée `proprietaire-observer` est séparée de cet enrôlement.
Elle exige tous les reçus privés déjà existants, le verrou et les identifiants
d'exécutions inchangés. Elle interdit les mutations de l'API administrative,
ne crée aucun état d'enrôlement et ne rappelle jamais le chemin de création
ou de courriel. La première étape vérifie email, mot de passe et OTP configurés,
sur le sujet durable exact, sans rôle d'administration d'identité. Ce constat
ne vaut pas authentification récente. La seconde attend au plus600secondes,
en ne réessayant que la projection SQL READ ONLY des notes de ce sujet.
La preuve exige pwd ET otp exécutés depuis≤300secondes ; un lien magique,
une session ancienne ou la seule présence de credentials ne suffisent pas.
Sans preuve, un résultat explicite `preuve_humaine_en_attente` est rendu sans
écrire de reçu de connexion. Après preuve, seul le reçu root0600 est écrit.
Le runner expose une étape d'attente identifiable : demander une connexion
normale seulement lorsque cette étape est active, jamais avant les minutes
de CI. La personne utilise son navigateur ; aucun Run workflow ni secret
en conversation n'est nécessaire. Cette phase ne rattache aucune donnée,
ne promeut aucun administrateur Vision et n'exécute aucune migration SQL.

Qualification de l’observateur sur Keycloak26.7.3 natif, avec compte/courriel
strictement synthétiques : activation par lien, choix de mot de passe et OTP,
vérification du sujet exact et absence d’admin, sans seconde création ni envoi.
[Reçu de qualification](../operations/vision-proprietaire-observation-qualification.json).
Huit tests de refus/attente,343tests locaux et évaluations Nix réussis. La
preuve de session native/PG17 reste celle du lecteur inchangé de PR70 ;
la vérification du compte réel reste à exécuter après CI exacte.


## Préparation de la bascule depuis le compte initial vérifié

La phase `vision-preparer` ne réutilise pas les gardes de l'ancien audity1.
Depuis le diagnostic4cb942c/38040462649, elle répare d'abord le seul cycle
de référence attesté. L'ancienne configuration régulière est vérifiée contre
`entree_empreinte` du plan privé initial ; l'entrée doit être exactement celle
du générateur connu. L'entrée prospective importe cette copie stable et doit
reproduirek4 avant le remplacement atomique. Le lien courant reste à son
emplacement, la source défectueuse et l'intention sont archivées en privé ;
réévaluation identiquek4 et six PID inchangés exigés ensuite. Aucun switch,
boot, test NixOS ou SQL n'est exécuté par cette réparation. Le rapport distingue
la modification de source des données de production et de la génération active.
Le générateur traite désormais une configuration régulière par sa copie stable.
Les futurs refus projettent directement leurs classes/cadres validés par AST
et code retour borné, sans argument, message ou traceback privé.
Elle appelle uniquement l'observateur déjà qualifié0fbce8d, depuis sa source
root protégée et dont le SHA256 exact est contrôlé, pour constater le soclek4
et le compte actuel. Le reçu privé de connexion doit correspondre au sujet
durable et à la fenêtre de l'observation réelle38002451652. Ce reçu atteste
la possession à l'amorçage ; aucune fraîcheur actuelle n'en est déduite.

Le nouveau relevé Vision, les ACL et les empreintes utilisent une même
transaction REPEATABLE READ READ ONLY et un snapshot exporté pour le dump.
Le propriétaire historique doit encore être unique et correspondre à l'unique
compte htpasswd actif, dont aucun hash n'est conservé. Le cluster privé IdP
possède son propre snapshot cohérent. Les deux dumps restent sur le VPS :
chiffrés dans le dossier opérateur et temporairement en clair uniquement dans
le staging privé supprimé après arrêt. Aucun dump/identifiant/email/contenu
n'est publié dans Actions ou Git ; les diagnostics sont root0600 bornés.

Le staging UTF-8/PG17 sans TCP exige un socket et un data_directory distincts
de la production. Il restaure les deux bases et compare toutes les empreintes
de lignes, y compris celles de l'identité. Les migrations019–025 et roles.sql
sont appliqués uniquement dans cette copie. L'association explicite(iss,sub)
à l'ancien identifiant et le premier admin applicatif n'existent que dans le
staging ; aucun rapprochement par email et aucun rôle humain d'admin IdP.
Les privilèges de contenu et rôles SQL privilégiés sont refusés. Le retour
ACL/owners/RLS est rejoué deux fois et les données historiques restent identiques.

Les composants sont construits sur l'entrée actuellement active et avec son
Nixpkgs, les sources Vision/style épinglées, le fournisseur immuable conservé,
un job/deux cœurs et des seuils mémoire/disque. Le routage hors Vision/identité,
le paquet/dataDir PostgreSQL et le pare-feu sont comparés. Les protections de
l'hôte d'identité déjà actives sont conservées, dont le refus d'enregistrement
public de clients et les en-têtes fixes. Le garde preconditionsValidees demeure
false : la génération complète n'est pas constructible et n'est jamais activée.
Ce n'est pas une attestation de possession de la clé privée personnelle ou de
copie extérieure ; celles-ci restent à vérifier avant la bascule. L'essai
nécessitera une recette distincte avec retour SQL/NixOS autonome et validation
juridique avant admission tierce. Les dossiers chiffrés de préparation doivent
être inclus dans l'inventaire de conservation, sans prétendre que le timer des
sauvegardes ordinaires purge automatiquement ces dossiers opérateur.

[Qualification locale](../operations/vision-bascule-qualification.json) :349tests,
six refus ciblés, association et admin sans contenu sur PG17 jetable, rejet
d'un second rattachement et d'un retour avec tiers, retour rejoué deux fois,
évaluation Nix avec le garde fermé. L'exécution réelle après CI exacte reste
nécessaire pour attester restauration et construction sur le VPS.
Cette preuve est maintenant fournie par464c81f/PR79,
[Actions38045641408](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38045641408),
job114194522693 : deux restaurations réelles, association/admin applicatif
isolés, retour ACL rejoué, dix composants construits avec source dans le store,
garde fermée et contrôles finaux SSH/six services/25sites réussis.
Voir [le rapport réel](../operations/vision-bascule-preparation-reelle.json).
Clé personnelle et copie extérieure restent non vérifiées ; aucune activation
ou migration de production, aucune invitation ouverte.

La phase suivante `vision-telephone` ne rejoue pas la préparation complète.
Elle remet par le relais existant un témoin synthétique chiffré vers la nouvelle
clé publique générée sur le téléphone du propriétaire. Aucune rotation de la
configuration des sauvegardes, copie réelle, migration ou activation. L'envoi
est idempotent pour le même opérateur et une remise ambiguë exige diagnostic.
Voir [la procédure et ses limites](COURRIEL-PROVISIONNEMENT.md).

Après le déchiffrement rapporté du témoin par l'exploitant, la phase fermée
`vision-sauvegarder` réutilise les snapshots/restaurations READ ONLY isolées,
sans réparation, migration ni construction/activation. Elle prépare une copie
réelle chiffrée vers cette clé, destinée uniquement au propriétaire, avec un
lecteur sans extraction pour le téléphone et une preuve aléatoire dans le
manifeste chiffré. La réception/vérification extérieure ne sont pas déduites
du SMTP ou de la CI. Aucun Run workflow ou accès au PC Linux n'est nécessaire
pour préparer cette copie. Les anciennes clés/copies et autres projets restent
conservés ; les conditions de bascule et d'admission demeurent séparées.

## Copie réelle déchiffrée sur le téléphone

Le propriétaire a retourné le résultat complet du lecteur pour
`vision-recuperation-20261010` : empreinte chiffrée exacte, tous les fichiers
identiques aux copies testées, déchiffrement complet, aucune écriture en clair.
Le SHA256 du défi aléatoire retourné correspond exactement au reçu
[38049744292](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38049744292).
La [confirmation séparée](../operations/vision-recuperation-confirmation.json)
consigne cette preuve sans réécrire l’événement SMTP antérieur, ni publier
le défi ou la clé privée. Clé personnelle correspondante et copie réelle
extérieure sur téléphone sont validées ; copie mensuelle sur disque Linux
et conservation indépendante de la clé restent à réaliser. La préparation
d’un essai protégé reste distincte, ainsi que les conditions juridiques
d’admission tierce. Aucun Run workflow n’est demandé au propriétaire.
