# Reprise — mission et amendement du 11 octobre 2026

Même tâche, état conservé. Aucun reset/nettoyage, ni nouvelle bascule.
Production : génération r6s7ags3, ancienne architecture, Keycloak provisoire ;
étape 1 non terminée, Kanidm non commencé. Aucun contenu/compte/séance/participation
fictif créé, fermé ou effacé en production. Dernière référence38118876078 : un
compte Vision/une identité, liens cohérents, trois participations Matheval ouvertes.

État constaté après amendement : main infrastructure 5e8342d ; branche locale
reorganisation/assemblage-central-20261011. Vision 1ef7174, Matheval/master 5e234c0,
Logique 032b4f5, Style 0ea000d (chronologie commune publiée ; autres vues encore à porter), Signature e9d9d34. Consignes/guides des cinq composants
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
