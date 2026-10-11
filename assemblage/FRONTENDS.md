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

Adaptateur `MrJam.Adaptateurs.Accessibilite` : uniquement ID, relations
aria-controls/aria-describedby, état aria-expanded et tabindex borné à -1/0.
Ces capacités manquent dans l'API publique elm-ui1.1.8 ; les libellés utilisent
Element.Region.description et les liens externes Element.newTabLink. Cinq tests
exercent les attributs réellement rendus. Les exceptions AST lient le module
commun, la fonction, le symbole et le nom littéral d'attribut.

Les assertions synthétiques de Test.Html.Selector.attribute dans tests/ peuvent
référencer directement les mêmes attributs ARIA ou tabindex pour vérifier le DOM.
Cette exception ne permet ni construction HTML, ni classe/style, ni nom dynamique,
ni utilisation dans les sources applicatives. Cinq cas AST couvrent cette frontière.
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
