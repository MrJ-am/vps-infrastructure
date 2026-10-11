# Journal technique

- Clones propres des six sources ; Matheval master, autres main ; révisions initiales
  dans le manifeste. Aucun autre dépôt de projet consulté.
- SBCL Debian 2.5.2, ASDF 3.3.1 ; paquet SHA256 vérifié, extrait sans installation
  système. Image interactive conservée pour cette tâche.
- ASDF load-system vision : neuf fichiers compilés, aucun daemon ni connexion.
  Contrôle initial render-json : symbole inexistant, retour au niveau supérieur.
  Contrôle corrigé json-object-get sur JSON synthétique {"reponse":0} : zéro conservé,
  un thread. Pas de contenu réel utilisé.
- Audit lecture seule Actions 38097638053 sur dac2505258fdbb8536d44fb23b9aec4ad755033e,
  succès constaté.

- Graphe ASDF : vision/json, vision/core, vision/http, matheval, agrégat mrjam-metier.
  Compilation incrémentale dans la même image interactive. Erreur de parenthèse
  date-iso corrigée dans la source avant rechargement. La comparaison avec Zod
  verrouillé a précisé caractères non BMP et secondes ISO obligatoires.
- Validation finale dans une image neuve : 116 cas différentiels, 8000 tirages,
  corpus public complet, statistiques, CSV, schémas et rattachements synthétiques.
  Réussi en 0,838 s avec cache FASL valide ; ce n'est pas une reconstruction sans cache.
  Sélecteur : 12 tests en 0,191 s. Reçus locaux non attestés, aucune autorisation
  de publication dérivée. Réutilisation après commits identiques : 2 suites évitées,
  seul contrôle éditorial rejoué car manifeste changé.
- Composants publiés avant leur référencement central : Vision d65cba5,
  Matheval 633588b, Logique e8478fc, Style 508f964, Signature c4a2067.
  Infrastructure 1abe1f5 publiée sans PR ni push forcé. Aucun service métier basculé.

- Référence détaillée Actions 38098717899 sur 1abe1f5 : succès. Un compte actif
  Vision/admin, une identité liée, zéro lien entre propriétaires, trois
  participations Matheval ouvertes. Aucun contenu personnel publié, aucune écriture.
  RSS principaux : Vision 83 578 880 octets ; Node Matheval 87 425 024 ; embeddings
  1 213 095 936. Keycloak : cgroup 600 293 376, son lanceur n'est pas la JVM.
  Médianes dix GET : Vision public 5,185 ms, Matheval santé 8,426 ms,
  MCP anonyme 401 5,899 ms, découverte Log 16,920 ms. Pas de mesure « après » production.
- CI centrale 38098700592 : cadre réussi ; checkout Vision privé code 128.
  L'API d'administration des secrets est refusée 403. Accès de lecture sources
  privées demandé ; pas de contournement ni de copie publique des sources privées.
  Contrôles historiques infrastructure 38098700515 : quatre jobs réussis.
- OpenSSL effectivement installé : réutilisé par SB-ALIEN ; demande Ironclad
  devenue inutile, aucune dépendance tierce ajoutée. API EVP/RAND/libpq officielles.
- Même image interactive pour collecte, transactions, administration scientifique,
  routage, primitifs et expériences. Changement du layout configuration : arrêt
  sur condition SBCL, CONTINUE standard invalidant l'ancien layout, rechargement
  des sources et recompilation des consommateurs ; aucune instance active concernée.
  Aucune utilisation de RECKLESSLY-CONTINUE. Image exploratoire jamais sauvegardée.
- Matheval : 40 parcours différentiels sur deux bases isolées PostgreSQL 17,
  rôle non propriétaire/NOSUPERUSER/NOCREATEROLE/NOBYPASSRLS, empreintes Node exactes,
  zéro/null, révisions, journal et clôture explicite de fixtures. Concurrence : un
  gagnant/un conflit, huit retransmissions identiques. Aucune clôture en production.
  Corrections UUID impossible/date de filtre impossible documentées dans le contrat.
