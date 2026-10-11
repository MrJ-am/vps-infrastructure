# Développement local et image commune

Mission/amendement du 11 octobre 2026 : qualification dans Codex ; CI/CD centrale
réservée aux déploiements, préconditions et sondes. Aucun test automatique au push,
workflow composant ou campagne distante de développement. Frontends : voir
[FRONTENDS.md](FRONTENDS.md), elm-review bloquant et suites selon impact.

Une image SBCL persistante par tâche. Pendant la même tâche ou une compaction,
conserver l’image saine ; si elle disparaît, reconstruire depuis sources/journal.
Bootstrap d’une nouvelle image : SBCL cible2.6.4, ASDF incrémental et
`assemblage/developper.lisp`. Ce bootstrap n’est pas la boucle normale de travail.

Utiliser conjointement les bibliothèques officielles :

- cl-mcp : sources/définitions/références, introspection courante, ASDF et tests ciblés.
- cl-tron-mcp via Swank : choisir dès l’évaluation initiale quand on veut conserver
  pile/variables locales en cas de condition ; inspecter l’exécution suspendue,
  corriger le fichier, compiler, puis invoquer un restart approprié.

Les deux doivent agir dans la même image applicative. Désactiver le pool cl-mcp,
notamment MCP_NO_WORKER_POOL=1 si confirmé dans la révision auditée ; connecter
Tron au Swank de cette image. Prouver PID, marqueur et mutation d’objet observés
par les deux outils. Deux connexions réussies ne suffisent pas. Sérialiser les
mutations/rechargements ; aucune redéfinition concurrente pendant un débogage.
Une erreur peut avoir produit des effets : inspecter avant répétition/restart.
Un rapport cl-mcp dont la pile a été dépilée ne devient pas une session Tron.

Corrections durables dans les sources avant chargement. ASDF/COMPILE-FILE pour
FASL ; COMPILE pour correction de fonction dans l’image. Tests ciblés et
introspection avant changements risqués. Scénario réel de qualification des
outils : condition volontaire, pile/locaux, correction enregistrée/compilée,
restart et reprise avec comptage des effets. Aucun scénario ignoré ou simulé
n’est un succès. Installation, serveurs, connexion de l’agent hébergé et bonne
image sont quatre résultats séparés ; une config Codex CLI ne prouve rien ici.

Outils de développement séparés des systèmes métier : aucun chargement implicite
par l’ASDF produit, endpoint public, secret ou connexion de production. MCP Vision
et ses contrats restent distincts. Bibliothèques/dépendances nécessaires nommées
sont autorisées après audit et verrouillage ; pas de cl-harness, fusion ou nouveau
MCP/débogueur. Limitation amont constatée avant toute adaptation étroite.

Commandes centrales existantes de sélection et campagnes isolées :

```sh
python3 scripts/assemblage.py selection --changement vps/lisp/serveur/quotas.lisp
python3 scripts/assemblage.py tester --suite selection
```

La sélection décrit l’impact sans lancer de test. Reçus locaux non attestés avec
empreintes des entrées, dépendances/outils/configuration/fixtures/tests. Réutiliser
uniquement le périmètre inchangé ; intégration/identité/concurrence ne sont pas
remplacées par unités. Frontend modifié ou nouvelles règles : requalifier les
contrôles affectés, sans reconstruction/rejeu global opportuniste.

Les contrôles Lisp existants116/8000Matheval et8003JSON/OpenSSL restent utiles et
leurs fixtures historiques figées/provenance conservées. Node/frontend et ancienne
référence différentielle Matheval sur base indépendante sont les usages approuvés ;
aucun Node métier cible. Les campagnes PG/navigateur/MCP/recherche restent locales.
Les outils et caches cibles sont décrits dans `state/outils-nix.json`.

Qualification finale dans une image propre ; production construite dans un autre
processus propre depuis sources/FASL qualifiés, jamais sauvegarde de l’exploration.
Promouvoir le même artefact : protocole [PROMOTION.md](PROMOTION.md), backup/restauration/
retour et sondes réelles, SSH central existant. Aucun ancienworkflow réactivé.
Journal synthétique sans secrets/données dans JOURNAL.md ; reprise compacte dans
REPRISE.md. Ancien guide exact archivé dans coordination/historique/.

État : image persistante83928 conservée et saine ; intégration des deux outils
encore à auditer/installer/qualifier. Aucune connexion MCP agent revendiquée.
