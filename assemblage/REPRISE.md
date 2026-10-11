# Reprise — mission et amendement du 11 octobre 2026

## Point de reprise actif — préparation de production

Préparation38183623725/8b9d7be échoue avant activation sur l’ordre IdentMap.
Diagnostic fermé38183852193/563c0ed réussi : assertions Nix vraies, aucun invariant
préservé modifié, seuls les7ajouts attendus ; lignes existantes2/après9, aucune
activation. PostgreSQL officiel ajoute sa ligne native à mkAfter1500 ; nos
7entrées étaient intercalées avant celle-ci. Module métier passe à mkOrder1600,
ancien préfixe exact et refus des autres accès conservés. Régression de cet ordre
ajoutée ; module Nix inclus dans entrées/impact de la suite sécurité. Pas de
modification des données, du binaire ou des interfaces. Nouvelle préparation
après qualification/scellement des opérateurs corrigés ; ne pas rejouer l’ancienne.

Opérateurs qualifiés56b6ef7be73acaf90d7fe2ece3335100873f6ff0.
Scellement et verifier_bundle COMPLET réussis localement, mêmes35reçus/sources
et même image296b7. Archive109013762octets, chiffré80ee4b46c3866150213f8a3265edf9a53e57ac1a3212b1f0e4491e896fff62da.
Transport publiébbc2aee495fbe1982884dfefaba1600a503b1fba, brancheartefacts/monolithe-56b6ef7be73a.
Descripteur central actualisé. Nouvelle préparation fermée à lancer ; production
ancienne conservée, aucune activation/restauration de données effectuée.
Les préparations précédentes ci-dessous sont historiques, sans effet applicatif.

Préparation38183043781/c7da012 terminée en échec avant toute activation :
verifier_bundle refusait le verrou historique Logique (objets Git SHA-1 comparés
à SHA-256).75fichiers vérifiés réellement avec leur format historique ; aucun
fichier consommé différent. Format déclaré dans le manifeste, contrôleur corrigé,
quatre régressions (acceptation, altération, format absent/inconnu) ajoutées ;
integration-securite et editorial passent. SHA-256 du bundle/reçus inchangé.
Scelleur applique désormais le même verifier_bundle complet localement avant
transport. Contrôle complet local05d1ade a refusé le .pyc créé par son import après scellement ;
aucun transport effectué. Contrôle déplacé dans un processus Python-B de lecture,
sans bytecode et avec ses modules propres. Nouveau sceau/opérateurs à publier ;
anciens stages/chiffrés conservés,
aucune tentative aveugle ni modification des données. Interfaces/binaire inchangés.

Sources qualifiées publiées b0140de44c761f202271a436882cd05195b18fd3.
Scellement réussi vers state/candidats-scelles/b0140de-transport :109011960octets,
chiffré8f338e0f2cd166aab2e56a8ccfb4c41f46f408b8df2fe5a83d1ba12f3f3611f2.
Transport publié1d64b9ac20af91cdcb61b11b01b2a7d59e8ce5db, trois parties40Mio,
branche artefacts/monolithe-b0140de44c76. Descripteur central lié aux sources et
qualification d’amendement réussie. Première tentative locale de scellement :
Nix absent du PATH, dossier vide conservé ; reprise réussie avec le Nix existant
/home/agent/.nix-profile/bin, aucune installation ni reconstruction.
Prochaine opération fermée : préparation centrale sans activation, puis
restauration fraîche/retour/bascule et sondes réelles. Production toujours ancienne.

Même tâche et architecture C ; image interactive saine conservée, aucun nouveau
qualifier MCP synthétique, aucune reconnexion. Production encore ancienne,
Keycloak conservé ; étape 1 non déployée, Kanidm non commencé.

Révisions publiées : Vision649122b, Math68df529 (master), Style27111a9,
Logiqued76f007, Signaturee9d9d34 ; hashes complets dans manifest.json.
Vision/Math consomment Style271 ; Logique conserve son verrou fbdb qualifié.
Les interfaces exactes passent : Math base14,7407s et96/96477,2098s ; Vision
interface62,7724s/navigateur-MCP23,7191s ; Stylebase131,6359s/logo264,5806s
(94parcours,2cas spécifiques à l’autre moteur) ; Logique119,9275s/correcteur14,6842s ;
Signature3,9372s. Typographie réellement peinte et contextes aux trois tailles,
contrôles AST208 et fixtures négatives exécutés. Anciennes traces conservées.

Session67854 terminée0. Elle a cependant reconstruit le fichier candidat local
au début de matheval-postgresql, faute de MRJAM_CONSTRUCTION_NIX. Reconstruction
d7c4cb1 conservée séparément dans state/artefacts, sans promotion. L’original Nix
296b7c89 reste intact dans son store ; sources Lisp inchangées. Fichier local
rétabli depuis ce store, puis qualifier_existant exécuté (21,1274s) avec provenance
originale. Qualificateur corrigé : sidecar Nix détecté, reconstruction directe
refusée ;2régressions passent. Aucun résultat d7c4 présenté comme preuve296b7.
Session56680 terminée0 : MathevalPostgreSQL22,565s/VisionPostgreSQL117,2998s/
sélection1,0666s réussis. SQLnative original16,8229s passe (session83150 terminée0).
Les35suites finales passent :34réutilisations exactes/éditorial seul rejoué.
Puis reçu MathevalPostgreSQL explicitement lié à296b7 et sélection requalifiés.
Scelleur : dernier contrôle exact avant soumission ; aucune preuve de production.
Ancien résumé archivé exactement, nouveau résumé local sans attestation CI.

Environnement exact non secret : state/qualification-env.sh ; SBCL_HOME et trois
DSOs Nix, venv navigateur existant, outils PDF inchangés. Aucun navigateur en
parallèle ni empreinte Firefox pendant son exécution. Rapport MCP non commité
préservé. Ancien résumé archivé exactement, état local consolidé ; publier les sources
centrales puis sceller le
même binaire296b7 et les quatre candidats frontend ; soumission chiffrée par Git,
préparation centrale sans activation puis restauration fraîche/retour et bascule.
Référence VPS récente38178534125 ; accès MCP réel lecture politique/séances obtenu
avant bascule, aucune écriture production. Comparer après déploiement.

## Qualification intermédiaire conservée — avant contrôle final des reçus

Infra publiée7ad2dbe (main vérifié) ; sources centrales complémentaires non
commitées préservées. Sources actuelles publiées :
Style27111a95d0222c634e55fb2e3ff8e45041b40b16,
Vision649122bb45eeaf558caa626c85b8a52b35fe8c73,
Math68df529042609561329e757145a187ca079a5cea,
Logiqued76f0074efa066098ec95c89cbf6d14da8c296cd,
Signaturee9d9d34d353422c2993cd1bc7c3c626f503bb5e0. Manifeste exact actualisé,
amendement NON qualifié. Production inchangée, étape1 non déployée, Kanidm non
commencé. Seule référence VPS en lecture seule38178534125 déclenchée ; pas SQL
mutant ni activation.