- Primitifs : 8003 cas OpenSSL/JSON, scrypt historique UTF-8, nombres binaire64 et
  ordre de propriétés. Vision/libpq : RLS Alice/Bob lecture/écriture, lien croisé
  refusé, paramètres liés et nettoyage de contexte sur connexion réutilisée.
- Fixture Vision initialement interrompue (psql code 2) : attente Unix atteignait
  le serveur temporaire initdb avant son redémarrage. Attente du listener TCP final
  corrigée ; nouvelle qualification réussie, pas de retry aveugle de la suite.
- Image neuve de construction, environnement sans credentials CI ni DSN ; contrôle
  sans cache FASL : 24 FASL effectivement créés. Exécutable local environ 10,3 Mo,
  construction 3,107 s ; parcours/tests de cet artefact 8,586 s. HTTP réel AF_UNIX,
  framing hostile, sauvegarde et session SQL conservées après redémarrage.
  Ce binaire SBCL 2.5.2 local ne qualifie pas la cible Nix/SBCL 2.6.4 installée.
- Sélecteur élargi : 14 tests. Contrôle des locks npm/directes et dépendances ASDF
  internes avant installation. Reçus sans confiance de publication ; compilation
  propre et tests concernés seront rejoués en CI lorsqu'elle lira les composants.
  Les CI satellites et auxiliaires Python restent actifs jusqu'à leur transfert
  complet ; cette tranche ne constitue pas le jalon 1 et Kanidm n'est pas démarré.

- Dernière qualification : 40 parcours, ajout du refus anonyme avant toute
  validation du détail scientifique ; Matheval publié au commit 62e6667,
  Vision au commit d9d5450. Exécutable local 10 261 112 octets, SHA256
  6e11db00faf61289493159900b7c69ccf20d5592a380787ada272fba6dc8757b,
  construction sans cache 2,735 s, 24 FASL, tests 6,693 s. La base Git infrastructure
  portée par cette preuve précède ses changements non commités ; les empreintes
  de chaque entrée du reçu identifient les sources testées, pas ce seul commit.
  Les reçus déjà valides sont réutilisés lorsque ces entrées restent identiques.

- UUID historiques : lecture limitée à la syntaxe SQL canonique, sans exiger
  les bits version/variant du schéma de création. Régression différentielle
  ajoutée ; 40 parcours et reconstruction sans cache réussis (24 FASL,
  3,209 s construction, 7,207 s tests). Matheval 2a82250 publié avant le manifeste.
- CI 38101080554 sur 82161d8 : cadre success, composants arrêtés code 2 au
  contrôle COMPONENTS_READ_TOKEN absent. Aucun checkout privé ni publication.
  Trois contrôles satellites Vision sur d9d5450 réussis ; ils ne qualifient pas
  l'assemblage complet et restent à transférer. Production toujours inchangée.

- Auxiliaires Vision portés en ASDF : administration, cycle, admission et fermeture.
  Contexte explicite, anciennes files SQLite/intentions JSONL conservées, aucun I/O
  au chargement ; HTTP et tâches périodiques détenus par le serveur commun.
  Client Keycloak provisoire borné aux clients de service existants, sans secret
  administrateur global. Courriel SMTP par curl existant, STARTTLS obligatoire et
  vérification CA/hostname ; secrets sur stdin, messages temporaires privés.
- Même REPL sain conservé : chargement incrémental ASDF après écriture des sources.
  SHA/scrypt/SQLite/libpq via API natives déjà présentes. SQLite NOFOLLOW, paramètres
  liés et transactions ; ancienne file/MIME relue sans modifier les blobs existants.
  Correction du décodeur RFC2231 pour les boundaries longs du MIME Python ; test
  indépendant email Python et idempotence concurrente. Les registres utilisent dup
  avant le fd-stream afin de garder le verrou/fsync jusqu'au terme de l'opération.
