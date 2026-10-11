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
