# PostgreSQL : transition vers l'assemblage central

PostgreSQL 17, ses bases, chemins, sauvegardes et moteur pgvector sont conservés.
Le monolithe n'impose aucune fusion physique des bases. Les bibliothèques ne
possèdent pas de rôle superutilisateur et le rôle applicatif ne possède pas les
tables privées. Les rôles de migration et d'exploitation restent distincts.

La production au début de la mission utilise encore les associations peer et
rôles décrits dans l'archive [du contrat antérieur](../coordination/historique/POSTGRESQL.md.avant-assemblage).
Cette archive décrit les contraintes de l'ancienne architecture ; elle n'impose
plus un compte Unix et processus par bibliothèque. Toute adaptation des HBA/ACL
est explicite, testée en isolation et munie d'un retour ciblé sans restauration
de données récentes. Aucune ACL n'est modifiée par le présent premier lot.

L'identité est vérifiée avant d'établir un contexte transactionnel. SET LOCAL
vision.utilisateur ne prouve pas l'authentification face à du SQL arbitraire.
Contraintes, politiques RLS et propriétaires doivent être constatés ; les tables
privées et données dérivées sont classées. Tester Alice/Bob, liens croisés,
recherche avant candidats, connexions réutilisées, suspension et révocation.

[Contrat de sécurité](../assemblage/SECURITE.md), [reprise](../assemblage/REPRISE.md).
