# Essai abandonné, pas qualification réussie

PostgreSQL17/pgvector verrouillé, conteneur synthétique sans réseau.
Module Nix exact c5c4a43 et script réellement construits ; SIGHUP reçu.
Résultat : hba_file et ident_file ont un contexte postmaster. Les nouveaux
chemins Nix ne s’appliquent pas sans restart. PID et données restaient inchangés,
mais nouveaux chemins non appliqués : test en échec, aucun déploiement de ce module.
Sources de l’essai conservées exactement avec suffixe archive, hors graphe actif.
Précondition retenue : restart borné PG et Keycloak, versions et données préservées.