- 644 cas différentiels du validateur administratif et 141 du validateur admission.
  Fixture PostgreSQL 17 avec toutes les migrations et vrais rôles limités : Alice/Bob,
  contenu inaccessible au rôle d'administration, préavis futur inchangé, conservation
  avant acceptation du registre, reprise, invitations, confirmation unique, consentement
  parental/contrôle manuel, sujet existant vérifié et fermeture ciblée idempotente.
  Un offset erroné d'extraction du token dans la fixture a été corrigé, pas le validateur.
- IdP simulé : dix échanges du client plus scénarios d'admission/fermeture. SMTP réel
  curl sur fixture STARTTLS locale : CA valide acceptée, certificat non fiable et
  mauvais hostname refusés avant AUTH. Aucun IdP/relai réel ni courriel envoyé.
  Age non disponible localement : archives synthétiques préexistantes pour tester
  l'ordre d'effacement ; chiffrement/restauration officielle reste à qualifier.
- Reçus de cette tranche : sélecteur 14 tests 0,152 s ; natifs 8003 cas 2,089 s ;
  administration 0,438 s ; courriel/SMTP 1,581 s ; client IdP 1,072 s ; admission
  0,457 s ; PostgreSQL/cycle/admission/fermeture 10,547 s. Empreintes par entrées,
  outils et DSO ; confiance locale uniquement. Nouveaux tests ajoutés au catalogue.
- Reconstruction de qualification SBCL neuf sans cache : 39 FASL, 3,412 s,
  exécutable 10 425 056 octets SHA256
  bfda1fa3a7fc1b1be8531d7ce809b42fc8e1ffafffb2428256c96e30ffcd1a5a.
  40 parcours Matheval et HTTP/redémarrage SQL : 7,049 s, réussis. Production
  inchangée ; cette preuve locale ne qualifie pas l'IdP, MCP ni la cible Nix.

- CI 38104435924 sur cd90f2a : quatre jobs réussis, évaluation Nix du serveur
  commun incluse. Paquet de test factice : aucune activation ni qualification
  du binaire cible SBCL 2.6.4. CI composants 38104435933 arrêtée au secret absent.
- SO_PEERCRED vérifie l'UID Unix Nginx avant lecture HTTP ; un émetteur d'un autre
  UID avec en-têtes forgés est refusé. Scrypt limité à deux calculs simultanés
  (~128 Mio chacun) ; dépassement refusé par condition typée/HTTP 503.
- ACL centrales vérifiées sur PostgreSQL 17 : entretien peut exécuter les deux
  purges bornées mais ne peut lire les contenus ; Matheval non propriétaire peut
  gérer réponses/journal/sessions mais pas créer un corpus. Le schéma réel est
  `answers`/`interaction_events`, pas l'ancien nom hypothétique `interactions`.
- Sauvegardes Nix adaptées aux chemins durables communs et à Matheval ; ancien
  lanceur Node exclu de la configuration cible. Les générations de retour restent
  conservées. Inventaire étendu aux requirements Python et manifests Elm déjà
  présents ; verrouillage des transitives Python restant à établir avant installation.
- Script de sauvegarde/restauration via CI existante préparé, pas encore exécuté
  sur le VPS : age officiel, clé éphémère enveloppée, snapshots SQL READ ONLY,
  restauration dans un cluster Unix propre. Quatre contrôles sur fixtures locales
  vérifient blobs SQLite/zero/null/UTF-8 et registres exacts ; liens, corruption et
  fichiers publics refusés. Ces contrôles ne prouvent pas encore le chiffrement.
- Le hook Keycloak de fermeture est une RequiredAction personnelle avec confirmation,
  pas un listener de suppression administrative. Le retrait d'une ancienne identité
  reste distinct d'une fermeture métier ; aucune identité supprimée pendant la mission.

- Sauvegarde/restauration réelle CI 38105867103 sur eff80b8 : réussite en cluster
  Unix isolé PostgreSQL 17. 30 tables Vision, 6 Matheval, 100 identité ; empreintes
  sémantiques identiques. Age : chiffrement/déchiffrement vérifiés, mauvaise clé
  refusée ; clé de transition enveloppée pour le destinataire existant, clé
  personnelle non utilisée. Aucun arrêt de service ni écriture SQL de production.
  Preuve publique minimale : `sauvegarde-transition.json`. ACL/rôles et retour
  applicatif restent des qualifications distinctes, explicitement non acquises.
