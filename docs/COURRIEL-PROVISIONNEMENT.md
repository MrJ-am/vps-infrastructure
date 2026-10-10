# Installer le courrier privé par Actions

Le code préparé est consultable dans `vision-courriel.yml` et
`scripts/courriel-provisionner.py`. Il installe le jeton Proton déjà fourni,
sans modifier une valeur différente, activer Keycloak ou ouvrir les comptes.
Il ne touche ni les MX, ni les domaines, ni les releases, ni les ACL SQL.

1. Publier ce workflow sur main après réussite de la CI exacte. Ajouter le
   secret Actions `VISION_PROTON_SMTP_TOKEN`, contenant **seulement** le jeton
   SMTP dédié à Automath, pas le mot de passe Proton. Le secret peut appartenir
   à l'environnement `vps-production` ou au dépôt privé. La connexion utilise
   la clé administrative existante ; aucune clé SSH supplémentaire n'est requise.
2. Lancer manuellement « Installer le courrier privé de Vision », sur main,
   en cochant le test. Le runner vérifie la clé d'hôte, transfère le commit
   exact, passe le jeton sur stdin et installe le JSON root 0600 dans
   `/var/lib/mrjam-identite`, répertoire 0700. Aucune donnée privée en artifact.
3. L'envoi exige STARTTLS et un certificat valide. Il utilise la clé publique
   age déjà déclarée pour les sauvegardes Vision, à la révision du workflow.
   Le résultat atteste seulement l'acceptation du relais. Vérifier la présence
   dans la boîte Proton, récupérer la pièce et la déchiffrer avec la clé privée
   correspondante hors VPS. Le témoin ne désigne aucun usager ; ne pas le
   soumettre au rejeu des effacements. Conserver uniquement la preuve technique.
4. Consigner URL Actions, commit, état du fichier privé et confirmation de
   réception/déchiffrement. Une clé privée manquante bloque la qualification
   des sauvegardes, même si l'envoi SMTP réussit. Un refus SMTP ne modifie
   aucun accès utilisateur ; le fichier privé reste disponible pour diagnostic
   opérateur et reprise. Ne pas afficher les réponses privées du relais.

Les outils Work actuels ne permettent ni de créer un secret Actions ni de
déclencher un nouveau workflow manuel. Le réseau Work n'autorise pas SMTP 587.
Ces deux actions d'interface GitHub sont donc les seules manipulations à faire
par l'exploitant pour cette étape ; aucune tentative SSH depuis Work.

Ce contrôle n'achève pas la migration multi-utilisateur. L'import privé,
l'identité initiale avec MFA, la restauration des bases, le retour des owners,
ACL et RLS, les contrats applicables et la réception du registre d'effacement
restent les conditions distinctes du dossier d'activation.

## Témoin sur téléphone du 10 octobre 2026

Le propriétaire a créé une clé AGE localement dans Nix-on-Droid, puis partagé
uniquement sa clé publique :
`age1p95t4z0aafq7j4fl7cc9f0cjz8j03dtlmz56kec4lj6vwxrvzpqqnc53cc`.
Le chiffrement AGE valide sa somme de contrôle. La clé privée reste sur le téléphone,
dans `~/.local/share/mrjam-recovery/cle-privee.age` ; sa possession et le déchiffrement
réel restent à confirmer. Aucun accès au PC Linux n'est nécessaire pour ce témoin.

La phase fermée `vision-telephone` du point d'entrée automatisé utilise le relais
déjà installé, après vérification de demande et CI exacte, sans nouvelle saisie
de secret ni clic Run workflow. Elle envoie uniquement au compte expéditeur
existant la pièce `vision-test-telephone-20261010.json.age`. Le message et le témoin
sont distincts du premier test SMTP. Le contenu est un JSON synthétique avec
`qualification_telephone: true`, la référence `vision-telephone-20261010` et
l'empreinte publique de la clé ; aucune donnée de compte, fiche, item ou identité.

Une intention root0600/fsync précède la remise SMTP et un reçu est écrit seulement
après acceptation du relais. Un rejeu de ce même opérateur terminé ne renvoie
aucun mail ; une remise ambiguë bloque pour diagnostic sans relance automatique.
Les exceptions SMTP ne sont jamais publiées. Les générations active/enregistrée
sont contrôlées avant/après, puis six services, nouvelle SSH et25sites.

La réception et le déchiffrement exigent encore une manipulation du propriétaire.
Ce test ne restaure aucune base et n'atteste aucune copie extérieure complète.
Il ne modifie pas la configuration des sauvegardes, les clés précédentes ou les
copies existantes ; Matheval reste inchangé. La nouvelle clé ne déchiffre pas les
anciens fichiers. Les nouvelles sauvegardes Vision/identité nécessiteront leur
préparation propre et leur vérification avant toute bascule.

