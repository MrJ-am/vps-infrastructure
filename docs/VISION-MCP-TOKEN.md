# Token MCP Vision pour Mistral

Le propriétaire a demandé le 22 septembre 2026 un accès Bearer à
`https://vision.mrj.am/mcp`, compatible avec l’authentification par token API
de Mistral. HTTP Basic reste accepté sur MCP et sur l’API historique.

## Utilisation

Après connexion à Vision, ouvrir `https://vision.mrj.am/auth/mcp`, créer un
token et le copier dans le connecteur Mistral personnel (type Bearer). Ne pas
ajouter le mot Bearer dans la valeur du token. La page permet son remplacement
ou sa révocation. Le secret est montré une seule fois, sans stockage navigateur.

Chaque compte dispose d’un token de 256 bits aléatoires, valide un an. Seul son
SHA-256 est conservé dans la base SQLite privée de mrj-auth. La comparaison de
l’empreinte du fichier des comptes révoque aussi les tokens après une rotation
des identifiants. Se déconnecter du navigateur ne révoque pas le token MCP.
La génération et la révocation exigent une session, l’origine exacte et CSRF.
Les tokens donnent accès aux cinq outils MCP, en lecture comme en écriture.
Ils ne donnent accès ni à `/api/v1/`, ni à `/api/web/`, ni à leur propre gestion.

Nginx utilise Basic OU une sous-requête interne `/verify-mcp` vers mrj-auth.
Une session seule ne satisfait pas cette sous-requête. Le proxy efface le
secret, le cookie et les en-têtes d’identité client avant d’attester l’accès
au serveur Lisp. Les limites de débit MCP sont conservées.

## Déploiement et preuves

Le workflow `mcp-token.yml` reçoit `operations/mcp-token.json` : opération
`preparer` ou `activer`, révision exacte dont la CI a réussi. La préparation
relève les générations actives, le Nixpkgs installé et les liens applicatifs,
reproduit la génération active, compare les invariants et construit le
candidat depuis `hosts/hostinger/logique.nix`. Elle préserve notamment tous
les sites et toutes les routes hors MCP, les comptes, certificats, services
métier, versions PostgreSQL et sauvegardes.

Une copie cohérente privée des sessions et les exports métier chiffrés sont
conservés. Le retour remet les sources et la génération antérieures, sans
restaurer les données. L’ajout de table de tokens est compatible avec l’ancien
service. L’activation arme un timer autonome de vingt minutes avant l’essai ;
le démarrage par défaut n’est enregistré qu’après les contrôles HTTPS.

`tests/test_mcp_token.py` vérifie stockage, cycle de vie, séparation, CSRF et
la configuration Nginx réelle. `scripts/mcp-verifier.py` contrôle en production
le navigateur, Basic, Bearer, initialize, tools/list, notification, lecture et
révocation, puis supprime son token de contrôle. Il refuse de remplacer un token
préexistant. Aucune fiche de test n’est écrite en production. Les écritures MCP
sont testées avec PostgreSQL jetable par la CI applicative de Vision.

La présence de ces fichiers ne prouve pas une activation. Les références de
publication effectives sont ajoutées dans ETAT.md après la réussite des Actions.
