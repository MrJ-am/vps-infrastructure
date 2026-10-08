# Courriels et cycle de vie — candidat

Aucun envoi Proton réel ni activation n'est attesté ici. Les parcours natifs
de récupération sont qualifiés sur Keycloak 26.7.3 et un relais synthétique.
Le mot de passe oublié conserve l'OTP ; le lien expire sous dix minutes,
ne se rejoue pas et impose une nouvelle connexion après changement.

`scripts/identite-preparer.py --smtp-prive CHEMIN` injecte la configuration
Proton dans l'import initial privé, hors Git et hors store. Le fichier contient
host, port, username, password, from_address, starttls_required et
certificate_verification. Les seules valeurs acceptées pour le transport sont
`smtp.protonmail.ch:587`, STARTTLS et vérification du certificat. Le nom SMTP
correspond à l'adresse active de l'expéditeur. Ne pas afficher le JSON ni son
jeton dans Actions. Un realm déjà importé exige une mise à jour API locale
contrôlée ; l'import ne le modifie pas.

La file SQLite privée stocke les messages, un Message-ID stable, l'état,
les reprises et l'accusé du relais. Une panne après DATA peut produire un
doublon ; ne pas promettre exactement un envoi. Les corps, adresses et pièces
locales sont purgés après trente jours pour les messages acceptés ou annulés.
Un échec conserve le message en attente et sa raison technique générique,
sans copier la réponse SMTP potentiellement sensible dans les logs.

`vision-cycle` dispose d'un rôle SQL sans accès aux contenus et d'un client
Keycloak limité à `view-users`. Le test réel prouve le refus de réinitialiser
un mot de passe avec ce client. Les administrateurs Vision ne reçoivent ni
ce secret ni ces permissions. L'identité du destinataire du préavis vient du
couple signé émetteur/sujet ; le navigateur ne fournit aucune adresse d'envoi.

Une demande administrative crée un préavis sans échéance. L'acceptation SMTP
fixe l'envoi et une échéance SQL trente jours plus tard. L'annulation est
sérialisée avec l'engagement de l'effacement ; un préavis annulé ou prématuré
ne crée jamais d'intention d'effacement. Pendant le délai, le compte reste
actif pour la lecture et l'export. L'annulation d'un préavis déjà envoyé produit
un courriel distinct. Une notification déjà en transit peut encore arriver.

L'effacement autonome passe par une route Nginx exacte, session, origine et CSRF,
vers le processus privé. Il consigne et synchronise une intention minimale,
chiffre sa copie avec age et la soumet à la boîte privée de l'exploitant avant
la suppression SQL. Si le relais n'accepte pas la copie, la réponse est 202
et explique l'attente ; une reprise automatique conserve l'intention.
L'acceptation SMTP ne prouve pas la réception en boîte. La récupération du
registre chiffré hors machine reste à qualifier avant l'ouverture.

Activer explicitement `infrastructure.courriel.enable` et
`infrastructure.visionCycle.enable` après provisioning et tests. Les fichiers
privés de cycle contiennent seulement `adresse_exploitant` et `recipient_age` ;
ils sont chargés par credentials systemd. Les adresses privées d'exploitation
ne figurent pas dans les exemples publics.

Les sauvegardes quotidiennes nouvelles incluent Vision, Keycloak, les sessions,
la file de cycle et les registres disponibles, tous chiffrés. Un manifeste
vérifie les empreintes d'une génération complète. Sur le PC Linux, la commande
`scripts/sauvegarde-externe.py copier` exige un disque monté, une clé privée
et des empreintes conformes ; elle vérifie le déchiffrement et publie la copie
par renommage seulement après réussite. Elle ne remplace ni la restauration
PostgreSQL isolée ni le registre Proton le plus récent. La fréquence mensuelle
et la purge des anciennes copies externes relèvent de la procédure d'exploitation.
