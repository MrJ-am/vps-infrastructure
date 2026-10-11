# Assemblage et exploitation MrJ.am

La mission du 11 octobre 2026 remplace la coordination et les publications par
application. Lire `assemblage/manifest.json`, `coordination/CONTRATS.org`,
`coordination/REGISTRE.org` et `assemblage/REPRISE.md`. Les preuves datées de
`docs/ETAT.md` restent historiques ; constater le VPS avant une bascule.

- Périmètre : uniquement les six dépôts du manifeste ; aucune modification tiers.
- L'infrastructure possède assemblage, commandes locales, toutes les exécutions
  CI/CD, frontend, NixOS, routage, bases et exploitation. Les bibliothèques
  conservent sources, contrats et tests. Aucun acquittement ni validation réciproque.
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
- Aucune nouvelle dépendance tierce directe sans autorisation, sauf Kanidm/outils
  officiels autorisés. Inventorier/verrouiller les transitives. Aucune installation
  opportuniste due à l'absence d'un outil.
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
