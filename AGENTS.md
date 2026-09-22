# Infrastructure VPS

<!-- coordination-commune:v1 -->
## Coordination commune

- Identifiant de ce projet : `vps`. À chaque reprise (y compris après compaction), lire aussi le [AGENTS.md distant de référence](https://github.com/MrJ-am/vps-infrastructure/blob/main/AGENTS.md), même sur une ancienne branche.
- Avant de travailler, consulter dans le dépôt privé `MrJ-am/vps-infrastructure`, **branche `main` actuelle**, [coordination/CONTRATS.org](https://github.com/MrJ-am/vps-infrastructure/blob/main/coordination/CONTRATS.org) et [coordination/REGISTRE.org](https://github.com/MrJ-am/vps-infrastructure/blob/main/coordination/REGISTRE.org). Lire le protocole au début du registre à la première utilisation ; ensuite, charger la synthèse et les messages destinés à `vps`. Ne pas charger les archives par défaut.
- Reconsulter avant toute modification d'un contrat partagé, avant publication et à la clôture. La commande `python3 scripts/coordination.py lire vps`, dans une copie fraîche du dépôt VPS, produit la vue ciblée. Les outils GitHub permettent aussi cette lecture sans clone ni SSH.
- Publier les impacts globaux pour tous les projets ; pour un impact ciblé, nommer explicitement les destinataires et les actions. Informer avant le changement puis consigner le résultat avec commit et preuves. Une demande n'est pas un changement exécuté.
- Acquitter uniquement pour `vps`, après lecture réelle, avec l'empreinte du message et le dépôt@commit du contexte. Distinguer LU, BLOQUE et DONE ; DONE exige une preuve. Suivre le protocole pour publier la réponse sur le main VPS sans écraser les autres écritures.
- Si le registre est inaccessible, le dire, poursuivre les tâches indépendantes et suspendre seulement les changements partagés dont les préconditions restent inconnues. Ne pas inventer d'accusé ni demander à l'utilisateur de transporter les messages entre projets.
- Les consignes locales continuent de s'appliquer. Le registre ne donne aucun droit supplémentaire de publication ou d'administration. Après les mises à jour, vérifier l'archivage des échanges intégralement traités ; ne jamais effacer un message non acquitté.

<!-- /coordination-commune:v1 -->

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
