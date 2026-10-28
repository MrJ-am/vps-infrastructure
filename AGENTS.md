# Préparer et qualifier l'infrastructure Rust/Elm

- Déploiements gelés : aucun SSH, SQL de production, activation Nix, DNS ou accès aux données.
- Lire la documentation de `environment/` avant ses commandes ; Rust 1.99.1, Elm et les outils verrouillés font référence.
- Préserver les frontends Log/Audition, leurs contrats et styles. Les propositions de règles canoniques Elm sont dans `mrjam-validation/review` ; leur adoption protégée reste à réaliser.
- `reference-nixos/` et `reference-schemas/` sont des références inactives : ne pas les importer, exécuter ou présenter comme une configuration déployable.
- Le module `operations/nixos/mrjam-rust.nix` reste désactivé. Aucun workflow des forges ne doit être réintroduit pendant le gel.
- N'utiliser que des sources autorisées et des données synthétiques ; ne pas récupérer archives, rapports historiques privés, journaux, secrets ou sauvegardes.
- Documenter les tests, limites et points de reprise ; un build ne prouve ni disponibilité ni autorisation de production.
