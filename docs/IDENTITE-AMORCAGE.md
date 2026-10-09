# Amorçage réservé de l'identité

Le compte commun initial et son MFA doivent exister avant la bascule Vision.
Le workflow `vision-identite-amorcage-preparer.yml` construit une génération
distincte à partir de `/etc/nixos/configuration.nix` réellement active. Il
ne l'active pas, n'enregistre aucune génération par défaut, ne crée aucune
personne et ne modifie aucun schéma, rôle, HBA ou contenu de production.

## Périmètre fermé

`identite-amorcage.nix` ajoute un cluster PostgreSQL17 indépendant : données
dans `/var/lib/mrjam-amorcage-postgresql`, socket
`/run/mrjam-amorcage-postgresql`, sans TCP. Les données restent 0700 sous
postgres ; le socket traversable utilise peer. Le rôle keycloak est LOGIN,
sans mot de passe, SUPERUSER, CREATEDB, CREATEROLE, REPLICATION, BYPASSRLS,
INHERIT ni appartenance. La relance refuse un rôle devenu privilégié et ne
réinitialise pas les données. Un autre UID Unix est refusé.
Les lanceurs exigent les chemins fixes de cette phase ; le socket de production
est refusé avant toute commande. Le lanceur d'identité refuse aussi UID0.

`mrjam-amorcage-identite` utilise le même paquet optimisé 26.7.3 réellement
qualifié. Son lanceur configure le socket privé et l'issuer `https://log.mrj.am`,
avec DynamicUser keycloak, credentials systemd et runtime 0700. Il importe
le realm privé fermé à l'inscription native, avec trois comptes de service
techniques et aucune personne. Aucun accès aux données Vision n'est accordé.
Mode commun ordinaire, admission et `preconditionsValidees` restent désactivés.

Le secret de l'administrateur technique temporaire est un credential séparé
root0600 hors Git/store, à provisionner dans la future opération d'activation.
Il n'apparaît ni dans une unité ni dans les rapports. L'import et les cinq
secrets existants sont conservés sans rotation. La personne choisira son mot
de passe ; une invitation ne peut attribuer les droits du premier administrateur.

Le domaine supplémentaire aura ACME/HTTPS : routes du realm, ressources et
offre AGPL seulement ; console/API master/admin et métriques restent 404.
L'enregistrement public de clients OIDC est également 404 ; port et préfixe
transmis au backend sont fixés par Nginx plutôt que repris du client.
Les accès et erreurs Nginx de ce seul domaine sont désactivés pour éviter
les liens d'action dans les logs. Les valeurs définies des anciens hôtes
Nginx, les unités essentielles, PostgreSQL de production et les ports du
pare-feu sont comparés à la base et doivent rester identiques.

Une copie locale quotidienne du seul cluster d'identité est chiffrée avec
le destinataire age déjà configuré et conservée trente jours. Elle ne prouve
ni possession de la clé privée ni copie extérieure ; ces conditions restent
nécessaires avant l'ouverture à d'autres personnes.

## Préparation et preuves

Le driver root exige main, CI exacte, vps-production, exclusion VPS et preuves
privées des composants, Unix et import. Générations active et par défaut,
release, Nixpkgs et fournisseur immuable sont contrôlés avant/après. Aucun
secret n'est lu par Nix ; les imports sont vérifiés par Python sans rotation
ni SMTP. Un job, deux cœurs et une racine GC sont utilisés pour construire.

L'inventaire lit seulement les identifiants utilisateur des tables personnelles,
dans une transaction REPEATABLE READ READ ONLY. Leur unicité doit correspondre
exactement à l'unique compte actif d'authentification. Les hashes ne sont ni
conservés ni publiés. Un second propriétaire, profil vide, identifiant inconnu,
compte discordant ou fichier non conforme provoque un refus. L'identifiant reste
uniquement dans le dossier root0700 ; Actions reçoit nombres et booléens.
Ce relevé n'associe encore aucune identité OIDC.

Le rapport contient les révisions, générations, paquet, comparaisons et compteurs.
Aucun nom de compte, email, hash, secret, titre, note ou contenu. Diagnostics
et relevés restent privés. Six services, nouvelle SSH et 25 HTTP/TLS sont
contrôlés même après échec. Le relevé d'association préparatoire sera retiré
à la clôture de la migration, après conservation d'une preuve sans identité.

Les tests couvrent les refus de rattachement, permissions/liens et preuves
divergentes. La CI évalue la génération séparée et construit ses unités.
Une qualification native sans réseau utilise les vrais lanceurs et le paquet :
cluster privé UTF-8/peer, relance, rôle privilégié refusé, issuer canonique,
import sans personne, SPI et SMTP TLS configuré sans envoi. Elle ne prouve
ni systemd, ACME, SMTP ou activation réels de cette nouvelle phase.

## Étapes suivantes

La construction réelle `37941066602` est réussie ; le rapport exact et
le nouvel essai avec retour autonome sont détaillés dans
[IDENTITE-AMORCAGE-ESSAI.md](IDENTITE-AMORCAGE-ESSAI.md). L'essai reste à lancer.

1. Constater la construction réelle, puis préparer l'activation temporaire :
   DNS/ACME, copie locale et retour autonome armé avant essai. Les anciens
   workflows de migration et leurs garde-fous ne sont pas réutilisés.
2. Créer par Actions le seul compte initial à l'adresse privée retenue ;
   envoyer l'enrôlement, vérifier email, choix du mot de passe et OTP, puis
   contrôler le sujet stable et les événements réussis sans les publier.
3. Révoquer les sessions et retirer l'administrateur technique temporaire
   et son credential dans une opération contrôlée. Conserver les clés et
   le sujet ; tester la restauration privée pour le transfert.
4. Associer explicitement (iss, sub) à l'ancien identifiant après une nouvelle
   vérification transactionnelle ; promouvoir le premier administrateur par
   l'exploitation. Préserver données et accès MCP non révoqués.
5. Préparer génération complète et retour SQL/NixOS ; contrôler avec les
   inscriptions fermées. Compléter sous-traitance, mineurs, clé age et copie
   extérieure avant toute admission tierce. Conserver aussi le refus public
   d'enregistrement de clients et les en-têtes de proxy fixés dans ce mode.