Session88512 terminée : Style271 base131,6359s ; Vision649 navigateur23,7191s
et interface62,7724s réussis. Construction Mathd817 refusée par le garde sources
(tracea98d9f111d69) : cinq amorçages suivis avaient des empreintes Elm anciennes.
Générateur existant build:main exécuté depuis l’atelier central, diff uniquement
cinq références ?v= (ni corpus ni autre source), publié68df529.

Session67854 à constater (observation, aucun PID constant) : Math68df construit,
candidat matheval-68df52904260-d69249b0/ensemble53e0fb3dfafcc9ba8791c7fa3510244be08a5d1fad1c450b5b3ebb4a45d38a01.
Caméra : 6/6 réussis (trois répétitions par moteur),51,5s ; trace ciblée privée
matheval-diagnostic-359dd4dfa881, ne remplace pas campagne complète. Base/96 en
cours puis Stylelogo271 puis12suites SBCL natives/VisionPostgreSQL/référence
historique indépendante. Tous les anciens shells12668/8233/64118/38282/88512 ont
terminé ; aucune reprise aveugle. STRICTEMENT séquentiel/set-e. Logs
state/rapports-frontends/{matheval-qualification-68df529,
style-logo-qualification-27111a9,qualification-native-nix-finale}.txt.
Environnement final : SBCL_HOME explicite vers outilsNix/sbcl/lib/sbcl et PATH
navvenv/SBCLNix/original ; trois MRJAM_LIB* Nix explicites. Les anciens reçus SBCL
empreintaient le SBCL_HOME exploratoire : contrôle natif final assumé sur la
toolchain Nix. Ne remplacer ni les PDF actuels ni l'image interactive saine.

Nouvelle correction justifiée : le test Vision visait .mrjam-ecran puis la
police du conteneur natif non peint ; il mesure maintenant texte/commande réels.
Le socle avait deux listes de polices différentes entre racines/lecteur/dialogue.
Theme.typographie mutualise la liste historique Inter/Aptos/SegoeUI/sansSerif,
police principale et fontes d'identité inchangées ; régression clavier/champ
modale aux trois tailles. Vision/Math consomment exactement271 ; Logique reste à
son verrou qualifiéfbdb, sans adoption non nécessaire. Aucun corpus/métier/modèle
ni bibliothèque tierce/toolchain modifié. Ces nouveaux candidats sont à qualifier.

Les essais intermédiaires ci-dessous sont conservés avec leurs anciennes entrées ;
ils ne sont pas des preuves de la nouvelle typographie.

C et image saine conservées : SBCL83928/Tron129399 constatés, jamais constantes
routées ; ancien79777 distinct/idle préservé. Aucun chargement/reconnexion/debug
nouveau pour le frontend. Contrôleurs MCP ciblés et usages documentés ; aucune
refonte du pont. Preuve historique réelle0,8033s/22appels vérifiée offline sans
réinitialiser fixture ; noyau/bibliothèques/lanceurs/trace inchangés, effets1,
resultat42. Nouveau routage/parser testé séparément8cas. Empreinte preuve dans
reçu, références privées copiées au bundle/préparateur ; aucune nouvelle connexion
ou scénario exécuté prétendu. Rapport MCP historique non commité préservé.

Socle/consommateurs portés : ElmUI/Animator/contextes, lecteur/note/scène/axes,
quatre entrées Math. Corpus/graines/Survey.Model/backend inchangés. Espace/Axes/
GraphiqueSpatial et événements ont des adaptateurs privés bornés ; Tableaux
flex-basis:auto constant corrige hauteur0Firefox (AST/doc/tests). Références
JSgéométriques déplacées verbatim dans docs/tests/references, hors produit.

Candidats propres construits une fois par révision :
Style30c6087e6975-16136a76 ensemble02f4216d, base138,5239s réussie ;
Logiqued76f0074efa0-cd66ef05 ensemble42954783, base139,1341s/correcteur12,8117s réussis ;
Vision2d9f31b existant conservé ; Math0b277f02800e-73b22d87 ensemble093fc670.
Math0b et8f02 assets identiques, seul interface.json change (révision identifiée).
Math8f base16,4047s ; Math0b base14,9149s et 96/96 navigateur477,8515s réussis.
Aucune source canonique modifiée par le harnais corrigé.

Campagnes Math :96pass mais garde sources refuse le harnais534,0746s ; correction
vers copie privée .central-tests-*/e2e,3tests source intacte/chemins/no-overwrite.
Surcharge4CPU/16Gio par3campagnes simultanées : timeouts clavier/Yatelier, seuls
runners arrêtés proprement ; tracesd27518040481/03933b67e84b conservées. Pas de hausse
des timeouts. Cible4scénarios passe63,4647s après sérialisation. Campagne seule8f :
95pass/1échec497,7386s : helper tactile retournait avant retrait aide/rerenduaxes ;
trace72a69aad4d47. Fix canonique helper attend count0 (état, aucun délai fixe),
publié0b277f0. Régression réelle CDPtouch3répétitions passe43,99s, traceafab2d0ebc7f.
Tous anciens résultats restent datés, aucun reçu de réussite fabriqué.

Session12668 terminée : Math0b réussit ; Stylelogo échoue sur les deux premiers
démarrages Chromium simultanés (92pass/2fail/2skip,230,6843s, trace4a43b577abaa).
Traces : création/navigation prennent le budget initial, pas erreur de géométrie.
Le harnais central limite désormais l'atelier à --workers=1 ; délais/assertions
inchangés, régression de commande ajoutée. Dix tests frontend-sources réussis.
Session8233 terminée : Stylelogo94pass/2skip303,5335s, Stylebase137,6476s,
Visioninterface69,1729s, Signature3,9372s passent. Mathbase17,0834s ; navigateur
95pass/1fail478,4127s (tracec9b1b0cee044). La trace prouve __playwright_scroll_top_=3
après la première ArrowRight : la focalisation native défile la page entre les
mesures. Test canonique focalise la scène avant mesure initiale ; précision4 et
assertions inchangées, publié53c1cfa. Aucun produit/corpus/métier modifié.
Reprise séquentielle : construire le candidat Math53 exact → Logique/MCP métier
→ régression caméra trois répétitions → campagne Math entière → qualification
native avec SBCL/contrib/DSOs Nix explicites. Même image interactive conservée.
Aucun autre navigateur en parallèle ; échec analysé avant toute reprise.
Session64118 arrêtée normalement sur échec navigateur Vision49,2026s : ancien
sélecteur .mrjam-ecran absent, trace6f52d8bb6f7a ; pas erreur métier/SQL. Test utilise
le repère accessible main, assertions de police page/dialogue conservées ;
publié068a9c6. Logique119,9275s/correcteur14,6842s réussis avant cet arrêt.
Math53 construit (b294a025), seul interface.json différent de0b. La régression
caméra et campagne complète n'ont PAS encore été exécutées pour53.