- Contrôle CI eff80b8 échoué : le module Matheval modifié contredisait la provenance
  « copie amont exacte ». Module actif transféré à `modules/matheval.nix`, ancienne
  copie exacte archivée ; contrôles d'empreinte/patch historique conservés et réussis.

- Approbation manuelle d'admission transférée au serveur commun ; l'ancien CLI
  Python n'est plus nécessaire à cette fonction. Migration 026 ajoutée sans table
  ni modification des contenus : autorisation SQL active gardée pendant l'écriture
  SQLite, ordre des verrous admission puis SQL pour éviter un blocage du worker.
  Même REPL conservé, chargement ASDF incrémental réussi. Tests natifs réexécutés
  sur fixtures : refus anonyme/Bob/acteur injecté, Alice autorisée après accord,
  644+141 cas différentiels toujours réussis. Aucun contrôle humain fabriqué.

- Artefact propre local : SHA256 601decf0db101eb2012bb8559e71e29f201b3f0a65171a78aaef022e874df385,
  10 425 040 octets, 39 FASL de référence, 4,748 s construction/7,703 s tests.
  Métadonnées de construction complétées par les empreintes exactes du graphe
  Lisp ; refus si les sources changent pendant la qualification. Cache FASL valide
  utilisé pour produire le candidat correspondant à ces nouvelles métadonnées.
- Le même binaire exerce API/MCP Vision sur PostgreSQL isolé, 40 parcours Alice/Bob
  concurrents et écriture d'observation MCP, refus des objets/écritures étrangers,
  du corps portant un utilisateur et du transport navigateur sans marque d'entrée.
  UID et identités synthétiques : aucune prétention à une vérification OIDC réelle.
- Frontends construits centralement sur leurs révisions exactes, sans modifier les
  sources partagées. Les trois anciennes versions de style restent des entrées
  verrouillées explicites, sans refonte graphique. Signature : mêmes fontes contrôlées
  depuis le dépôt autorisé, sans miroir externe nouveau. Quatre candidats conservés,
  empreintes et sources associées ; publication non acquise.
- Python navigateur/typo/logo : résolution des requirements déjà présents via pip,
  roues Python 3.12/Linux/x86_64 verrouillées par SHA256, transitives identifiées.
  Pillow 11.3 et 12.3 isolés ; aucune nouvelle dépendance directe ni mise à jour pip.
  Le compilateur Elm 0.19.1 de l'atelier est celui du paquet @lydell déjà verrouillé,
  sans downloader binaire hors lock du paquet elm historique.
- Qualification style interrompue : le candidat Pages seul omettait la galerie et
  l'atelier nécessaires aux tests. Condition analysée, conservation des trois sorties
  ajoutée et nouveau candidat demandé ; pas de relance inchangée jusqu'au vert.

- CI infrastructure 38107422877 sur 520cf53 : cinq jobs réussis. Module Matheval
  central et archive exacte qualifiés ; aucun binaire SBCL 2.6.4 construit/activé.
  CI assemblage 38107422889 : cadre réussi, secret de lecture privé toujours absent.
- REPL conservé : chargement du nouveau chargeur, ASDF incrémental puis contrôle
  court. Cache privé 0700, refus des liens/propriétaires étrangers, namespace sur
  runtime/core/ASDF, architecture/ABI et options speed1/safety3/debug1/space1.
  Régression : les package.fasl de composants différents doivent être distincts.
  Huit changements de descriptor invalident le cache ; répertoire public refusé.
- Même graphe compilé dans une image propre : candidat f205c50b0e1b2537f903cb08f432aedaed4ec1d0d97f27548e6a1c2c6983803f,
  cache valide, construction 1,958 s / 40 parcours 6,565 s. Référence sans cache :
  39 FASL, 4,470 s / 40 parcours 9,345 s, e480624fd63e9eb5f98b2da6b32bd94cda06222be005e4c7077d95d6cba43760.
  Le dernier temps a été mesuré pendant d'autres tests navigateur ; pas une
  mesure comparable de gain de latence. API/MCP Alice/Bob et auxiliaires toujours
  réussis sur le candidat ; aucun accès de production dans ces expériences.
