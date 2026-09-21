# Infrastructure VPS

- Lire README.md, docs/MIGRATION.md, docs/POSTGRESQL.md et docs/ETAT.md avant toute intervention.
- Depuis ChatGPT Work, aucun accès SSH direct au VPS n'est disponible. C'est
  le fonctionnement retenu par le propriétaire : ne pas retenter SSH depuis
  Work, ni lui redemander une clé pour résoudre cette limitation réseau.
  Préparer les commandes dans ce dépôt et utiliser GitHub Actions pour les
  exécuter sur le VPS. Les connexions SSH sont celles des runners GitHub.
- Pour constater un état serveur, lire les journaux d'une exécution Actions
  identifiée par son URL et son commit. Un test local ou une CI sans connexion
  au VPS ne prouve pas cet état. Le diagnostic manuel est décrit dans
  `docs/ACCES.md` ; chaque migration constitue une opération distincte à préparer.
- Ce dépôt possède la configuration NixOS de la machine, Nginx, ACME, SSH,
  le pare-feu, PostgreSQL, ses bases/rôles/accès et sauvegardes locales,
  ainsi que l'attribution des domaines/ports. Les projets applicatifs ne
  peuvent ni publier cette configuration ni reconstruire NixOS.
- `projects.json` est le registre utilisé par la passerelle et ses contrôles.
  Un domaine (y compris ses alias) et un port local appartiennent à un seul
  projet. Ne pas auto-détecter des projets ni télécharger leur branche courante.
- `databases.json` attribue les bases ; un nom désigne la base, son rôle et
  son compte système dédié. Seul `modules/postgresql.nix` règle l'instance et
  les sauvegardes locales. Aucun module applicatif ne redéclare ces services.
- Les modules de `vendor/` sont des copies explicitement revues et identifiées
  par commit et SHA-256. Les mises à jour sont des changements d'infrastructure.
- Une adaptation locale d'un module importé doit conserver l'empreinte amont,
  son patch réversible et l'empreinte résultante. La transmettre à son projet.
- Le transfert ne doit modifier ni l'application active, ni le réseau,
  ni la version majeure de PostgreSQL, ni les chemins de données, ni les clés,
  ni les certificats. Les nouvelles règles d'accès PostgreSQL sont un changement
  explicite à auditer et tester ; ne pas présenter l'activation comme neutre.
  Le relevé Git n'est pas une preuve de l'état actuel du serveur.
- Avant activation : auditer le serveur, conserver les sources et la génération
  active, construire le candidat avec le Nixpkgs déjà installé, comparer les
  unités et le routage, armer un retour arrière indépendant de SSH, puis tester.
- Vérifier tous les sites existants, l'API, les accès administratifs anonymes
  refusés, une nouvelle connexion SSH et les sauvegardes. Enregistrer ensuite
  seulement la génération par défaut. Ne jamais effacer l'ancienne génération.
- Ne pas lancer de mise à jour NixOS, de rotation de clé ou de migration de base
  pendant une extraction du routage. Aucun secret ni dump en clair dans Git.
- Le retour de génération NixOS ne restaure pas les ACL et attributs de rôles
  modifiés en SQL. Préparer leur retour ciblé avant activation, sans écraser
  les données collectées. Vision n'est pas activé par son exemple d'intégration.
- La migration initiale a été activée et enregistrée le 18 septembre 2026,
  exécution Actions `35395320446`. Lire les générations dans `docs/ETAT.md`.
  Les workflows `check.yml` et `audit.yml` ne déploient pas. `migration.yml`
  prépare ; `activate-migration.yml` active uniquement sur demande distincte.
  Leurs garde-fous sont liés à l'audit initial : ne pas les contourner pour une
  nouvelle opération, mais préparer un nouvel audit et un retour adapté.
- Après les contrôles pertinents, commit en français et push sur une branche
  dédiée. La publication d'applications et celle de l'infrastructure sont séparées.

## Style MrJ.am

- Lire `docs/STYLE-MRJAM.md` pour le périmètre, l’état réel et la coordination. La préparation des branches ne constitue ni une migration d’interface terminée ni un déploiement.
- La bibliothèque ElmUI française appartient au dépôt public `MrJ-am/style-mrjam`, pas à l’infrastructure. Mutualiser les composants à la compilation, à une révision exacte. Les variantes de boutons sont sémantiques ; ne pas recréer leur décoration dans chaque application.
- Garder le code lisible, compact et français lorsque les noms sont contrôlés. Avant les renommages de code existant, compiler une référence ; renommer un seul symbole avec tous ses usages, compiler et vérifier les contrats avant le suivant. Ne pas renommer aveuglément les protocoles ni les données persistantes.
- Une adoption du style doit reconstruire et redéployer tous les consommateurs. Tester tous les artefacts avant toute activation, conserver les versions antérieures et vérifier les versions effectivement servies. Le dépôt public ne reçoit aucun secret de publication.
- Signature reste la source du logo et de la signature à révision précise. Toute utilisation du logo est strictement réservée ; cette mention doit figurer clairement dans le README public de style. Conserver le texte sélectionnable `MrJ.am`.
- Ne pas rejouer une migration NixOS, modifier PostgreSQL ou restaurer des données pour un changement de style. Confirmer les cibles réelles, y compris l’hébergement statique d’Apprendre à démontrer, avant de mettre en place l’orchestration.
