# Publication coordonnée du 22 septembre 2026

L'audit réel `35712882397` constate l'absence du domaine Logique dans Nginx,
de son certificat et de sa publication. Le serveur par défaut renvoie alors
vers Matheval. Le domaine contractuel est `logique.echos.systems`.

Le correctif ajoute les phases ACME puis HTTPS, refuse les hôtes inconnus
et récupère les anciennes adresses `/matheval` sur le domaine Logique vers
`/?accueil=1`, distinct de la racine susceptible d'avoir été mise en cache.

Les deux archives conservées dans `vendor/candidats` sont les artefacts exacts
de CI, avec les fontes originales. `operations/corrections-artefacts.json`
lie les trois consommateurs à la même révision de style et à leurs CI.
Le contrôleur exige l'inventaire complet, toutes les empreintes, les révisions
et la validation typographique. Le manifeste archivé reste celui du test ;
les attestations d'hébergement et de publication sont ajoutées au seul manifeste
servi lors de la bascule, après construction et contrôle du serveur.

Le workflow `corrections-sites.yml` exige une CI d'infrastructure réussie sur
la révision exacte. Une demande `preparer` construit les deux générations
avec le Nixpkgs installé, compare les invariants, conserve les sources et les
sauvegardes chiffrées, vérifie Nginx et le déclenchement indépendant du retour.
Elle ne change aucun lien actif. Les simulations d'activation sont conservées.

Une demande distincte `activer`, sur la même révision préparée, arme un retour
autonome de vingt minutes. Après ACME, le vrai certificat permet de tester
la configuration HTTPS. Les liens de Logique et de l'interface Vision sont
changés, puis les contrôles publics comparent chaque fichier servi à l'artefact.
Les sites précédents, les six services, les sauvegardes, une nouvelle connexion
du runner et l'authentification Vision réelle sont vérifiés avant enregistrement
de la génération de démarrage. Les captures de Vision montrent la connexion vide.

Un échec rétablit la génération précédente et l'ancien lien Vision ; seul le
lien Logique de cette tentative est retiré. Les versions et certificats sont
conservés. Aucun retour ne restaure une base ni n'efface des réponses.

Matheval utilise ensuite son propre workflow de publication, avec sa migration
additive de sessions et son retour applicatif. Les preuves de publication
effective doivent être consignées dans `ETAT.md` et le registre commun :
ce document décrit la procédure et ne déclare pas encore une bascule réussie.
