# Préparer et qualifier l'infrastructure Rust/Elm

- Directive utilisateur du 4 novembre, reprise depuis Spectre : priorité aux outils,
  à Forgejo et à une livraison automatique simple. Les anciennes chaînes arrêtées
  ne sont pas un objectif à terminer ou à réactiver. Le circuit courant est préparé
  dans `operations/continuous-delivery/` : runner Forgejo standard, tests Nix,
  puis livraison du `main` testé sur le slot inactif et retour rapide.
- Un seul dépôt modifié par intervention ; `mrjam-validation` reste en lecture
  seule par défaut. Les sauvegardes sont temporairement hors priorité ; conserver
  leurs fichiers et services. Les schémas et migrations suivent une intervention
  distincte. Depuis Spectre, l'administration nécessaire est autorisée, sans
  lecture des données métier ni affichage de secrets.

- Directive utilisateur du 4 novembre 2026 : toute demande de déploiement autorise
  sa réalisation. Préparer le candidat en amont, conserver l'ancienne version
  disponible, basculer de manière transactionnelle, tester immédiatement et revenir
  à l'ancienne version en quelques secondes en cas d'échec. Une indisponibilité
  prolongée est exclue ; la durée de bascule et de retour doit être mesurée.
- Le démarrage des fixtures locales PostgreSQL/Nginx est explicitement autorisé
  par l'utilisateur pour terminer cette qualification.

- La directive utilisateur du 30 octobre demande d'achever la migration jusqu'à la première mise en service ; voir `operations/mise-en-service/mandat.org`. L'ancien gel d'objectif est remplacé par cette autorisation, sans déclarer une révision qualifiée par défaut.
- Directive du 1 novembre : ViSe ne doit jamais bloquer le premier déploiement. Le profil principal l'exclut ; reporter sa qualification et sa réintégration si nécessaire, en conservant ses données. Ne pas exiger son exécutable, ses tests ou sa disponibilité pour déployer le socle.
- Depuis Cloud : aucun SSH général/root, SQL de production, secret ou donnée réelle. Une intervention VPS exige une capacité techniquement bornée ou un amorçage humain précisément identifié, avec artefacts qualifiés et retour vérifié.
- Lire la documentation de `environment/` avant ses commandes ; Rust 1.99.1, Elm et les outils verrouillés font référence.
- Préserver les frontends Log/Audition, leurs contrats et styles. Les propositions de règles canoniques Elm sont dans `mrjam-validation/review` ; leur adoption protégée reste à réaliser.
- `reference-nixos/` et `reference-schemas/` sont des références inactives : ne pas les importer, exécuter ou présenter comme une configuration déployable.
- Les modules restent désactivés par défaut. Implémenter et qualifier la chaîne nouvelle avant activation ; ne jamais réintroduire `connect.sh` ou les anciens workflows.
- N'utiliser que des sources autorisées et des données synthétiques ; ne pas récupérer archives, rapports historiques privés, journaux, secrets ou sauvegardes.
- Documenter les tests, limites et points de reprise ; un build ne prouve ni disponibilité ni autorisation de production.
