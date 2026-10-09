# Connexion par courriel et fermeture personnelle commune

Candidat non activé. La qualification porte sur Keycloak **26.7.3** réel et
des identités synthétiques ; tout changement de cette version exige de
recompiler et requalifier l'extension `services/keycloak-mrjam`.

## Connexion

La méthode courriel est une alternative native au mot de passe. Un jeton
d'action signé par Keycloak est lié à son utilisateur vérifié et actif, au
client OIDC, à l'exécution et à la session d'authentification d'origine. Il
expire après dix minutes. Un navigateur étranger ne peut pas le reprendre.
La visite affiche une confirmation ; elle ne termine pas une connexion.
Le POST natif conserve les contrôles de session et passe ensuite par l'OTP
conditionnel. Un scanner de courrier ne peut pas confirmer cette intention.

Le message public est générique pour une adresse inconnue, suspendue ou non
vérifiée. Au plus un envoi est effectué par session ; les limites Nginx et
la protection native contre les tentatives sont conservées. Les comptes de
gestion Vision exigent toujours les AMR **pwd et otp**, de moins de cinq
minutes : email et otp ne remplissent pas cette exigence.

Le thème de connexion emploie OKLCH, avec la teinte commune MrJ.am et les
rôles de palette figés par Style 96fa28ac564b9492768837d4087608e83acc721b.
Vision conserve ses composants ElmUI et sa teinte propre. Les styles tiers
natifs de la console de compte restent ceux de Keycloak.

Le fournisseur SMTP natif est remplacé par `CourrielSecurise`, compilé contre
la même version exacte. Jakarta Mail impose STARTTLS avant AUTH, la chaîne de
certificats et le nom du serveur, TLS 1.2 ou 1.3, sans confiance universelle ni
repli en clair. La configuration d'exploitation accepte seulement Proton 587.
Le relais loopback de qualification et ses certificats synthétiques exigent
une variable absente du service de production. Les tests natifs prouvent le
refus avant AUTH d'un relais sans STARTTLS, d'un certificat non reconnu et d'un
certificat reconnu portant un autre nom ; ils prouvent aussi AUTH dans TLS.
Les erreurs publiques et journaux ne contiennent pas la réponse du relais.

Les tentatives natives sont plafonnées à dix par adresse et par heure, et
250 par jour pour le processus Keycloak. Le compteur en mémoire utilise des
condensats et est perdu au redémarrage ; les protections Nginx restent donc
nécessaires. Ce plafond ne représente ni la limite contractuelle Proton ni
le total des autres files transactionnelles privées.

Le workflow manuel `vision-courriel.yml` installe le seul jeton fourni par
`VISION_PROTON_SMTP_TOKEN` dans un fichier root 0600 hors store. Il refuse
de remplacer une valeur différente. Son option de test envoie à l'expéditeur
lui-même une pièce age sans donnée d'usager. Ce témoin n'est pas un registre
d'effacement. Il reste à vérifier sa réception et son déchiffrement avec la
clé de sauvegarde existante. Le workflow ne démarre aucun service, ne change
pas les MX et n'ouvre aucune inscription.

## Fermeture

Le droit natif account.delete-account ne permet que la fermeture personnelle.
`scripts/identite-fermeture-configurer.py` active cette action et ajoute ce
droit au rôle par défaut, sans modifier les autres actions ni accorder de
gestion d'identité aux administrateurs Vision. À exécuter par Actions après
qualification SMTP, registre externe et services ; aucune activation dans
le premier import. La configuration privée de maintenance est 0600, hors
store et logs. Détruire les identifiants de maintenance temporaires après
l'opération, selon leur procédure native ; ne pas supprimer le compte personnel.

La fermeture demande une réauthentification native et une saisie exacte
FERMER MON COMPTE. L'extension prend le sujet depuis l'utilisateur natif et
l'émetteur depuis son realm. Elle appelle uniquement loopback 3028 avec un
credential systemd ; aucune route Nginx ne publie ce service. Le navigateur
ne choisit ni un autre sujet ni un rôle privilégié.

