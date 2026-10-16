# Forgejo — déployé le 16 octobre 2026

**https://forge.mrj.am/** est opérationnel, avec HTTPS vérifié, PostgreSQL existant
et Git HTTPS/SSH (port **2222**). SSH administratif reste sur 22. Inscriptions
fermées, authentification requise, dépôts privés imposés, aucun runner installé.

Versions : **Forgejo 16.0.3**, **Pandoc 3.7.0.2**, **MathJax et polices 4.1.3**.
Nixpkgs et archives sont verrouillés dans `versions.json` avec SHA-256.

## Configuration publiée dans VPS Infrastructure

- Nix : `assemblage/forgejo/module.nix`, `integration.nix`, `assets.nix`.
- Ressources locales MathJax, extension officielle `custom/footer`, fixtures,
  vérificateur des sauvegardes et opérateur dans `assemblage/forgejo/`.
- Déploiement/sondes : `scripts/forgejo-*.py`, `scripts/monolithe-operation.py`,
  options du workflow administratif existant et `operations/forgejo-candidat.json`.
- Régression Nix : `tests/forgejo-integration.nix`.

Le VPS inspecté n’avait **pas de flake** : son entrée classique
`/etc/nixos/configuration.nix` et toute sa chaîne d’imports sont préservées.
Le module officiel `services.forgejo` porte l’installation déclarative.
La source finale est `f79bcaddf7ddaa637350d04bec01d30629e49c29` ; génération
`6791pn34plb531ygfxfyk9riq79x10d0`.

## Tests réellement effectués sur le VPS

- Construction NixOS avant activation ; assertions, priorités HBA, timers TLS,
  comparaison des unités/hôtes/réseau/SSH et Gixy réussis. Sauvegarde de l’existant
  déchiffrée puis restaurée isolément, 38/6/100 tables aux empreintes identiques.
- Certificat HTTPS vérifié ; 25 sondes HTTP/TLS existantes passent. Lors de
  l’installation, PostgreSQL et son dépendant métier ont redémarré avec le même
  code. La correction finale ne change que les deux unités de sauvegarde Forgejo,
  sans redémarrage PostgreSQL ni autre service protégé.
- Dépôt privé `forgejo-validation/org-validation`, compte non administrateur,
  README et trois documents Org dans des sous-répertoires. Clone/push HTTPS et
  SSH réussis ; clé de test temporaire retirée. Rôle PostgreSQL sans superuser,
  createdb, createrole, réplication ou bypassrls.
- Chromium réel : huit vues à 1280/390 px, puis mêmes tests après redémarrage
  et sauvegarde. Pandoc remplace réellement le moteur Org natif ; MathJax produit
  des nœuds CHTML. Quatre délimiteurs, align, fractions, matrices et référence
  d’équation composés. Titres, listes, tableaux, code, liens et images vérifiés.
  Injections HTML/JS rejetées ; aucune erreur JavaScript, ressource manquante ou
  requête CDN ; pas de débordement mobile. Capture mobile inspectée visuellement.
- Redémarrage Forgejo : même commit Git et confidentialité ; PID des autres
  services conservés. Sauvegarde chiffrée réellement déchiffrée, **130 tables**
  restaurées dans un cluster PostgreSQL isolé sans TCP, empreintes identiques,
  **un dépôt** restauré vérifié par `git fsck`. Aucune donnée de production restaurée.
- Retour du code réellement exercé lors d’une première sonde incorrecte : l’API
  de version anonyme était justement interdite par le mode privé. La sonde HTTPS
  utilise désormais la page de connexion ; la version est vérifiée authentifiée.
  Configuration/génération précédentes rétablies sans restaurer d’anciennes données.

Preuves et liens des exécutions : `qualification-production.json`,
`preparation-vps.json`, `qualification-locale.json`.
[Déploiement final](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38888040761) ·
[Persistance/restauration](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38888153134).

## Premier accès administrateur

Compte : **`mrjam-admin`**. Depuis le canal SSH administrateur habituel ou le
terminal VPS, consulter en root `/var/lib/forgejo-bootstrap/initial-admin.txt`,
puis se connecter à l’URL HTTPS. Changement du mot de passe imposé au premier accès.
Le secret n’a été ni lu par l’agent ni publié ; il reste hors Git/store/journaux.
Après changement, supprimer le fichier initial et configurer la double authentification.

## Limites et exploitation

- Redémarrage du service vérifié ; **aucun redémarrage complet du VPS** effectué.
- Sauvegarde quotidienne à 04:45 UTC (+0–10 min), rétention 30 jours dans
  `/var/backup/forgejo`, chiffrée pour le destinataire age existant. Pas de copie
  hors VPS configurée : une destination externe reste à raccorder.
- Mail sortant désactivé ; récupération de compte par l’administrateur.
- Pour une mise à jour, requalifier les versions verrouillées et actualiser les
  préconditions de génération/configuration de l’opérateur avant construction.
  La procédure de restauration et les imports conservés sont détaillés dans `README.md`.
