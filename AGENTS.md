# Préparer et qualifier l'infrastructure Rust/Elm

- La directive utilisateur du 30 octobre demande d'achever la migration jusqu'à la première mise en service ; voir `operations/mise-en-service/mandat.org`. L'ancien gel d'objectif est remplacé par cette autorisation, sans déclarer une révision qualifiée par défaut.
- Depuis Cloud : aucun SSH général/root, SQL de production, secret ou donnée réelle. Une intervention VPS exige une capacité techniquement bornée ou un amorçage humain précisément identifié, avec artefacts qualifiés et retour vérifié.
- Lire la documentation de `environment/` avant ses commandes ; Rust 1.99.1, Elm et les outils verrouillés font référence.
- Préserver les frontends Log/Audition, leurs contrats et styles. Les propositions de règles canoniques Elm sont dans `mrjam-validation/review` ; leur adoption protégée reste à réaliser.
- `reference-nixos/` et `reference-schemas/` sont des références inactives : ne pas les importer, exécuter ou présenter comme une configuration déployable.
- Les modules restent désactivés par défaut. Implémenter et qualifier la chaîne nouvelle avant activation ; ne jamais réintroduire `connect.sh` ou les anciens workflows.
- N'utiliser que des sources autorisées et des données synthétiques ; ne pas récupérer archives, rapports historiques privés, journaux, secrets ou sauvegardes.
- Documenter les tests, limites et points de reprise ; un build ne prouve ni disponibilité ni autorisation de production.