Autres preuves :208AST/6ressources/3fixtures18,7958s, géométrie336cas40,2ms ;
sélection20/source9/transport/isolation/migration/classification privés passent.
VisionPostgreSQL289,8156s réussie ; SQLnative reçu réutilisé exact. Psycopg3.2.5
venv navigateur existant (même Python3.12.14/binaire), pas installation. Référence
historique Node sur base indépendante16,2075s après correction empreinteenv ;
aucun Nodebackend cible/production. Nativepures/Lisp inchangés à réutiliser exact.

Changements centraux : orchestration scientifique/lecture/note/géométrie, AST et
ressources ; dépendances inventoriées déjà autorisées (aucun ajout opportuniste).
Empreintes DSOs seulement suites natives,2régressions ; reçus frontend inchangés
réutilisables sous env Nix. Préparateur utilise Style réellement consommé par
Vision/Logique, archives immuables privées/3régressions ; garde sources conservée.
Sondes VPS vérifient les4ElmMath +interop, pas seulement enquete.js. Historique
qualification-locale.json non réécrit ; archiver exactement avant résumé actuel.

Après jobs : comparer35reçus dans env final (SBCLNix/navvenv/DSOs existants, PDF
actuels ; ne pas remplacer par popplerNix). Pas de lecture empreinteFirefox quand
il tourne : son verrou transitoire est refusé, attendre fin des campagnes.
Qualifier processus Lisp propre à étape pertinente, préserver imageinteractive.
Commiter/pousser composants avant manifeste, sceller mêmeNix296b7c89 déjà propre,
transportchiffré central puispréparer/restaurer/basculer/sondes/redémarrage/invariants.
Backup ancien02:40 doit être réévalué, pas restauré sur SQLrécent pour retour.
Référence centrale fraîche38178534125/7ad2dbe réussie en lecture seule21:58UTC :
générationr6s7ags3 inchangée ; Vision1compteactif/admin,1identité,0orphelin/0liencroisé,
0séanceouverte ; Math1admin/1corpus/3participations toutes ouvertes. Mémoire/latences
agrégées dans state/reference-38178534125/reference.json. Téléchargement artefact
refusé403 ; même JSON complet extrait du log du run, sans nouveau dispatch.
Connecteur Vision de cet agent réellement appelé : lire_politique et lister_seances
réussis/total0, aucune écriture ni contenu personnel journalisé. À comparer après
bascule ; cette lecture ne qualifie pas encore la nouvelle image en production.


Remote relu : maininfra15496df ; PagesMath workflow/dynamicbuiltinactive mais aucun
run depuis28septembre, malgré pushesOct11 ; workflowsStyle/Logique historiques
manuellementdisabled. Protectionsmain/master403 «Resource not accessible by
integration» ; environmentvps-production lisible/branchpolicy seulement. Pages
PUTdisable422 historique concerne builtin, ne pas le confondre avec suppression
site. Vérifier mécanisme autorisé après publicationcentrale sans réactivation
satellite. Ne prétendre aucun nettoyage inaccessible accompli. Ensuite étape1
réellement constatée avant Kanidm automatique. Références/histoire ci-dessous.

## Références et résultats historiques conservés

Même tâche, état conservé. Aucun reset/nettoyage, ni nouvelle bascule.
Production : génération r6s7ags3, ancienne architecture, Keycloak provisoire ;
étape 1 non terminée, Kanidm non commencé. Aucun contenu/compte/séance/participation
fictif créé, fermé ou effacé en production. Dernière référence38118876078 : un
compte Vision/une identité, liens cohérents, trois participations Matheval ouvertes.

État avant la publication de cette reprise : infrastructure ad98feb ; branche locale
reorganisation/assemblage-central-20261011. Vision 1ef7174, Matheval/master 5e234c0,
Logique 032b4f5, Style c9663ce (chronologie et adaptateur accessibles publiés ; autres vues encore à porter), Signature e9d9d34. Consignes/guides des cinq composants
publiés avec archives exactes ; root intègre les corrections Nix/préparateur et
le refus de promotion avant qualification de l’amendement. Aucun AGENTS imbriqué/override trouvé dans les sources
actives ciblées ; relecture des six fichiers effectuée. Aucun run de promotion
actif, ni build/migration locale en cours au constat.

Image de tâche SBCL2.6.4 PID83928/session27658 conservée et saine, métier chargé ;
contrôle de reprise court réussi. L’ancien PID79777/SBCL2.5 reste séparé et idle :
ne pas le présenter comme la session commune. Swank4105/cl-mcp4106 dans ce PID ; Tron4107/PID129399, processus outil seulement.
Sources officielles/35 bibliothèques Nix auditées/verrouillées. Connexion réelle
agent→pont HTTP local qualifiée : marqueur/PID/objet11→12, condition/pile/locaux40/2,
correction enregistrée compilée/restart42, effet1 avant/après. Scénario canonique
0,8729s ; trois assertions ASDF confirmées par marqueur, compte générique amont inconnu.
Ports loopback, aucun catalogue natif hébergé prétendu modifié. Limites backtrace
RPC et installation de skills documentées dans outils/audit-mcp.md.

Travail conservé : bibliothèques ASDF Matheval/Vision/auxiliaires, serveur commun,
contrats/isolation/SQL/états durables, catalogue/sélecteur/reçus, absence de CI
satellite. Candidat Nix propre296b7c89 (12486040octets), sources158e4a5, SBCL2.6.4/
ASDF3.3.1/Nixpkgs c5c4a43. Les 31suites antérieures passent, dont Matheval56/56,
Vision API/MCP40parcours multi-comptes, RLS30/6, recherche réelle existante et
interfaces. Ces preuves restent datées ; elles ne qualifient pas l’amendement.

Promotion : asset GitHub refusé401 ; repli Git chiffré108401335octets, trois parties,
commit transport29cde31, bundle/opérateurse522c2a. Transfert/import NAR réussis ;
préparation38126827329@2f1a7c2 refusée avant activation. Diagnostic38127124960@a209c00
réussi : toutes assertions et autres invariants identiques, seuls chemins générés
PG hba_file/ident_file changent pour le peer du compte commun. Correction locale :
comparer toutes autres propriétés et contrôler les seuls ajouts HBA/IdentMap exacts
sans modifier les règles antérieures ; 13 régressions passent, incluant le refus
d’un candidat antérieur/en attente avant transfert. Correction publiée c6ecf2d ; pas encore requalifiée sur VPS. Stage privé /root/mrjam-assemblages/e522c2a… ; aucune
preparation.json ou activation.json. Aucune opération à effets de bord incertaine.

Plan actualisé et critères de passage :

1. Consolider les consignes/guides/manifestes/reprise selon l’amendement ; relire
   explicitement, verrouiller la promotion en attente de nouvelle qualification.
