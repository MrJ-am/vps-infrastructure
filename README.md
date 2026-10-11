# Infrastructure et assemblage MrJ.am

Ce dépôt est le point d'entrée de la réorganisation autorisée le 11 octobre 2026.
[Manifeste des six sources](assemblage/manifest.json), [contrat central](coordination/CONTRATS.org),
[reprise](assemblage/REPRISE.md), [dépendances](assemblage/dependances.json),
[contrat de sécurité](assemblage/SECURITE.md).

La cible est un exécutable métier SBCL assemblant Vision et Matheval en bibliothèques
ASDF. Log reste indépendant ; Logique reste statique. Interfaces Elm/ElmUI, identité
visuelle, Nginx, PostgreSQL, Nextcloud et moteur d'embeddings existants sont conservés.
Toutes les exécutions CI/CD doivent être centralisées ici. Aucune CI de bibliothèque
ou attente de réponse d'une autre conversation ne qualifie l'assemblage.

La migration est **en cours**, sans bascule métier. Vision et Matheval sont des
composants ASDF assemblés et qualifiés localement. Les treize recettes CI satellites
sont archivées et leurs YAML retirés ; leurs fonctions utiles sont orchestrées ici.
La recherche utilise toujours le même modèle réel verrouillé. La sauvegarde chiffrée
et une restauration isolée des données réelles sont vérifiées. L’accès de lecture
aux sources privées manque encore au runner central ; ni le monolithe ni Kanidm
ne sont annoncés comme déployés. [Limites et preuves exactes](assemblage/REPRISE.md).

La production antérieure est décrite dans [ETAT.md](docs/ETAT.md). L'audit réel
[38097638053](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38097638053)
a confirmé le 11 octobre la génération et les services sans mutation métier.
Ne pas confondre la source main avec les versions effectivement servies.

Commandes de l'atelier (six clones frères, outillage déjà autorisé) :

```sh
python3 scripts/assemblage.py verifier
python3 scripts/assemblage.py selection --changement vision/src/json.lisp
python3 scripts/assemblage.py tester --suite selection --suite editorial --suite matheval-pures
```

Le catalogue candidat est dans assemblage/suites.json. Les reçus locaux contiennent
les empreintes des entrées, outils et bibliothèques natives ; ils n'autorisent pas
une publication. La CI rejoue les suites concernées tant qu'une attestation de
confiance n'existe pas. Le mode --reference sélectionne toutes les suites, sans cache.
Les préconditions des suites PostgreSQL/navigateur doivent être fournies par le
futur orchestrateur complet ; aucune réussite globale n'est revendiquée.

Le chargement interactif utilise assemblage/charger.lisp et ASDF. L'image de travail
est conservée par tâche ; la validation finale utilise une image neuve, distincte
de l'artefact de production. Les secrets et connexions n'entrent pas dans les builds.

[Accès administratifs existants](docs/ACCES.md), [PostgreSQL](docs/POSTGRESQL.md),
[méthode de sauvegarde/retour](docs/MIGRATION.md). Les anciennes procédures restent
historiques ; les garde-fous utiles sont conservés et adaptés à l'état réel.
