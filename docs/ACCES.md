# GitHub, SSH et hPanel

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

Le terminal de cette session ne peut pas joindre le réseau SSH du VPS. Lui
fournir une clé privée ne suffirait donc pas. Il faut reprendre l'activation
depuis un environnement dont la connexion SSH fonctionne, ou utiliser le
terminal du VPS dans hPanel avec les sources vérifiées.

L'archive privée du projet Mémoire a depuis été retrouvée et la clé
administrative extraite hors Git. Son empreinte a été comparée avec succès
au relevé initial. La tentative SSH munie de cette clé échoue toujours au
niveau réseau : il n'est pas nécessaire de renvoyer l'archive ou de régénérer
une clé pour résoudre ce blocage.

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
