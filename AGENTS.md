# Infrastructure VPS

- Lire README.md, docs/MIGRATION.md et docs/ETAT.md avant toute intervention.
- Ce dépôt possède la configuration NixOS de la machine, Nginx, ACME, SSH,
  le pare-feu et l'attribution des domaines/ports. Les projets applicatifs ne
  peuvent ni publier cette configuration ni reconstruire NixOS.
- `projects.json` est le registre utilisé par la passerelle et ses contrôles.
  Un domaine (y compris ses alias) et un port local appartiennent à un seul
  projet. Ne pas auto-détecter des projets ni télécharger leur branche courante.
- Les modules de `vendor/` sont des copies explicitement revues et identifiées
  par commit et SHA-256. Les mises à jour sont des changements d'infrastructure.
- L'extraction initiale ne doit modifier ni l'application active, ni le réseau,
  ni PostgreSQL, ni les chemins de données, ni les clés, ni les certificats.
  Le relevé Git n'est pas une preuve de l'état actuel du serveur.
- Avant activation : auditer le serveur, conserver les sources et la génération
  active, construire le candidat avec le Nixpkgs déjà installé, comparer les
  unités et le routage, armer un retour arrière indépendant de SSH, puis tester.
- Vérifier tous les sites existants, l'API, les accès administratifs anonymes
  refusés, une nouvelle connexion SSH et les sauvegardes. Enregistrer ensuite
  seulement la génération par défaut. Ne jamais effacer l'ancienne génération.
- Ne pas lancer de mise à jour NixOS, de rotation de clé ou de migration de base
  pendant une extraction du routage. Aucun secret ni dump en clair dans Git.
- Les scripts fournis effectuent des contrôles ; ils n'activent pas le système.
- Après les contrôles pertinents, commit en français et push sur une branche
  dédiée. La publication d'applications et celle de l'infrastructure sont séparées.
