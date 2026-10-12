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


## Reprise après création du secret de lecture

Nouvelle image SBCL interactive 2.5.2/ASDF3.3.1 ; load-system mrjam-metier depuis
cache incrémental, quota IPv6 2001:db8:12:ff::1 → 2001:db8:12::/56, contrôle réussi.
Image gardée pendant cette tâche ; aucune connexion de production.

Actions 38118779445 sur c11d342 : lecture des cinq composants réussie. Nixpkgs
c5c4a43 verrouillé, build image propre réussi avec SBCL2.6.4/ASDF3.3.1, artefact
e32ee43ef552c1d95982e3785a89960486ce0d27b58fa404c8651dbf3216a03e,
12 453 272 octets, 9,3644 s image et outils. Qualification arrêtée sur pdfinfo
absent lors du build Matheval, avant les suites ; aucun déploiement. Cause précise :
préparation centrale omettait Poppler, présent dans trois anciennes recettes.
Réparation : poppler-utils/age dans PATH Nix et besoin d’outils pour une sélection
frontend Matheval seule. Bibliothèques système Playwright préparées par son
install --with-deps comme les anciennes CI, sans nouvelle dépendance directe.
Sonde lecture seule 38118876078 : succès, génération r6s7ags3 inchangée ; compte
Vision unique et rattachement cohérent, trois participations Matheval ouvertes.


38119057570 sur 27bf244 : build Nix et Matheval frontend réussis. Arrêt au contrôle
byte pour byte de Palette-Y.svg dans Style, avant toute publication. Central CI
utilisait Node22.23.2 partout, alors que l'ancien atelier Style utilise Node24 et
la qualification locale Node24.19.0. Aucun SVG ni palette modifié pour contourner
le contrôle ; alignement du runtime de construction/test sur Node24.19.0.


38119274041 sur add6c26 : quatre frontends construits, égalité des exports Style
réussie avec Node24.19.0. Cache/documents ASDF, contrats Vision, Matheval purs et
quotas réussis. Différentiel arrêté sur ECONNREFUSED localhost55432 malgré le
healthcheck initial du service Actions. Conteneur encore actif selon son journal,
pas de preuve d'accès à son port publié au moment du test ; cause du mapping
non établie. Remplacement du service partagé par une fixture PG dédiée au test,
port loopback dynamique vérifié depuis l'hôte juste avant le différentiel,
nettoyage du seul conteneur créé. Pas de nouvelle image ni dépendance.


Fixture dédiée qualifiée localement sur le même binaire 22655808 : quarante
parcours Node/Lisp, concurrence/idempotence, transport Unix et redémarrage réussis.
Journal borné scratch/differentiel-fixture-dediee.log, données synthétiques seules.
Préparation VPS écrite : bundle des six révisions/artefacts, vérification des reçus
de ce runner, transfert SSH/NAR de la même image, hashes revérifiés sur VPS,
remplacement des seules déclarations Nix actuelles gateway/PG/Matheval, invariants
services tiers, build système et dry-activate. Aucune activation/migration SQL dans
ce chemin. Six tests négatifs de bundle réussis. Le chemin distant reste à exercer.

## Réorganisation du rythme de travail

Instruction complémentaire du propriétaire : audit préalable suffisant pour les
bibliothèques Common Lisp ; développement interactif local, CI/CD réservée au
déploiement. Causes des répétitions constatées : workflows push concurrents et
dispatch choisissant les 31 suites, sans réutilisation de reçus locaux.
Run 38119666775/d57b08c : build Nix et différentiel réussis ; tests du correcteur
Logique réussis, reçu refusé pour entrées modifiées pendant l'exécution. Diagnostic
de provenance à traiter localement, aucun transfert ni activation de production.

Actions : trois workflows désactivés par API, état disabled_manually relu ; aucune
exécution encore active au constat. YAML archivés byte pour byte avec révision
d57b08c et SHA256, sans effacement de sauvegarde ou modification des services.
AGENTS/contrat mis à jour et commandes REPL `recharger`/`verifier` ajoutées : mêmes
image et cache ASDF, durées/allocations locales sans attestation de publication.
Pas de nouvelle dépendance ni de lancement Node pour vérifier cette correction.
La toolchain cible locale et le transfert de confiance vers la promotion restent
à achever avant un nouveau déploiement ; aucune production annoncée à ce stade.

