# Construction des composants MrJ.am

La construction réelle [37930689913](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37930689913),
opérateur `296e4d159544f01af1345ea844871d11f17897f7`, réussit le 9 octobre
à 12:33 UTC : sept unités, six imports sans privilèges et sources AGPL ;
garde fermé, socle inchangé, six services/nouvelle SSH et 25 HTTP/TLS.
[Rapport technique](../operations/vision-mrjam-composants-qualification.json).

Le workflow manuel `vision-mrjam-composants-construire.yml` construit à côté
du système actif les unités Keycloak, mrj-auth, administration Vision, cycle,
admission, fermeture et courriels, ainsi que leurs dépendances et sources AGPL.
Il n'active aucune génération et ne lance aucun service candidat.

`scripts/vision-mrjam-composants.nix` active les options dans sa seule évaluation,
en gardant **preconditionsValidees=false** et les inscriptions fermées. Il exige
que l'unique assertion en échec soit celle de l'identité et vérifie réellement
que `system.build.toplevel` reste impossible à évaluer. Le lot est un ensemble
de liens vers les unités et dépendances dans le store, sans
`switch-to-configuration`. Ce n'est pas une génération NixOS complète ni une
qualification du routage, des certificats ou du retour autonome.

Le driver root exige la CI du commit exact, les preuves privées de construction
Keycloak, qualification Unix et import initial, les mêmes candidats, le Nixpkgs
installé, la génération et la release actives. La source du fournisseur local
est épinglée à son chemin immuable relevé. L'import privé existant et ses secrets
sont revérifiés par Python, hors de l'évaluation Nix et sans rotation. Nix reçoit
uniquement les chemins de credentials configurés dans les unités.

La construction utilise un seul job et deux cœurs, conserve une racine GC dans
le dossier root de l'opération, puis vérifie les sept unités, leurs exécutables,
le paquet Keycloak déjà qualifié et l'archive AGPL. Les six processus d'import
Python utilisent les interpréteurs réellement déclarés par les unités et un
utilisateur sans privilèges (`nobody` depuis root). Leur environnement est vidé,
les points d'entrée de serveur ne sont pas exécutés et les appels Python de
connexion/bind socket, SQLite et sous-processus sont refusés pendant les imports.
Le mode OIDC est importé explicitement en plus du serveur historique.

Cette vérification des imports ne remplace pas les tests fonctionnels des
services ni l'isolation réseau systemd de la qualification Keycloak. Elle permet
de détecter une dépendance manquante dans les paquets avant la bascule.

Les journaux restent root privés ; le rapport Actions ne contient que versions,
chemins store, révisions et booléens. Les six services, une nouvelle connexion
SSH et les 25 sondes HTTP/TLS sont contrôlés même après échec, avec vérification
du socle. Aucun secret, donnée pédagogique, SQL de production, envoi SMTP,
DNS/ACME ou création d'identité humaine.

La CI construit aussi le lot sur son Nixpkgs de qualification et teste les
imports. La construction locale du 9 octobre sur le Nixpkgs installé `c5c4a43`
réussit avec des utilisateurs `nixbld` sans privilèges et les six imports sous
`nobody`. La preuve VPS distincte est consignée ci-dessus. L'identité du
propriétaire/MFA, l'association historique, la génération complète et son
retour restent à préparer avant activation. La [phase d'amorçage](IDENTITE-AMORCAGE.md)
prépare ce compte sans changer Vision ni lever le garde du mode commun.
