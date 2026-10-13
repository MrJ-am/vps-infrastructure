# Audition — compte rendu de livraison

État du 13 octobre 2026, horodatages techniques en UTC. La mission ajoute Audition
au serveur commun ; aucune application serveur distincte, dépendance externe,
inférence, facturation de jetons ou modification DNS.

## Réalisation

Bibliothèques ASDF `mrjam-audition/modele`, `/services` et `mrjam-audition` : cours,
activités ouvertes/QCM, attendus, critères/barèmes, affectations/échéances, séances,
tentatives, aides, observations, annotations/rectifications et remédiations. Versions
épinglées et adoption explicite ; propositions MCP non officielles jusqu'à validation
enseignante ; états non observé/en cours/difficulté/réussite aidée/autonome.

PostgreSQL : schéma additif, rôle non propriétaire et sans bypass, RLS, transactions,
verrou de groupe, contrôle des révisions, séance unique, reçus d'idempotence et audit.
Identité Log vérifiée à chaque appel, cloisonnement par groupe/ressource ; pas d'accès
pédagogique implicite pour l'administration. Actions administratives sensibles :
MFA récente du socle, confirmation et audit. Corrigés filtrés côté serveur.

Elm/elm-ui/Animator du socle : landing publique, préparation et suivi enseignant,
matrice par activité/version/attendu, traces et remédiation, travail et reprise élève,
habilitations/groupes/diagnostic/suppression pour l'administration. Brouillons,
conflits, cours/calendriers, expiration/reconnexion et mise à jour à chaud ; mathématiques
avec le moteur existant. Oreille et palette de l'identité faisant autorité, signature
et fontes réservées dans le transport chiffré.

MCP public : vingt opérations cohérentes, entrées fermées et sorties documentées,
politique/version/actions suivantes, pages et limites, liens canoniques, erreurs et
reprise. Transport Vision réutilisé ; aucune exposition de MCP/Swank de développement.
Log : OIDC/PKCE, cookies host-only et délégation OAuth ; audiences Vision/Audition
séparées, rotation/révocation et session parent vérifiées.

Indicateurs : effectifs et observations brutes conservés, logit translaté sur une
référence de hasard seulement justifiée pour les QCM, extrema/absence explicites,
centinats sans signe positif, aucune moyenne logarithmique hétérogène ni certification
de maîtrise. Le jugement d'un client LLM reste attribué, justifié et révisable.

## Révisions et artefacts

- Vision : `0270c38ec981b610dd6194d7c1cf691c7152de52`.
- Style : `cebba1824b6b5e939ae0155481ed87d7a98771e0`, changements concurrents conservés.
- Signature : `17194087eec9162bb5372221c43e1de0501dfe6a`, ressources source inchangées.
- Binaire construit une fois : sources `29ebb727a1046dc7b5157de018f8526d726473c9`.
- Binaire Nix : `/nix/store/dv109y63kv9cvpmnkqkcvcyjiqh1ssi2-mrjam-metier-29ebb727a104`.
- SHA256 binaire : `a74247c45b0889548c4d05d749cda8d2c77df902cdc9e3f18632789b45e82ae3`.
- SHA256 site : `a90dc352ca8e3b59cc900a9a537214ab613f4ed735ce0e12422106aa717676b3`.
- Sources déployées : `9feac618022a310de4f61cf2ce992ebe35e2f6dc` ; descripteur
  central `97e6e43c130f9ced0844c52087ea75fc2440221f`, transport chiffré
  `57146d9f1078c09c427c89528300a59fd9fa02ee`.

Le manifeste verrouille tous les producteurs. Les sorties générées, données de test,
clés/cookies/jetons et fontes réservées ne sont pas commis en clair.

## Contrôles effectivement exécutés

- 74 assertions métier sur PG17.11 : droits, données invalides, calculs, absence/incertitude,
  aides, versions, prescriptions/propositions, ordres incomplets, conflits/concurrence,
  interruption/reprise, timeout après écriture/rejeu, révocation, suppression/rejeu.
  Sauvegarde/restauration isolée avec empreintes sémantiques des tables Audition.
- 228 assertions intégrées avec Kanidm1.11.2 réel : deux comptes MFA isolés, TLS/signature/
  nonce/PKCE, retour vers l'action, cookies, préparation/affectation, séance MCP avec aide,
  rapport, refus croisés, rotation/rejeu/révocation/logout, redémarrage natif et image neuve,
  restauration. Maintenance officielle ponctuelle et secret client conservé.
- 40 parcours du même binaire Nix : PostgreSQL/HTTP, rôle non propriétaire, transactions,
  concurrence, framing hostile AF_UNIX et persistance au redémarrage.
- Neuf tests Elm ; elm-review central, ressources/interopérabilité et format bloquants.
  Navigateur Chromium154/Playwright1.61 : public320/768/1440, trois rôles390, clavier/focus,
  reduced-motion, inversions, saisies/conflits/rejeu, actualisation et consentement.
  API/Log du test navigateur doublées ; elles ne prouvent pas la connexion réelle.
- Neuf contrôles d'assemblage/promotion, dont évaluation Nix réelle, conservation des autres
  sites/identités/services et calendriers ACME, refus du retour concurrent et retour du
  code conservant les données. Sélection centrale : 25 tests ; règles frontend : 208.
  Inventaire des dépendances et CI/contrats conformes, aucune nouvelle dépendance.
- Transport MCP Vision : six assertions, comportement par défaut préservé.
  Régression du socle Log également exécutée depuis le chargeur central propre.

