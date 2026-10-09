# Admission commune et droits Vision

Candidat fermé par défaut. `modules/admission.nix` ajoute le service privé
`mrjam-admission` sur loopback 3027, uniquement lorsque l'identité commune,
les courriels et le mode multi-utilisateur sont activés explicitement.
L'inscription native de Keycloak reste toujours interdite.

Le formulaire Vision transmet l'invitation, la version de notice, le courriel,
le pays de résidence et une tranche d'âge déclarée : moins de quinze ans,
quinze à dix-sept ans, ou majeur. Le pseudonyme est facultatif. Ni date de
naissance, ni nom légal, ni copie de pièce d'identité ne sont demandés.
Le profil Keycloak minimal, versionné dans `operations/identite/profil.json`,
ne réclame que l'identifiant et le courriel. Son import est qualifié sur le
fournisseur réel 26.7.3.

## Vérifications avant admission

La migration Vision 024 réserve une place pendant sept jours, sous le verrou
commun des invitations. Les demandes en attente sont comptées dans le maximum,
sans être présentées comme des inscriptions acquises. Une baisse du maximum
ne peut retirer une place déjà réservée. Révocation, expiration, fermeture et
changement de notice sont recontrôlés lors de la finalisation. Les quotas
effectifs sont ceux du lien au moment de l'activation.

Chaque adresse doit être confirmée par un secret aléatoire de 256 bits,
valable quarante-huit heures. Seul son SHA-256 demeure dans le dossier de
demande ; le courrier de la file contient nécessairement le lien. Le fragment
est transmis par POST et ne figure pas dans les journaux HTTP. Consulter la
page ou l'aperçu ne consomme pas le lien ; une confirmation explicite est
nécessaire. Le lien ne fournit jamais une session de connexion.

En France avant quinze ans, une adresse distincte de représentant légal est
obligatoire. Sa confirmation expire avec la réservation, au bout de sept
jours. Le courrier décrit le service, les accès techniques potentiels, les
assistants choisis par l'usager, le contact RGPD et le retrait de l'accord.
La confirmation seule ne prouve pas l'autorité parentale. Elle est suivie
d'une vérification manuelle proportionnée, avec référence minimale, méthode
et date. Le représentant peut contacter le responsable avec la référence
de demande ; aucune pièce d'identité n'est sollicitée spontanément.

Toutes les demandes de mineurs restent en contrôle manuel au lancement,
y compris de quinze à dix-sept ans pour vérifier la capacité et les règles
de la relation de service. Toutes les demandes hors de France restent aussi
en contrôle manuel. L'exploitant doit examiner une source officielle du pays
et les exigences effectives, notamment parentales, avant de les approuver.
La tranche d'âge est déclarative ; ce dispositif ne garantit pas à lui seul
une vérification juridique suffisante dans tous les pays. Le seuil français
n'est ni une règle mondiale ni une base juridique unique.

## Séparation des pouvoirs

Le rôle SQL `vision_admission` ne lit aucune table pédagogique. Il ne peut
qu'effectuer les réservations, certifier les identités après contrôle,
finaliser leur admission, annuler une réservation et retrouver la seule
métadonnée de rattachement nécessaire à une reprise. `vision_identite`,
le navigateur et `vision_administration` ne peuvent certifier une admission
ni appeler directement l'ancienne allocation contournant cette preuve.
Les requêtes HTTP acceptent une liste fixe de champs, jamais un sujet OIDC,
un rôle ou une permission choisis par le client.

Le client privé Keycloak `mrjam-admission` dispose des rôles `manage-users`
et `view-users`, nécessaires à la création et à l'envoi natif du choix de
mot de passe. Ces rôles sont puissants : leur secret est un credential privé
du service système, absent du navigateur, du store et des dépôts. Ce processus
fait partie de l'exploitation technique privilégiée, pas de l'administration
Vision. Une adresse historique non vérifiée ou une identité suspendue n'est
jamais réinitialisée ou reprise par le formulaire.

Pour une identité commune existante dont le courriel est vérifié, le contrôle
de cette adresse permet d'ouvrir le nouveau droit Vision ; il ne récupère
aucun ancien compte pédagogique et ne donne pas de session. La connexion
conserve les identifiants habituels et le second facteur éventuel. Une nouvelle
identité est créée désactivée, avec un nom technique lié à la demande. Le
rattachement SQL doit réussir avant son activation et avant le courrier natif
de choix de mot de passe. La saga reprend après erreur, sans créer une seconde
identité. Une réservation révoquée entre deux services peut laisser une
identité désactivée : elle n'obtient aucun accès et est retirée à expiration.

## Contrôle par l'exploitant

Les seules routes HTTP sont demande, aperçu et confirmation. Il n'existe
aucune route publique d'approbation, d'envoi arbitraire ou d'administration IdP.
Les opérations manuelles utilisent le programme du service depuis une action
d'exploitation fixant sa révision et ses credentials. `--lister` affiche les
références, pays, tranches et états ; aucun courriel ou justificatif dans les
journaux Actions. `--approuver UUID --methode entretien|verification_relation|controle_pays
--reference REFERENCE_MINIMALE --source-pays URL_OFFICIELLE` exige les confirmations
préalables. `controle_pays` ne remplace pas le contrôle de la qualité parentale.
Cette commande enregistre une décision humaine ; elle ne vérifie pas elle-même
qu'une page Web est une source officielle ni que l'analyse locale est correcte.

Les limites initiales de protection sont cinquante demandes par jour, trois
par adresse et trois par adresse parentale, avec limites Nginx par IP.
Les liens d'invitation restent la condition d'entrée. Les demandes expirées
sont purgées après trente jours. Les adresses et pseudonymes de la demande
aboutie sont retirés après trente jours ; la preuve minimale de l'admission
reste pendant la relation de service. L'identité commune conserve son propre
courriel. Les payloads acceptés de courrier sont purgés après trente jours.
Les dossiers et files SQLite privés sont inclus dans la sauvegarde chiffrée.

## Qualification

- Dix tests du service : accord mail insuffisant, contrôle manuel, pays/âge,
  preuve à usage unique, absence de création sans réservation, identité existante
  sans changement de mot de passe, compte non vérifié refusé et reprise inactive.
- Vrais rôles PostgreSQL : activation directe refusée, certificat non modifiable
  par le rôle applicatif, réservation sérialisée, identité non substituable,
  consommation unique et administration exclue des contenus.
- Chromium 320 et 1440 pixels : formulaire, réponse visible, confirmation
  parentale explicite et affichage de la nécessité du contrôle manuel.
- Keycloak réel : client de provisionnement privé, création désactivée,
  activation explicite, courrier natif et profil sans nom légal.

Ces tests n'attestent ni un envoi Proton réel, ni une décision juridique pour
tous les pays, ni l'activation du service sur le VPS. Les parcours de connexion
par lien magique et de fermeture globale sont qualifiés séparément.