2. MCP installé/verrouillé et scénario réel conservé dans le rapport historique.
   Maintenir C, contrôler la cible après reconnexion, borner les chemins distants.
   Ne pas rejouer le qualifier synthétique en contrôle de santé. Continuer dans
   l'image saine ; test final propre distinct lorsque pertinent.
3. Auditer/verrouiller elm-animator/elm-review ; règles mutualisées/testées,
   alias/exposing/frontières/adaptateurs, fixture interdite qui fait échouer
   la commande canonique, contrôles HTML/CSS/JS complémentaires.
4. Corriger le socle style et interfaces affectées ; Continuous UI réel,
   focus/clavier/reduced-motion/interruption/inversion/arrêt ; requalifier selon
   impact. Réutiliser les reçus Lisp dont les entrées sont inchangées.
5. Reprendre Nix réel puis backup/restauration isolée/ACL/retour, accès API/MCP,
   même binaire et nouvelles ressources qualifiées ; bascule courte/redémarrage/
   invariants/sondes. Ni ancienne DB restaurée ni séances ouvertes clôturées.
6. Constater étape 1 en production, puis Kanidm automatiquement : nouvel IdP réel,
   politiques/sessions/révocations/MCP/panneau et propriétaire métier stable.
   Enrôlement personnel distinct ; supprimer Keycloak après accès/récupération sûrs.

Références : manifest.json, DEVELOPPEMENT.md, FRONTENDS.md, PROMOTION.md,
SECURITE.md, JOURNAL.md, reference-production.json et sauvegarde-transition.json.
Ancien protocole/registres/résultats gardés historiques sans faux acquittements.
APIs protections/environments/deploy keys403 ; Pages intégré Matheval disable422.
Ne pas prétendre leur nettoyage distant achevé. Sauvegardes/tiers conservés.

Travail affecté en cours : elm-review Nix installé (paquet2.13.5, CLI annonce2.13.4),
règles/fixtures/contrôle de qualification à intégrer ; elm-animator1.1.1 existant
référence de Matheval. L’atelier logo emploie déjà2.0.0, confirmé officiel ;
API incompatible, cible commune2.0.0 après portage explicite et qualification. Présentation CSS/HTML existante dans
Matheval/Style et adaptateurs applicatifs à corriger ; aucune conformité annoncée.
Image métier296b7c89 et suites backend inchangées restent conservées.

elm-review : configuration unique2.15.0 + règle existante unused1.2.3 + règle
AST MrJam.Presentation. 21 cas réussis et commande canonique : fixture conforme
acceptée, H.div rejeté, dépendance inutilisée rejetée (noms de règles contrôlés).
Guards sur construction et qualification de candidats existants, aucune suppression.
Sources partagées effectivement consommées : 339 violations Style/330 Vision/
466 Matheval/406 Logique, principalement les mêmes échappatoires du socle à
corriger une fois puis adopter à révision exacte. Ces échecs bloquent la promotion.
L’atelier logo est un second projet Elm dans Style : étendre le contrôle à son
elm.json, conserver la géométrie et mutualiser son lecteur/horloge Animator.

Socle de transitions publié0ea000d : lecteur Echo.Player déplacé sans doublon
vers MrJam.Transitions, utilisé par Main/abonnementLecteur. 82 anciens tests
passent ; 8 nouvelles propriétés ciblées passent (102ms), après constat que
Timeline.isRunning est vrai à init dans2.0.0 : le socle borne explicitement les
frames aux changements demandés. Réduction/inversion/continuité/cible immédiate
et durée nulle qualifiées en unités, navigateur encore requis. Consommateurs
Vision/Math/Logique restent sur leurs pins de style antérieurs jusqu'au portage.
Complément HTML/CSS/JS avec HTMLParser/Babel déjà dans Playwright1.58.2 : 3tests
(9casJS dont alias/calculé/optionnel) passent. Garde canonique branché sur build
et qualification ; rapports actuels restent en échec, dont atelier logo690
violations avant déplacement. Pas de promotion, pas de Kanidm commencé.

Style6f1a8eb publié : libellés accessibles portés vers Element.Region.description
et lienExterne vers Element.newTabLink (noopener/noreferrer natifs), galerie
compile incrémentalement. Travail suivant non commité : adaptateur DOM ID/ARIA
controls-expanded-describedby/tabindex strict et adopteurs, sans CSS. Classement
font/SVG/dialogue et portage Theme/CSS restent à poursuivre ; couleurs de marques
doit conserver leur sens avec contexte explicite, pas par CSS variables globales.
Raccordement MCP toujours sain PID83928/poolNIL/métierT ; aucun déploiement.

Progression conservée : Style c9663ce publie Accessibilite (ID, relations ARIA et
tabindex -1/0). Cinq tests DOM réussis247ms, aucune classe/style/nom arbitraire.
Règles AST26cas + fixtures canoniques + complément ressources3tests qualifiés
localement8,4137s ; assertions de test strictement bornées, renderers Animator
HTML/CSS interdits. Atelier/socle encore625violations, aucune conformité déclarée.
Image saine83928/poolNIL/métierT confirmée ; tentative de lecture d'un nom de
package incorrect refusée avant toute évaluation, corrigée à partir de la source.
Suite à poursuivre : contexte explicite de palette pour préserver les marques
sans cascade CSS, présentation elm-ui et adaptateurs manquants ; consommateurs
toujours verrouillés aux anciennes révisions, preuves frontend à renouveler.

## Interruption pour audit MCP — état historique du 11 octobre 2026, 11:55 UTC

**État historique : chantier suspendu pendant l’audit. Interruption close par
l’amendement ciblé de reprise ; voir l’état actuel ci-dessous.** Aucune consigne,
architecture, dépendance ou production modifiée par l’audit ; aucun commit,
nouvelle condition, compilation, restart ou suite de tests. Rapport autonome :
[RAPPORT-EXPERIENCE-MCP-20261011.md](RAPPORT-EXPERIENCE-MCP-20261011.md), onze
sections, preuves et plan exact de reprise. Constats privés et empreintes :
state/outils-mcp/audit-20261011.json ; état Actions dans audit-actions-20261011.json.

HEAD infra ad98feb812017391621a3533ca696b6137c456ee, branche locale
reorganisation/assemblage-central-20261011. Autres HEADs inchangés : Vision
1ef7174/main, Math 5e234c0/master, Logique 032b4f5/main, Style c9663ce/main,
Signature e9d9d34/main. Ces quatre composants hors Style sont propres.

Travail interrompu non commité, conservé :
- Infra : assemblage/elm-review/src/MrJam/Presentation.elm et
  assemblage/elm-review/tests/PresentationTest.elm.
- Style : src/MrJam.elm ; src/MrJam/{Theme,Controles,Disposition,Documents,
  Fenetres,Identite}.elm ; src/MrJam/Adaptateurs/Accessibilite.elm.
