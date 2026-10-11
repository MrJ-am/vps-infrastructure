# Reprise — mission du 11 octobre 2026

État : inventaire réel terminé ; collecte et administration Matheval portées et
qualifiées localement ; auxiliaires Vision portés et qualifiés sur fixtures ;
production inchangée, assemblage complet non qualifié.

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

Restent à réaliser avant le jalon 1 : qualification de chiffrement age/restauration, configuration du cycle de vie
commun et listener/routage central avec rôles SQL en production, compilation propre Nix,
transfert complet CI/frontends/sauvegardes puis retrait satellites, qualification
multi-comptes Vision/OIDC/MCP, restauration isolée, bascule réelle et redémarrage.
Ne pas déclencher Kanidm avant ces preuves de production.

Demandes historiques pertinentes : données/corpus, invitations/consentement,
récupération chiffrée, MCP minimisé, interfaces réellement servies, sauvegardes.
Anciens essais/publications satellites/acquittements remplacés par la mission ;
faits conservés dans l'archive exacte. Copies mensuelles Linux et clé personnelle
mentionnées dans ETAT.md restent personnelles, sans blocage technique artificiel.

Dernière preuve CI : 38104435924 sur cd90f2a, quatre jobs infrastructure réussis,
dont évaluation Nix du module commun (paquet factice, pas un binaire qualifié).
38104435933 : cadre réussi, arrêt avant checkout privé (COMPONENTS_READ_TOKEN absent).
Qualification locale : 40 parcours, reconstruction propre sans cache 39 FASL,
HTTP AF_UNIX réel et redémarrage SQL. Sources nouvelles : Vision aa7f10d ;
Matheval 2a82250. Le manifeste porte les SHA
complets ; la révision infrastructure est celle du commit qui le contient.

Auxiliaires ASDF locaux : administration/cycle/admission/fermeture, file courriel
durable et client provisoire Keycloak ; 644+141 cas différentiels, isolation
PostgreSQL, ancien SQLite/MIME et SMTP STARTTLS qualifiés. IdP synthétique uniquement.
Dernier binaire local propre : 39 FASL, 40 parcours Matheval, redémarrage SQL réussi.
Le même artefact exerce API/MCP Vision et 40 parcours Alice/Bob concurrents,
avec PostgreSQL 17 et rôles réels ; entrée d'identité synthétique, pas preuve OIDC.

Frontends : `scripts/outiller.py`, puis `scripts/frontends.py preparer/construire/qualifier`.
Trois anciennes révisions de style déclarées dans le manifeste pour préserver le
rendu. Caches exacts issus du même dépôt, aucun fetch implicite, fontes Signature
contrôlées. Générateurs dans des worktrees temporaires ; candidats privés sous
`state/frontends-candidats`, métadonnées adjacentes. Vision/Matheval/Logique/style
construits localement. Qualifications de cette tranche en cours ; transfert CI
complet et retrait des YAML satellites restent à achever. Nouveaux profils Python
3.12/Linux/x86_64 : navigateur, logo, Signature ; transitives verrouillées par SHA.

Sauvegarde/restauration réelle réussie : workflow central `monolithe-reference.yml`,
run 38105867103 sur eff80b8, `operation=sauvegarde-restauration`. Copie chiffrée des
trois bases et états SQLite/JSONL ; restauration PostgreSQL dans un cluster Unix
privé, sans arrêt ni écriture SQL de production. La clé éphémère a été enveloppée
pour le destinataire personnel existant puis détruite. 30/6/100 tables restaurées,
empreintes identiques ; `sauvegarde-transition.json`. ACL/rôles et qualification
du retour applicatif restent à réaliser. Avant une bascule : vérifier actualité
du snapshot, registre d'effacements récent et préconditions, pas restaurer une
ancienne base pour revenir sur du code.
