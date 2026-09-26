# Publication coordonnée des interfaces documentaires

Le propriétaire a demandé le 26 septembre 2026 d'aller jusqu'à la mise en ligne.
Les trois applications utilisent le style `3aab7233465ac0abe49464fa26a360765ccb4004`.
Les révisions, CI et empreintes exactes figurent dans `operations/interfaces-candidat.json`.
Les archives originales ont été téléchargées depuis les CI réussies, comparées aux
empreintes GitHub, puis conservées dans le dépôt privé. Vision utilise les sources
Lisp à la même révision que son interface, vérifiées contre leurs blobs Git.

`interfaces.yml` reçoit une demande `operations/interfaces.json` avec une opération
`preparer`, `activer` ou `constater` et la révision complète des sources VPS.
Cette révision doit être intégrée et avoir sa propre CI réussie. Les demandes
successives conservent la même révision préparée. La CI ne déploie pas seule.

La préparation lit les générations, la configuration et les quatre liens actifs,
vérifie collectivement les manifestes, construit Vision et installe les dépendances
Mémoire dans des répertoires neufs. Elle refuse toute différence des migrations
Vision et du code métier, hors routes HTTP révisées et validées ; elle compare
également le serveur et les données éditoriales Mémoire à la version active.
Les fonctions partagées des publicateurs précédents sont réutilisées, sans appeler
leur migration SQL ni leurs opérations NixOS. Un timer témoin valide le mécanisme
indépendant. Les versions actives doivent être identiques à la fin de la préparation.

L'activation arme un retour à vingt minutes. Mémoire passe par son compte dédié
`matheval-deploy` et l'exécutable installé `matheval-release`, avec son verrou et
son contrôle de santé. Les deux liens Vision basculent pendant un bref arrêt du
serveur ; Logique change de lien statique. Aucune nouvelle migration n'est introduite, aucune base n'est restaurée et aucun
système n'est reconstruit. Les démarrages conservent leurs vérifications SQL
idempotentes existantes, avec les mêmes fichiers de schéma et le même corpus. Les anciens répertoires restent
présents. Seules les attestations de publication du manifeste Logique sont ajoutées
aux métadonnées de préparation ; ses ressources restent celles de l'artefact testé.

Les sondes vérifient les fichiers effectivement servis sur les trois origines,
seize rendus publics, les refus anonymes, les sessions, CSRF, Basic, Bearer, OAuth
et les treize outils MCP. Les captures restent publiques, sans données métier.
La finalisation exige les liens, générations et fichiers attendus, puis désarme
le retour. Une nouvelle connexion constate l'état enregistré ; une seconde demande
`constater` permet un contrôle indépendant après l'exécution initiale.

En cas d'échec avant finalisation, le retour remet les trois versions antérieures
sans restauration SQL. Il refuse de remplacer une publication ou une génération tierce. Un timer
ancien devient inopérant après enregistrement. Les tests couvrent ces scénarios,
les archives sortantes ou dupliquées, l'intégrité et le refus d'un changement métier.
Les contrôles de l'audit historique du 18 septembre ne sont pas réutilisés pour
juger l'état actuel. Les preuves de cette opération seront ajoutées après exécution.
