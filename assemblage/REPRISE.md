# Reprise — mission du 11 octobre 2026

État : inventaire/cadre central ; production inchangée, candidat non qualifié.

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

En attente : autorisation Ironclad (SHA-256, scrypt, signatures OIDC).
Permissions GitHub constatées : sources lecture/écriture, lancement Actions.
APIs protections de branche, secrets et deploy keys : 403. Leur inspection/nettoyage
distant ne sont pas acquis ; ce refus ne bloque pas les travaux indépendants.

Demandes historiques pertinentes : données/corpus, invitations/consentement,
récupération chiffrée, MCP minimisé, interfaces réellement servies, sauvegardes.
Anciens essais/publications satellites/acquittements remplacés par la mission ;
faits conservés dans l'archive exacte. Copies mensuelles Linux et clé personnelle
mentionnées dans ETAT.md restent personnelles, sans blocage technique artificiel.
