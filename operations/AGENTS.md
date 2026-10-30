# Exploitation Rust ; objectif de première mise en service autorisé

- Lire `mise-en-service/mandat.org` : la directive courante autorise l'achèvement jusqu'à la première mise en service. L'ancien gel n'est plus un motif d'arrêt ; la qualification et les frontières techniques restent exigées.
- Aucun accès général/root au VPS depuis Cloud, SQL libre, lecture de secrets ou données. Les opérations de production passent par un composant borné qualifié ou par l'administrateur humain, jamais par une délégation générale à l'agent.
- `nixos/mrjam-rust.nix` reste désactivé par défaut et sans démarrage/routage automatique.
- Les artefacts préconstruits doivent provenir d'une qualification indépendante ; un chemin Nix store n'en est pas la preuve.
- Préserver PostgreSQL, authentification, Forgejo, Nginx, Nextcloud, archives et références historiques.
- `tests/module-evaluation.nix` ne contient que des configurations synthétiques à évaluer, jamais à activer.
- Les fichiers `evidence/` contiennent uniquement des métadonnées de code. Ne pas leur ajouter journaux, données, JSON de qualification historique ou sauvegardes.
- Lire `exploitation-future.org` et `retrait-ancien-code.org` avant toute modification ; root seul publie les changements distants.