- Nouveaux fichiers Style : exemples/Contextes.elm, src/MrJam/Contexte.elm,
  src/MrJam/Adaptateurs/{Dialogue,Selection}.elm et tests/contextes.py.

Palette immuable explicite Theme.Contexte/MrJam.Contexte et MrJam.pour,
composants elm-ui colorés sans cascade, select/dialog natifs étroits,
focus explicitement rétabli après déplacement keyed. Tests ciblés Contextes
passés320/768/1440px (4,117659s), JS state/contextes.js SHA2b8e1951a4683953684a40f4d6b68c2ec7faca67948c456f2bb5b18ebab49bf7.
Nouveau test pas encore raccordé à la commande centrale, autres contextes/vues,
typographie et consommateurs à terminer. Règle AST37cas passent ; reçu canonique
frontend-regles9,5305s valide ces contrôles, pas la conformité des applications.
Dernière analyse réelle socle/atelier541violations/exit1. Aucun nouveau candidat
frontend qualifié ni changement des trois pins Style consommés. Les ajouts ARIA
suivants et les autres composants de contexte étaient prévus, pas encore écrits.

État Lisp lu sans mutation applicative : PID83928 SBCL2.6.4/ASDF3.3.1, métierT,
cl-mcp4106/Swank4105, poolNIL, pool-status0workers/0sessions affectées.
MCP_NO_WORKER_POOL="1" ; MCP_WORKER_SWANK/INIT_SYSTEM/INIT_ENTRY non définies.
TronPID129399/4107 connecté au Swank83928 ; ancienne image79777 séparée et
préservée. Objet12, effets1, résultat42 et même marqueur lus des deux côtés.
Aucun débogage suspendu : THREADNIL/LEVEL0. Les outils REPL/Swank visent
l’application ; les inspecteurs/mesures locaux Tron ne sont pas cette image
(frontière constatée dans le code, détaillée au rapport). Les outils natifs
ne sont pas enregistrés dans le catalogue hébergé ; pont HTTP réellement utilisé.

Trace synthétique antérieure22appels, empreinte canonique cd79880769a83adab908b5e25dc80040c8e0e159aff6dc821873d22b015eae9a
recalculée conforme ; toutes sources du reçu actuel inchangées. Ne pas en déduire
un total d’appels de session. Ne pas lancer qualifier-mcp.py comme simple sonde :
il réinitialise la fixture et provoque une condition. Aucune opération locale
de build/test/migration en cours ; API GitHub de l’assembleur0in_progress,
0queued,0waiting. Production non resondée pendant l’audit, dernière preuve
38118876078/ancienne générationr6s7ags3 ; aucune bascule/activation achevée.

Reprise après instructions seulement : constater mutations concurrentes/PID/
débogage ; conserver image saine ou reconstruire le seul environnement absent ;
appliquer les nouveaux choix explicitement, puis terminer le portage frontend et
ses commandes bloquantes. Publier composants avant manifeste, requalifier selon
impact ; reprendre Nix/HBA/promotion/backup/restauration/retour et sondes réelles.
Étape1 non terminée, Kanidm non commencé. Aucun reset ni répétition d’opération
à effets de bord incertaine nécessaire pour cet audit.

## Reprise actuelle après audit — architecture C conservée

Interruption levée par instruction explicite, même tâche reprise sans reset.
Image saine conservée, trois listeners loopback et identité croisée relus :
CL-MCP/Tron même PID83928, marqueur/objet12/effets1/résultat42 ; pool arrêté,
aucun débogage suspendu. Ces PID restent des observations, jamais paramètres fixes.
Les fichiers de chantier sont inchangés au constat ; aucune commande interrompue
encore active hormis les images. Aucune production modifiée ou campagne relancée.

Consignes centrales/AGENTS Lisp actualisés : architecture C, cibles distinctes,
édition structurelle facultative, sources canoniques, discipline DEBUG/restarts/
effets, revalidation après reconnexion et test propre distinct permis.
Pont HTTP borné aux cinq chemins Tron distants qualifiés, trois sondes et connexion
Swank explicitement locale ; locaux/fallbacks/inconnus refusés avant transport,
statut distant obligatoire avant opération. Garde de routage sans sandbox.
Cinq tests ciblés du pont passent0,012s, sans serveur Lisp ni mutation du calcul.
Ancienne qualification synthétique conservée historiquement ; son empreinte du
pont ne qualifie pas la modification actuelle, aucun scénario réinitialisé.

Plan actif : terminer le socle/contextes ElmUI et intégrer Contextes aux commandes
centrales ; corriger les violations réelles puis adopter les révisions dans les
consommateurs et qualifier les parcours affectés. Ensuite reprendre qualification
Nix/HBA/préconditions, promotion/sondes de l’étape1, puis Kanidm après constat réel.
Aucune nouvelle validation manuelle requise pour les décisions déjà arrêtées.

## Progression de la reprise ciblée — 11 octobre 2026

Consignes MCP publiées : Vision 9cb1fb145d6a, Math 78137b0a0e9e. Aucun code métier
modifié dans ces deux commits. Manifeste actualisé après leurs push, protection
amendement-en-cours conservée ; aucune promotion ni campagne distante lancée.
Pont : six tests isolés et reçu central outils-routage réussis0,3246s ; un diff
limité au pont sélectionne cette suite,33 évitées. Le qualifier vérifie le restart
actuel par nom/sens/position/thread/niveau et le relit après compilation ; contrôle
pur testé, scénario suspendu non rejoué. Rapport d'audit inchangé, preuve historique.

Socle frontend en sources, non encore publié/adopté : contextes explicites pour
MrJam, Documents, Donnees, Tableaux, Disposition et Pictogrammes ; rôles/états ARIA
bornés. Adaptateurs Saisie/Texte/Pictogramme sans nouvelle dépendance. Le nœud
texte échappé corrige le white-space normal imposé aux .t d'elm-ui. Le composant
Animations.deploiement impose minimum0, nécessaire au repli réel de sa hauteur.
Le raccord animations.js transmet uniquement matchMedia au port, sans animation
JS ni horloge ; corps de callback Playwright explicite pour éviter l'invocation
immédiate du disposer retourné (cause du second échec du test, pas bug du raccord).

56 cas AST passent459ms ; huit tests DOM d'accessibilité précédents conservés.
Contextes compile avec Galerie/Bibliotheque ; navigateur320/768/1440 réussi sur
JS SHA b3537d128fb954467baf10fb4ea3e96bfcd376b64765f2b48167d74007babce3 :
couleurs OKLCH de trois marques, isolation après réordonnancement/focus, select,
String/Int, tableau et palette, limite/Entrée unique, zéro/vide, dates, menu Échap/
focus, espaces/retours/mot long, SVG original, cibles44px, progression bornée,
inversions/interactions rapides/saisie pendant mouvement/arrêt des frames,
réduction pendant mouvement et au chargement, modale inerte/clavier/focus/deux
fermetures exactes. Nouveau test raccordé à la qualification centrale Style ;
package.json compile Contextes et fait partie des entrées de reçus.

