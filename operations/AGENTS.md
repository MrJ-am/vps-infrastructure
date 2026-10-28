# Proposition d'exploitation Rust ; déploiements gelés

- Aucun accès au VPS, SSH administratif, SQL libre, lecture de secrets ou activation Nix.
- `nixos/mrjam-rust.nix` reste désactivé par défaut et sans démarrage/routage automatique.
- Les artefacts préconstruits doivent provenir d'une qualification indépendante ; un chemin Nix store n'en est pas la preuve.
- Préserver PostgreSQL, authentification, Forgejo, Nginx, Nextcloud, archives et références historiques.
- `tests/module-evaluation.nix` ne contient que des configurations synthétiques à évaluer, jamais à activer.
- Les fichiers `evidence/` contiennent uniquement des métadonnées de code. Ne pas leur ajouter journaux, données, JSON de qualification historique ou sauvegardes.
- Lire `exploitation-future.org` et `retrait-ancien-code.org` avant toute modification ; root seul publie les changements distants.
