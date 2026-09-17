# Raccorder un projet sans modifier les précédents

Chaque projet reçoit un domaine ou sous-domaine propre et un port local
réservé. Le registre actuel réserve `principiipetit.io`,
`www.principiipetit.io` et `127.0.0.1:3000` à Matheval. Le préfixe existant
`/matheval` est conservé ; les nouveaux projets peuvent utiliser la racine
de leur propre domaine, avec `prefix` vide.

`examples/project.json` fournit une entrée à adapter puis à fusionner dans le
registre, après réservation réelle du domaine et du port. Ce fichier n'est
pas importé par Nginx ; il ne crée aucun domaine ni aucun service à lui seul.

Le registre simple de cette première version attribue un **nom d'hôte entier**
à chaque projet. Un partage futur du même domaine entre plusieurs projets par
préfixes demandera une extension explicite avec contrôle des chevauchements ;
il ne faut pas attribuer deux fois le même domaine.

1. Le projet fournit son contrat : domaine demandé, port local, préfixe,
   origine publique, route GET de santé, limites de requêtes, éventuel besoin
   de WebSocket et fichiers publics stables à vérifier.
2. L'infrastructure réserve domaine et port dans `projects.json`. Elle relit
   et intègre le module du service à un commit précis. Copier un module dans
   `vendor/` et enregistrer sa provenance/SHA-256 ; jamais un import de la
   branche `master` distante actualisé à chaque reconstruction.
3. Démarrer et tester le backend sur `127.0.0.1`, avec son compte système,
   ses dossiers, ses secrets et son compte de publication. Accorder à ce
   dernier uniquement les opérations nécessaires à son application.
   Définir des limites de ressources adaptées au service avant de l'exposer.
4. Vérifier le DNS et préparer le certificat du nouveau domaine. Les
   certificats absents nécessitent une étape ACME préalable adaptée au
   serveur réel ; une erreur d'émission ne doit pas retirer les certificats
   ou les vhosts existants. Ne pas simplement accepter un `nginx -t` en échec
   au motif qu'un certificat sera créé plus tard.
5. Conserver le registre actuellement installé, capturer ses contrôles HTTP,
   construire le nouveau système et relire son activation prévue. Le candidat
   ne doit pas redémarrer des applications sans rapport avec l'ajout.
6. Tester la configuration Nginx candidate avec ses certificats, armer le
   retour arrière et activer temporairement. Vérifier ensuite **tous** les
   projets avec le nouveau registre et le relevé précédent.
7. Enregistrer la génération, puis mettre à jour l'état et les contrats.

Les déploiements applicatifs restent indépendants après ce raccordement :
publier le projet A ne reconstruit pas Nginx et ne redémarre pas le projet B.
Les demandes de changement de routage passent par une modification de ce dépôt.

Le module Matheval active actuellement PostgreSQL 17, impose le socket Unix
et déclare les sauvegardes locales. Avant de partager PostgreSQL avec un second
projet, l'infrastructure devra arbitrer les paramètres globaux, conserver
des bases et rôles distincts, et vérifier les sauvegardes de chaque base.
Ne pas confondre des comptes applicatifs séparés avec une isolation complète
du processeur, de la mémoire ou du disque sur un VPS unique.

Le générateur reprend seulement les en-têtes du proxy existant. Un besoin
de WebSocket, de streaming, d'upload important ou de socket Unix fait l'objet
d'une extension revue, avec des contrôles adaptés, avant publication.
