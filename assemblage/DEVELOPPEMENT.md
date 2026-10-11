# Développement local, déploiement distant

L'instruction du propriétaire du 11 octobre 2026 précise le rythme de travail :
qualification dans Codex, chaîne CI/CD réservée au déploiement et à ses contrôles.
Un push ne déclenche aucune campagne de développement. Les anciens workflows
`assemblage`, `check` et `vision-autonomie-controles` sont désactivés et archivés ;
les sauvegardes et opérateurs distants existants sont conservés.

Depuis la racine de l'infrastructure, avec le SBCL de l'atelier dans `PATH` :

```sh
sbcl --noinform --load assemblage/developper.lisp
```

Garder ce processus pendant la tâche. Écrire les modifications dans les sources,
puis utiliser le graphe ASDF dans cette même image :

```lisp
(mrjam-developpement:recharger)
(mrjam-developpement:verifier "matheval" "native")
(mrjam-developpement:verifier "json" "quotas")
```

Les contrôles Matheval couvrent les vecteurs/stats et 116 cas avec 8000 tirages.
Le contrôle `native` couvre 8003 vecteurs JSON/OpenSSL. Les fixtures synthétiques
figées portent les empreintes de leurs références historiques ; leur exécution
ordinaire est entièrement Lisp et ne relance aucun générateur Node. Les sorties mesurent durée et
allocations ; elles ne constituent pas des attestations de publication.
Une condition reste dans le débogueur : inspecter la pile, tracer les fonctions
concernées, corriger les sources et recharger. Utiliser `COMPILE` pour une fonction
exploratoire ; ASDF/`COMPILE-FILE` produisent les FASL durables. Aucun REPL public,
aucune connexion de cette image à la production.

Choisir les campagnes supplémentaires avant de les exécuter :

```sh
python3 scripts/assemblage.py selection --changement vps/lisp/serveur/quotas.lisp
python3 scripts/assemblage.py tester --suite selection
```

La première commande décrit l'impact, sans exécuter de test. La seconde montre
le lancement d'une suite indépendante du REPL : choisir la suite réellement
affectée. Le pilote réutilise un reçu local réussi seulement si ses entrées,
outils, configuration, fixtures et tests ont des empreintes identiques.
Les tests de PostgreSQL, navigateur, MCP, identité, transactions et concurrence
restent locaux et isolés, avec les outils déjà approuvés, sur les parcours affectés.
Ne pas reconstruire les quatre interfaces pour une correction SQL isolée.

Node sert aux interfaces Elm/interopérabilité et, temporairement, à comparer le
portage au backend Matheval historique sur une base indépendante. Ce différentiel
était demandé par la mission ; il ne fait pas de Node une dépendance du serveur
cible. Lancer les régressions Lisp ordinaires dans le REPL ; conserver le vieux
serveur comme référence de qualification du portage, sans le promouvoir ni le
rejouer pour chaque correction de prose ou de déploiement.

Avant livraison : validation courte des changements dans une image neuve.
Aux jalons du portage : campagne de référence locale selon le catalogue, sans
cache ni sélection, et construction de production dans un processus propre.
Le SBCL 2.6.4 cible et Nixpkgs c5c4a43 sont désormais disponibles localement.
La qualification cible utilise `state/outils-nix.json`, sans campagne distante.

Le déploiement doit vérifier la provenance et les empreintes du candidat et des
preuves, transférer et promouvoir le même artefact sans refaire les campagnes,
vérifier sauvegarde/restauration/retour, puis sonder l'état réel du VPS. Les reçus
locaux actuels restent non attestés : le transfert de confiance vers la promotion
reste à terminer. L'ancien workflow de qualification archivé n'est pas une voie
de publication à réactiver pour contourner ce travail. Aucun nouveau canal SSH.
Plusieurs opérateurs historiques Vision demandent encore `check.yml` via
`ci-exacte.py` ; ils ne constituent pas le circuit du monolithe. Leur remplacement
se fait dans la promotion centrale, sans réactiver cette CI de développement.

Bibliothèques Common Lisp tierces : audit documenté avant intégration, sources et
transitives verrouillées dans l'inventaire. Aucun ajout tiers Lisp n'est nécessaire
pour cette réorganisation du workflow. Tout autre nouveau langage/runtime/service
produit exige une autorisation explicite ; Python est permis pour les outils de
l'agent. Préférer `rg`, Git, ASDF et les outils SBCL aux scripts jetables lorsque
ces commandes suffisent.
