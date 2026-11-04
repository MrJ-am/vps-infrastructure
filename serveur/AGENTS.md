# Serveur et services Rust MRJ.am

- Ce workspace appartient désormais à `vps-infrastructure`. Log, le serveur,
  le service d'identité et celui d'effacement sont maintenus ici avec leurs tests.
- Conserver Rust 1.99.1, Cargo.lock et les gitlinks exacts de Vision et Mateval.
  Le préparateur `tools/bootstrap_components.py` utilise la racine de ce dépôt
  et les URL HTTPS Forgejo de son `.gitmodules`.
- Audition reste une bibliothèque isolée dans `crates/audition` en attendant
  son extraction dans un dépôt autonome ; ne pas déplacer sa logique dans le serveur.
- Préserver les contrats HTTP/MCP, les interfaces Elm, les schémas, les identités
  et la compatibilité des sessions. Aucun changement de schéma implicite.
- Vérifier formatage, Clippy, tests du workspace et intégrations PostgreSQL sur
  les seules fixtures locales explicitement synthétiques.
- Une publication de code et une réponse HTTP saine ne prouvent pas un déploiement.
  Identifier l'artefact qualifié, vérifier la promotion et prévoir le retour arrière.
