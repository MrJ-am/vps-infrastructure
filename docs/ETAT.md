# État attesté au 18 septembre 2026

## Reprise de la migration complète

- Le propriétaire autorise la migration du VPS et de Mémoire, via GitHub
  Actions. La reprise amont du module Matheval au commit
  `0bcdaf101cbdacb85694ca217fd21ab3f2eac828` est intégrée sans changement
  d'octets dans `vendor/matheval/`. Sa provenance et le patch historique sont
  conservés ; ce patch ne doit plus être appliqué au module courant.
- Commit VPS de cette intégration :
  `e0f0c33a312708a54babdbfca00bd958682845b0`.
  Sa [CI complète](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35324107270)
  a réussi (registres, NixOS et PostgreSQL isolé).
- Les consignes de Mémoire sont actualisées sur la branche de la PR nº 8,
  commit `fdd71f8ea63da9e65f40cd59f4e6d5ea3ba942ad`. Elle reste non fusionnée,
  pour finaliser le relais après la bascule serveur vérifiée.
- La demande `operations/audit-request.json` permet désormais de lancer
  l'audit depuis Work avec les outils GitHub, sans connexion SSH directe ni
  déclenchement manuel dans le navigateur.
- Première exécution : [audit nº 35324107274](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35324107274).
  Échec à la préparation de la clé : `VPS_ADMIN_SSH_KEY` est vide ou inaccessible
  au job de l'environnement `vps-production`. Les trois étapes serveur/HTTP
  ont été ignorées. Le nettoyage du runner a réussi ; aucun accès au VPS n'a
  eu lieu dans cette exécution.
- La clé administrative existante se trouve dans l'archive privée déjà
  fournie. Sa valeur n'est pas publiée. La configuration du secret GitHub
  reste à effectuer ; le connecteur ne fournit pas cette opération et la
  connexion du navigateur a échoué à la validation à deux facteurs (demande
  mobile expirée, puis message GitHub « Two-factor authentication failed »).
  La connexion doit être terminée par le propriétaire avant cette configuration.
- La migration serveur et l'intégration finale de la PR nº 8 restent en
  attente d'un audit administratif réussi. Aucune activation, modification
  SQL ou restauration n'a été exécutée à ce stade.

## Mode d'accès retenu : GitHub Actions

- Le propriétaire confirme l'absence d'accès SSH direct depuis ChatGPT Work.
  Les connexions réussies observées depuis Work ont été effectuées par GitHub
  Actions. Les futures opérations distantes doivent utiliser ce canal.
- Les workflows de Mémoire relus sur `master` publient via `matheval-deploy`
  et exportent les sauvegardes chiffrées. Ils n'administrent pas NixOS.
- Le workflow manuel `audit.yml` est préparé dans ce dépôt pour exécuter les
  deux scripts d'inventaire depuis un runner, avec vérification de l'hôte.
  Il exige le secret administratif `VPS_ADMIN_SSH_KEY` de l'environnement
  `vps-production`. La présence de ce secret n'a pas été vérifiée et le
  diagnostic n'a pas été exécuté pendant cette adaptation.
- Validation locale : les 18 tests Python réussissent ; le YAML du workflow
  et la syntaxe shell de ses étapes sont vérifiés. L'absence de secret produit
  l'erreur attendue avant toute connexion, et le nettoyage reste exécutable.
- Les consignes et la procédure d'accès sont actualisées. La migration reste
  non activée ; aucun changement de configuration serveur n'est réalisé ici.

Les sections datées du 17 septembre ci-dessous conservent l'historique de la
préparation ; leurs exécutions Actions ne constituent pas un relevé actuel.

## Extension de la préparation à PostgreSQL

- Sources VPS relues au commit `36cac12fdf29c3147e407b82aadff7eef27083f2` de `main`.
- `modules/postgresql.nix` et `databases.json` prennent en charge l'instance
  PostgreSQL 17, les bases/rôles, l'authentification locale et les dumps quotidiens.
- La copie Matheval est adaptée avec un patch réversible et deux empreintes
  (amont et résultat). Elle conserve l'export chiffré et sa publication ; elle
  attend désormais la fin de `postgresql-setup.service`.
- Vision a été lu au commit `930d555aac2f49d55ea7afa631dce3ef2936998c` : aucun
  stockage PostgreSQL ni module NixOS. Son exemple reste hors du registre actif.
- Le message de reprise pour Mémoire est dans `docs/MESSAGE-MEMOIRE.md`.
- Les 18 tests Python locaux passent. Nix n'est pas disponible dans cet
  environnement ; le contrôle local signale explicitement cette limite.
  La [CI du commit `7227604`](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35277121343)
  a réussi : syntaxe, évaluation complète des configurations NixOS avec une
  puis deux bases, isolation effective dans PostgreSQL 17, conservation de
  données préexistantes, réapplication des ACL et restauration de chaque dump.
  Les tests utilisent exclusivement un conteneur jetable sans réseau.
  Cela ne remplace pas la construction et les contrôles sur le VPS réel.
- Aucun accès ni changement serveur n'a été effectué pendant cette extension.
  La migration demeure non activée ; les vérifications serveur et le retour
  ciblé des ACL sont décrits dans `docs/MIGRATION.md`.

Les sections suivantes conservent les constats de la préparation initiale.

## Sources examinées

