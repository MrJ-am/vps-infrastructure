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

## Retour et ouverture

Le retour SQL verrouille la configuration et les comptes. Il refuse toute
inscription ouverte, admission réservée en cours ou nouveau compte tiers.
Après ouverture, conserver une version compatible avec l'isolation et les
données de toutes les personnes. Le retour ancien n'est plus une possibilité.
Ne pas lancer `retour-acl.sql` indépendamment des arrêts et du retour système.
La préparation produit et qualifie cette pièce, elle ne lance pas la bascule.

L'activation doit encore construire avec le Nixpkgs réellement installé,
comparer les unités/routage, vérifier JDBC Unix et réserver compte.mrj.am,
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

Le DNS public de `compte.mrj.am` répond NXDOMAIN au relevé du 9 octobre 2026.
Créer son enregistrement A vers `187.77.95.158` chez alwaysdata avant ACME.
Ne pas ajouter d'AAAA sans routage IPv6 qualifié et ne pas modifier les MX Proton.
Les pages d'accès MCP utilisent aussi les rôles OKLCH de la palette commune ;
le thème tiers de la console native conserve les limites déclarées.

L'audit de la machine active est réel et identifié. L'exécution VPS de cette
nouvelle préparation, SMTP Proton/réception, la possession de la clé privée,
le disque Linux, les contrats applicables et l'identité initiale restent des
preuves à établir. Ni CI ni option Nix ne déclarent la conformité générale.
