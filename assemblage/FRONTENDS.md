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

Conserver fonctionnalités, accessibilité, ressources, domaines/chemins et identité
visuelle. Les projets statiques restent statiques, interfaces tierces exclues.
Les anciennes interfaces sont des références fonctionnelles, pas une preuve de
conformité à ce contrat. Les nouveaux artefacts et parcours affectés doivent être
qualifiés avant promotion ; ne pas rejouer les suites Lisp arithmétiques pour du style.

État : dépendances/règles/intégration en cours, aucune conformité nouvelle revendiquée.
