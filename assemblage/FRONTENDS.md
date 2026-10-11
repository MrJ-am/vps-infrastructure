# Contrat frontend central — amendement du 11 octobre 2026

Toutes les interfaces Elm du périmètre utilisent elm-ui pour construire et
présenter l’interface, elm-animator pour les transitions. style-mrjam mutualise
composants, présentation et comportements communs. Les applications fournissent
intentions et état métier ; aucune seconde bibliothèque de composants ou moteur
local d’animation. Aucune dépendance Elm dans le métier Lisp ou Signature.

Pas de présentation construite avec Html, Html.Styled, elm-css, styles inline,
CSS applicatif ou HTML injecté. Document d’amorçage minimal et code produit par
les bibliothèques autorisés. Capacités spécialisées absentes : adaptateur étroit,
identifié, documenté et testé (mathématiques/SVG notamment), avec périmètre précis.
Element.html et Element.htmlAttribute réservés à ces adaptateurs ; les références
de type nécessaires au démarrage ne sont pas des violations.

elm-review devient un contrôle bloquant des commandes centrales de construction
et qualification. Règles existantes pertinentes d’abord, spécifiques seulement
si manquantes ; configuration/règles uniques dans l’infrastructure, appliquées
aux sources réellement assemblées et à la révision de style consommée. Résoudre
les symboles : alias/exposing ne contournent pas les frontières. L’animation
peut être encapsulée dans le socle ; pas d’import direct exigé dans chaque écran.
Cas conformes/non conformes par règle, fixture volontairement interdite : la
commande canonique doit échouer. Aucun vert par exclusions/suppressions globales.

HTML/CSS/JS hors Elm : contrôles complémentaires avec l’outillage existant,
adaptateurs explicites, bootstrap borné. Déclarer les limites et écarts ; un succès
statique ne prouve pas l’expérience Continuous UI. Vérifier au navigateur les
changements d’état, apparitions/disparitions/déplacements, interruptions rapides,
inversions, état/focus/navigation clavier, reduced-motion, arrêt du rafraîchissement
inutile. Aucune interaction métier ne dépend d’une animation décorative.

Les exceptions AST lient les sources communes, le module, la fonction, les
symboles autorisés et les valeurs constantes pertinentes. Aucun module exempté.
Les capacités ci-dessous manquent dans l'API publique elm-ui1.1.8 ; les libellés
ordinaires restent Element.Region.description, les liens Element.newTabLink.

| Adaptateur MrJam.Adaptateurs | Capacité bornée | Vérification effectuée |
| --- | --- | --- |
| Accessibilite | ID/relations ARIA, états, rôles constants, nom du radiogroup, tabindex -1/0, progression bornée, marqueurs fixes du pont de dialogue | Tests DOM ; tableaux, nom de groupe et focus au navigateur ; noms/valeurs de rôles contrôlés par AST |
| Selection.native | select/option natifs ; sept resets fixes de cadre, police et dimensions | Choix String/Int, clavier, focus, valeur et police aux trois largeurs |
| Dialogue.natif/assembler | dialog, événement cancel, racines sœurs sans présentation ; trois resets constants | Fond inerte, Tab/Shift-Tab, Échap, réouverture et focus restitué |
| Saisie | number/date/datetime-local + step any ; champ identifié, placeholder/maxlength ; keydown Entrée/Échap ; trois constantes de dimensions intrinsèques absentes de Length | Zéro/vide, dates, soumission unique, focus du menu ; densité des boutons courts et repli réel des libellés longs |
| Texte | Deux styles fixes pre-wrap/overflow-wrap ; nœud Html.text échappé ; emphase sémantique em sans attribut | Espaces et retours, mot long replié ; DOM em original et choix au clavier |
| Pictogramme.traits | SVG décoratif, viewport 24×24, path et attributs géométriques énumérés ; aucun événement, CSS, foreignObject ou image | Tracé original inchangé, non focalisable, nom de commande, cible 44px et couleur courante |
| Typographie | Classes littérales de Signature, métriques fractionnaires et baseline absentes de Font ; aucun nom/style libre, taille et couleur elm-ui | Fontes originales, alignement des capitales, motifs des points à zoom4, interligne borné aux trois largeurs |
| Complement.natif | details/summary natifs sans attribut ni événement ; résumé et corps construits par elm-ui | Entrée/Espace, focus visible par focused/:focus-within généré par elm-ui, état conservé après repli et redimensionnement |
| Constructions | Trois polygones et leurs ombres littérales originales, absents de l'API elm-ui ; marqueurs techniques énumérés | Pixels des encoches/languettes/cavités ouvertes, couleurs originales, trois profondeurs, clavier, sept formats et défilements bornés |
| Curseur.natif | input range, ID/nom/valeur/min/max/pas et onInput ; aucune annonce automatique, classe ou style | Clavier et tactile de l'atelier, valeur et absence d'ancêtre aria-live |
| Dessin | SVG spécialisé : contours, matrices, masques, références et quadrillage ; capacités par fonction, deux styles littéraux de comparaison | 94 parcours Chromium/Firefox, page autonome Firefox, définitions originales, quatre formats et16 comparaisons raster réussis |
| Diagrammes | Courbes/coordonnées scientifiques neutres, sélection SVG à deux axes, flèches/Maj ; quatre styles techniques littéraux | Saisies françaises/clavier, précision/URL, gestes souris dans les deux moteurs et tactiles Chromium réussis |
| Mathematiques.expression | Balise math-tex fixe, sans enfant ; seuls formula et display-mode=true, chaîne TeX échappée | KaTeX0.18.7 existant réel : MathML, texte échappé, formule hostile sans lien, trois formats ; pont avec trust=false |
| Video.lecteur/format | Conteneur course-video avec un seul iframe vide, événement video-etat, URL/titre et attributs fixes ; quatre styles constants de surface et ratio16/9 du cadre | SDK simulé, iframe réel intercepté : activation clavier, focus, reprise/arrêt, erreur, ancien lecteur détruit et promesse obsolète ignorée, hôtes invalides et SDK absent refusés aux trois formats |
| Atelier | Marqueurs data-progress/data-running/data-selected fixes, sans présentation ni identité métier | État de lecture et inspection de l'atelier |

