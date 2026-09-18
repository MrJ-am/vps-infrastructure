# Accéder au VPS par GitHub Actions

**Décision du propriétaire, 18 septembre 2026 : ChatGPT Work ne dispose pas
d'accès SSH direct au VPS. Les opérations distantes passent par GitHub
Actions.** Les succès SSH observés depuis Work sont ceux des runners GitHub.
Ne pas répéter les essais réseau depuis Work ni demander à nouveau l'archive
privée pour débloquer cette connexion.

## Dépôt GitHub

Le propriétaire a créé le dépôt **privé**
[MrJ-am/vps-infrastructure](https://github.com/MrJ-am/vps-infrastructure).
Les droits de lecture et d'écriture de l'application GitHub ont été vérifiés.
Les publications applicatives restent dans leurs propres dépôts.

Ce dépôt ne doit contenir aucune clé privée, mot de passe, fichier d'activation
administrateur, sauvegarde PostgreSQL ou fichier `.env`. Les clés présentes
dans les modules et `ssh-known-hosts` sont exclusivement publiques.

## Accès administratif

L'hôte vérifié historiquement est `root@187.77.95.158`, port 22 ; empreinte
ED25519 du serveur : `SHA256:0FOvxV7dd/mibk8/zo9TPaVJfZLPAo2qEjN0rLcN8Xk`.
`scripts/connect.sh` utilise sa clé publique connue, refuse un autre hôte et
ne demande pas de mot de passe.

La clé root existante peut être réutilisée pour la migration. Son nom local
historique `matheval_admin` ne signifie pas que l'application Matheval doit
conserver les droits d'administration. Aucun changement de clé n'est nécessaire
pour déplacer la configuration. La clé CI `matheval_deploy` reste séparée.

Le terminal Work ne peut pas joindre le réseau SSH du VPS. Lui fournir une
clé privée ne suffirait donc pas. `scripts/connect.sh` doit être exécuté par
le runner GitHub pour les opérations préparées depuis Work.

L'archive privée du projet Mémoire a depuis été retrouvée et la clé
administrative extraite hors Git. Son empreinte a été comparée avec succès
au relevé initial. La tentative SSH munie de cette clé échoue toujours au
niveau réseau : il n'est pas nécessaire de renvoyer l'archive ou de régénérer
une clé pour résoudre ce blocage.

## Diagnostic manuel depuis GitHub

Le workflow `.github/workflows/audit.yml`, **Auditer le VPS**, se lance
manuellement sur `main` ou lors d'un commit sur `main` modifiant uniquement
la demande `operations/audit-request.json` (avec, si nécessaire, les sources
revues du diagnostic). Il ouvre deux connexions avec `scripts/connect.sh`
pour exécuter `scripts/audit.sh` et `scripts/audit-postgresql.sh` via l'entrée
standard, sans installer de fichiers ni reconstruire NixOS. Il n'accepte pas
de commande libre. Ses journaux contiennent l'inventaire technique, sans
lecture des réponses collectées, mots de passe ou clés privées.

Préparer dans ce dépôt l'environnement GitHub **`vps-production`**, limité
à la branche `main`, et son secret **`VPS_ADMIN_SSH_KEY`** contenant la clé
administrative existante. Ne jamais placer sa valeur dans Git, une variable
publique, un journal ou un message. La clé d'hôte publique est déjà figée dans
`scripts/ssh-known-hosts` ; la vérification stricte reste obligatoire.
Sans ce secret, le workflow échoue explicitement avant toute connexion.

Les secrets de Mémoire ne sont pas automatiquement disponibles dans ce dépôt.
`MATHEVAL_SSH_KEY` appartient au compte applicatif `matheval-deploy` : ce n'est
pas la clé administrative et ce compte ne doit pas recevoir de droits root.
Les publications et les exports chiffrés existants restent dans Mémoire.

Pour lancer le diagnostic : onglet **Actions**, workflow **Auditer le VPS**,
**Run workflow**, branche `main`. Si l'outil GitHub de la session permet ce
déclenchement, l'utiliser ; sinon fournir ce lien de lancement au propriétaire.
Depuis Work, donner un nouvel identifiant à `operations/audit-request.json`,
conserver `operation: "audit"`, puis publier ce changement sur `main` avec
les outils GitHub. Ce déclencheur explicite n'emploie aucune commande fournie
par la demande et ne permet aucune activation. Lire ensuite l'exécution
associée au commit. Ne pas tenter SSH depuis Work ni modifier les workflows
applicatifs pour administrer le VPS.

Après exécution, relever son URL, son commit, sa conclusion et les étapes
effectivement réussies dans `docs/ETAT.md`. Distinguer workflow préparé,
workflow exécuté et changement appliqué au serveur. La présence du fichier
YAML ou la réussite de `check.yml` ne valide pas l'accès administratif.

La future activation de l'infrastructure doit suivre `MIGRATION.md` dans un
workflow dédié, avec commit identifié, contrôles et retour arrière sur le
VPS. Le diagnostic actuel ne lance aucune activation. Le terminal hPanel
reste la voie de récupération indépendante si GitHub ou SSH devient indisponible.

Si la clé administrative a été perdue, une session root déjà ouverte ou le
terminal hPanel peut ajouter une **nouvelle clé publique**. Il faut préserver
les clés déjà autorisées, reporter l'ajout dans la configuration NixOS
responsable de root et vérifier une deuxième connexion avant de fermer la
première. Ne pas désactiver la vérification d'identité SSH.

## hPanel et DNS

**Aucune modification de hPanel ou du DNS n'est requise pour la séparation
actuelle.** Ne pas réinstaller le VPS, modifier son réseau ou changer de système.
Le terminal hPanel est seulement une voie d'administration/récupération possible.

Pour un futur domaine ou sous-domaine, son enregistrement A devra pointer vers
`187.77.95.158`, dans l'interface du fournisseur qui gère effectivement sa zone
DNS. Ajouter un AAAA seulement après vérification de l'accessibilité IPv6 et
du routage associé. Les ports publics applicatifs restent 80/443 ; ne pas ouvrir
3000, 3001, etc. L'émission de certificats supplémentaires est gérée par le
projet VPS après validation du DNS.
