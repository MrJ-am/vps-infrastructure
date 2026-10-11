# Reprise — mission et amendement du 11 octobre 2026

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
2. Auditer/verrouiller/installer cl-mcp et cl-tron-mcp/Swank. Vérifier séparément
   installation, serveurs, connexion agent, même PID/marqueur/mutation d’objet.
   Scénario réel : condition/pile/locaux/correction enregistrée compilée/restart,
   effet déjà exécuté compté une seule fois. Continuer dans la même image.
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
