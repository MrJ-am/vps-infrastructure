# Publication additive de Vision 2.6

La préparation et l’activation passent par `vision-autonomie.yml`. La présence
des sources et des archives ne prouve pas leur publication. Les preuves finales
sont enregistrées dans `operations/vision-autonomie-publication.json`.

L’audit 37427041831 du 6 octobre 2026 a constaté la génération active et de
démarrage `y1azkcagkf54nq5vjn4j16g5v1c61c4c`, Vision 2.5, PostgreSQL 17.11,
pgvector 0.8.2 et 25 contrôles HTTP/TLS réussis. Aucun changement NixOS,
Nginx, fournisseur local, compte ou secret n’est prévu par cette publication.

Le candidat conserve les sources exactes validées par les CI applicatives et
l’interface compilée, avec leurs empreintes. Le serveur est construit sur le
Nixpkgs déjà installé ; l’interface n’est pas reconstruite pendant la bascule.
Le wrapper de release fournit l’adresse publique MCP à partir de `projects.json`.
Ce réglage appartient à la release et revient avec elle. Le code applicatif
possède également sa configuration Nix pour un déploiement sur une autre origine.

Les migrations 017 et 018 ajoutent le seuil de séance courte et les métadonnées
de datation, puis les lectures de politique et les rapports. Les anciens rappels
incertains ne sont pas réhorodatés. Les réglages existants, versions, contenus,
séances, observations et états mémoriels sont comparés avant/après. Le nouveau
seuil vaut 60 minutes sans remplacer les autres réglages.

Avant activation, un dump récent est restauré dans une base jetable appartenant
à Vision. Les extensions sont préparées par PostgreSQL puis leurs instructions
de création sont exclues du TOC restauré. Les essais de clôture/rejeu sont annulés.
Le vrai retour des fonctions SQL est essayé, puis la migration réinstallée ; un
test CI indépendant vérifie aussi qu’une modification postérieure des réglages
survit au retour. Aucun dump ni contenu privé n’est publié dans Git ou Actions.

L’activation arrête Vision, conserve un nouveau dump et les définitions exactes
des fonctions remplacées, puis applique les migrations additives et remplace
les deux liens de release. Un timer systemd indépendant de SSH revient au bout
de trente minutes si la publication n’a pas été enregistrée. Le retour remet
les fonctions compatibles et les liens anciens ; il conserve les colonnes et
toutes les données nouvelles, sans restauration de la base de production.

Les contrôles HTTPS vérifient l’artefact exact, l’accueil anonyme, `/connexion`,
les pages publiques, les liens privés, la consultation de politique, le tutoriel
et les rapports, puis Basic, Bearer, OAuth PKCE, sessions, CSRF et révocation.
Les seules captures publiées sont des pages de connexion vides. Les essais
métier restent dans des bases jetables. Les tokens et autorisations temporaires
de contrôle sont révoqués sans modifier ceux déjà présents.

Après validation, le timer est désarmé et une nouvelle connexion constate les
liens, les services et les contrats SQL 7/1. Une opération `constater` séparée
répète les parcours HTTPS et le constat après finalisation. Les anciennes
releases et la génération active sont conservées.

Le contrat pédagogique prescrit le comportement du LLM. Les tests de contenu
et des réponses serveur ne constituent pas une évaluation de tous les modèles.
Les bornes temporelles vérifient la plausibilité d’une date, pas son authenticité.
