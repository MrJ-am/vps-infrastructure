# Publication de la vitrine Vision

Cette opération publie le serveur 2.6.1 et l’interface provenant de la même
révision applicative. Le nouvel accueil, les onze chapitres du tutoriel et la
confidentialité utilisent les composants communs à une révision exacte.
Les cinq visuels du produit passent par la route statique déjà active.

L’opération appartient à VPS. Les archives sont figées par l’assembleur de
Vision après réussite des CI serveur et navigateur. Le candidat les identifie
par SHA-256 et les rapproche du manifeste compilé. Les sources, le style et
l’audit portent chacun une révision complète. La CI VPS contrôle le candidat,
le retour applicatif et la configuration avant toute connexion administrative.

La demande `operations/vision-vitrine.json` désigne une source opérateur
immuable, un audit réussi et l’une des étapes `preparer`, `activer` ou `constater`.
Seul le workflow `vision-vitrine.yml` exécute les commandes distantes.

La préparation compare les publications, les générations et la configuration
avec l’audit. Elle construit avec le Nixpkgs réellement installé. Elle conserve
un dump privé et vérifie sa restauration dans une base jetable. Le serveur
candidat démarre sur cette copie. Le compte Unix `postgres` ouvre la connexion
avec le rôle SQL `vision`. Cela respecte le refus des bases étrangères pour
le compte Unix `vision` sans modifier les règles d’accès de production.
Le groupe supplémentaire `vision` permet de lire la release pendant ce seul
processus de contrôle. Aucun compte ou droit de fichier n’est modifié. Les empreintes de toutes ses tables doivent
rester identiques après les lectures. La base jetable est ensuite supprimée.
Aucune donnée personnelle ne quitte le VPS ou n’entre dans les captures.

L’activation arme un retour indépendant de SSH pendant vingt minutes. Elle
arrête Vision, conserve une nouvelle sauvegarde, compare toutes les tables,
change les deux liens de publication, vérifie les données puis redémarre.
Les fonctions SQL 7/1, les migrations déjà enregistrées, NixOS, le routage et
les autres applications restent inchangés. Le retour inverse les deux liens
et préserve les écritures intervenues depuis la publication. Il ne restaure
aucune base et refuse une publication concurrente.

Avant finalisation, les contrôles HTTPS et navigateur vérifient l’artefact
exact, les images, les fontes, le clavier et quatre tailles d’écran. Les onze
chapitres sont comparés au JSON commun sur le web et en MCP. La configuration
publique fournit l’adresse réelle ; sa copie est vérifiée. Basic, Bearer,
OAuth PKCE, sessions, CSRF, liens privés, rapports et révocation sont contrôlés
sans création de fiche, item, séance ou réglage en production. Seuls des accès
temporaires de contrôle sont créés puis révoqués.

Les rapports ne contiennent que les états de publication et les empreintes.
Les captures publiées concernent l’accueil, le tutoriel, la confidentialité et
le formulaire de connexion vide. Une nouvelle exécution `constater` répète
les contrôles après enregistrement et vérifie que le retour est désarmé.

Les clients ChatGPT, Claude et Gemini ne sont pas administrés par cette
opération. Leurs guides officiels sont vérifiés au 6 octobre 2026. Les comptes
et offres nécessaires restent ceux proposés par chaque fournisseur. La
validation OAuth concerne le service Vision ; elle ne simule pas une connexion
à un compte personnel chez ces fournisseurs.