Vérification dans le REPL de tâche conservé : load developper.lisp, puis verifier
Matheval/JSON/quotas ; 0,040/0,092/0,140 s, un seul thread vivant après le contrôle
concurrent. Validation finale en image neuve SBCL2.5.2/ASDF3.3.1 : trois contrôles
réussis, sortie en 0,578 s avec cache valide. Aucun Node ni campagne navigateur.
Contrat/archives/dépendances : succès local 0,310 s ; 18 tests du sélecteur et
reçus : succès 0,637 s (pilote 0,791 s). Reçus machine locaux non attestés conservés.
Ces contrôles qualifient le changement de workflow, pas le candidat de production.


## Reprise locale — SBCL cible et fixtures figées, 11 octobre 2026

Nix officiel 2.31.2 préparé uniquement dans Codex ; archive et SHA officiels,
store vérifié. Nixpkgs c5c4a43 exact ; image propre
/nix/store/nq8729macji666smhhddvf9i4xqzkdy4-mrjam-metier-158e4a52e012,
SHA 296b7c89d9f40679a8fa69a3ceac1d8825d7bb211a051fe173af41a6e7bda69c,
12486040 octets, SBCL2.6.4/ASDF3.3.1. Construction non chronométrée.
Image de tâche alignée une fois sur ce compilateur, conservée ensuite.

Formulaires : recharger le helper source puis verifier matheval/native.
116 cas et 8000 tirages / 8003 vecteurs synthétiques JSON/OpenSSL passent.
Initialiser MRJAM_LIBCRYPTO au chemin Nix dans le REPL : son absence avait
sélectionné le DSO hôte incompatible ; condition inspectée, environnement corrigé,
sans redémarrage. Dernières mesures 0,324 s/17,1 Mo et 1,724 s/226,5 Mo alloués.
Références générées une fois par Node, identiques aux fixtures précédentes ;
PROVENANCE.json lie chaque référence et corpus. Les suites ordinaires sont Lisp.

40 cas Matheval/PG et concurrence, transport Unix et redémarrage réussis sur le
même artefact : 16,5902 s. Vision SQL natif/multi-comptes : 16,3945 s.
elm-format remplaçait son wrapper au premier appel : initialisation avant les
empreintes, aucun ajout de paquet. Les interfaces Python utilisaient Playwright
1.62 global au lieu du profil verrouillé1.57 ; commande centrale corrigée, aucun
nouveau navigateur téléchargé. Vision/Logique/Style passent sur le profil prévu.

Matheval : 55/56 parcours, trace synthétique montrant un lecteur réduit à une
bille après fermeture/réouverture ; animation fill:forwards conservée. Libérer
l'animation au frame suivant : huit répétitions ciblées réussies, régression
ajoutée, commit composant7438ce6 publié. Seule interface Matheval reconstruite ;
Lisp/RNG/corpus inchangés et même image Nix. Campagne finale en cours.

Initialisation des copies SQLite dans le REPL avec SMTP et recipient synthétiques :
réussie, aucune tâche ni connexion SMTP/IdP. Opérateurs de promotion/retour écrits,
qualification restante ; aucune intervention de production ni run Actions ici.


Campagne Matheval finale : 56/56, 371,337 s, candidat frontend5b0108d9,
image296b7c89. Validation finale des helpers dans SBCL2.6.4 neuf : Matheval/native/
JSON/quotas réussis (0,268/1,764/0,176/0,212 s), FASL incrémentaux réutilisés.
Promotion : dix refus/provenances synthétiques, retour : cinq contrôles avec
écriture après bascule et reprise idempotente, sauvegarde SQLite/JSONL : quatre,
sélecteur : dix-huit contrôles réussis. Aucune attestation CI ou production.

Promotion : uploads.github.com refuse le credential (401), release non publiée.
Repli par push Git autorisé : branche isolée contenant seulement le chiffré,
commit/chemin et SHA verrouillés depuis main. NAR limité aux sorties propres ;
dépendances officielles de la même closure par substitution Nix signée existante.
Aucune reconstruction du binaire296b7c89, aucun nouveau fournisseur ou secret.
Préparation reprenable avec bundle/état vérifiés ; retour avant création de
l’unité commune et migration déjà26 traités explicitement.