- Dépôt canonique : [MrJ-am/M-moire](https://github.com/MrJ-am/M-moire).
- Base auditée : `d8d0f17f37f030d58c152d5e57ca2e2c5b5814ea`.
- Séparation proposée : `c83308ddfeefa03dfbb6692773c3d1274c867936`, branche
  `infra/separer-nginx`, [PR nº 8](https://github.com/MrJ-am/M-moire/pull/8).
- Fichiers lus : AGENTS.md, deploy/REPRISE.org, deploy/README.org, tous les
  modules et scripts de deploy/, workflows de publication et de sauvegarde,
  routes et paramètres d'écoute du serveur Node.js.

## Organisation antérieure constatée dans les sources

Le fichier `/etc/nixos/configuration.nix` est décrit comme important
`/etc/nixos/hostinger/configuration.nix`, lui-même relié au matériel et à
`/etc/nixos/matheval.nix`.

Le module applicatif déclarait le service Node.js, PostgreSQL 17, ses comptes,
ses sauvegardes et la publication, mais aussi Nginx, ACME, les ports publics
80/443 et le vhost principal. L'alias `www` était dans la configuration de
l'hôte, avec le réseau, le démarrage et la clé publique root.

La publication GitHub Actions utilise le compte `matheval-deploy`. Elle
transfère une archive applicative, appelle `matheval-release` et vérifie les
fichiers servis. Elle ne copie pas les modules NixOS et n'exécute aucun
`nixos-rebuild`. C'est la frontière conservée par cette préparation.

## Accès et production

- GitHub : lecture et création de la branche/PR réussies via l'application
  connectée. Le push Git HTTPS direct ne disposait pas d'identifiants ; la
  publication de la branche a été réalisée avec les outils GitHub autorisés.
- SSH : tentative TCP vers `187.77.95.158:22` rejetée par l'environnement avec
  `OSError: [Errno 101] Network is unreachable`, avant toute authentification.
- Clé privée : initialement indisponible, puis retrouvée dans l'archive privée
  du projet Mémoire après création de ce dépôt. Seule la clé administrative
  nécessaire a été extraite, hors Git. Son empreinte correspond au relevé
  `SHA256:Ls0fnnzPHPLzsEOIH3wO/pwe2biKEtvJjyJ4nHCUsno`.
  Une nouvelle tentative avec cette clé et la clé d'hôte vérifiée échoue
  toujours avec `Network is unreachable`, avant toute authentification.
  Aucune clé n'a été créée ou remplacée sur le VPS.
- Le dépôt privé `MrJ-am/vps-infrastructure` a été créé par le propriétaire ;
  l'accès en écriture a été vérifié et les sources préparées y sont publiées.
- Les neuf serveurs du connecteur Hostinger figurent dans la configuration
  locale, mais leurs outils ne sont pas exposés dans cette session. Aucun
  changement de compte, de DNS, de pare-feu ou de VPS via Hostinger.
- Dernière publication de master observée : [exécution réussie](https://github.com/MrJ-am/M-moire/actions/runs/35181932892),
  terminée le 17 septembre à 04:32 UTC.
- Dernière sauvegarde observée : [exécution réussie](https://github.com/MrJ-am/M-moire/actions/runs/35202085733),
  terminée le 17 septembre à 08:53 UTC.
- Les tentatives de consultation publique dans cette session n'ont pas permis
  de vérifier le site. Ces échecs d'accès ne démontrent pas que le site est en panne.

**Aucun changement n'a été appliqué au VPS.** Son état réel, ses fichiers NixOS,
la génération active, les certificats et les sauvegardes doivent être relus
avant la migration. Les réussites Actions précédentes ne remplacent pas cet audit.

## Validations de la préparation

- Le code du module applicatif hors passerelle est conservé à l'identique.
- Le bloc Nginx déplacé dans le module de compatibilité est conservé à l'identique.
- La configuration historique complète importe ce module de compatibilité.
- Les onze contrôles Python du registre, des réponses HTTP et de provenance ont réussi : collisions,
  contenu de santé trompeur, administration anonyme, suppression d'anciens
  contrôles et changements d'empreintes sont détectés.
- Nix n'est pas installé dans l'environnement de préparation. La commande de
  contrôle s'arrête explicitement avec le code 2 après les tests Python ; elle
  ne présente pas cette validation comme complète. La [CI de la PR](https://github.com/MrJ-am/M-moire/actions/runs/35271624287)
  a réussi : syntaxe des modules du mémoire, données, API PostgreSQL, compilation
  et parcours navigateur. La [CI de ce dépôt](https://github.com/MrJ-am/vps-infrastructure/actions/workflows/check.yml)
  prend en charge la syntaxe et les tests de génération du routage. Sa réussite
  ne dispense pas d'une construction NixOS complète sur le VPS.
- La construction complète, les contrôles HTTP réels et la répétition du retour
  arrière sur le serveur restent à effectuer.

## À renseigner après une migration réussie

| Élément | État |
|---|---|
| URL du dépôt d'infrastructure | https://github.com/MrJ-am/vps-infrastructure (privé) |
| Commit d'infrastructure installé | Non installé |
| Source Nixpkgs utilisée | À relever sur le VPS, sans mettre à jour le canal |
| Ancienne génération protégée | À relever et protéger de la collecte |
| Nouvelle génération | Non construite sur le VPS |
| Sauvegarde des sources avant migration | À créer sur le VPS |
| Contrôles HTTP/SSH/sauvegardes | À effectuer sur le VPS |
| Relais définitif côté mémoire | PR en brouillon |
