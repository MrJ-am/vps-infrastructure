# Intégrer une révision de composant

Le périmètre de la mission est fermé : les six dépôts du manifeste. L'ajout d'un
projet ou d'une dépendance tierce directe exige une autorisation explicite distincte.

Publier d'abord le commit de bibliothèque, puis mettre à jour sa révision centrale.
Déclarer interfaces, dépendances ASDF et entrées des tests. Le chargement ne démarre
ni connexion, migration ou daemon. Une bibliothèque ne reçoit pas automatiquement
un port, processus ou compte Unix. Les rôles SQL servent des capacités vérifiées,
non une frontière entre packages Lisp.

Qualifier les tests concernés, l'intégration et la sécurité, construire un artefact
propre puis promouvoir celui-ci. Pour une publication : état réel, sauvegarde
restaurable, retour ciblé, sondes après activation et redémarrage. Les ressources
statiques sont construites/publées centralement sans backend artificiel.

[Contrat applicable](../coordination/CONTRATS.org), [reprise](../assemblage/REPRISE.md).