Remise réelle réussie le 10 octobre2026 à13:15 Europe/Paris :
[Actions38047719442](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38047719442),
job114200542052, opérateur415e9d7/PR80 après CI exacte38047434345/369tests.
Le relais accepte le nouveau témoin, générations conservées et contrôles finaux
nouvelle SSH/six services/25sites réussis. Aucun secret privé transmis depuis
le téléphone. [Reçu public borné](../operations/vision-telephone-resultat.json).
Réception, déchiffrement, sauvegarde réelle et copie extérieure restent distincts
et non vérifiés par cette opération.

Le propriétaire a ensuite déchiffré ce témoin depuis Documents dans Nix-on-Droid
et retourné le JSON attendu, avec l'empreinte
`86e1797da7805848ab8e56858f4308a483249c6130fc09cf23b45cd321673725`.
[Confirmation](../operations/vision-telephone-confirmation.json) : réception et
déchiffrement rapportés par l'exploitant, sans transmission de clé privée. Cette
confirmation porte sur le témoin ; elle ne prouve pas une sauvegarde complète.

## Copie réelle vérifiable sur téléphone

La phase fermée `vision-sauvegarder` reprend les mêmes snapshots READ ONLY et
restaurations PG17 isolées, avec le compte/socle immuable déjà qualifié. Elle
ne répare aucune configuration, ne migre aucun schéma et ne construit/active
aucune génération. Les deux bases doivent rester identiques après restauration,
avec les credentials et le sujet IdP ; le cluster est arrêté avant l'archive,
puis retiré avant l'envoi. SQLite utilise l'API de sauvegarde cohérente, WAL
compris, et `integrity_check`. Le mot de passe historique n'est jamais en clair :
son fichier htpasswd privé est inclus seulement dans l'enveloppe chiffrée.

La pièce `vision-recuperation-20261010.tar.gz.age` contient les deux dumps,
les sessions, les ACL, le htpasswd, le contexte technique et les registres
d'effacement présents aux seuls chemins connus. Chaque fichier est décrit
par taille/SHA256 dans le manifeste chiffré. Un défi aléatoire de256bits reste
dans ce manifeste ; seulement son SHA256 figure dans le reçu public. Tout
Les copies chiffrées restent root600 sur le VPS ; les fichiers en clair
temporaires sont retirés après l'archive. La limite de copie est512Mio en clair
et15Mo chiffrés pour le courrier ; un dépassement refuse la remise plutôt
qu'une pièce incomplète. Aucun dump, credential, nom de personne, défi ou
contenu dans Git/Actions.

L'envoi autorisé au propriétaire utilise le relais et la seule boîte existants,
avec une intention fsync avant SMTP ; une remise ambiguë interdit le rejeu.
Le mail fournit aussi `verifier-vision-recuperation.py`, code sans donnée privée.
Contrôler son SHA256 indiqué dans la conversation avant exécution. Le lecteur
vérifie le SHA256 du cryptogramme, la clé locale privée, tous les fichiers et
leurs empreintes, puis consomme AGE jusqu'à sa fin et exige le code0. Pas
d'extraction ni de données en clair écrites sur le téléphone. Une mauvaise clé,
troncature, archive incomplète, doublon, lien ou chemin étranger est refusé.
Le résultat affiché ne contient que références/booléens/empreinte chiffrée et
le défi aléatoire, à rapprocher du reçu : aucune donnée des bases ou clé privée.

Ce jeu couvre Vision et l'identité avant bascule, pas le VPS entier. La réception
et la vérification du fichier réel restent nécessaires ; elles ne sont pas
déduites du témoin ou de l'acceptation SMTP. La copie mensuelle sur disque Linux
reste à organiser à son retour ; conserver aussi la clé privée hors téléphone.
Une restauration future exige le registre externe d'effacement récent et une
recette propre, sans réintroduire des comptes supprimés. Les archives opérateur
restent dans l'inventaire de conservation ; le timer ordinaire ne les purge pas.
Ni configuration de sauvegarde active ni ancienne copie ni Matheval modifié ;
les sauvegardes futures Vision/identité devront cibler la nouvelle clé lors de
l'opération d'activation distincte, sans toucher aux autres clés de projets.

Exécution réelle réussie le10octobre2026 à13:50 Europe/Paris :
[Actions38049744292](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38049744292),
job114206319683, opérateur6f0d38c/PR81, CI exacte38049451451/373tests.
Deux restaurations comparées et intégrité SQLite passent ; copie chiffrée
473596octets et vérificateur remis au relais. Cluster/clair retirés avant
SMTP, garde/inscriptions fermées, aucune réparation/migration/activation.
Nouvelle SSH/six services/25sites finaux réussis.
[Reçu public](../operations/vision-recuperation-resultat.json) : SHA256 du
cryptogramme, du vérificateur et du défi, sans données privées. La réception
et la vérification complète sur téléphone restent à confirmer par le propriétaire.
