# Publication statique de l’atelier de preuves

Le propriétaire a demandé l’atelier dans Logique et sa publication. Le code Elm,
les certificats, les gestes du navigateur et les tests vivent dans
`MrJ-am/apprendre-a-demontrer`. Le module optionnel `MrJam.Blocs` appartient à
`style-mrjam`. Les autres consommateurs conservent leurs versions épinglées.

Le workflow `logique-atelier.yml` exécute une opération bornée sur `main`, dans
`vps-production`, avec la clé administrative et l’hôte vérifié existants. Aucun
SSH depuis Work, changement NixOS, migration SQL ou redémarrage applicatif.
La seule activation est le remplacement atomique de `/srv/logique/current`.

## Préconditions et provenance

`operations/logique-atelier-candidat.json` identifie trois révisions complètes,
la CI applicative réussie et l’empreinte de `vendor/logique-atelier/logique.zip`.
Cette archive est celle de l’artefact testé `site-logique-verifie`. Tous les
fichiers, l’inventaire, les fontes originales et la validation typographique
sont vérifiés par `corrections_artefacts.lire`. Le workflow vérifie aussi les
exécutions réelles des CI applicative et infrastructure, à leurs SHA exacts.

La demande `operations/logique-atelier.json` ne contient que `operation` et
`revision` : `preparer`, `activer` ou `constater`, et le SHA de l’opérateur validé.
Chaque demande constitue un commit distinct. Aucun texte de commande libre.

## Séquence et retour

1. `preparer` relève la génération active, celle du démarrage, l’empreinte de
   configuration, les quatre publications et les services/sauvegardes. Les deux
   générations doivent coïncider. Il crée une nouvelle release inactive, sans
   réécrire une identité existante, puis vérifie un minuteur autonome témoin.
2. `activer` exige le même état réel et les mêmes fichiers, arme un retour sous
   dix minutes, puis remplace uniquement le lien Logique sous verrou.
3. Le runner ouvre une nouvelle connexion, exécute les 35 sondes existantes,
   compare tous les octets HTTPS au manifeste et contrôle l’atelier dans trois
   formats. La création d’un théorème et son rechargement restent locaux au
   navigateur ; aucune donnée n’est envoyée au serveur.
4. Après ces contrôles, `finaliser` enregistre le succès sous verrou et désarme
   le retour. Une nouvelle connexion vérifie les invariants. Une demande
   `constater` séparée répète les sondes, les octets et les parcours HTTPS.

En cas d’échec avant finalisation, le runner ou le minuteur rétablit l’ancien
lien. Une publication concurrente inconnue interdit ce retour. L’ancienne
release, les autres applications, les données et les générations sont conservées.
Le retour ne restaure aucune base. La préparation et le constat techniques sont
conservés dans les artefacts Actions et sous `/root/logique-atelier/<revision>`.

## Contrôles et état

`python3 -m unittest discover -s tests -v` inclut cinq contrôles du publicateur :
bascule limitée à Logique, liens atomiques et conservation, refus des symlinks
dans l’artefact, révision complète obligatoire et altération détectée.
`sh scripts/check.sh` contrôle aussi l’archive candidate ; Nix et PostgreSQL
sont vérifiés par la CI infrastructure existante.

L’état réellement publié et les exécutions seront consignés dans
`operations/logique-atelier-publication.json` et `docs/ETAT.md` après constat.
Ce document décrit le mécanisme et ne prouve pas à lui seul une publication.