Dernier contrôle réel complet de l'atelier+socle :421 violations, exit1 ; le
contrôle n'a pas atteint le second projet Style. Répartition : Echo.Render121,
Main23, Palette183, Philosophie7, Shared.Licorne2, Shared.Ui19, Blocs11,
Disposition26, Identite16, Vitrine13. Aucun écart dans les adaptateurs nouvellement
bornés, MrJam/Controles/Documents/Donnees/Lecture/Tableaux ; aucune suppression.
Cette analyse précède le nouveau composant Animations, à recontrôler ensuite.
Les pins Style des consommateurs restent historiques, aucune interface globale
qualifiée. À reprendre : typographie réservée, dialogues composés/companions,
Vitrine/Blocs, atelier ; adopter ensuite les nouvelles sources exactes, vérifier
les parcours existants et ressources, puis reprendre l'étape1 réelle et Kanidm.
Image Lisp persistante conservée, aucun DEBUG ouvert au constat, aucune cible
ni objet ancien réinventé. Production inchangée depuis les preuves précédentes.

Typographie ajoutée au socle après le reçu précédent : Typographie ne permet
que les classes littérales de la bibliothèque générée Signature et ses métriques
absentes de l'API elm-ui (1,183/baseline-.005em/synthèse/sélection). Les marqueurs
applicatifs deviennent data-mrjam-marque. Signature en ligne ne force pas une
seconde boîte d'interligne : cause du surplus42,621px trouvée en mode standards
(la sonde sans doctype en mode quirks ne reproduisait pas ce défaut). Variante
signatureEnLigne conserve la ligne commune. Fonte/contours/blobs inchangés.
Les validateurs peints précédents de Vision sont déplacés sans duplication dans
Style/tests/typographie.py ; Vision les importe depuis STYLE_MRJAM_SOURCE et
refuse une source verrouillée dépourvue du helper. Ce diff Vision est encore
non commité, pin Style non adopté : ne pas prétendre Vision qualifiée.
Contextes utilise Signature/web + Parisienne.ttf en FontFace, ressources originales
non copiées dans le bundle ; argument --signature central, entrées fonts/ttf et
helper commun ajoutées aux reçus. Nouveau navigateur complet réussi sur JS SHA
76f5d76e3694b92dd991212c92d2dccac2e8ff433778a6d1bef8eb3a4acb8dc5,
320/768/1440px, capitales et motifs de points agrandis identiques/interligne borné.
Reçu central frontend-regles9,8957s :60 tests AST +3 tests ressources et fixtures
conforme/interdite/inutilisée avec noms de règles vérifiés. Dernière analyse réelle
405 violations/exit1, Identite désormais conforme à cette règle ; reste du portage
bloquant. Consignes/pont publiés infra9801479 ; aucun déploiement. Prochaine étape
concrète : Vitrine (dimensions explicites et compléments contrôlés elm-ui), ses
consommateurs Galerie/Vision, puis dialogues/constructions/atelier. Préserver tous
les diffs Style ; publier composants avant le manifeste exact, promotion en attente.

## Chronologie frontend antérieure — historique, remplacée par le point actif

Infra publiée15496df ; lecteurs/notes communs publiés, géométrie pure en cours.
Style113169d (révision complète dans le manifeste) et
Logiqued76f007 (révision complète dans le manifeste) publiés.
Vision2d9f31bff90eed0dd330e4a568afaae92ce761f2, Math/master78137b0 et
Signaturee9d9d34 conservés. Production inchangée : étape1 non déployée,
Kanidm non commencé. Aucune CI ni opération de données déclenchée.
Rapport MCP historique non commité préservé. ArchitectureC et image saine
conservées (processus constatés83928/129399), sans reconnexion ni qualifier.

Style : socle/contextes/TeX/vidéo/gestes publiés ; iframe stable, générations,
façades publiques, frontière des adaptateurs privés. Candidat
state/frontends-candidats/style-fbdb9dbb0c72-78eef4b9,
ensemble59108d807326d74d1b58fa3e1c8d4d3b5d431ce2ab8a70d33b7e176d0db33a82.
Qualification base81,0367s, complément201,1529s :98tests Elm,
94parcours Chromium/Firefox,16comparaisons raster, géométrie/exports identiques.
Médias320/768/1440 : KaTeX réel, SDK synthétique, délai réel15s, focus/reprise,
source refusée et génération obsolète. Vidéo bornée à un lecteur visible par page.

Vision : candidat2d9f31bff90e-29425f7e / ensemble
a8e9f4e8186b194b09d7318aaea0cb94cb2f79b7d157680e4b041fda95a20198,
qualification48,3092s conservée, Style196ab46 effectivement consommé inchangé.
Les outils d'orchestration modifiés sont requalifiés au jalon final selon impact.

Logique : vues et atelier elm-ui, indice Animator mesuré, réductions initiale/live,
focus/historique/MCP et actions indépendants des animations. Geste hors Document,
fantôme commun inerte sans identifiants, horloge active seulement pendant geste.
JS limité aux pointeurs/hit-test/scroll/fichiers/reprise ; aucune CSS applicative.
Retarget tactile Chromium corrigé par prise géométrique ; scroll natif conservé.
Candidat7137ff286284-c36463f0 / ensemble
c604bd4d54cc35e9d0ff2574b1dc2adef262af61b437125fabad14ad0f6f1294,
qualification navigateur132,2951s :58exercices303TeX12bilans12vidéos,
3contrats WebMCP,4largeurs ;6ContinuousUI ;13atelier+2tactiles ;polices originales.
Deux tests historiques exigeaient CSS retirée/ancien hash du pont ; corrigés sans
changer corpus/correcteur. Autre ancien contrôle visait video.js supprimé : vise
maintenant les lecteurs communs et atelier.js. La révisiond76f007 ne change que
ce script ; unité centrale12,3742s réussie (190correcteur/299TeX/14Python/97atelier,
format), sans site navigateur artificiellement requis. Le reçu navigateur reste
celui de7137ff2 ; aucune qualification navigateur revendiquée pourd76f007.
Aligner candidat exact au jalon final avant promotion.

Contrôles centraux :136tests AST+6ressources+3fixtures réellement refusées,
10,5718s ;6tests de sources0,6622s ;18tests de sélection0,8401s.
Pas de suppressions/exclusions ni seuils abaissés. Reçus privés machine dans
state/recus, confiance locale non attestée, jamais autorisation de publication.
Stade exploratoire Logique et captures conservés dans state ; pas candidat.