Input.slider1.1.8 place Region.announce sur le parent produit par applyLabel,
sans option publique pour le retirer. Le curseur commun dessine piste/poignée
en elm-ui et conserve un input natif pour clavier/tactile, comme la bibliothèque,
sans cette annonce à chaque frame. Internal.Style.sliderReset rend ce proxy
invisible ; aucun nouveau CSS de poignée ou de piste n'est nécessaire.
Les scènes vectorielles conservent les mêmes courbes, matrices et couleurs ;
Echo.Render ne fait que convertir leurs résultats vers les données neutres.
Les exports SVG autonomes restent des fichiers scientifiques, pas du HTML injecté.

Le raccord JS de téléchargement autorise uniquement document.createElement("a")
dans telecharger ; le sélecteur de réglages autorise uniquement input dans
choisirReglages. Ces délégations ne permettent ni style, HTML, autre balise,
création indirecte ou animation. Cas positifs/négatifs dans le complément AST JS.
La préférence de mouvement est raccordée par animations.js ; l'atelier la lit
dans ses flags et ne répète pas l'émission initiale, pour préserver le p de l'URL.
Les mutations de focus et entrées du plan sont regroupées par microtask, sans
horloge de présentation. Les anciens curseurs géométriques restent à porter
avec leur consommateur Matheval, toujours sur son ancien verrou. Leur CSS est
retiré du nouveau Style ; cette rupture empêche une adoption Matheval sans portage.
L'export CSS de palette est une donnée scientifique produite par Elm, sans
import d'interface ; empreintes du fichier et de ses producteurs contrôlées,
reproduction CSS/JSON testée contre les sorties du constructeur existant.

Pour le texte littéral, Internal.Style.elm d'elm-ui force white-space:normal
sur les enfants .t des paragraphes (lignes1638/1651 à cette révision). Le réglage
du parent seul échoue au navigateur ; le nœud texte natif hérite correctement.
Ce raccord n'interprète aucune chaîne HTML. Les fontes et dessins réservés
restent des ressources d'identité, sans copie dans une archive publique.

Dans Input.radioHelper, le filtre events conserve Internal.Attr et ignore
Internal.Describe : Region.description ne nomme que la zone interne. nomGroupe
transmet le même libellé au radiogroup focalisable, sans attribut libre.
Length.Content produit width:auto (Internal.Style), et les enfants de row ont
flex-basis:0%. Les paragraphes souples se réduisaient au plus long mot, puis leur
hauteur était tronquée dans le bouton. Saisie.intrinseque borne width:max-content,
max-width:100% et flex-basis:auto ; aucune couleur/fonte/position/configuration
CSS exposée. Les icônes de dimensions exactes n'utilisent pas ce raccord de largeur.

Les assertions synthétiques de Test.Html.Selector.attribute dans tests/ peuvent
référencer directement les mêmes attributs ARIA, rôles ou tabindex pour vérifier le DOM.
Cette exception ne permet ni construction HTML, ni classe/style, ni nom dynamique,
ni utilisation dans les sources applicatives. Cas conformes/non conformes couvrent cette frontière.
Les renderers HTML/CSS d'Animator restent interdits, même dans le socle : seules
ses valeurs numériques et timelines raccordent les attributs elm-ui.

