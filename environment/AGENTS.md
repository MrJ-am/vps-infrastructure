# Environnement Cloud synthétique

- `bash setup.sh --check` : vérifie sans installer ni démarrer les services.
- `bash setup.sh --install` : prépare les versions verrouillées dans cet atelier.
- `source .local/activate.sh` : expose les outils et la seule URL synthétique.
- `bash services.sh up` puis `bash check.sh --services` : contrôlent le démarrage.
- `python3 -m unittest discover -s tests -v` : tests du helper sur fixtures.
- Ne modifier que des données entièrement synthétiques. Les schémas Vision et
  Mateval sont distincts ; ne pas arrêter PostgreSQL pendant leurs tests.
- Aucun accès de production, aucun déploiement. Le Docker local ne constitue
  pas une séparation des pouvoirs de la future CI VPS.
- Les versions sont dans `toolchains.lock.json`, `package-lock.json` et
  `browser-bundles.lock.json`. Une modification exige une nouvelle qualification.
- Ne versionner ni `.local`, ni `node_modules`, ni captures ou logs de données.
- Lire `README.org` pour configurer les champs réels Install script / Start skill.
