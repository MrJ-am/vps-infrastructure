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