- Frontends : candidats existants réutilisés, construction non répétée pour les
  campagnes. Style : 82 tests Elm, 21 références, géométries, 92 parcours navigateur
  réussis / 4 ignorés prévus, rasters réussis. Signature : fontes/CSS/HTML identiques
  après régénération, géométrie JSON sémantiquement identique (entiers rendus en
  floats par fontTools), sélection/copier-coller réussis. Aucun changement graphique.
- Vision historique porté vers l'entrée de fixture du vrai serveur commun :
  17+7+6+12 tests HTTP métier, migrations/formules, dix tests comptes/quotas et
  mesures SQL réussis. Rôles non propriétaires ; sujets synthétiques explicitement
  admis par la fixture. Navigateur 320/375/768/1280 et parcours mutation/reprise
  réussis. Cette entrée loopback de test ne qualifie pas Nginx/OIDC de production.
- Matheval navigateur : 55/56 réussis. Un scénario Firefox n'a pas fermé le lecteur
  après clic ; première trace perdue par nettoyage du worktree, conservation des
  diagnostics corrigée. Cas isolé puis vingt répétitions instrumentées réussis,
  sans reproduire le défaut. Cause non établie ; campagne complète non qualifiée.
  Traces privées : state/rapports-frontends/matheval-diagnostic-6c454d496fe7.
- Catalogue et CI centrale étendus aux interfaces, atelier, Signature, PostgreSQL
  historique et navigateur commun. Diff des pins Git disponible après checkout :
  prose seule ne déclenche pas l'arithmétique ; macro JSON/toolchain élargissent.
  Dix-sept tests du sélecteur réussis. CI rejoue les suites affectées, sans croire
  les reçus Codex ; une construction par candidat, aucune publication acquise.
- Outils sémantiques existants : torch 2.6.0 CPU (ancien workflow Vision) et les
  requirements existants résolus en 35 roues verrouillées SHA256, profil séparé.
  Installation autorisée de cet outillage déjà utilisé, sans nouveau service ni
  runtime. Qualification du modèle réel à poursuivre avant retrait du déclencheur.
# 11 octobre — centralisation, modèle réel et inventaire SQL

Sources publiées avant mise à jour du manifeste : Vision fcb35f8, Matheval/master
d64f235, Logique 586ae18, Style 1132afe ; Signature c4a2067 inchangé.
Treize YAML satellites déplacés dans leurs archives exactes avec index SHA256.
Workflows personnalisés GitHub désactivés, y compris les restes d’anciennes
branches ; builtin Pages Matheval PUT disable refuse 422, état distinct consigné.
L’ancien signal operations/vision et workflow_run central sont archivés sans
modifier leurs faits historiques. Sauvegardes serveur/timers conservés.

`scripts/modele-vision.py --preparer`, puis suite vision-semantique : modèle officiel
e8f8c211, onze fichiers SHA256, fournisseur contenu-fenetres-1 inchangé. Six
paraphrases rang 1/rappel 1, archives/modifications/alias/isolation réussis.
35 roues du profil CPU déjà utilisé verrouillées ; aucun fournisseur ajouté.
Suite vision-postgresql avec documents HTTP du serveur commun : 95,7303 s ;
modèle réel : 36,174 s. Reçus locaux, aucune attestation CI/production.

`tester --suite matheval-navigateur` : 56/56 en 300,2492 s sur 5dd18de2,
participations synthétiques/PG17 isolé, frontend 36013c2e. L’échec Firefox initial
55/56 n’est pas effacé : vingt diagnostics ciblés puis deux campagnes complètes
réussissent sans changement UI, cause non établie. Les changements des quatre
pins frontend ne touchent que leurs manifestes/reçus ; ressources fonctionnelles
byte-identiques aux candidats qualifiés. Signature et atelier complet inchangés.

