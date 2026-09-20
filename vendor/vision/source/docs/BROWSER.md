# Navigateur de fiches Vision 1.3

`https://vision.mrj.am/` sert l'interface française, dans la palette de Matheval
(`#087f71`, `#193d38`, fonds vert pâle, panneaux blancs). Les fichiers de
l'interface ne contiennent aucune donnée personnelle. Toutes les lectures et
écritures exigent une session mrj.am, vérifiée par l'infrastructure.

La liste est paginée côté serveur. Elle propose recherche dans titre, contenu,
synthèse, alias et tags ; combinaison des tags (tous / au moins un) ; états
actif, à réviser, nouveau, planifié, sans échéance et archivé ; filtres par
importance, dates, stabilité, difficulté et rappel estimé ; dix critères de
tri avec direction explicite et identifiant comme départage stable.

Le panneau affiche le contenu, les observations et leur contexte JSON, les
instantanés numériques des révisions, l'état mémoriel courant et la configuration
globale du modèle. La synthèse, le contenu, les tags, alias, importance,
échéance, stabilité, difficulté et date de référence sont modifiables. Le
nombre d'observations et de révisions notées reste dérivé du journal, et le
rappel estimé reste calculé. Le modèle FSRS existant est conservé ; cette
interface ne décide pas du remplacement éventuel par un autre modèle.

La migration additive 004 conserve les tables et observations originales.
Une correction ajoute une entrée à `vision_observation_corrections` ; les
lectures du navigateur et du MCP utilisent la dernière correction, et le
navigateur permet de consulter la version originale. Les modifications
manuelles de fiches sont historisées. Une écriture basée sur une version
périmée reçoit HTTP 409, sans écraser les changements concurrents du LLM.
L'archivage est réversible et ne supprime rien. Les observations sont paginées
par 50, sans limiter l'accès aux plus récentes.

## Contrat avec VPS Infrastructure

- `GET /` et `/app.js`, `/app.css` : interface publique vide de données ;
- `GET /auth/session`, `POST /auth/login`, `POST /auth/logout` : service de
  sessions commun appartenant à l'infrastructure ;
- `POST /api/web/list`, `/get`, `/save`, `/correct` : routes dédiées au navigateur ;
- preuve interne `X-Vision-Authenticated: 1` et `X-Vision-Browser: 1` après
  validation de la session et du jeton CSRF par Nginx ;
- identité `X-Mrj-User` écrasée par Nginx et conservée avec les corrections ;
- `/mcp` et `/api/v1/` conservent leur authentification Basic indépendante ;
- le compte jetable `mobile-live` n'ouvre jamais les données de Vision.

Les en-têtes internes ne doivent jamais être repris des requêtes clientes.
L'application reste liée à 127.0.0.1 ; PostgreSQL, Nginx, la connexion partagée et
l'activation NixOS restent gérés par le dépôt VPS. Le service de sessions
réutilise le fichier d'identifiants durable déjà prévu pour Vision. Un verrou
de bootstrap ne constitue pas un compte humain utilisable.

## Vérification

`tests/check_browser_database.py`, appelé par `database_integration.sh`, vérifie
les refus anonymes, les entrées invalides, recherche, tags, tris, pagination,
paramètres, conflits, archives, corrections et accès à plus de 100 observations
avec un vrai PostgreSQL isolé. Les tests historiques HTTP, MCP et FSRS restent
dans la CI. Aucune fiche de démonstration n'est ajoutée à la production.
