# État attesté au 17 septembre 2026

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
  La CI étendue vérifie la syntaxe, l'évaluation NixOS, l'isolation effective
  dans PostgreSQL 17 et les restaurations. Son résultat doit être consulté
  sur le commit publié avant activation.
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
