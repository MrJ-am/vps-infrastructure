# Reprise — mission du 11 octobre 2026

État : inventaire réel terminé ; collecte et administration Matheval portées et
qualifiées localement ; production inchangée, assemblage complet non qualifié.

1. Constater sources et VPS, dépendances/données/mesures ; commandes et bibliothèques.
2. Porter Matheval et auxiliaires, qualifier HTTP/MCP/isolation/concurrence.
   Transférer les fonctions des workflows avant leur retrait.
3. Sauvegarder/restaurer en isolation, construire proprement, promouvoir, vérifier
   invariants/redémarrage. Consigner le jalon réel de production étape 1.
4. Après ce jalon : qualifier/basculer Kanidm ; nouvelle identité associée
   explicitement au propriétaire métier. Retirer Keycloak après accès sûr.

Critères : mission utilisateur, dont aucun Node métier Matheval, une image métier,
aucune CI satellite, données préservées, retour utilisable. Kanidm inclut OIDC/MCP
réels et accès personnel ; ne pas inventer l'enrôlement.

OpenSSL existant réutilisé via SB-ALIEN ; aucune dépendance Ironclad ajoutée.
Blocage extérieur constaté : le GITHUB_TOKEN du runner infrastructure ne lit pas
Vision privé (run 38098700592, checkout code 128). Le credential de la session lit
les sources mais l'API des secrets est interdite (403). Secret Actions
`COMPONENTS_READ_TOKEN`, lecture contenu limitée à Vision et Signature, demandé
au propriétaire ; ne jamais fournir sa valeur en conversation.
Permissions GitHub constatées : sources lecture/écriture, lancement Actions.
APIs protections de branche, secrets et deploy keys : 403. Leur inspection/nettoyage
distant ne sont pas acquis ; ce refus ne bloque pas les travaux indépendants.

Restent à réaliser avant le jalon 1 : cycle de vie et auxiliaires métier dans
l'image commune, listener/routage central et rôles SQL, compilation propre Nix,
transfert complet CI/frontends/sauvegardes puis retrait satellites, qualification
multi-comptes Vision/OIDC/MCP, restauration isolée, bascule réelle et redémarrage.
Ne pas déclencher Kanidm avant ces preuves de production.

Demandes historiques pertinentes : données/corpus, invitations/consentement,
récupération chiffrée, MCP minimisé, interfaces réellement servies, sauvegardes.
Anciens essais/publications satellites/acquittements remplacés par la mission ;
faits conservés dans l'archive exacte. Copies mensuelles Linux et clé personnelle
mentionnées dans ETAT.md restent personnelles, sans blocage technique artificiel.
