# Adresse publique MCP du serveur commun

Le diagnostic 39332607246 confirme la référence Nextcloud SSO `84sxk2qr` :
génération active, démarrage et configuration identiques. Le binaire du correctif
OAuth du 14 octobre est inchangé. L'adresse publique manque encore au serveur
commun et fait échouer la sérialisation du tutoriel après authentification.

`module.nix` applique la même valeur que `modules/metier.nix` à cette génération
installée. L'évaluation refuse toute autre unité modifiée, tout changement des
autres variables, du binaire, du noyau, des ports et des paquets système.
La régression locale évalue Nix puis exécute le véritable tutoriel dans SBCL :
échec avant l'ajout, succès après. Les variantes Nextcloud et pare-feu sont refusées.

La CI centrale existante expose `vision-mcp-preparer`, `vision-mcp-deployer`,
`vision-mcp-retour` et `vision-mcp-diagnostic`. Le descripteur référence exactement
les sources et leurs empreintes qualifiées localement. Préparer ne bascule rien.
Déployer exige encore la même référence, sauvegarde/chiffre/restaure les bases
en isolation et vérifie le retour indépendant sur un processus témoin. Le timer
de retour peut interrompre l'unité de déploiement après perte de la CI.

Seul le serveur métier redémarre, avec le même exécutable. Les autres PID,
clients OAuth existants, interface statique, découverte et refus anonyme sont
contrôlés. La configuration inclut toujours Nextcloud SSO ; le retour restaure
uniquement la configuration précédente, jamais les bases ou anciens jetons.
Les appels ChatGPT réels et le parcours Android sont des vérifications distinctes.

## Mise en service du 19 octobre 2026

Sources `178a781317f09bd6d588d3cde3177d35c11bb435`, préparation 39334439095,
activation 39334676138, génération `vsw0jx0yv1w5rd8fv72sfbn7j2w9sv54`.
Les 29 clients sont conservés et les huit PID protégés inchangés. Appels réels
ChatGPT à 22:26 UTC : tutoriel et réglages réussis. 26 sondes HTTP/TLS passent ;
le registre inclut maintenant les adresses publiques de `/mcp-config.json`.
La preuve de production distingue ces succès du parcours Android encore attendu.
Le retour indépendant vérifie aussi ses outils Nix et son accès HTTPS dès la
préparation, avec une liste fermée de chemins d'environnement transmis.
