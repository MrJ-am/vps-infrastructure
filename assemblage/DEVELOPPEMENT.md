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

Architecture C conservée après le rapport MCP : métier, cl-mcp sans pool et Swank
dans l’image de tâche ; Tron dans un processus d’outillage distinct, connecté à
ce Swank ; accès agent par le pont HTTP existant. MCP_NO_WORKER_POOL=1 et
:worker-pool nil dans le lanceur actuel. Ce choix concerne le développement,
pas la production ni une interdiction définitive du mode workers. Ni A/B,
troisième bibliothèque, mise à niveau ou campagne de crash pour cette reprise.

Après reconnexion/reconstruction, lire PID/marqueur/état partagé depuis les deux
chemins. Invalider les anciens objets, threads, restarts et références de session,
sans effacer les preuves historiques. Les PID du rapport sont des observations,
aucun script ne les fixe. Deux connexions ou mêmes fichiers ne prouvent pas la
même image. Le qualifier synthétique provoque une condition/réinitialise une
fixture : réservé à sa qualification explicite, jamais contrôle de santé.

La suite centrale `outils-mcp` utilise `qualifier-mcp.py --reutiliser` : elle
vérifie la trace du scénario déjà exécuté et les empreintes inchangées des
bibliothèques, lanceurs et sources de fixture. Elle ne réinitialise aucun objet,
ne provoque aucune condition et ne prouve pas une nouvelle connexion. La preuve
et sa trace sont incluses dans le bundle privé et l'identité du reçu. Les deux
contrôleurs Python amendés ont leurs propres tests de routage/parser dans
`outils-routage` ; leurs changements ne sont pas présentés comme un nouveau
débogage réel. Modifier une entrée du scénario invalide sa réutilisation et
exige une qualification explicite, hors contrôle de santé.

Le routage opérationnel est le suivant ; cible établie et comportement testé
restent deux propriétés différentes :

| Chemin | Cible | Comportement qualifié / limites |
| --- | --- | --- |
| CL-MCP direct sans pool | Image applicative | repl-eval, load-system, test-op ASDF de fixture et lectures d’état exercés ; catalogue/édition structurelle ne sont pas tous testés |
| Tron repl_eval/repl_compile/repl_frame_locals/repl_get_restarts/repl_invoke_restart | Swank applicatif connecté | Condition/pile/locaux, compilation et restart contrôlé exercés ; restart applicatif choisi à nouveau par sens/index courant |
| Tron repl_status/swank_status/swank_debugger_state | État de connexion/débogage tenu par Tron | Sondes lues ; ne prouvent pas seules l’identité du tas applicatif |
| Tron inspect_object/inspect_package/runtime_stats/thread_list et autres inspecteurs locaux | Processus Tron | Cible établie par lecture du code, comportement non qualifié sur l’application ; ne pas les utiliser comme observations métier |
| Tron code_compile_string/reload_system | Distant si connecté, fallback local sinon | Non employés en usage applicatif ; choisir les chemins explicitement distants |
| Autres outils annoncés | À établir avant usage | Ajout seulement pour besoin concret, vérification de cible puis contrôle proportionné ; pas de qualification globale des 91 outils |

Le pont refuse les commandes Tron locales/à fallback/inconnues avant transport.
Pour les cinq commandes distantes ci-dessus, il exige un statut connecté à
Swank127.0.0.1:4105 avant d’envoyer l’opération. repl_connect exige cette cible
explicitement. Le catalogue et les trois sondes restent disponibles. La liste
opérationnelle est dans scripts/mcp-appel.py, testée par tests/test_pont_mcp.py.
C’est un garde-fou de routage, pas un sandbox ni une preuve de PID : le constat
croisé reste obligatoire après toute reconnexion. Un échec ne bascule pas localement.

Édition structurelle disponible, facultative : utiliser lisp-edit-form/patch-form
si cela rend la modification plus précise/sûre ; patch textuel ou fichier complet
autorisé. Aucun appel MCP artificiel pour Elm, Nix, Python ou documentation.

