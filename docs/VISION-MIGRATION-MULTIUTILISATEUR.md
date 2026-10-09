# Qualification opérateur de la migration Vision

Le workflow manuel `vision-multiutilisateur-preparer.yml` est distinct des
anciennes opérations « refonte » et « identité ». Il **n'active aucun service**.
La CI du commit opérateur exact doit avoir réussi avant toute connexion VPS.
Les révisions Vision et Style et l'empreinte de l'archive privée sont figées
dans `operations/vision-multiutilisateur-candidat.json` ; aucune branche courante
n'est téléchargée sur la machine. Le commentaire Git de l'archive est vérifié.

## Ce que fait la préparation

- Elle refuse une autre génération active ou de démarrage, un autre Nixpkgs
  installé ou une autre release Vision que ceux de l'audit Actions 37858455559.
  Un changement légitime nécessite un nouvel audit et un manifeste revu.
- Elle conserve `/etc/nixos`, les sources exactes, les ACL effectives, owners,
  états RLS, attributs du rôle Vision et empreintes privées des tables.
  Le relevé des droits ne lit aucun mot de passe. Les identifiants historiques
  et empreintes demeurent dans le dossier root ; ils ne sont pas des artifacts.
- Une transaction PostgreSQL exportée relie le dump, les droits et les
  empreintes à la même copie cohérente. Le dump est chiffré par age pour la
  clé publique déjà déclarée ; le clair est limité à la restauration locale.
- Un **autre cluster**, sur socket Unix privé sans TCP, restaure Vision 001–018.
  Les migrations 019–025 et `roles.sql` s'appliquent seulement à ce cluster.
  La création/modification de rôles PostgreSQL ne touche donc pas la production.
- Les empreintes historiques sont rapprochées après restauration et migration.
  Le retour ciblé des droits est appliqué deux fois, sans restaurer de données.
  Les tables retrouvent leurs owners avant les séquences liées. Les nouveaux
  objets et les migrations restent présents ; aucune donnée n'est effacée.
- Les fichiers du cluster isolé sont retirés après son arrêt. Sur succès,
  seuls l'archive chiffrée et les preuves root subsistent. Sur échec, examiner
  puis retirer les copies privées inutiles ; ne pas les publier dans les logs.
- Une nouvelle connexion runner et le relevé HTTP des autres sites doivent
  réussir. L'artifact contient seulement `preparation.json`, sans contenu,
  adresse personnelle, sujet, titre ou fichier de droits.

Les rôles hérités, privilèges de colonnes ou délégations inhabituelles bloquent
la génération d'un retour plutôt que perdre des droits légitimes. Le protocole
actuel vise l'instance historique à un propriétaire ; plusieurs propriétaires
exigent une migration distincte. Le dossier privé est
`/root/vision-multiutilisateur-operations/<commit>/`.

L'exécution [37893102123](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37893102123)
sur `48aa2fa6d05388d48bc6e7ef3625b358bdb53905` s'est interrompue sans
activation. Le journal initial masquait l'étape fautive ; les 25 contrôles
HTTP/TLS relancés depuis Work réussissent après cet arrêt. Cela ne prouve pas
encore une nouvelle connexion administrative après l'échec.

Le correctif affiche seulement des noms d'étapes fixes et des raisons écrites
par le programme. Les erreurs des sous-processus et la trace Python demeurent
dans `diagnostic-prive.log`, root 0600, jamais dans un artifact ou la sortie
Actions. Le constat de l'ancienne tentative lit uniquement la présence de
fichiers connus, sans ouvrir leur contenu. Le workflow conserve séparément
les contrôles HTTP et la nouvelle connexion même après échec de qualification.
Les diagnostics privés inutiles sont à retirer après résolution avec les
autres copies privées de l'opération ; ne pas conserver de traces de personnes
dans les preuves versionnées.

## Retour et ouverture

Le retour SQL verrouille la configuration et les comptes. Il refuse toute
inscription ouverte, admission réservée en cours ou nouveau compte tiers.
Après ouverture, conserver une version compatible avec l'isolation et les
données de toutes les personnes. Le retour ancien n'est plus une possibilité.
Ne pas lancer `retour-acl.sql` indépendamment des arrêts et du retour système.
La préparation produit et qualifie cette pièce, elle ne lance pas la bascule.

L'activation doit encore construire avec le Nixpkgs réellement installé,
comparer les unités/routage, vérifier JDBC Unix et réserver log.mrj.am,
préparer l'import privé, vérifier la possession de l'identité initiale et son
MFA, rattacher exactement iss/sub à l'ancien utilisateur et ses principaux
MCP. Aucun rattachement par courriel ressemblant n'est autorisé. Conserver les
empreintes historiques valides ; ne pas réactiver les tokens révoqués.

Armer et répéter un retour systemd indépendant de SSH **avant** tout changement
de génération, SQL ou symlink. Fermer les mutations pendant l'essai, garder les
admissions fermées, contrôler les autres sites, sessions/CSRF, MCP, MFA récent,
export, effacement, sauvegardes et nouvelle connexion. Le dossier produit ne
constitue pas un script d'activation ; aucun workflow existant n'est détourné.

