# Code des services MrJ.am

Copyright Jean-Christophe Jameux. Les modifications et services MrJ.am de
cette archive sont proposés sous GNU AGPL version 3 ou ultérieure. Voir LICENSE.
Les composants tiers conservent leurs licences et leurs auteurs respectifs.

Cette archive provient des mêmes sources immuables que les services compilés
dans la génération NixOS. Elle contient les services de connexion, de gestion,
d'admission, de courrier et de fermeture, l'extension native Keycloak, son thème,
les modules de compilation et les modèles d'import sans secrets. Les fichiers
de configuration privés, les identifiants, les données des personnes et le
registre privé de coordination ne sont pas inclus.

Keycloak 26.7.3 est distribué sous Apache-2.0 :
https://github.com/keycloak/keycloak/tree/26.7.3
L'extension Java se compile avec JDK 21 et les bibliothèques de cette version,
par services/keycloak-mrjam/compiler.sh. Aucun protocole cryptographique propre
n'est nécessaire : signatures et flux utilisent les API natives Keycloak.

Les dépendances Python sont psycopg, requests, passlib et Authlib, à prendre
dans le Nixpkgs de la génération. Les versions sont fixées par ce Nixpkgs ;
la préparation ne met pas à jour le canal. La configuration de référence est
NixOS 26.05, PostgreSQL 17 avec pgvector, Nginx et les modules fournis. Remplacer
les chemins de credentials par les vôtres et créer vos propres secrets hors
store. Le modèle d'import ne crée aucun compte personnel et reste fermé.

Le code Vision et ses migrations se téléchargent séparément sur la même
instance. La bibliothèque commune d'interface est publique, sous AGPL-3.0-or-later :
https://github.com/MrJ-am/style-mrjam
Sa révision exacte figure dans interface/style.lock.json de l'archive Vision.
Les marques, logos et fontes d'identité conservent leurs droits réservés.