VPS : préparation38126827329 refusée avant activation ; diagnostic38127124960
réussi. Seuls postgres.settings.hba_file et ident_file changent, comme attendu
pour le compte Unix commun ; toutes assertions et autres invariants identiques.
Ces chemins générés sont sortis du comparateur général, remplacés par un contrôle
strict du contenu : deux lignes HBA en tête, sept mappings bornés en fin, ancien
ordre/règles intacts. Régressions refusent trust, rôle postgres, nouveau mapping
d’identité et changement d’ordre. Aucun processus tiers ou donnée modifié.

Amendement 11octobre — reprise réelle : PID83928/SBCL2.6.4 sain, aucune promotion
active ni activation/migration incertaine. Six AGENTS et guides actifs remplacés,
archives exactes conservées ; relecture explicite. Composants publiés avant pins
centraux, documentation seule : pas de recompilation métier. Ancien candidat
refusé avant transport par le descripteur tant que l’amendement n’est pas qualifié.
`python3 -m unittest discover -s tests -p test_monolithe_stage.py` : 13 succès.
Outils officiels récupérés pour audit seulement ; pas de raccordement revendiqué.

Outils de développement : cl-mcp197f5e8 + Tron39d00b4 + Swank2.29.1/35 sources
Nix. Raccordements amont de breakpoints incompatibles constatés à compilation :
patch local Nix6 lignes ; sous-système officiel core, installation de skills
facultative défectueuse exclue et non qualifiée. Registre ASDF récursif MGL, DSO
OpenSSL existants, Quicklisp privé/dists vide, aucun téléchargement implicite.
`python3 scripts/qualifier-mcp.py` : condition réelle et pile DEBUG, locaux40/2,
correction source compilée, restart42, effets1→1, objet11→12 vu des deux outils
dans PID83928 ; 0,8729s. Compteur ASDF amont inconnu : marqueur explicitement
requis après les3 assertions réussies. Backtrace RPC amont différent de pile
suspendue : cause examinée, première exécution reprise sans répéter son effet,
puis qualification complète corrigée. Agent connecté via pont HTTP existant,
pas catalogue natif prétendu modifié. Refus provenance/patch/toolchain :5 tests ;
sélecteur14, coordination/absence CI satellite/inventaire passent. Aucun métier
ni production touché. elm-review construit depuis Nixpkgs retenu, paquet2.13.5
mais annonce2.13.4 ; règles Elm2.15.0/unused1.2.3 audit en cours, pas conformité UI.