Pendant une suspension, conserver l’événement DEBUG et son thread/niveau ; lire
sa pile et les locaux ciblés, jamais la pile du RPC d’inspection comme celle du
calcul. Pas d’opération métier concurrente sans lien avec la résolution. Le verrou
par appel n’arrête pas les threads et ne couvre pas toute une réparation.
Limiter les modifications à celle-ci ; identifier le restart par son sens et sa
position actuelle, pas par l’index0 de la fixture. Vérifier résultat et effets
métier indépendamment de l’enveloppe protocolaire. Un timeout ne prouve ni annulation
ni absence d’effets ; ne pas rejouer une opération pour obtenir une meilleure trace.
Après dépilage CL-MCP : diagnostic et effets persistants, aucune pile vivante à reprendre.

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

`qualifier-metier.py` utilise le fichier `.construction-nix.json` adjacent au
candidat lorsqu'il existe : il exerce cette image sans reconstruction. Un appel
direct de construction sur cette destination est refusé. Une reconstruction de
référence sans cache doit utiliser une destination distincte ; ses résultats ne
qualifient pas implicitement l'image Nix à promouvoir.

Dans l'atelier Codex actuel, exécuter les campagnes navigateur lourdes une après
l'autre. L'orchestrateur borne l'atelier logo à `--workers=1` : la trace
`4a43b577abaa` montre deux démarrages simultanés absorbant le délai initial.
Cette borne ne modifie ni les assertions ni les délais des tests.

Qualification finale dans une image propre ; production construite dans un autre
processus propre depuis sources/FASL qualifiés, jamais sauvegarde de l’exploration.
Promouvoir le même artefact : protocole [PROMOTION.md](PROMOTION.md), backup/restauration/
retour et sondes réelles, SSH central existant. Aucun ancienworkflow réactivé.
Journal synthétique sans secrets/données dans JOURNAL.md ; reprise compacte dans
REPRISE.md. Ancien guide exact archivé dans coordination/historique/.

Raccordement qualifié dans cette tâche : cl-mcp4106 et Swank4105 dans l’image
applicative ; Tron4107 dans un processus d’outillage séparé, ciblant ce Swank.
Les ports sont exclusivement loopback. Sources/licences/35 transitives/limites et
patch de raccordement : `outils/mcp.lock.json`, `outils/audit-mcp.md`, `outils/mcp.nix`.
Le scénario réel est exécuté par `python3 scripts/qualifier-mcp.py` ; il refuse de
réinitialiser la fixture si un débogage est suspendu. Un échec exige inspection,
pas une répétition aveugle de l’opération ayant déjà incrémenté son compteur.
Les résultats du rapport MCP sont historiques, rattachés à leurs empreintes.
Le garde de routage actuel est testé isolément par outils-routage ; il ne transforme
pas cette preuve en nouveau succès du scénario suspendu, qui n'est pas rejoué
comme sonde. Le qualifier vérifie maintenant le nom, le sens, la position et la
cible actuels du restart de fixture, puis les relit après compilation. Un ordre
ou format inattendu impose une inspection ; aucune supposition d'index conservé.

Depuis cet agent hébergé, utiliser le transport existant avec le pont HTTP :

```sh
python3 scripts/mcp-appel.py cl-mcp tools/list
python3 scripts/mcp-appel.py tron tools/list
python3 scripts/mcp-appel.py cl-mcp load-system <<'JSON'
{"system":"mrjam-metier","force":false,"clear_fasls":false}
JSON
python3 scripts/mcp-appel.py tron repl_eval <<'JSON'
{"code":"(mrjam-developpement:verifier \"quotas\")"}
JSON
```

Le pont sérialise les appels aux deux outils ; un seul rédacteur de l’image.
Pour une nouvelle image seulement : installer les sources avec l’expression Nix
`outils/mcp.nix` et le Nixpkgs verrouillé, enregistrer le résultat dans
state/outils-sources/mcp-store.txt, charger `outils/application.lisp` une fois après
`developper.lisp`, puis lancer le processus d’outillage SBCL avec `outils/tron.lisp`.
Employer les DSO de state/outils-nix.json. Ne pas relancer cette installation ou
les serveurs à chaque commande. Le catalogue MCP natif hébergé n’est pas modifié ;
la connexion par le pont ci-dessus est la connexion réellement vérifiée.

Pour la pile suspendue, lire les FRAMES de l’événement DEBUG initial et appeler
repl_frame_locals. Le backtrace RPC amont n’est pas la pile suspendue. Garder cet
événement jusqu’au restart ; ne pas prendre un HTTP200 ou le compteur ASDF inconnu
pour un résultat fonctionnel. Qualification finale propre distincte, avec reprise
consignée ; l’image persistante saine reste utilisée pendant cette tâche.
