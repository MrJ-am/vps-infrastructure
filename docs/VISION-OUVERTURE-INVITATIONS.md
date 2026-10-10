# Ouverture de Vision exclusivement par invitation

Vérification du 10 octobre 2026. Jean-Christophe Jameux demande explicitement
la vérification des fournisseurs et le déblocage de son invitation. Il confirme
avoir vérifié le fonctionnement de Vision et créé un premier lien dans
l'administration. Ce constat humain complète la bascule réelle 008671e,
Actions38080453548 ; aucun mot de passe, code OTP ou secret de lien n'est collecté.

## Contrats et transferts vérifiés

- [Hostinger : conditions](https://www.hostinger.com/legal/universal-terms-of-service-agreement),
  section 2 : le DPA est incorporé aux conditions. Leur utilisation continue
  est traitée comme acceptation des conditions publiées ; une signature
  indépendante n'est pas exigée par ce texte.
- [Hostinger : DPA](https://www.hostinger.com/legal/dpa), version du 29 septembre 2026 :
  les VPS sont explicitement couverts. Le texte traite confidentialité,
  sécurité partagée, assistance aux droits, notification des incidents,
  sous-traitance ultérieure et transferts ; son annexe 3 énumère les prestataires.
  Les clauses contractuelles types sont prévues pour les transferts concernés.
  Une liste commune à plusieurs produits ne prouve pas leur intervention sur
  notre VPS. Il ne faut pas promettre l'absence de tout accès hors EEE ni le
  chiffrement individuel de nos textes. Le responsable garde la charge de
  configurer et sécuriser son instance.
- [Proton : conditions](https://proton.me/legal/terms), version du 9 octobre 2026,
  section 7 : le DPA s'applique lorsque Proton traite pour son utilisateur
  responsable de traitement des données soumises au RGPD. Cette disposition
  ne réserve pas le DPA à un abonnement Business.
- [Proton : DPA](https://proton.me/legal/dpa), version du 10 février 2026 :
  services et obligations de traitement, confidentialité, droits, incidents,
  audit, sous-traitants et transferts sont encadrés. Le champ vise une activité
  organisée indépendamment de sa forme juridique.
- [Proton SMTP](https://proton.me/support/smtp-submission) : la soumission
  automatisée d'une application est prévue pour les abonnements payants avec
  adresse de domaine personnalisé. Aucun changement d'abonnement n'est requis
  pour l'adresse et le jeton déjà qualifiés sur cette instance.
- [Proton Mail : confidentialité](https://proton.me/mail/privacy-policy),
  version du 14 septembre 2026 : stockage annoncé en Suisse, Allemagne ou Norvège,
  métadonnées SMTP accessibles et sauvegardes limitées à 30 jours. Cela ne
  désigne pas le pays individuel de notre boîte. Les mails SMTP ne sont pas
  chiffrés de bout en bout ; ils ne contiennent pas de fiches ou d'items.
- [Commission : adéquation](https://commission.europa.eu/law/law-topic/data-protection/international-dimension-data-protection/adequacy-decisions_en) :
  la Suisse figure sur la liste actuelle. L'Allemagne est dans l'UE et la
  Norvège dans l'EEE. L'hébergement de Vision reste en Allemagne, déjà vérifié
  pour le VPS. La notice distingue hébergement et messagerie.

Conclusion pour cet usage : les conditions publiques encadrent les traitements
nécessaires ; aucun obstacle contractuel spécifique ni exigence de nouvel achat
n'a été identifié. L'application du DPA résulte des clauses d'incorporation et
de l'usage des services existants ; aucun écran privé d'acceptation, facture ou
confirmation personnalisée des fournisseurs n'est prétendu consulté. Cette
vérification n'est pas une certification générale de conformité de tout usage
futur, et les clauses doivent être revues à un changement de fournisseur,
d'offre, de pays ou de finalité.

## Périmètre opérationnel

La lecture publique réelle de `/auth/configuration` le 10 octobre confirme
OIDC actif, inscriptions fermées, rétention 30 jours, mais coordonnées et version
de notice encore vides. L'ouverture renseigne donc aussi les seules données
publiques déjà confirmées : Jean-Christophe Jameux, RGPD@MrJ.am, Allemagne,
version `vision-20261010`. Elle refuse des coordonnées contradictoires au lieu
de les remplacer silencieusement. La notice compilée existante reste identique,
avec ses mises en garde, droits et informations sur les courriels.
L'ouverture change le drapeau `vision_gestion.configuration.inscriptions_ouvertes`.
L'option Nix historique `inscriptionsOuvertes` ne pilote pas cette table et
ne doit pas être confondue avec le réglage effectif. Aucune reconstruction,
migration, réinitialisation, rotation de clé, modification de quota, création
de compte ou consommation d'invitation n'est effectuée par l'opération.
L'inscription native Keycloak reste désactivée. Le seul chemin autorisé exige
une invitation disponible, sa notice, une adresse vérifiée et les confirmations
nécessaires. Les plafonds, expirations, réservations et quotas existants restent
appliqués atomiquement. Les administrateurs applicatifs ne reçoivent aucun
accès aux contenus ni administration du fournisseur d'identité.

Les adultes résidant en France sont admis après confirmation de leur courrier.
Au lancement, tous les mineurs et les autres pays restent soumis au contrôle
manuel existant. Avant quinze ans en France, le courrier parental doit être
confirmé et la qualité de représentant vérifiée ; un simple clic ne suffit pas.
L'exploitant vérifie par entretien ou relation déjà connue avec l'adulte, en
évitant de conserver une pièce d'identité. Il enregistre seulement la méthode,
une référence minimale, la date et la source officielle de la règle locale.
Il vérifie la nécessité d'autres accords pour le pays et la situation concernés.
En cas de doute, aucune admission n'est approuvée. L'examen manuel passe par
l'exploitation technique, sans conférer ces données à un administrateur Vision.
Les preuves minimales sont conservées pendant la relation de service ; adresses
et pseudonymes du dossier terminé sont purgés après 30 jours, dossiers inachevés
après expiration 7 jours puis 30 jours. Un retrait est reçu à RGPD@MrJ.am, vérifié
proportionnellement et traité avec les mécanismes de fermeture/effacement.

Les nouvelles sauvegardes locales communes sont chiffrées et limitées à 30 jours.
Le téléphone a permis une récupération complète d'une copie extérieure réelle.
Les archives root des opérations précédant cette ouverture concernent le
compte initial et ne deviennent pas une sauvegarde générale des nouveaux
inscrits. Aucun nouveau dump d'usager ni snapshot fournisseur n'est demandé ici.
La copie mensuelle sur disque Linux et la copie indépendante de la clé restent
à réaliser lorsque le PC est accessible, sans abonnement supplémentaire.
L'utilisateur est averti du risque de perte entre copies extérieures et peut
exporter ses propres données. Les textes sensibles identifiants sont déconseillés,
les accès techniques privilégiés possibles sont annoncés, et les droits,
contacts, bases juridiques et durées figurent dans la notice existante.

## Exécution et preuve

L'opération exige la demande dédiée, le main et les quatre jobs de CI du commit
exact. Elle vérifie la génération activée ET enregistrée 008671e, les services,
PostgreSQL 17 sans TCP, le schéma 25, la notice et l'absence de privilèges de
contenu administratif. Elle réserve une invitation réellement disponible dans
une sous-transaction annulée puis vérifie invitations et réservations identiques.
Aucun secret de lien, adresse d'ami ou contenu n'est publié. Après ouverture,
25 HTTP/TLS,22 fichiers exacts, identité et accès anonymes/falsifiés refusés,
puis nouvelle SSH sont vérifiés. Un refus avant finalisation referme seulement
les admissions ; aucune donnée n'est restaurée ou effacée.

## Résultat réel du 10 octobre 2026

La reprise ad8123c/PR97 réussit dans
[Actions38087925818](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38087925818),
job 114318255509, après les quatre jobs de CI exacte 38087565641 et 422 tests.
Les inscriptions sont **ouvertes uniquement par invitation**. La notice est
renseignée et relue par HTTPS depuis le runner puis indépendamment depuis Work.
La réservation d'une invitation réelle est annulée sans changement de place,
quota, version ou réservations. Aucun compte ni courrier créé par le contrôle.
La génération enregistrée reste identique, les services et ACL sont vérifiés,
les 25 HTTP/TLS et22 fichiers exacts/refus publics passent avant/après, ainsi que
la nouvelle SSH et les25 contrôles finaux. Aucun retour de génération ou de base.
[Reçu réel](../operations/vision-inscriptions-ouverture-reelle.json).

Le lien existant peut être réouvert ou sa page actualisée ; une page laissée
ouverte avant cette opération doit recharger sa configuration. Les personnes
mineures et les résidents d'autres pays restent dans l'examen manuel prévu.
La preuve de cette ouverture ne prétend pas qu'un ami a déjà terminé son
inscription, ni qu'un nouveau courrier lui a été effectivement remis.
