# Assemblage et exploitation MrJ.am

La mission du 11 octobre 2026 remplace la coordination et les publications par
application. Lire `assemblage/manifest.json`, `coordination/CONTRATS.org`,
`coordination/REGISTRE.org` et `assemblage/REPRISE.md`. Les preuves datées de
`docs/ETAT.md` restent historiques ; constater le VPS avant une bascule.

- Périmètre : uniquement les six dépôts du manifeste ; aucune modification tiers.
- L'infrastructure possède assemblage, commandes locales, déploiement distant,
  frontend, NixOS, routage, bases et exploitation. Les bibliothèques
  conservent sources, contrats et tests. Aucun acquittement ni validation réciproque.
- Développement et qualification dans Codex : REPL SBCL persistant, ASDF
  incrémental et suites locales selon impact. Aucun test automatique au push,
  aucune campagne distante pour explorer une panne locale. La CI/CD sert au
  déploiement du candidat qualifié, à ses préconditions et aux sondes réelles ;
  sauvegardes et mécanismes d'exploitation existants restent conservés.
- Publier les commits des composants avant leur référencement central. Promouvoir
  le même artefact qualifié, construit depuis les sources/FASL dans une image propre.
  Aucun secret, connexion ou donnée dans le store ou l'exécutable.
- Une image SBCL métier active. Serveur, connexions et tâches appartiennent à
  l'assembleur. Chargement ASDF sans daemon, connexion ni migration. Log distinct,
  Logique statique, Nginx/PostgreSQL/Nextcloud/embeddings conservés.
- Démarrer SBCL neuf par tâche autonome, charger par ASDF, contrôle court ; garder
  cette image pendant la tâche, écrire les corrections avant chargement. Validation
  finale dans une image neuve. Aucun REPL public ou lié aux données de production.
  Journal technique synthétique sans secrets ni contenus dans assemblage/JOURNAL.md.
- Bibliothèques Common Lisp tierces autorisées après audit consigné : provenance,
  révision, licence, dépendances, effets au chargement et risques pour leur usage.
  Verrouiller sources et transitives avant intégration ; pas de cryptographie maison.
  Kanidm et ses outils officiels sont autorisés. Tout autre langage, runtime,
  bibliothèque ou service nouveau dans le produit exige une autorisation explicite.
  Python est autorisé pour l'outillage propre de l'agent ; préférer les commandes
  existantes et efficaces, sans installation opportuniste ni nouveau service.
- Serveur métier uniquement Common Lisp. Node reste limité aux constructions/tests
  frontend déjà approuvés et à la référence différentielle temporaire Matheval,
  jamais à un auxiliaire de production. Les contrôles Lisp courants s'exécutent
  dans l'image de tâche ; le différentiel historique ne se rejoue que sur impact.
- Préserver données, observations, dates, politiques, liens et séances ouvertes.
  Vérifier tous les comptes avant destruction. Supprimer une identité ne supprime
  jamais implicitement un compte métier. Aucun contenu fictif en production.
- Identité vérifiée, refus par défaut, autorisation par ressource/opération,
  contexte borné, SQL non propriétaire/non superutilisateur et RLS adaptée.
  Les packages Lisp ne sont pas des frontières de sécurité. Contenus lisibles
  côté serveur, HTTPS et sauvegardes chiffrées conservés.
- Exploitation distante par la CI/CD centrale existante (docs/ACCES.md) ; tests
  et développement locaux dans Codex autorisés. Aucun nouveau canal administratif.
- Avant bascule : état réel, sauvegarde récupérable, restauration isolée, invariants
  et retour indépendant. Ne jamais restaurer des données anciennes pour annuler du code.
- Préserver écritures concurrentes : état Git, commits français, push sans force,
  aucun nettoyage destructeur. Aucun PR, contact tiers, changement de visibilité/licence.
- La mission autorise les deux déploiements ; après constat de l'étape 1, poursuivre
  Kanidm sans confirmation intermédiaire. Distinguer local, CI et production.
  Signaler exactement permission manquante ou enrôlement personnel indispensable.