Matheval en cours, non commité : lecteur scientifique commun Style48cb06a,
142tests AST11,9332s, qualification centrale Style91,9703s sur candidat
style-48cb06aaa08f-befceaca / ensemble
2514d258c02f6ae10da64f98153d67b7491596fef15f28c8e6aab55858b75ad9.
Huit cas scientifiques aux3largeurs320/390/1363 réussis, retraits comparés à
l'ancien rich-text, TeX réel/HTML échappé/Markdown/soumission bornée. Le reçu
Style-logo précédent reste historique ; additions hors logo pas encore finalisées.
Administration : Math.document, métadonnées publiques, soumission INPUT et
contexte Matheval, CSS locale retirée, compile incrémentale22puis2modules.
Trois parcours Chromium réussis8,4s sur binaire Nix296b7c89/PG jetable : accès,
activation/Entrée, corpus/statistiques/réponses avec zéro/absence et déconnexion.
Première fixture incomplète (assets absents) et environnement DSO distribution
au lieu de Nix : démarrage refusé avant parcours ; fixture préservée. Avec DSO
Nix, démarrage réussi mais instrumentation répétée dans la fixture réutilisée :
refus de tests. Nouvelle fixture neuve depuis sources canoniques, trois succès.
Aucune répétition d'effets production, aucun backend Node. Config Playwright
locale n'en lance plus ; la commande centrale possède le serveur SBCL isolé.
Prototype et DemoCard en cours, non commité : Main elm-ui/TableSpatiale/T.Transition,
mêmes BoardLogic/positions/miniscale/dimensions. Nouveau socle Spatial publié816b663,
167tests AST+6ressources+3fixtures11,3080s ; review intégral Style réussi.
Premier prototype5/7 : boîtes non peintes recouvraient les voisines en tactile,
ancrage transparent et surface transformée active corrigés ;2mobiles ciblés9,6s
réussis. Test long injecte le JSON scientifique avant chargement (aucune mutation
du vieux custom element retiré). Main et DemoCard compilés séparément, comme le
constructeur canonique ; bundle exploratoire combiné refusé à cause des ports
homonymes, conservé sans usage. Huit nouveaux parcours de continuité Firefox/
Chromium390/1280 normal/réduit passent1,2min : interruptions/inversions, Entrée/
Espace/Échap, nœud/focus préservés, préférence live et frames arrêtées au repos.
Le Demo recentre désormais une carte dans sa boîte elm-ui plutôt que le coin
absolu de l'ancien div ; aucune donnée scientifique concernée. Hauteurs explicites
compactes240desktop/360mobile, bornées par92% du viewport ; à vérifier avec le
reste des parcours avant qualification finale. test.html construit DemoCard actuel,
ancien bundle test.js retiré (histoire Git intacte). Survey encore ancien.
Math verrou Style816b663 local (SHA256 exact de tous modules/ressources utilisées),
Animator2/time existant/bezier2 transitif ; pas de mise à niveau d'outil.
Stage incrémental state/matheval-developpement-jbgia3ck (sources absolues canoniques),
pointeur matheval-developpement-courant.txt ; jamais candidat. Toutes opérations
citées locales ; rapport MCP/Image persistante et production conservés.

Avancement complémentaire : Survey lecteur elm-ui/Math.document, timeline commune,
notes facultatives avec aperçu distinct de la réponse, fermeture immédiate sans
WebAnimations ou attente "closed". Les aperçus/frames/mesures/préférences n'émettent
pas de checkpoints scientifiques. Question mesurée, lecteur placé sous l'énoncé
(cap32% viewport), commandes à droite en paysage compact. Aides à contenu défilant
borné pour conserver fermeture disponible. Stage même chemin ci-dessus, survey.js
incrémental ; Math non commité. Corpus, tirages, Model.point/S.move et serveur Lisp
inchangés. Bootstrap index/enquete identiques ; erreur de chargement rendue Elm.

Qualifications locales ciblées :181tests AST+6ressources+3fixtures12,0871s,
review Style intégral réussi. Notes : souris/clavier320/390/1363 dans Chromium143
et Firefox146 existants, un tactile Chromium réel (diagonale/annulation), sept
cas réussis depuis fixture actuelle (notes-ciblées-finales.txt).
Lecteur commun : huit formats normal/réduit, focus/défilement/changement de texte
et arrêt des frames réussis depuis sources finales (lecture-ciblee-finale.txt).
Style113169d publié : sources/correctifs/assets et tests conservés, aucune nouvelle
construction ou qualification globale Style revendiquée. Math verrou local113169d
avec tous modules et fenetres.js/notes.js supplémentaires ; manifeste Math garde
encore le verrou historique de78137b0, jusqu'au commit composant réellement publié.
Tests ajoutés à orchestration Style centrale, pas de CI déclenchée ni qualification
complète du nouveau Style revendiquée. Scénarios Math sur Nix SBCL/PG jetable :
fixture3 quatre succès17,9s avant nouveau placement ; fixture4 ciblée placement/aide
portrait un succès6,1s ; fixture5 deux portraits réussis, deux paysages échoués
(aide dépassait439px pour viewport390px), correction de hauteur de texte commune.
Fixture6 quatre succès15,0s : source exacte, zéro/absence/relecture, focus/clavier,
placement sous énoncé, aide accessible portrait/paysage, frames au repos.
Premières fixtures1/2 échouées avant lecteur : ressources puis index d'entrée ancien.
Leur trace est préservée ; index/enquete sources corrigés ensemble. Native DSOs Nix
exactes, aucune fixture instrumentée réutilisée ; copie suivante doit être neuve.
Logs/captures dans state/rapports-frontends et stage/lecteur-fixture-1..6.

Géométrie pure en cours, non publiée : Style src/MrJam/GeometrieSpatiale.elm,
exemples/Geometrie.elm et tests/geometrie.cjs. Programme Elm sans navigateur pour
comparaison avec les références frontend historiques M-moire/docs/site/space-layout.js
et slider-layout.js.323cas (12séparations3D,30poignées dont10prises surélevées,
280déplacements relatifs et projection de référence caméra0) réussis46,5ms,
compile incrémentale2modules. Comparaison de toutes positions/ordres/valeurs ;
seul cout de tri interne historique, inutilisé par la vue, absent du nouveau DTO.
Deux défauts de fixture corrigés : champ cout inclus par spread JS ; poignée
surélevée pas nécessaire dans toutes les largeurs. Aucune assertion de position
relâchée. Coordonnées originales immuables. Nouvelle entrée compilateur et test
raccordés localement dans infrastructure, empreintes des deux références dans
suite Style. Sélection18cas0,9974s et review intégral Style réussis. Geometrie
n'est pas encore consommée par Survey ; aucune conformité de sa scène revendiquée.
Logs dans state/rapports-frontends/geometrie-differentielle-*.txt ; js exploratoire
state/geometrie-developpement.js. Publier seulement après raccordement utile ou
jalon ciblé, puis verrou exact ; dernier Style publié reste113169d.