REPL conservé : reload ASDF et `load tests/quotas-http.lisp`. Fenêtres Matheval
historiques, budget activation/connexion commun, horloge monotone, capacité 4096,
vingt threads/huit succès. IPv6 /56, IPv4 mappé et adresses malformées contrôlés ;
en-têtes draft-8 conservés, origine/JSON avant quota. Une vérification ajoutée a
d’abord traité à tort les objets JSON comme hash-tables : le GET health l’a
refusée ; correction utilisant les prédicats publics Vision avant nouveau test.
`qualifier-metier.py --sans-cache` ensuite : 40 FASL dans une image neuve,
22655808c3fe9941417e13da231b4ae2c310b9d3eaa64a46295ee2ce1b6ddfa8,
10457800 octets, 3,559 s build/8,3669 s qualification. 40 cas différentiels,
transport hostile, quotas/en-têtes, origine et JSON invalides, sessions SQL au
redémarrage réussis. Aucun artefact de la tentative refusée n’est qualifié.

`verifier-tables.py` lit uniquement metadata PG : 30/6 tables, propriétaires,
RLS forcée/politiques, ACL tables/colonnes et héritage de rôles. Anciennes tables
Vision privées sans RLS interdites au runtime ; Matheval pseudonyme/scientifique
classé séparément. Tests Alice/Bob et cycle/admission/fermeture passent. Six
régressions du garde-fou et 17 du sélecteur passent. Les documents chargés dans
Vision/core sont désormais static-file ASDF et entrées de compilation ; test
modification/rechargement de MCP.md dans la même image réussi.

Référence Nix du VPS : commit complet c5c4a43b0e8056328ec4529f735cabdb8f1942bb,
archive officielle SHA256 53c2d41b0e5ab001e97d4478985287a82870e7c044f5185a250d98627b253fc0.
Circuit CI ajouté : compilateur/outils exacts seulement selon impact, une image
Nix propre, qualification de ce même candidat sans reconstruction. Nix absent
localement : pas d’installation opportuniste ; build cible encore non exécuté.
La CI reste bloquée avant lecture privée par COMPONENTS_READ_TOKEN absent.

Campagne Python historique élargie localement : 401 tests, 20 skips, dix erreurs
d’environnement (psycopg/passlib/Authlib et age-keygen absents, plus fixture de
droits dépendant de l’umask). La dernière fixture fixe désormais explicitement
0755 ; ses quatre tests passent. Les autres modules restent qualifiés par leur
CI existante et les campagnes différentielles portées, sans prétendre que cette
tentative globale était verte ni installer des outils par opportunité.

Production inchangée. Sauvegarde/restauration réelle 38105867103 reste une preuve
de données, sans qualification ACL/retour applicatif. Aucun jalon production ni
Kanidm annoncé ; état compact et préconditions restantes dans REPRISE.md.

## Constat CI de ce lot

2cd93ce publié : infrastructure 38112469913 réussie (Python et Nix, paquet métier
factice) ; assemblage 38112469897 cadre réussi, arrêt explicite avant lecture
privée, COMPONENTS_READ_TOKEN absent. Aucun build Nix métier ou déploiement dans
ces runs. Deux anciens coordinateurs distants lus après désactivation :
disabled_manually, IDs 379772835/379772836.

Le cadre borne maintenant ses tests par impact. Pilote CLI testé sur trois
commits Git synthétiques : prose uniquement → aucun composant/test inchangé ;
sélecteur → sa suite seulement ; classification SQL → garde-fou et composants.
18 tests du sélecteur/pilote/reçus réussis. Aucun nouveau réseau, outil ou service.

Cadre 38113070010 sur eb94866 réussi : seule la suite du pilote/sélecteur est
rejouée ; sauvegarde, garde-fou SQL et composants sont skipped. Ce vert incrémental
ne qualifie aucun artefact métier. Le workflow infrastructure exclut désormais
tous les tests test_assemblage*.py pour laisser leur exécution à ce cadre.