Conserver fonctionnalités, accessibilité, ressources, domaines/chemins et identité
visuelle. Les projets statiques restent statiques, interfaces tierces exclues.
Les anciennes interfaces sont des références fonctionnelles, pas une preuve de
conformité à ce contrat. Les nouveaux artefacts et parcours affectés doivent être
qualifiés avant promotion ; ne pas rejouer les suites Lisp arithmétiques pour du style.

Commandes canoniques :

```sh
python3 scripts/assemblage.py tester --suite frontend-regles
python3 scripts/revoir-frontends.py --composant matheval
python3 scripts/frontends.py construire --composant matheval
```

Configuration/règles/tests uniques dans elm-review/. Le constructeur et la
qualification d'un candidat déjà construit appellent le contrôle, sur chaque
projet Elm et le src/ commun réellement verrouillé ; Style inclut son atelier
logo. Le sélecteur propage une modification des règles aux interfaces/navigateurs
sans rejouer les unités Lisp. Reçus locaux non attestés, aucune permission de
publication accordée par eux. Les fixtures utilisent la même commande ; le
contrôle vérifie les noms de règles, pas seulement un code de sortie non nul.

Une commande de composant exige des producteurs propres à leurs révisions
exactes : application, Style, Signature (Signature seule pour ses tests).
Elle ne prépare ni ne vérifie le checkout d'un autre consommateur ; ses changements
concurrents sont préservés. La commande globale preparer conserve ses contrôles
de l'ensemble. Le cache Elm central déjà constitué est utilisé sans installation
opportuniste. frontend-sources vérifie ce périmètre et le refus des entrées modifiées.

Le complément ressources analyse le document d'amorçage avec HTMLParser et le
JS avec le parseur Babel déjà embarqué dans Playwright de Matheval : aucune
installation supplémentaire, aucun JS inspecté exécuté. CSS applicatif refusé ;
ressources générées de bibliothèques/typographie conservées à empreinte exacte,
interopérabilité bornée par fonction/capacité. Les alias simples de sinks DOM et
les accès calculés sont exercés ; le JS dynamique et les générateurs ne sont
pas une preuve statique complète. Contrôler également les artefacts et les
parcours de navigateur, les styles/actions/focus effectivement rendus.

État : outils/règles locaux qualifiés ; interfaces encore refusées, sans exclusion
ni suppression. Première mutualisation Animator réelle dans MrJam.Transitions
et lecteur logo ; API numérique pour attributs elm-ui, arrêt au repos/réduction.
Les autres vues, adaptateurs et ressources restent à porter/requalifier. Production
inchangée ; aucun reçu ancien utilisé pour qualifier ces nouvelles interfaces.

Contextes immuables : utiliser le même MrJam.Contexte avec les façades `pour`
de MrJam, Documents, Donnees, Tableaux, Disposition, Pictogrammes et modalePour.
Les couleurs ne dépendent plus d'une cascade CSS ou de la carte voisine. Les
fonctions historiques emploient le contexte commun ; une application de marque
doit adopter son contexte explicitement. Contextes.elm couvre320/768/1440px et
est compilé/testé par la commande centrale Style. Après fermeture du menu,
update commande Documents.restituerFocusMenu ; aucune attente d'animation.
Socle, dialogues, constructions et atelier sont portés. Les consommateurs restent
à qualifier individuellement ; les tests de règles verts ne prouvent pas leur conformité.

`MrJam.Animations.deploiement` raccorde les valeurs de Transitions à la hauteur
et à l'alpha elm-ui, avec minimum0 pour permettre le repli effectif du contenu.
Le raccord JS animations.js transmet uniquement la préférence matchMedia au port
Elm et retourne sa fonction de détachement ; il n'anime rien et n'emploie aucun
timer de rafraîchissement. Contextes exerce interruptions rapides/inversions,
focus et saisie disponibles, arrêt des frames, réduction en cours de mouvement
et préférence initiale. La qualité des autres écrans reste à vérifier après adoption.

`MrJam.Ecran` lit la largeur initiale puis les événements resize du navigateur,
sans rafraîchissement permanent. `Vitrine.pour contexte largeur` applique les
tailles/espacements mobiles historiques au seuil600px ; les anciennes fonctions
gardent la variante desktop commune. Le focus du complément est rendu par les
sélecteurs :focus-within générés par elm-ui (Internal.Model.renderStyleRule),
sans réutiliser ses classes internes ni ajouter du CSS à summary.

Vision exprime sa marque dans `interface/src/Presentation.elm` : uniquement
contexte et façades communes, sans rendu, palette ou composant parallèle.
La confirmation de copie MCP emploie Transitions/deploiement ; les contrôles
restent disponibles pendant le mouvement. Browser.Dom.getElement attend le rendu
avant le raccord de focus existant, sans horloge de présentation JS. Le seul
createElement("a") délégué à exporter produit un téléchargement Blob détaché ;
aucune classe, feuille, animation ou injection HTML n'est autorisée.
Les tests de contraste comparent les couleurs rendues à l'oracle OKLCH du
navigateur, à un niveau8bits près pour les conversions indépendantes ; ils
calculent ensuite les mêmes seuils sur les valeurs effectivement observées.

