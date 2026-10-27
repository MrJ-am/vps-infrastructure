# Assemblage et exploitation MrJ.am

La mission et son amendement du 11 octobre 2026 gouvernent le travail. Lire
`assemblage/manifest.json`, `coordination/CONTRATS.org`, `assemblage/REPRISE.md`,
`assemblage/DEVELOPPEMENT.md` et `assemblage/FRONTENDS.md`. Les preuves anciennes
restent historiques ; constater l’état installé avant une opération.

- Périmètre : les six dépôts du manifeste et Audition, composant interne
  expressément demandé le 13 octobre 2026. ETP Vie Amoureuse exclu du monolithe.
  Exception d’hébergement autorisée les 25–27 octobre : ViSe sur vise.mrj.am,
  serveur Rust autonome et base séparée dans le PostgreSQL général existant.
  Adapter uniquement service, vhost, HBA ciblée et sauvegarde ; aucun SSO,
  thème, SDK, graphe métier ou instance PostgreSQL supplémentaire.
  Aucune modification tiers, licence/visibilité, PR ou contact externe.
- L’infrastructure possède assemblage, commandes locales, CI/CD et exploitation.
  Composants : sources/contrats/tests. Aucun workflow satellite, acquittement,
  validation entre conversations ou campagne de développement distante.
- Développement et qualification locaux. CI/CD uniquement pour promotion,
  préconditions et sondes réelles, sauvegardes et exploitation existantes.
  Aucun test automatique au push. Publier composants avant manifeste exact.
- Bibliothèques métier ASDF sans daemon/connexion/migration au chargement ; une
  image SBCL métier active. Cycle de vie/transport/tâches dans le serveur commun.
  Log distinct, Logique statique ; Nginx/PG/Nextcloud/embeddings conservés.
- Même tâche : conserver l’image SBCL persistante saine. Architecture actuelle C :
  métier/cl-mcp sans pool/Swank dans l’image, Tron séparé, pont HTTP existant.
  CL-MCP ordinaire pour évaluations/ASDF/tests/sources ; Tron via Swank dès
  l’appel qui doit conserver pile/restarts. Cibles et comportements testés
  distincts : voir DEVELOPPEMENT.md. Inspecteurs locaux/fallbacks Tron ne sont
  pas l’application distante. Après reconnexion, vérifier PID/marqueur/état
  partagé et invalider les références anciennes ; aucun PID constant en script.
  Pendant une suspension : aucune opération métier concurrente sans lien avec
  la réparation, pile DEBUG/thread/niveau conservés, restart choisi par sens et
  position actuelle, effets vérifiés après reprise. Timeout n’annule pas les effets.
  Édition structurelle facultative, aucun appel MCP artificiel pour Elm/Nix/prose.
  ASDF incrémental ; contrôle de santé sans qualifier synthétique. Processus
  de test propre distinct permis pour reproduction, sans détruire l’image saine.
- Écrire les corrections durables dans les sources avant chargement/compilation.
  Qualification finale en image propre. Outils MCP/Swank uniquement de
  développement, sans production ni endpoint public ; MCP métier distinct.
- Frontends Elm : elm-ui et elm-animator, politique/composants communs dans
  style-mrjam. Pas de présentation Html/Html.Styled/elm-css/CSS/HTML injecté ou
  moteur d’animation applicatif. Adaptateurs techniques étroits, nommés et testés.
  Element.html/htmlAttribute encadrés centralement. elm-review obligatoire sur
  les sources assemblées et composants verrouillés ; pas d’exclusions générales
  ni suppressions régénérées. Tests des règles, alias/exposing et fixture rejetée.
- Continuous UI : interruptions/inversions, état, focus/clavier, reduced-motion,
  absence de rafraîchissement inutile. Le métier n’attend pas une décoration.
  Préserver ressources/identité visuelle et les fonctionnalités ; statique reste statique.
- Log : le parcours utilisateur doit adopter le socle ElmUI/Animator partagé et
  l'identité MrJ.am ; les pages natives Kanidm ne prouvent pas cette conformité.
  Kanidm reste l'IdP séparé ; ni fork Rust, ni authentification réimplémentée,
  ni perte des sessions/enrôlements existants. Voir FRONTENDS.md pour le raccordement.
- Dépendances nommées par l’amendement et leurs nécessaires transitives autorisées
  après audit/verrouillage : elm-animator, elm-review, cl-mcp, cl-tron-mcp/Swank.
  Aucun cl-harness, fusion, MCP ou débogueur réécrit. Autres bibliothèques Lisp
  après audit ; Kanidm/outils officiels autorisés. Tout autre nouveau runtime,
  langage/service produit exige autorisation. Python permis pour l’outillage agent.
- Serveur métier Common Lisp. Node limité aux constructions/tests frontend
  approuvés et référence différentielle temporaire Matheval sur bases isolées.
- Outils communs : même paquet au même niveau, même version verrouillée dans
  assemblage/dependances.json. Ne pas conserver plusieurs SDK/moteurs par projet ;
  exceptions de niveau/ABI justifiées dans DEVELOPPEMENT.md. Vérification locale
  bloquante avant qualification ; aucune installation implicite au push.
- Données : propriétaires, observations/dates/stabilités/politiques/liens/historiques
  et séances ouvertes préservés. Vérifier tous les comptes avant destruction.
  IdP et compte métier distincts ; contenus clairs côté serveur, HTTPS et backups
  chiffrés. Aucun faux contenu, séance ou participation en production.
- Identité vérifiée/refus par défaut, autorisation de chaque ressource/opération,
  contexte borné, SQL non propriétaire/non superuser/RLS adaptée. Packages Lisp
  et paramètre SQL ne prouvent pas l’authentification face à une compromission.
- Promotion du même artefact propre qualifié, provenance/entrées exactes, secrets
  et connexions au démarrage hors store/image. Ancien reçu réutilisé seulement
  sur périmètre inchangé ; nouvelles interfaces/configurations requalifiées.
- Exploitation distante par CI centrale existante (`docs/ACCES.md`). Avant bascule :
  backup récupérable/restauration isolée/retour indépendant/invariants. Retour du
  code avec données actuelles, jamais restauration ancienne sur écritures récentes.
- Préserver écritures concurrentes : aucun reset/nettoyage destructeur/force-push.
  Journal synthétique sans secrets/contenus. Les deux déploiements sont autorisés ;
  après constat de l’étape 1, poursuivre Kanidm sans confirmation intermédiaire.
  Séparer installation, démarrage, connexion agent et même-image réellement prouvés.
