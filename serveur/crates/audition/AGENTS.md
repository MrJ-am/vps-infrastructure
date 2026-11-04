# Modèle pur Audition

- Lire `README.org` pour le contrat porté, les sources et les limites.
- Aucun accès production, SQL réel, transport, secret, faux dépôt ou succès persistant simulé.
- Préserver proposition MCP / prescription web, versions de cours/barèmes, adoption explicite et traces anciennes.
- `unsafe` interdit ; erreurs sans production, identifiant personnel ni message libre.
- Depuis `platform/` : `cargo test --locked -p mrjam-audition`, `cargo clippy --locked -p mrjam-audition --all-targets -- -D warnings`, `cargo fmt -p mrjam-audition --check`.
- Tous les jeux de tests sont inventés. Un changement de contrat et sa compatibilité doivent être documentés ; ne pas affaiblir les contrôles pour accepter le candidat.
- Aucun endpoint Audition ne doit être ouvert avant qualification indépendante de l'autorité, du transport et du stockage.