Suite immédiate : publier lecteur/note communs et verrous exacts après résultats
ciblés, terminer Survey axes/scène/contextes/compagnons et JS de mesure/pointeurs.
L'ancienne projection/sliders/rich-text restent seulement à porter, pas qualifiés.
Les quatre entrées Math, règles/ressources et ContinuousUI doivent passer sur
sources/candidat exacts ; ne pas présenter les tests des règles comme conformité
Math. Ensuite qualification finale assemblage, Nix/HBA/préconditions actuelles,
backup/restauration/retour et étape1 réelle avant Kanidm. Promotion refusée tant
que l'ensemble reste incomplet. Image SBCL de tâche saine conservée ; aucun
rechargement/reconnexion/MCP artificiel pour ce travail Elm.

## Point frontend précédent — historique, remplacé par le point actif

### Observation antérieure des candidats frontend

Infrastructure publiée15496df ; Style30c6087 publié après03a7b7f ;
Matheval8f02f64 publié avec corrections finales et verrou Style30c6087 ;
Vision2d9f31b, Logiqued76f007, Signaturee9d9d34 inchangés. Révisions complètes
assemblées dans manifest.json. Production inchangée : étape1 non déployée,
Kanidm non commencé. Aucun déclenchement CI ni opération de données pendant
cette reprise. Rapport MCP historique non commité préservé.

ArchitectureC et image saine conservées, aucun chargement/reconnexion artificiel,
aucun qualifier synthétique. Processus83928/129399 constatés, non fixés dans les
scripts ; aucun débogage ouvert connu. Outillage hors graphe produit. Les consignes
centrales et renvois C sont en vigueur ; aucune refonte du pont nécessaire.

Conservés : socle ElmUI/Animator scientifique (lecteur, note, scène, axes), quatre
entrées Matheval, contextes, contrôles AST/ressources et géométrie différentielle.
Corpus/graines/Survey.Model/backend inchangés. Références géométriques historiques
moved verbatim vers docs/tests/references, hors site. Les résultats frontend
antérieurs restent historiques : aucune conformité déduite des seuls tests AST.

Qualification ciblée :208cas AST,6ressources et3fixtures conformes/interdites
vérifiées par commande canonique,18,7958s ; review Style intégral réussi. Sélecteur
18cas et sources6cas passent1,1624s/1,2019s. Géométrie336cas (323différentiels,
13séquences des machines Elm),40,2ms. Tableaux encadrés/actions/état/focus/Tab et
transitions/reduced-motion passent aux320/768/1440px dans Contextes actuel.

Campagnes globales exactes03a7b7f/8814b8e analysées, PAS qualifiées :
Style49,6087s échoue sur Tab (corrigé) ; Matheval343,6956s :49pass/5échecs/42non
exécutés sur96. Défauts réels corrigés : Firefox tableau réduit à0 (adaptateur
flex-basis:auto constant, AST strict/documenté), restitution de focus sans
interférer avec Tab, note tactile proxy clavier seulement, proportions des axes
et scène. Assertions de sauvegarde adaptées au texte visible, renforcées par un
vrai PUT200 portant la note2, sans masquer erreurs/conflicts. Fixture19 :8pass/
2échecs proportions ; fixture20 :2passFirefox/Chromium19,8s après hauteur scène450.
Fixtures17/18 : annulation tactile note et axes confirmée, aucune note commitée
par pointercancel ; capture native/prévisualisation séparées. Diagnostics privés
state/rapports-frontends, fixtures exécutées jamais réinstrumentées.

Matheval base exacte8814b8e passe15,297s. Candidats antérieurs conservés mais
supplantés par les fixes : Style03a7b7fac2fe-4efc0ce2, Math8814b8eb9ef3-68b51f4d.
Stade incrémental privé state/matheval-developpement-jbgia3ck, pointeur courant,
quatre sorties compilées séparément. Binaire métier Nix296b7c89/DSOs store audités,
PG17 jetable, aucun backend Node, aucune donnée production.


Qualification exacte conservée : Style30c6087 base138,5239s,
Math8f02f64 base16,4047s ; Logique candidat42954783 base139,1341s et correcteur
12,8117s. Nouveaux candidats : Style30c6087e6975-16136a76/02f4216d ;
Math8f02f64b578d-5c98bd2e/1916a502 ; Logiqued76f0074efa0-cd66ef05/42954783.
Math96parcours ont tous réussi534,0746s mais qualification refusée par garde
sources (harnais ajoutait quota aux tests suivis) : diagnosticmatheval-0a410bb62774,
aucun reçu vert fabriqué. Harnais corrigé vers copie privée .central-tests-*/e2e,
profondeurs/imports identiques,3tests : source intacte, chemins, refus réutilisation.
Frontend-sources9cas passent0,7902s.

Trois campagnes lourdes simultanées ont saturé4cœurs/16Gio : pression mémoire,
timeouts Matheval clavier13/14/15 et atelierY Chromium34. Arrêt SIGINT des seuls
runners265998/268010 constatés ; cleanupPG/SBCL/worktrees par harnais normal,
tracesmatheval-d27518040481/style-03933b67e84b conservées. Aucune hausse de timeout
ni affaiblissement d'assertion. Cible Math4scénarios sérialisés passent63,4647s,
source intacte et trace6e2c8a2048ab. Jobs suivants EXCLUSIVEMENT séquentiels :
Math96 → Stylelogo → Vision/Signature → MCP métier, shellset-e, session à constater
par processus/logs (pas PID constant). Logs *final-serialise.txt / mcp-metier-final.txt.

Visionpostgresql passe289,8156s sous contention, SQLnative reçu réutilisé exact.
L'absence psycopg Python global a été corrigée en utilisant le venv navigateur
existant3.2.5, même binairePython3.12.14/empreinte, aucune installation. Bibliothèques
Nix/runtime existants, pas popplerNix à la place des outils PDF déjà qualifiés.

Contrôles centraux source6+harnais3, sélection20, sauvegarde/migration/classes
privées, transport et isolation passent. Préparateur teste désormais Style
réellement consommé plutôt que HEAD,3cas acceptation/revision/fichier altéré ;
bundle privé inclut sources verrouillées immuables. Le scénario MCP historique
0,8033s/22appels reste intact : vérification offline sourcescoeur/trace/effet1/
resultat42. Contrôleurs Python amendés qualifiés séparément par8cas routage,
aucune condition ou nouvelle connexion prétendue. Reçu inclut empreinte preuve,
tracecopiée dans bundle privé, préparateur vérifie. Manifeste reste nonqualifié.

Suite immédiate : manifeste/empreinte actualisés ; construire UNE fois les
nouveaux candidats propres,
qualifier Style base et Math base/navigateur96parcours. Rejouer seulement suites
affectées, réutiliser reçus inchangés avec provenance exacte. Ne pas confondre
AST, parcours fonctionnels et production. Ensuite aligner toutes preuves requises,
validation Lisp propre distincte sans détruire image saine, Nix/HBA actuel,
backup/restauration isolée/retour, bascule réelleAPI/MCP/invariants/redémarrage.
Kanidm seulement après constat réel étape1. Accès GitHubsettings403/Pagesdisable422
historiques, aucun nettoyage distant prétendu réussi. Références ci-dessous.