## Intégration et exploitation réelle

| État | Preuve et portée |
| --- | --- |
| Implémenté | Bibliothèques ASDF, services/persistance, adaptateurs HTTP/MCP et trois interfaces Elm. |
| Testé | Métier, Native/OIDC et scénario enseignant–élève–MCP–rapport en isolation ; navigateur et assemblage ci-dessus. |
| Intégré | Serveur, graphe, manifeste, commandes et workflow centraux ; producteurs publiés aux révisions exactes. |
| Déployé | [Run38470128833](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38470128833), 13octobre21:23:54UTC. Même binaire et même site qualifiés, sans reconstruction de publication. |
| Vérifié sur le service réel | Génération active/démarrage, binaire, 95ressources exactes, HTTPS, landing/guide et entrée Log au navigateur ; refus anonymes et métadonnées OAuth. |

[Audition](https://audition.mrj.am) répond200 avec TLS vérifié. Génération active et
profil de démarrage : `/nix/store/zmd027b9fcpl8xnpmp0ysxdgzj7dn11a-nixos-system-nixos-26.05.8639.c5c4a43b0e80`.
Le diagnostic38470473342 confirme le SHA du binaire réellement exécuté, le schéma1,
un administrateur technique déjà rattaché au compte central, zéro groupe et zéro
objet pédagogique. La référence38470476909 confirme les comptes/rattachements
existants et les trois participations Matheval ouvertes conservés. Native, SSH,
Nextcloud, Redis et embeddings restent actifs avec les mêmes PID ; PostgreSQL et
le serveur commun ont seuls redémarré. Les sondes centrales des autres sites passent.

Préparation38469826749 puis sauvegarde nouvelle lors de la bascule : déchiffrement
age, restauration isolée de38tables Vision (Audition compris),6Matheval et100SQLite
identité, empreintes sémantiques identiques. Ce contrôle de restauration de données
ne restaure pas les rôles/ACL ; leur qualification isolée et les contrôles du rôle,
des propriétaires/RLS et de la connexion peer en production sont distincts.
Backup automatique actuel réussi. Le timer indépendant est qualifié par un témoin
réel et désarmé après succès ; retour manuel fermé `audition-retour`, code seul,
schéma et écritures récentes conservés. Aucune ancienne base n'est réinjectée.

95ressources vérifiées depuis le VPS et à nouveau depuis l'atelier. Session web,
API métier et MCP anonymes :401. Discovery OAuth/protected resource :200, audience
et scope Audition corrects, challenge Bearer lié à ses métadonnées. Chromium154 réel,
sans API doublée : landing et guide390/1440, logo, aucun débordement ou erreur JS ;
le lien ouvre le formulaire HTTPS de Log, aucune donnée personnelle saisie. Un premier
attendu global `networkidle` a expiré ; le contrôle réussi attend le DOM puis les
éléments/actions effectivement utilisables. Les parcours personnels enseignant/élève
sur production restent non effectués, afin de ne créer aucune participation de test.

Mesure après activation : RSS principal du serveur138518528octets, cgroup129286144,
plafond1GiB ; distinctions conservées. Les latences des services existants figurent
dans la preuve datée ; aucun résultat de charge ni précision psychométrique déduit de
ces sondes anonymes. DNS Alwaysdata inchangé ; même VPS que Vision.

## Échecs conservés et corrections

Les premiers préparateurs ont refusé l'historique Git peu profond, le PATH transitoire,
la référence Nixpkgs implicite et une unité systemd témoin déjà collectée. Corrections
requalifiées, aucune activation attribuée à ces essais. Préparation38464990665 réussie.
La première bascule38466325512 a engagé le schéma additif et le retour OIDC Audition,
puis le contrôle des PID a refusé le redémarrage PostgreSQL attendu par NixOS. Le
retour du code a réellement rétabli wib5an et le binaire Log précédent ; le diagnostic
38468816255 le confirme, avec schéma/admin/audit conservés et aucune donnée pédagogique.

L'essai SIGHUP archivé et une lecture PG17.11 isolée confirment le contexte postmaster
des chemins hba_file/ident_file. Le candidat SIGHUP a seulement été préparé, jamais
activé. La correction finale borne le redémarrage PostgreSQL : paquet, autres réglages,
hardening et données identiques, nouvelles règles chargées et rôle peer effectivement
vérifiés ; tous les autres PID protégés restent bloquants. Le déploiement corrigé
38470128833 et les lectures suivantes réussissent. Aucune protection générale retirée.

## Limites et exploitation

Aucun essai avec un compte Mistral ou autre fournisseur LLM. Les offres/conditions
Mistral ont été consultées et citées dans le guide ; disponibilité réelle du connecteur
et conditions du compte élève restent à vérifier pour l'offre choisie. La compatibilité
JSON-RPC/OAuth testée ne constitue pas un essai fournisseur. Aucun parcours personnel
du propriétaire ni enrôlement personnel effectué. L'architecture de développement
MCP/Swank dans une même image persistante n'a pas été prouvée dans cette session ;
les qualifications propres ci-dessus sont distinctes et le produit n'expose pas ces outils.

La preuve durable est [qualification-production-20261013.json](qualification-production-20261013.json).
Voir [EXPLOITATION.md](EXPLOITATION.md), [CONTRAT.md](CONTRAT.md) et [MCP.md](MCP.md).
Les reçus qualifient les entrées exactes avant scellement ; les mises à jour éditoriales
et du statut de manifeste après déploiement ne changent pas le binaire/site servis.