Les outils npm existants sont copiés dans les worktrees privés de construction,
sans installation. Un dossier réel garde les règles Git node_modules/ applicables,
contrairement à un lien racine ; la provenance de toutes les sources reste vérifiée
après construction et qualification. Un générateur modifiant un fichier suivi
empêche l'enregistrement du candidat. Les helpers Python d'une dépendance verrouillée
sont importés avec PYTHONDONTWRITEBYTECODE=1 ; le cache reste vérifié intégralement,
sans ignorer des fichiers ajoutés ni des différences de sources.

Le reçu Vision identifie les sources de Style à sa révision effectivement
consommée, et non à sa tête actuelle. Le candidat, les versions de navigateurs,
installations npm, profil Python, configuration Elm, bootstrap/interop et ressources
entrent dans son empreinte. Une tête Style non consommée ne remplace pas cette
preuve ; changer le verrou invalide les entrées affectées. La régression utilise
deux vrais commits Git synthétiques et vérifie les deux cas, sans modifier les
bibliothèques ni fabriquer d'attestation de publication.

Le lecteur commun ne contacte pas le fournisseur avant une action explicite.
Ses positions sont dans le modèle Elm, bornées à0..86400s ; chaque activation
a une génération, invalidée au changement de vue/arrêt. videos.js conserve
seulement le cycle de vie du SDK déjà fourni et le focus de l’iframe : aucun
DOM ordinaire créé, style ou animation. Les tests isolés emploient KaTeX réel
verrouillé de Logique et un double du SDK : ils ne prouvent pas la disponibilité
du fournisseur Vimeo. L’API0.18.7 déjà approuvée est mesurée comme outil de test
du socle ; aucune nouvelle dépendance du produit ni installation automatique.

`MrJam.Manipulation` porte seulement l'état transitoire du geste, les repères
nommés et le fantôme elm-ui (inert, sans identifiants métier dupliqués). Les
preuves, leurs historiques/certificats et le stockage restent dans Logique.
L'adaptateur privé borne les attributs de raccord, touch-action/prise, inert et
zoom50–150% : contrôle AST de la valeur canonique, tests de paramètres/let
qui masqueraient clamp. `Transitions.abonnementGeste` fournit un delta uniquement
pendant le déplacement ; JS effectue hit-test/PointerEvents/scroll, sans clone,
styles, classes ou RAF applicatif. Le pont corrige la réorientation tactile de
Chromium au point réellement peint ; les taps/scrolls natifs ordinaires restent
qualifiés. Export/import : seuls a/input détachés dans deux fonctions nommées.
Les applications utilisent les façades publiques, pas les adaptateurs privés.

Le document scientifique commun `Mathematiques.document` conserve titres/listes,
code/gras, TeX et portées initiales, sans interpréter HTML. Les unités ch ne sont
pas disponibles dans elm-ui1.1.8 : `Adaptateurs.Texte.portee` autorise seulement
padding-left calculé par `String.fromInt (Basics.max 0 espaces) ++ "ch"`, avec
un unique argument et sans let/lambda. Les métadonnées document/portée sont
nommées et littérales. La source scientifique n'est pas réécrite. Cas navigateur
positifs/hostiles, ratios de portée et repli sont intégrés à la qualification
locale Style ; le test de développement compare aussi l'ancien rendu Matheval.
`Saisie.soumettreChamps` borne keydown aux INPUT ; Entrée sur un bouton conserve
son action. Aucune animation n'est ajoutée au document statique.

Les cartes 2D Main/DemoCard passent par `TableSpatiale`, en elm-ui/Element.Keyed,
avec T.Transition et la préférence initiale/live commune. L'application fournit
coordonnées/dimensions/contenu et intentions ; le socle possède présentation et
entrées. `Adaptateurs.Spatial.taille` ne permet que scale numérique0.1–1.5, borné
par l'AST ; aucune chaîne transform libre. Les boîtes de placement non peintes
sont transparentes aux pointeurs (ancrage), la carte transformée seule les reçoit
(surface). Ce réglage fixe évite qu'une boîte non réduite capture une voisine.
Événements mousedown/touchstart/touchmove/touchend/touchcancel/click/keydown nommés
par fonction, rôle button fixe ; aucune vue HTML. Les sources Main/DemoCard sont
compilées séparément, comme dans le constructeur canonique : leurs ports de
même nom ne peuvent être regroupés dans un fichier Elm unique de développement.