Amendement frontend : elm-review Nix2.13.5/CLI2.13.4, APIElm2.15.0,
NoUnused.Dependencies1.2.3 ; 111transitives npm +25 bibliothèques Elm auditées et
verrouillées, nouveaux packages extraits dans Nix. Règle AST résout alias/exposing
et refuse CSS/HTML/échappatoires/frontières ; ARIA pris en charge par ElmUI.Region
reste ElmUI (pas d'adaptateur aria-label inutile). 21cas Review.Test passent ;
commande canonique accepte type Html et rejette H.div/dépendance inutilisée par
nom de règle. Suite locale frontend-regles12,3342s. Complément HTML/CSS/JS :
parseur déjà embarqué dans Playwright, parsing sans exécution/config externe ;
3tests passent. Pas de CI au push, pas de nouvelle lib JS/parser installée.
Les interfaces sont réellement refusées : anciennes échappatoires communes et
applicatives, Style339/Vision330/Math466/Logique406/logo690 avant premier portage.
Ces chiffres sont une référence datée, aucune conformité prétendue.

Socle Animator : atelier logo déjà2.0.0 officiel, Matheval1.1.1 ; API différente
constatée. Cible2.0.0/elm-bezier2.0.0 officielle vérifiée. Lecteur170lignes déplacé
vers MrJam.Transitions, sans toucher calculs de géométrie ; Main l'utilise.
82anciens tests passent929ms ; nouvelles propriétés : 2échecs init/durée0 dus à
Timeline.isRunning vrai à init. Correctif enregistré : enMouvement explicite,
aucune frame sans changement demandé, cible immédiate/réduction/repos. 88tests
puis 8ciblés réussis102ms après ajout même-cible/durée0, géométrie inchangée.
Publication Style0ea000d avant source centrale ; autres pins de consommateurs
restent historiques pendant leur portage. Backend296b7c89 inchangé, pas de tests
Node serveur relancés, pas de déploiement ni données réelles modifiées.

Reprise ciblée après audit : architecture C préservée ; cibles/édition facultative/
DEBUG/restarts/timeouts clarifiés et relus, pont HTTP limité aux chemins distants
qualifiés. Statut distant avant appel, refus local/fallback et connexion implicite.
Six tests purs, reçu outils-routage0,3246s ;33 suites évitées pour le pont seul.
Qualifier non lancé comme sonde ; choix de restart de fixture contrôlé avant/après
compilation par nom/sens/cible actuelle. AGENTS Vision/Math publiés avant manifeste.

Frontend local : contexte immuable dans les façades, ARIA bornée, SVG original,
champs natifs/texte littéral testés. Le parent pre-wrap ne suffisait pas : .t force
normal dans elm-ui ; raw Html.text échappé, aucun élément HTML ajouté. Déploiement
animé : minimum de contenu92px empêchait le repli, corrigé par Element.minimum0.
Préférence : Playwright.evaluate invoquait le disposer retourné par le raccord ;
corps de callback sans retour corrige le test, écouteur natif inchangé. 56 cas AST
et parcours Contextes320/768/1440 passent, réduire en mouvement/au chargement,
frames réellement arrêtées, saisie/focus disponibles. Sources et JS synthétiques,
aucune donnée réelle, aucune suite métier Node ou campagne distante. Analyse
réelle421 violations encore bloquantes ; ces unités ne prouvent pas la conformité
frontends. Détails de reprise et SHA dans REPRISE.md ; suite du portage requise.

- Reprise ciblée : les six dépôts et l'image persistante sont conservés. Lecture
  croisée CL-MCP/Tron : PID83928, session qualification-83928-4000700556,
  objet12/effets1/résultat42 ; aucun DEBUG ouvert. Une première lecture d'un
  symbole de marqueur inexistant a produit UNBOUND-VARIABLE, sans effet ; lecture
  corrigée des symboles réels, aucun restart ni scénario synthétique relancé.
- Préparation38184214522 réussie ; déploiement38184424703 arrêté en restauration
  avant activation. Diagnostic38185217273 : 14 tables privées public sans RLS/force,
  une politique chacune ; Gestion.comptes protégé. Restauration PG locale préserve
  les attributs. Migration027 publiée dans Vision18c52cdd : liste fermée, prédicat
  propriétaire normalisé, ENABLE/FORCE, refus de politique inattendue, aucune
  ligne métier ni compteur réécrit. Tests PG isolés réels : refus tardif atomique,
  double application, empreintes identiques de toutes données hors registre des
  migrations, observation datée et séance ouverte conservées, Alice/Bob et lien
  interpropriétaires, transaction sans identité. Suite migration11,9687s réussie.
- CLI GitHub brièvement401, lecture authentifiée de nouveau réussie avant push.
  Aucun autre canal d'administration créé. Frontend Vision reconstruit une fois
  pour sa nouvelle révision embarquée ; requalifier ce candidat exact. Binaire
  métier296b7 inchangé, graphe Lisp identique ; qualifications SQL/semantic/MCP
  affectées lancées localement. Production ancienne, aucune activation ni Kanidm.
- Correction027 qualifiée : VisionPostgreSQL145,7859s, SQLnative16,6193s
  dans un processus SBCL de test propre, rechercheCPU36,871s, sécurité0,8142s,
  sélection1,0072s, présentation76,2795s et navigateur/MCP26,9502s. Migration
  finale13,4831s avec refus avant toute activation si preuve027 absente. Les35
  reçus exacts passent :34réutilisés/éditorial seul rejoué ; aucune preuve de
  production. Nouveau frontendVision37871df2 ; autres candidats inchangés.