L'accès AGPL au code est prévu sur deux routes de téléchargement exactes.
L'archive Vision correspond au commit épinglé ; l'archive des services contient
leurs sources de la génération, modules et modèles sans secret. Vérifier leur
contenu et leur concordance avec les exécutables avant l'ouverture. Le registre
de coordination, les configs privées et les dossiers de personnes sont exclus.

## Niveau de preuve actuel

Les contrôles synthétiques couvrent réellement PostgreSQL 17 : socle 18,
migrations 19–25, owners/ACL/RLS rétablis deux fois, refus après ajout d'un tiers,
contenu préservé. Ils sont exécutés en CI avec l'archive Vision exacte.
Le test complémentaire d'IdP réalise un dump PostgreSQL natif chiffré, restaure
le sujet et ses credentials, ouvre une session par mot de passe et OTP, puis
retire le sujet deux fois dans la seule copie.

`tests/keycloak-unix.py` démarre également Keycloak natif avec les deux plugins
junixsocket du Nixpkgs épinglé : URL JDBC de la configuration NixOS, socket Unix,
rôle sans mot de passe et règle `peer` effectivement chargée. PostgreSQL n'a
aucune écoute TCP et son conteneur aucun réseau. La console native répond après
création du schéma ; les connexions sont bien locales et un autre UID est refusé.
Cette qualification synthétique ne remplace pas l'essai de la génération sur VPS.

L'adresse retenue par le propriétaire le 9 octobre 2026 est `log.mrj.am`.
Son enregistrement A chez alwaysdata répond `187.77.95.158` au relevé public.
Ce DNS ne prouve pas encore l'émission du certificat ACME ni l'activation IdP.
Ne pas ajouter d'AAAA sans routage IPv6 qualifié et ne pas modifier les MX Proton.

La relance réelle [37897757438](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37897757438),
opérateur `8c3721c5fc25724c409a5f9e2b56e0bccfdd702b`, est arrêtée à
`evaluation_nixos` : « Socle actif non reproduit ». Les invariants initiaux et
l'archive candidate passent ; le dump et les migrations ne commencent pas.
Les six services et les 25 sondes HTTP/TLS passent après l'arrêt. Le workflow
d'audit existant compare désormais les seuls paramètres techniques des trois
évaluations : point d'entrée, source installée et import classique NixOS.
Ce diagnostic ne remplace ni ne relâche le contrôle strict du préparateur.

L'audit [37899364733](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37899364733),
opérateur `98ab45e24b2b82fec512fe046681830092919531`, réussit : génération
active et démarrage conformes au relevé, PostgreSQL 17 sans TCP/écoute.
Les trois évaluations produisent cependant la même autre génération
`/nix/store/mvgw1a0cy7mmf1fq2ji02zynafmg604m-nixos-system-nixos-26.05.8639.c5c4a43b0e80`.
Le diagnostic compare ensuite les textes des seules unités techniques et
les deux scripts du fournisseur, sans en publier les contenus ni empreintes.
L'évaluation supplémentaire avec sa source active épinglée reste une lecture
de configuration ; elle n'est pas une activation ni une correction du socle.

L'audit [37900599245](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37900599245),
opérateur `99d355bc12c11d3eb48a6af8014e138ab2e62e57`, réussit : dix unités
comparées sont identiques, seules `vision-embeddings` et son backfill diffèrent.
La comparaison des fichiers du fournisseur est interrompue ; ce constat ne
prouve pas encore la cause ni l'effet d'un épinglage. Le diagnostic conserve
désormais la présence de chaque script et poursuit son évaluation si un fichier
manque, sans publier de contenu et sans modifier le système.

L'audit [37901569064](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37901569064),
opérateur `566b279f15c9042d4b8f31906318d3cdf56fdf7b`, identifie la source
réellement active `/nix/store/20nds4zvi1pcnljpwnwzcsysvyk15g11-vision-fournisseur-c0bfcac`
avec ses deux scripts présents. Le chemin recalculé n'est pas réalisé par
`--eval` : l'absence de sa copie dans le store n'est pas une perte de fichier.
La première conversion `toPath` conserve une unité mais perd le contexte de
source et change la génération. Le test synthétique confirme que `storePath`
rétablit exactement celle-ci, y compris après ajout d'un répertoire au brut.
Le manifeste épingle la source active observée et le préparateur vérifie
encore la génération entière, la source du fournisseur et PostgreSQL. Il ne
modifie aucun fichier brut ni système actif. L'audit réel `storePath` et la
nouvelle préparation restent à qualifier.

Les pages d'accès MCP utilisent aussi les rôles OKLCH de la palette commune ;
le thème tiers de la console native conserve les limites déclarées.

L'audit de la machine active est réel et identifié. L'exécution VPS de cette
nouvelle préparation, SMTP Proton/réception, la possession de la clé privée,
le disque Linux, les contrats applicables et l'identité initiale restent des
preuves à établir. Ni CI ni option Nix ne déclarent la conformité générale.