Le service vision_fermeture ne peut lire aucune fiche, item, titre ou note.
La migration Vision 025 lui donne seulement la liste des identifiants Vision
associés à iss/sub et une fonction d'effacement aveugle idempotente. Le
verrou de configuration partagé empêche toute nouvelle certification ou
admission du sujet dès l'engagement de fermeture. Le dossier d'admission
annule aussi les demandes personnelles encore sans sujet, en consultant
l'adresse vérifiée dans l'IdP privé avant son retrait ; cette adresse ne
figure jamais dans le registre extérieur. Le marqueur minimal de fermeture
empêche une copie ancienne de réadmettre ce sujet.
Le registre persistant contient version, type, iss/sub, date et identifiants
des outils adoptants, actuellement Vision. Même sans espace Vision restant,
l'identité personnelle peut être fermée.

L'intention est synchronisée sur disque, chiffrée par age et placée dans une
file privée avant transmission à la boîte de l'exploitant. L'acceptation
SMTP précède l'effacement SQL et du dossier d'admission ; seule une réponse
200 permet la suppression native immédiate. 202 conserve l'identité et une
intention en attente. Après un délai minimal de deux minutes, le processus
réessaie à chaque passage minute, avec le délai de reprise de la file SMTP,
puis retire l'identité via le client technique privé mrjam-fermeture. Les
effacements SQL et natifs acceptent le rejeu. La séparation des bases impose
une procédure de reprise ; aucune transaction distribuée n'est annoncée.

Les sessions et autorisations de l'outil cessent d'être utilisables dès que
l'association disparaît. Leur nettoyage privé périodique retire les lignes
correspondantes, au plus tard au passage horaire suivant lorsque le service
et la base sont disponibles. Les nouvelles sauvegardes incluent les files
SQLite et registres de fermeture chiffrés.

## Restauration

Récupérer dans Proton les pièces d'effacement postérieures à la copie
complète ; vérifier leur déchiffrement et leur schéma avant toute réouverture.
La seule acceptation par le relais ne prouve pas leur présence en boîte.
Le registre extérieur récent est une précondition d'exploitation.

`scripts/vision-effacements-rejouer.py` accepte les registres historiques
à deux champs, les pièces age version 1 et les fermetures communes version 2.
Une pièce commune exige `--identite-config` privé : un Keycloak restauré sur
loopback 38xxx, distinct du port actif 8085, avec son realm isolé et les
identifiants de maintenance. Les cibles Vision sont exclusivement
vision_restauration_*. Les sujets sont retirés via l'API native, puis les
contenus Vision sont effacés avant accès public. Aucune redirection ou proxy
HTTP n'est autorisé pour cet appel privé. Un schéma inconnu bloque le rejeu.

La qualification `tests/vision-restauration.py --vision SOURCE --identite-port
38085` réalise dump/restauration PostgreSQL 17, chiffrement/déchiffrement age,
effacement de contenus et d'une identité native importée, puis second rejeu.
Ce parcours combiné utilise Keycloak H2. Un contrôle complémentaire
`tests/keycloak-postgresql-restauration.py` réalise réellement le dump natif
Keycloak sur PostgreSQL 17, age, restauration, connexion avec le mot de passe
et l'OTP restaurés, puis double retrait du sujet dans la seule copie isolée.
Le sujet original reste présent. Cette qualification synthétique emploie
JDBC TCP loopback ; JDBC Unix, les données réelles et la récupération physique
du disque Linux restent des contrôles de staging.

## Preuves et limites d'activation

Les tests natifs couvrent le mot de passe et l'OTP, récupération sans retrait
de l'OTP, lien magique, PKCE/état/nonce, AMR courriel, mauvais navigateur,
rejeu, confirmation, fermeture avec MFA, erreur du hook conservant l'identité,
suppression native après réponse 200 et configuration idempotente préservant
les actions natives. Les tests SQL refusent les lectures de contenu et
vérifient l'émetteur exact ; le registre joint est chiffré réellement avec age.

L'audit Actions **37858455559**, commit
9fda3ad29ed2312311c84684c441a8490351517e, du 8 octobre 2026 est réussi :
25 contrôles HTTP, Vision active 2.6.1 et génération système conservée.
Il n'active aucun nouveau service. SMTP Proton réel, contrats applicables,
clé privée de restauration, réception du registre, migration du propriétaire,
retour des ACL et compilation sur Nixpkgs installé restent requis.
