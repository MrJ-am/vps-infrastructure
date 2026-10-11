module PresentationTest exposing (tests)

import Elm.Project
import Elm.Type
import Json.Decode as Decode
import MrJam.Presentation
import Review.Project as Project
import Review.Project.Dependency as Dependency
import Review.Test
import Review.Test.Dependencies as Dependencies
import Test exposing (Test, describe, test)


details : List String
details =
    [ "Composer le socle style-mrjam/elm-ui ; les capacités absentes passent par un adaptateur nommé, borné et testé dans l'infrastructure." ]


review path source =
    Dependencies.projectWithElmCore
        |> Project.addDependency Dependencies.elmHtml
        |> Project.addDependency svgDependency
        |> Project.addModule
            { path = "dependencies/Element.elm"
            , source = "module Element exposing (html, htmlAttribute, row)\nhtml value = value\nhtmlAttribute value = value\nrow attrs children = children"
            }
        |> Project.addModule
            { path = "commun/MrJam.elm"
            , source = "module MrJam exposing (x)\nx = 1"
            }
        |> Project.addModule { path = path, source = source }
        |> Project.addModule
            { path = "dependencies/Test/Html/Selector.elm"
            , source = "module Test.Html.Selector exposing (attribute)\nattribute value = value"
            }
        |> (\project -> Review.Test.runOnModulesWithProjectData project MrJam.Presentation.rule [])


{-| Métadonnées de fixture, sans runtime SVG : les noms et exports nécessaires
à la résolution sont ceux d'elm/svg1.0.1, déjà consommé par les interfaces.
-}
svgDependency =
    let
        metadata =
            Decode.decodeString Elm.Project.decoder "{\"type\":\"package\",\"name\":\"elm/svg\",\"summary\":\"Fixture de résolution des symboles SVG\",\"license\":\"BSD-3-Clause\",\"version\":\"1.0.1\",\"exposed-modules\":[\"Svg\",\"Svg.Attributes\"],\"elm-version\":\"0.19.0 <= v < 0.20.0\",\"dependencies\":{\"elm/core\":\"1.0.0 <= v < 2.0.0\"},\"test-dependencies\":{}}"

        documenter ( nom, exports ) =
            { name = nom
            , comment = ""
            , unions = []
            , aliases = []
            , binops = []
            , values = List.map (\export -> { name = export, comment = "", tipe = Elm.Type.Var "a" }) exports
            }
    in
    case metadata of
        Ok elmJson ->
            Dependency.create "elm/svg"
                elmJson
                (List.map documenter [ ( "Svg", [ "svg", "path", "circle", "image", "mask", "foreignObject" ] ), ( "Svg.Attributes", [ "d", "style", "viewBox", "fill", "opacity", "maskUnits" ] ) ])

        Err erreur ->
            Debug.todo (Decode.errorToString erreur)


rejected moduleName path source message under =
    review path source
        |> Review.Test.expectErrorsForModules
            [ ( moduleName, [ Review.Test.error { message = message, details = details, under = under } ] ) ]


rejectedAt moduleName path source under range =
    review path source
        |> Review.Test.expectErrorsForModules
            [ ( moduleName
              , [ Review.Test.error
                    { message = "Présentation ou échappatoire technique non autorisée."
                    , details = details
                    , under = under
                    }
                    |> Review.Test.atExactly range
                ]
              )
            ]


tests : Test
tests =
    describe "Frontières et symboles résolus"
        [ test "type Html nécessaire permis" <|
            \() ->
                review "application/Main.elm" "module Main exposing (main)\nimport Html exposing (Html)\nmain : Html msg\nmain = Debug.todo \"amorçage\""
                    |> Review.Test.expectNoErrors
        , test "SVG graphique dans son adaptateur exact" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Dessin.elm" "module MrJam.Adaptateurs.Dessin exposing (definition)\nimport Svg as V\nimport Svg.Attributes as G\ndefinition chemin = V.path [ G.d chemin ] []"
                    |> Review.Test.expectNoErrors
        , test "masque vectoriel autorisé sans HTML" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Dessin.elm" "module MrJam.Adaptateurs.Dessin exposing (masque)\nimport Svg as V\nimport Svg.Attributes as G\nmasque = V.mask [ G.maskUnits \"userSpaceOnUse\" ] []"
                    |> Review.Test.expectNoErrors
        , test "rendu SVG refuse foreignObject" <|
            \() ->
                rejected "MrJam.Adaptateurs.Dessin" "commun/MrJam/Adaptateurs/Dessin.elm" "module MrJam.Adaptateurs.Dessin exposing (vue)\nimport Svg as V\nvue = V.foreignObject [] []" "Présentation ou échappatoire technique non autorisée." "V.foreignObject"
        , test "rendu SVG refuse un attribut arbitraire" <|
            \() ->
                rejected "MrJam.Adaptateurs.Dessin" "commun/MrJam/Adaptateurs/Dessin.elm" "module MrJam.Adaptateurs.Dessin exposing (vue)\nimport Html.Attributes as A\nvue = A.attribute \"onclick\" \"commande()\"" "Présentation ou échappatoire technique non autorisée." "A.attribute"
        , test "comparaison vectorielle admet son seul style littéral" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Dessin.elm" "module MrJam.Adaptateurs.Dessin exposing (vue)\nimport Html.Attributes as A\nvue = A.style \"mix-blend-mode\" \"difference\""
                    |> Review.Test.expectNoErrors
        , test "comparaison vectorielle refuse un autre style" <|
            \() ->
                rejected "MrJam.Adaptateurs.Dessin" "commun/MrJam/Adaptateurs/Dessin.elm" "module MrJam.Adaptateurs.Dessin exposing (vue)\nimport Html.Attributes as A\nvue = A.style \"background\" \"red\"" "Présentation ou échappatoire technique non autorisée." "A.style"
        , test "fonction SVG inconnue refuse les capacités voisines" <|
            \() ->
                rejected "MrJam.Adaptateurs.Dessin" "commun/MrJam/Adaptateurs/Dessin.elm" "module MrJam.Adaptateurs.Dessin exposing (autre)\nimport Svg as V\nautre = V.image [] []" "Présentation ou échappatoire technique non autorisée." "V.image"
        , test "diagramme scientifique autorisé au bon endroit" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Diagrammes.elm" "module MrJam.Adaptateurs.Diagrammes exposing (courbe)\nimport Svg as V\nimport Svg.Attributes as G\ncourbe chemin = V.path [ G.d chemin ] []"
                    |> Review.Test.expectNoErrors
        , test "diagramme interdit dans une application malgré exposing" <|
            \() ->
                rejectedAt "Graphique" "application/Graphique.elm" "module Graphique exposing (vue)\nimport Svg exposing (path)\nvue = path [] []" "path" { start = { row = 3, column = 7 }, end = { row = 3, column = 11 } }
        , test "diagramme refuse une feuille CSS de présentation" <|
            \() ->
                rejected "MrJam.Adaptateurs.Diagrammes" "commun/MrJam/Adaptateurs/Diagrammes.elm" "module MrJam.Adaptateurs.Diagrammes exposing (plan)\nimport Html.Attributes as A\nplan = A.style \"color\" \"red\"" "Présentation ou échappatoire technique non autorisée." "A.style"
        , test "curseur range natif sans annonce" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Curseur.elm" "module MrJam.Adaptateurs.Curseur exposing (natif)\nimport Html as H\nimport Html.Attributes as A\nnatif = H.input [ A.type_ \"range\", A.attribute \"aria-label\" \"Progression\" ] []"
                    |> Review.Test.expectNoErrors
        , test "curseur refuse une saisie parallèle différente" <|
            \() ->
                rejectedAt "MrJam.Adaptateurs.Curseur" "commun/MrJam/Adaptateurs/Curseur.elm" "module MrJam.Adaptateurs.Curseur exposing (natif)\nimport Html.Attributes exposing (type_)\nnatif = type_ \"text\"" "type_" { start = { row = 3, column = 9 }, end = { row = 3, column = 14 } }
        , test "curseur refuse style et classe libres" <|
            \() ->
                rejected "MrJam.Adaptateurs.Curseur" "commun/MrJam/Adaptateurs/Curseur.elm" "module MrJam.Adaptateurs.Curseur exposing (natif)\nimport Html.Attributes as A\nnatif = A.class \"vue\"" "Présentation ou échappatoire technique non autorisée." "A.class"
        , test "suivi lecteur admet son marqueur fixe" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Atelier.elm" "module MrJam.Adaptateurs.Atelier exposing (suivi)\nimport Html.Attributes as A\nsuivi = A.attribute \"data-progress\" \"0\""
                    |> Review.Test.expectNoErrors
        , test "suivi lecteur refuse attribut non borné" <|
            \() ->
                rejected "MrJam.Adaptateurs.Atelier" "commun/MrJam/Adaptateurs/Atelier.elm" "module MrJam.Adaptateurs.Atelier exposing (suivi)\nimport Html.Attributes as A\nsuivi nom = A.attribute nom \"0\"" "Présentation ou échappatoire technique non autorisée." "A.attribute"
        , test "complément natif sans présentation ni attributs" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Complement.elm" "module MrJam.Adaptateurs.Complement exposing (natif)\nimport Html as H\nimport Element as E\nnatif resume corps = E.html (H.details [] [ H.summary [] [ resume ], corps ])"
                    |> Review.Test.expectNoErrors
        , test "complément sans liste arbitraire d'attributs" <|
            \() ->
                rejected "MrJam.Adaptateurs.Complement"
                    "commun/MrJam/Adaptateurs/Complement.elm"
                    "module MrJam.Adaptateurs.Complement exposing (natif)\nimport Html as H\nnatif attrs resume = H.summary attrs [ resume ]"
                    "Présentation ou échappatoire technique non autorisée."
                    "H.summary"
        , test "complément n'autorise pas une construction parallèle" <|
            \() ->
                rejected "MrJam.Adaptateurs.Complement"
                    "commun/MrJam/Adaptateurs/Complement.elm"
                    "module MrJam.Adaptateurs.Complement exposing (natif)\nimport Html as H\nnatif = H.div [] []"
                    "Présentation ou échappatoire technique non autorisée."
                    "H.div"
        , test "complément applicatif homonyme refusé" <|
            \() ->
                review "application/MrJam/Adaptateurs/Complement.elm"
                    "module MrJam.Adaptateurs.Complement exposing (natif)\nimport Html as H\nnatif = H.details [] []"
                    |> Review.Test.expectErrorsForModules
                        [ ( "MrJam.Adaptateurs.Complement"
                          , [ Review.Test.error { message = "Le namespace MrJam appartient aux sources communes verrouillées.", details = details, under = "module" }
                            , Review.Test.error { message = "Présentation ou échappatoire technique non autorisée.", details = details, under = "H.details" }
                            ]
                          )
                        ]
        , test "interligne original du titre de vitrine" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Typographie.elm" "module MrJam.Adaptateurs.Typographie exposing (titreVitrine)\nimport Html.Attributes as A\ntitreVitrine = A.style \"line-height\" \"1.06\""
                    |> Review.Test.expectNoErrors
        , test "titre sans CSS supplémentaire" <|
            \() ->
                rejected "MrJam.Adaptateurs.Typographie"
                    "commun/MrJam/Adaptateurs/Typographie.elm"
                    "module MrJam.Adaptateurs.Typographie exposing (titreVitrine)\nimport Html.Attributes as A\ntitreVitrine = A.style \"font-size\" \"58px\""
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "dialogue intégré dans la même racine Element" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Dialogue.elm" "module MrJam.Adaptateurs.Dialogue exposing (integrer)\nimport Element as E\nintegrer = E.html"
                    |> Review.Test.expectNoErrors
        , test "emphase sémantique sans attribut HTML" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Texte.elm" "module MrJam.Adaptateurs.Texte exposing (emphase)\nimport Element as E\nimport Html as H\nemphase texte = E.html (H.em [] [H.text texte])"
                    |> Review.Test.expectNoErrors
        , test "emphase sans attribut libre" <|
            \() ->
                rejected "MrJam.Adaptateurs.Texte" "commun/MrJam/Adaptateurs/Texte.elm" "module MrJam.Adaptateurs.Texte exposing (emphase)\nimport Html as H\nemphase attrs texte = H.em attrs [H.text texte]" "Présentation ou échappatoire technique non autorisée." "H.em"
        , test "encoche originale littérale" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Constructions.elm" "module MrJam.Adaptateurs.Constructions exposing (encocheEntete)\nimport Html.Attributes as A\nencocheEntete = A.style \"clip-path\" \"polygon(0 0,15px 0,21px 5px,38px 5px,44px 0,100% 0,100% 100%,0 100%)\""
                    |> Review.Test.expectNoErrors
        , test "aucun contour arbitraire" <|
            \() ->
                rejected "MrJam.Adaptateurs.Constructions" "commun/MrJam/Adaptateurs/Constructions.elm" "module MrJam.Adaptateurs.Constructions exposing (encocheEntete)\nimport Html.Attributes as A\nencocheEntete valeur = A.style \"clip-path\" forme" "Présentation ou échappatoire technique non autorisée." "A.style"
        , test "pas de couleur de présentation par l’adaptateur" <|
            \() ->
                rejected "MrJam.Adaptateurs.Constructions" "commun/MrJam/Adaptateurs/Constructions.elm" "module MrJam.Adaptateurs.Constructions exposing (encocheEntete)\nimport Html.Attributes as A\nencocheEntete valeur = A.style \"color\" \"yellow\"" "Présentation ou échappatoire technique non autorisée." "A.style"
        , test "aucun filtre arbitraire" <|
            \() ->
                rejected "MrJam.Adaptateurs.Constructions" "commun/MrJam/Adaptateurs/Constructions.elm" "module MrJam.Adaptateurs.Constructions exposing (selectionne)\nimport Html.Attributes as A\nselectionne valeur = A.style \"filter\" valeur" "Présentation ou échappatoire technique non autorisée." "A.style"
        , test "fonction de raccord précisément nommée" <|
            \() ->
                rejected "MrJam.Adaptateurs.Constructions" "commun/MrJam/Adaptateurs/Constructions.elm" "module MrJam.Adaptateurs.Constructions exposing (autre)\nimport Html.Attributes as A\nautre valeur = A.style \"clip-path\" \"polygon(0 0,15px 0,21px 5px,38px 5px,44px 0,100% 0,100% 100%,0 100%)\"" "Présentation ou échappatoire technique non autorisée." "A.style"
        , test "pas de classe de présentation" <|
            \() ->
                rejected "MrJam.Adaptateurs.Constructions" "commun/MrJam/Adaptateurs/Constructions.elm" "module MrJam.Adaptateurs.Constructions exposing (repere)\nimport Html.Attributes as A\nrepere valeur = A.class \"bloc\"" "Présentation ou échappatoire technique non autorisée." "A.class"
        , test "marqueur sans nom arbitraire" <|
            \() ->
                rejected "MrJam.Adaptateurs.Constructions" "commun/MrJam/Adaptateurs/Constructions.elm" "module MrJam.Adaptateurs.Constructions exposing (repere)\nimport Html.Attributes as A\nrepere valeur = A.attribute nom \"bloc\"" "Présentation ou échappatoire technique non autorisée." "A.attribute"
        , test "marqueur technique de construction borné" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Constructions.elm" "module MrJam.Adaptateurs.Constructions exposing (repere)\nimport Html.Attributes as A\nrepere = A.attribute \"data-mrjam-construction\" \"bloc\""
                    |> Review.Test.expectNoErrors
        , test "dimensions intrinsèques bornées du bouton" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Saisie.elm" "module MrJam.Adaptateurs.Saisie exposing (intrinseque)\nimport Html.Attributes as A\nintrinseque = [ A.style \"width\" \"max-content\", A.style \"max-width\" \"100%\", A.style \"flex-basis\" \"auto\" ]"
                    |> Review.Test.expectNoErrors
        , test "dimensions sans largeur configurable" <|
            \() ->
                rejected "MrJam.Adaptateurs.Saisie"
                    "commun/MrJam/Adaptateurs/Saisie.elm"
                    "module MrJam.Adaptateurs.Saisie exposing (intrinseque)\nimport Html.Attributes as A\nintrinseque valeur = A.style \"width\" valeur"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "dimensions sans présentation arbitraire" <|
            \() ->
                rejected "MrJam.Adaptateurs.Saisie"
                    "commun/MrJam/Adaptateurs/Saisie.elm"
                    "module MrJam.Adaptateurs.Saisie exposing (intrinseque)\nimport Html.Attributes as A\nintrinseque = A.style \"background\" \"red\""
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "nom du radiogroup transmis par attribut borné" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Accessibilite.elm"
                    "module MrJam.Adaptateurs.Accessibilite exposing (nomGroupe)\nimport Html.Attributes as A\nnomGroupe libelle = A.attribute \"aria-label\" libelle"
                    |> Review.Test.expectNoErrors
        , test "nom de groupe sans attribut arbitraire" <|
            \() ->
                rejected "MrJam.Adaptateurs.Accessibilite"
                    "commun/MrJam/Adaptateurs/Accessibilite.elm"
                    "module MrJam.Adaptateurs.Accessibilite exposing (nomGroupe)\nimport Html.Attributes as A\nnomGroupe valeur = A.attribute \"onclick\" valeur"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.attribute"
        , test "type natif date borné permis par alias" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Saisie.elm" "module MrJam.Adaptateurs.Saisie exposing (date)\nimport Html.Attributes as A\ndate = A.type_ \"date\""
                    |> Review.Test.expectNoErrors
        , test "un type natif ne devient pas une échappatoire arbitraire" <|
            \() ->
                rejected "MrJam.Adaptateurs.Saisie"
                    "commun/MrJam/Adaptateurs/Saisie.elm"
                    "module MrJam.Adaptateurs.Saisie exposing (date)\nimport Html.Attributes as A\ndate = A.type_ \"password\""
                    "Présentation ou échappatoire technique non autorisée."
                    "A.type_"
        , test "step natif fixe seulement" <|
            \() ->
                rejected "MrJam.Adaptateurs.Saisie"
                    "commun/MrJam/Adaptateurs/Saisie.elm"
                    "module MrJam.Adaptateurs.Saisie exposing (nombre)\nimport Html.Attributes as A\nnombre valeur = A.step valeur"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.step"
        , test "Entrée utilise uniquement keydown" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Saisie.elm" "module MrJam.Adaptateurs.Saisie exposing (soumettre)\nimport Html.Events as E\nsoumettre message = E.preventDefaultOn \"keydown\" message"
                    |> Review.Test.expectNoErrors
        , test "soumission ne gagne pas un événement libre" <|
            \() ->
                rejected "MrJam.Adaptateurs.Saisie"
                    "commun/MrJam/Adaptateurs/Saisie.elm"
                    "module MrJam.Adaptateurs.Saisie exposing (soumettre)\nimport Html.Events as E\nsoumettre message = E.preventDefaultOn \"click\" message"
                    "Présentation ou échappatoire technique non autorisée."
                    "E.preventDefaultOn"
        , test "espaces littéraux bornés permis" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Texte.elm" "module MrJam.Adaptateurs.Texte exposing (litteral)\nimport Html.Attributes as A\nlitteral = A.style \"white-space\" \"pre-wrap\""
                    |> Review.Test.expectNoErrors
        , test "adaptateur littéral ne donne pas du CSS libre" <|
            \() ->
                rejected "MrJam.Adaptateurs.Texte"
                    "commun/MrJam/Adaptateurs/Texte.elm"
                    "module MrJam.Adaptateurs.Texte exposing (litteral)\nimport Html.Attributes as A\nlitteral = A.style \"color\" \"red\""
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "nœud texte échappé sans élément HTML permis" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Texte.elm" "module MrJam.Adaptateurs.Texte exposing (texte)\nimport Html as H\nimport Element as E\ntexte = E.html << H.text"
                    |> Review.Test.expectNoErrors
        , test "adaptateur texte ne devient pas constructeur HTML" <|
            \() ->
                rejected "MrJam.Adaptateurs.Texte"
                    "commun/MrJam/Adaptateurs/Texte.elm"
                    "module MrJam.Adaptateurs.Texte exposing (texte)\nimport Html as H\ntexte = H.span [] []"
                    "Présentation ou échappatoire technique non autorisée."
                    "H.span"
        , test "pictogramme décoratif non focalisable borné" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Pictogramme.elm" "module MrJam.Adaptateurs.Pictogramme exposing (traits)\nimport Html.Attributes as A\ntraits = A.attribute \"focusable\" \"false\""
                    |> Review.Test.expectNoErrors
        , test "un pictogramme décoratif ne devient pas focalisable" <|
            \() ->
                rejected "MrJam.Adaptateurs.Pictogramme"
                    "commun/MrJam/Adaptateurs/Pictogramme.elm"
                    "module MrJam.Adaptateurs.Pictogramme exposing (traits)\nimport Html.Attributes as A\ntraits = A.attribute \"focusable\" \"true\""
                    "Présentation ou échappatoire technique non autorisée."
                    "A.attribute"
        , test "pictogramme ne permet pas un élément HTML" <|
            \() ->
                rejected "MrJam.Adaptateurs.Pictogramme"
                    "commun/MrJam/Adaptateurs/Pictogramme.elm"
                    "module MrJam.Adaptateurs.Pictogramme exposing (traits)\nimport Html as H\ntraits = H.div [] []"
                    "Présentation ou échappatoire technique non autorisée."
                    "H.div"
        , test "tracé SVG résolu par alias dans son adaptateur" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Pictogramme.elm" "module MrJam.Adaptateurs.Pictogramme exposing (traits)\nimport Svg as S\nimport Svg.Attributes as G\ntraits chemin = S.path [ G.d chemin ] []"
                    |> Review.Test.expectNoErrors
        , test "tracé SVG applicatif exposé interdit" <|
            \() ->
                rejectedAt "Main"
                    "application/Main.elm"
                    "module Main exposing (x)\nimport Svg exposing (path)\nx = path [] []"
                    "path"
                    { start = { row = 3, column = 5 }, end = { row = 3, column = 9 } }
        , test "adaptateur de tracés ne gagne pas foreignObject" <|
            \() ->
                rejected "MrJam.Adaptateurs.Pictogramme"
                    "commun/MrJam/Adaptateurs/Pictogramme.elm"
                    "module MrJam.Adaptateurs.Pictogramme exposing (traits)\nimport Svg as S\ntraits = S.foreignObject [] []"
                    "Présentation ou échappatoire technique non autorisée."
                    "S.foreignObject"
        , test "classe littérale de la fonte générée permise seulement dans signature" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Typographie.elm" "module MrJam.Adaptateurs.Typographie exposing (signature)\nimport Html.Attributes as A\nsignature = A.class \"mrjam\""
                    |> Review.Test.expectNoErrors
        , test "même adaptateur ne gagne pas une classe de présentation" <|
            \() ->
                rejected "MrJam.Adaptateurs.Typographie"
                    "commun/MrJam/Adaptateurs/Typographie.elm"
                    "module MrJam.Adaptateurs.Typographie exposing (signature)\nimport Html.Attributes as A\nsignature = A.class \"carte\""
                    "Présentation ou échappatoire technique non autorisée."
                    "A.class"
        , test "métrique fractionnaire précise permise" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Typographie.elm" "module MrJam.Adaptateurs.Typographie exposing (signature)\nimport Html.Attributes as A\nsignature = A.style \"line-height\" \"1.183\""
                    |> Review.Test.expectNoErrors
        , test "métrique typographique ne devient pas réglage libre" <|
            \() ->
                rejected "MrJam.Adaptateurs.Typographie"
                    "commun/MrJam/Adaptateurs/Typographie.elm"
                    "module MrJam.Adaptateurs.Typographie exposing (signature)\nimport Html.Attributes as A\nsignature h = A.style \"line-height\" h"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "TeX partagé avec alias et attribut échappé" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Mathematiques.elm" "module MrJam.Adaptateurs.Mathematiques exposing (expression)\nimport Html as H\nimport Html.Attributes as A\nexpression s = H.node \"math-tex\" [ A.attribute \"formula\" s, A.attribute \"display-mode\" \"true\" ] []"
                    |> Review.Test.expectNoErrors
        , test "TeX partagé avec symbole exposé" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Mathematiques.elm" "module MrJam.Adaptateurs.Mathematiques exposing (expression)\nimport Html exposing (node)\nexpression = node \"math-tex\" [] []"
                    |> Review.Test.expectNoErrors
        , test "TeX ne reçoit pas une autre balise" <|
            \() ->
                rejected "MrJam.Adaptateurs.Mathematiques"
                    "commun/MrJam/Adaptateurs/Mathematiques.elm"
                    "module MrJam.Adaptateurs.Mathematiques exposing (expression)\nimport Html as H\nexpression = H.node \"div\" [] []"
                    "Présentation ou échappatoire technique non autorisée."
                    "H.node"
        , test "TeX ne reçoit pas une balise dynamique" <|
            \() ->
                rejectedAt "MrJam.Adaptateurs.Mathematiques"
                    "commun/MrJam/Adaptateurs/Mathematiques.elm"
                    "module MrJam.Adaptateurs.Mathematiques exposing (expression)\nimport Html exposing (node)\nexpression tag = node tag [] []"
                    "node"
                    { start = { row = 3, column = 18 }, end = { row = 3, column = 22 } }
        , test "TeX ne reçoit pas des enfants dynamiques" <|
            \() ->
                rejected "MrJam.Adaptateurs.Mathematiques"
                    "commun/MrJam/Adaptateurs/Mathematiques.elm"
                    "module MrJam.Adaptateurs.Mathematiques exposing (expression)\nimport Html as H\nexpression children = H.node \"math-tex\" [] children"
                    "Présentation ou échappatoire technique non autorisée."
                    "H.node"
        , test "TeX refuse des attributs de présentation exposés" <|
            \() ->
                rejectedAt "MrJam.Adaptateurs.Mathematiques"
                    "commun/MrJam/Adaptateurs/Mathematiques.elm"
                    "module MrJam.Adaptateurs.Mathematiques exposing (expression)\nimport Html.Attributes exposing (attribute)\nexpression = attribute \"class\" \"carte\""
                    "attribute"
                    { start = { row = 3, column = 14 }, end = { row = 3, column = 23 } }
        , test "TeX borne le mode bloc" <|
            \() ->
                rejected "MrJam.Adaptateurs.Mathematiques"
                    "commun/MrJam/Adaptateurs/Mathematiques.elm"
                    "module MrJam.Adaptateurs.Mathematiques exposing (expression)\nimport Html.Attributes as A\nexpression mode = A.attribute \"display-mode\" mode"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.attribute"
        , test "TeX refuse un nom attribut dynamique" <|
            \() ->
                rejected "MrJam.Adaptateurs.Mathematiques"
                    "commun/MrJam/Adaptateurs/Mathematiques.elm"
                    "module MrJam.Adaptateurs.Mathematiques exposing (expression)\nimport Html.Attributes as A\nexpression name s = A.attribute name s"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.attribute"
        , test "un faux raccord TeX applicatif est refusé" <|
            \() ->
                review "application/MrJam/Adaptateurs/Mathematiques.elm"
                    "module MrJam.Adaptateurs.Mathematiques exposing (expression)\nimport Html as H\nexpression = H.node \"math-tex\" [] []"
                    |> Review.Test.expectErrorsForModules
                        [ ( "MrJam.Adaptateurs.Mathematiques"
                          , [ Review.Test.error { message = "Présentation ou échappatoire technique non autorisée.", details = details, under = "H.node" }
                            , Review.Test.error { message = "Le namespace MrJam appartient aux sources communes verrouillées.", details = details, under = "module" }
                            ]
                          )
                        ]
        , test "iframe partagée bornée par sa surface" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Video.elm" "module MrJam.Adaptateurs.Video exposing (lecteur)\nimport Html as H\nimport Html.Attributes as A\nlecteur url = H.node \"course-video\" [] [ H.iframe [ A.src url, A.style \"aspect-ratio\" \"16/9\", A.attribute \"referrerpolicy\" \"strict-origin-when-cross-origin\" ] [] ]"
                    |> Review.Test.expectNoErrors
        , test "iframe avec import exposé" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Video.elm" "module MrJam.Adaptateurs.Video exposing (lecteur)\nimport Html exposing (node, iframe)\nlecteur = node \"course-video\" [] [ iframe [] [] ]"
                    |> Review.Test.expectNoErrors
        , test "iframe sans contenu interprété" <|
            \() ->
                rejected "MrJam.Adaptateurs.Video"
                    "commun/MrJam/Adaptateurs/Video.elm"
                    "module MrJam.Adaptateurs.Video exposing (lecteur)\nimport Html as H\nlecteur children = H.iframe [] children"
                    "Présentation ou échappatoire technique non autorisée."
                    "H.iframe"
        , test "conteneur vidéo ne reçoit pas des enfants arbitraires" <|
            \() ->
                rejected "MrJam.Adaptateurs.Video"
                    "commun/MrJam/Adaptateurs/Video.elm"
                    "module MrJam.Adaptateurs.Video exposing (lecteur)\nimport Html as H\nlecteur children = H.node \"course-video\" [] children"
                    "Présentation ou échappatoire technique non autorisée."
                    "H.node"
        , test "conteneur vidéo ne devient pas une div" <|
            \() ->
                rejected "MrJam.Adaptateurs.Video"
                    "commun/MrJam/Adaptateurs/Video.elm"
                    "module MrJam.Adaptateurs.Video exposing (lecteur)\nimport Html as H\nlecteur = H.node \"div\" [] []"
                    "Présentation ou échappatoire technique non autorisée."
                    "H.node"
        , test "SDK écoute seulement son événement déclaré" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Video.elm" "module MrJam.Adaptateurs.Video exposing (lecteur)\nimport Html.Events as E\nlecteur decode = E.on \"video-etat\" decode"
                    |> Review.Test.expectNoErrors
        , test "SDK ne gagne pas des événements arbitraires" <|
            \() ->
                rejected "MrJam.Adaptateurs.Video"
                    "commun/MrJam/Adaptateurs/Video.elm"
                    "module MrJam.Adaptateurs.Video exposing (lecteur)\nimport Html.Events as E\nlecteur nom decode = E.on nom decode"
                    "Présentation ou échappatoire technique non autorisée."
                    "E.on"
        , test "SDK ne gagne pas un style dynamique" <|
            \() ->
                rejected "MrJam.Adaptateurs.Video"
                    "commun/MrJam/Adaptateurs/Video.elm"
                    "module MrJam.Adaptateurs.Video exposing (lecteur)\nimport Html.Attributes as A\nlecteur largeur = A.style \"width\" largeur"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "SDK garde sa politique de référent" <|
            \() ->
                rejected "MrJam.Adaptateurs.Video"
                    "commun/MrJam/Adaptateurs/Video.elm"
                    "module MrJam.Adaptateurs.Video exposing (lecteur)\nimport Html.Attributes as A\nlecteur = A.attribute \"referrerpolicy\" \"unsafe-url\""
                    "Présentation ou échappatoire technique non autorisée."
                    "A.attribute"
        , test "SDK ne reçoit pas de srcdoc" <|
            \() ->
                rejected "MrJam.Adaptateurs.Video"
                    "commun/MrJam/Adaptateurs/Video.elm"
                    "module MrJam.Adaptateurs.Video exposing (lecteur)\nimport Html.Attributes as A\nlecteur code = A.attribute \"srcdoc\" code"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.attribute"
        , test "le ratio technique vidéo reste constant" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Video.elm" "module MrJam.Adaptateurs.Video exposing (format)\nimport Html.Attributes as A\nformat = A.style \"aspect-ratio\" \"16/9\""
                    |> Review.Test.expectNoErrors
        , test "le ratio vidéo ne devient pas une capacité CSS libre" <|
            \() ->
                rejected "MrJam.Adaptateurs.Video"
                    "commun/MrJam/Adaptateurs/Video.elm"
                    "module MrJam.Adaptateurs.Video exposing (format)\nimport Html.Attributes as A\nformat valeur = A.style \"aspect-ratio\" valeur"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "adaptateur privé ne devient pas une API applicative" <|
            \() ->
                rejected "Main"
                    "application/Main.elm"
                    "module Main exposing (x)\nimport MrJam.Adaptateurs.Video as V\nx = 1"
                    "Frontière du socle partagé contournée."
                    "import MrJam.Adaptateurs.Video as V"
        , test "import exposé ne contourne pas la façade" <|
            \() ->
                rejected "Main"
                    "application/Main.elm"
                    "module Main exposing (x)\nimport MrJam.Adaptateurs.Mathematiques exposing (expression)\nx = 1"
                    "Frontière du socle partagé contournée."
                    "import MrJam.Adaptateurs.Mathematiques exposing (expression)"
        , test "façade publique accessible à l'application" <|
            \() ->
                review "application/Main.elm" "module Main exposing (x)\nimport MrJam.Mathematiques as Math\nx = 1"
                    |> Review.Test.expectNoErrors
        , test "Html.div par alias rejeté" <|
            \() ->
                rejected "Main"
                    "application/Main.elm"
                    "module Main exposing (main)\nimport Html as H\nmain = H.div [] []"
                    "Présentation ou échappatoire technique non autorisée."
                    "H.div"
        , test "Html.div exposé rejeté" <|
            \() ->
                rejectedAt "Main"
                    "application/Main.elm"
                    "module Main exposing (main)\nimport Html exposing (div)\nmain = div [] []"
                    "div"
                    { start = { row = 3, column = 8 }, end = { row = 3, column = 11 } }
        , test "CSS inline exposé rejeté même dans un module commun" <|
            \() ->
                rejectedAt "MrJam.Test"
                    "commun/MrJam/Test.elm"
                    "module MrJam.Test exposing (x)\nimport Html.Attributes exposing (style)\nx = style \"color\" \"red\""
                    "style"
                    { start = { row = 3, column = 5 }, end = { row = 3, column = 10 } }
        , test "Html.Styled interdit même sans usage" <|
            \() ->
                rejected "Main"
                    "application/Main.elm"
                    "module Main exposing (x)\nimport Html.Styled as H\nx = 1"
                    "Frontière du socle partagé contournée."
                    "import Html.Styled as H"
        , test "Animator dans l'application interdit" <|
            \() ->
                rejected "Main"
                    "application/Main.elm"
                    "module Main exposing (x)\nimport Animator as A\nx = 1"
                    "Frontière du socle partagé contournée."
                    "import Animator as A"
        , test "Animator peut être encapsulé dans le socle" <|
            \() ->
                review "commun/MrJam/Transitions.elm" "module MrJam.Transitions exposing (x)\nimport Animator as A\nx = 1"
                    |> Review.Test.expectNoErrors
        , test "pas d'import Animator exigé dans les modules métier" <|
            \() ->
                review "application/Calcul.elm" "module Calcul exposing (x)\nx = 1 + 1"
                    |> Review.Test.expectNoErrors
        , test "palette interne inaccessible à l'application" <|
            \() ->
                rejected "Main"
                    "application/Main.elm"
                    "module Main exposing (x)\nimport MrJam.Theme as T\nx = 1"
                    "Frontière du socle partagé contournée."
                    "import MrJam.Theme as T"
        , test "le socle ne dépend pas de l'application" <|
            \() ->
                rejected "MrJam.Test"
                    "commun/MrJam/Test.elm"
                    "module MrJam.Test exposing (x)\nimport Main\nx = 1"
                    "Frontière du socle partagé contournée."
                    "import Main"
        , test "un faux module MrJam applicatif ne gagne pas de droits" <|
            \() ->
                rejected "MrJam.Faux"
                    "application/MrJam/Faux.elm"
                    "module MrJam.Faux exposing (x)\nx = 1"
                    "Le namespace MrJam appartient aux sources communes verrouillées."
                    "module"
        , test "adaptateur ARIA nommé et littéral précis permis" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Accessibilite.elm" "module MrJam.Adaptateurs.Accessibilite exposing (controle)\nimport Html.Attributes as A\ncontrole label = A.attribute \"aria-controls\" label"
                    |> Review.Test.expectNoErrors
        , test "le nom de l'adaptateur n'autorise pas une classe" <|
            \() ->
                rejected "MrJam.Adaptateurs.Accessibilite"
                    "commun/MrJam/Adaptateurs/Accessibilite.elm"
                    "module MrJam.Adaptateurs.Accessibilite exposing (controle)\nimport Html.Attributes as A\ncontrole label = A.attribute \"class\" label"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.attribute"
        , test "attribut arbitraire même dans adaptateur rejeté" <|
            \() ->
                rejected "MrJam.Adaptateurs.Accessibilite"
                    "commun/MrJam/Adaptateurs/Accessibilite.elm"
                    "module MrJam.Adaptateurs.Accessibilite exposing (controle)\nimport Html.Attributes as A\ncontrole name = A.attribute name \"foo\""
                    "Présentation ou échappatoire technique non autorisée."
                    "A.attribute"
        , test "un autre nom de fonction ne profite pas de l'exception" <|
            \() ->
                rejected "MrJam.Adaptateurs.Accessibilite"
                    "commun/MrJam/Adaptateurs/Accessibilite.elm"
                    "module MrJam.Adaptateurs.Accessibilite exposing (autre)\nimport Html.Attributes as A\nautre label = A.attribute \"aria-controls\" label"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.attribute"
        , test "Element.html par alias rejeté" <|
            \() ->
                rejected "Main"
                    "application/Main.elm"
                    "module Main exposing (x)\nimport Element as UI\nx = UI.html 1"
                    "Présentation ou échappatoire technique non autorisée."
                    "UI.html"
        , test "Element.htmlAttribute exposé rejeté" <|
            \() ->
                rejectedAt "Main"
                    "application/Main.elm"
                    "module Main exposing (x)\nimport Element exposing (htmlAttribute)\nx = htmlAttribute 1"
                    "htmlAttribute"
                    { start = { row = 3, column = 5 }, end = { row = 3, column = 18 } }
        , test "une variable locale appelée div ne désigne pas Html.div" <|
            \() ->
                review "application/Main.elm" "module Main exposing (x)\nimport Html exposing (div)\nx = let div = 1 in div"
                    |> Review.Test.expectNoErrors
        , test "adapter Element.htmlAttribute borné permis" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Accessibilite.elm" "module MrJam.Adaptateurs.Accessibilite exposing (identifiant)\nimport Element as UI\nimport Html.Attributes as A\nidentifiant id = UI.htmlAttribute (A.id id)"
                    |> Review.Test.expectNoErrors
        , test "vue avec socle partagé conforme" <|
            \() ->
                review "application/Main.elm" "module Main exposing (x)\nimport Element\nimport MrJam\nx = Element.row [] [MrJam.x]"
                    |> Review.Test.expectNoErrors
        , test "vue parallèle sans socle rejetée" <|
            \() ->
                rejected "Main"
                    "application/Main.elm"
                    "module Main exposing (x)\nimport Element\nx = Element.row [] []"
                    "La vue doit composer le socle partagé."
                    "Element.row"
        , test "assertion ARIA synthétique résolue malgré l'alias" <|
            \() ->
                review "tests/AccessibiliteTest.elm" "module AccessibiliteTest exposing (x)\nimport Test.Html.Selector as S\nimport Html.Attributes as A\nx = S.attribute (A.attribute \"aria-expanded\" \"true\")"
                    |> Review.Test.expectNoErrors
        , test "l'oracle ne donne aucun attribut à une vue de production" <|
            \() ->
                rejected "Main"
                    "application/Main.elm"
                    "module Main exposing (x)\nimport Test.Html.Selector as S\nimport Html.Attributes as A\nx = S.attribute (A.attribute \"aria-expanded\" \"true\")"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.attribute"
        , test "un test ne peut construire du HTML de présentation" <|
            \() ->
                rejected "AccessibiliteTest"
                    "tests/AccessibiliteTest.elm"
                    "module AccessibiliteTest exposing (x)\nimport Html as H\nx = H.div [] []"
                    "Présentation ou échappatoire technique non autorisée."
                    "H.div"
        , test "l'oracle ne permet pas une classe CSS" <|
            \() ->
                rejected "AccessibiliteTest"
                    "tests/AccessibiliteTest.elm"
                    "module AccessibiliteTest exposing (x)\nimport Test.Html.Selector as S\nimport Html.Attributes as A\nx = S.attribute (A.attribute \"class\" \"foo\")"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.attribute"
        , test "l'oracle ne permet pas un nom d'attribut dynamique" <|
            \() ->
                rejected "AccessibiliteTest"
                    "tests/AccessibiliteTest.elm"
                    "module AccessibiliteTest exposing (x)\nimport Test.Html.Selector as S\nimport Html.Attributes as A\nx name = S.attribute (A.attribute name \"true\")"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.attribute"
        , test "le select natif hérite du cadre elm-ui sans couleur CSS" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Selection.elm" "module MrJam.Adaptateurs.Selection exposing (native)\nimport Html.Attributes as A\nnative = A.style \"font\" \"inherit\""
                    |> Review.Test.expectNoErrors
        , test "le select natif ne peut définir une couleur CSS" <|
            \() ->
                rejected "MrJam.Adaptateurs.Selection"
                    "commun/MrJam/Adaptateurs/Selection.elm"
                    "module MrJam.Adaptateurs.Selection exposing (native)\nimport Html.Attributes as A\nnative = A.style \"color\" \"red\""
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "un reset natif ne peut recevoir un réglage dynamique" <|
            \() ->
                rejected "MrJam.Adaptateurs.Selection"
                    "commun/MrJam/Adaptateurs/Selection.elm"
                    "module MrJam.Adaptateurs.Selection exposing (native)\nimport Html.Attributes as A\nnative valeur = A.style \"font\" valeur"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "la fonction d'adaptation n'autorise pas une autre construction HTML" <|
            \() ->
                rejected "MrJam.Adaptateurs.Selection"
                    "commun/MrJam/Adaptateurs/Selection.elm"
                    "module MrJam.Adaptateurs.Selection exposing (native)\nimport Html as H\nnative = H.div [] []"
                    "Présentation ou échappatoire technique non autorisée."
                    "H.div"
        , test "un autre composant ne peut hériter de ces resets" <|
            \() ->
                rejected "MrJam.Test"
                    "commun/MrJam/Test.elm"
                    "module MrJam.Test exposing (native)\nimport Html.Attributes as A\nnative = A.style \"font\" \"inherit\""
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "dialog natif littéral autorisé" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Dialogue.elm" "module MrJam.Adaptateurs.Dialogue exposing (natif, assembler)\nimport Html as H\nnatif = H.node \"dialog\" [] []"
                    |> Review.Test.expectNoErrors
        , test "un autre élément natif refusé" <|
            \() ->
                rejected "MrJam.Adaptateurs.Dialogue"
                    "commun/MrJam/Adaptateurs/Dialogue.elm"
                    "module MrJam.Adaptateurs.Dialogue exposing (natif, assembler)\nimport Html as H\nnatif = H.node \"style\" [] []"
                    "Présentation ou échappatoire technique non autorisée."
                    "H.node"
        , test "pas de tag dynamique dans le dialogue" <|
            \() ->
                rejected "MrJam.Adaptateurs.Dialogue"
                    "commun/MrJam/Adaptateurs/Dialogue.elm"
                    "module MrJam.Adaptateurs.Dialogue exposing (natif, assembler)\nimport Html as H\nnatif tag = H.node tag [] []"
                    "Présentation ou échappatoire technique non autorisée."
                    "H.node"
        , test "racines sœurs sans présentation autorisées" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Dialogue.elm" "module MrJam.Adaptateurs.Dialogue exposing (natif, assembler)\nimport Html as H\nassembler = H.div [] []"
                    |> Review.Test.expectNoErrors
        , test "un reset du dialogue ne peut fixer une dimension" <|
            \() ->
                rejected "MrJam.Adaptateurs.Dialogue"
                    "commun/MrJam/Adaptateurs/Dialogue.elm"
                    "module MrJam.Adaptateurs.Dialogue exposing (natif, assembler)\nimport Html.Attributes as A\nnatif = A.style \"width\" \"680px\""
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "cancel natif borné autorisé" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Dialogue.elm" "module MrJam.Adaptateurs.Dialogue exposing (natif, assembler)\nimport Html.Events as E\nnatif = E.preventDefaultOn \"cancel\" x"
                    |> Review.Test.expectNoErrors
        , test "rôle table constant dans l'adaptateur autorisé avec alias" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Accessibilite.elm" "module MrJam.Adaptateurs.Accessibilite exposing (tableau)\nimport Html.Attributes as A\ntableau = A.attribute \"role\" \"table\""
                    |> Review.Test.expectNoErrors
        , test "rôle d'un autre composant refusé malgré le bon nom de fonction" <|
            \() ->
                rejectedAt "MrJam.Adaptateurs.Accessibilite"
                    "commun/MrJam/Adaptateurs/Accessibilite.elm"
                    "module MrJam.Adaptateurs.Accessibilite exposing (tableau)\nimport Html.Attributes exposing (attribute)\ntableau = attribute \"role\" \"button\""
                    "attribute"
                    { start = { row = 3, column = 11 }, end = { row = 3, column = 20 } }
        , test "rôle dynamique refusé dans le socle" <|
            \() ->
                rejected "MrJam.Adaptateurs.Accessibilite"
                    "commun/MrJam/Adaptateurs/Accessibilite.elm"
                    "module MrJam.Adaptateurs.Accessibilite exposing (tableau)\nimport Html.Attributes as A\ntableau valeur = A.attribute \"role\" valeur"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.attribute"
        , test "attribut d'une progression ne peut changer son maximum" <|
            \() ->
                rejected "MrJam.Adaptateurs.Accessibilite"
                    "commun/MrJam/Adaptateurs/Accessibilite.elm"
                    "module MrJam.Adaptateurs.Accessibilite exposing (progression)\nimport Html.Attributes as A\nprogression = A.attribute \"aria-valuemax\" \"200\""
                    "Présentation ou échappatoire technique non autorisée."
                    "A.attribute"
        , test "méta source fixe" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Manipulation.elm" "module MrJam.Adaptateurs.Manipulation exposing (..)\nimport Html.Attributes as A\nsource valeur = A.attribute \"data-atelier-source\" valeur"
                    |> Review.Test.expectNoErrors
        , test "fantôme inerte" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Manipulation.elm" "module MrJam.Adaptateurs.Manipulation exposing (..)\nimport Html.Attributes as A\nfantome = A.attribute \"inert\" \"\""
                    |> Review.Test.expectNoErrors
        , test "prise tactile native" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Manipulation.elm" "module MrJam.Adaptateurs.Manipulation exposing (..)\nimport Html.Attributes as A\nprise = A.style \"touch-action\" \"none\""
                    |> Review.Test.expectNoErrors
        , test "pointeur fantôme transparent" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Manipulation.elm" "module MrJam.Adaptateurs.Manipulation exposing (..)\nimport Html.Attributes as A\nfantome = A.style \"pointer-events\" \"none\""
                    |> Review.Test.expectNoErrors
        , test "zoom borné" <|
            \() ->
                review "commun/MrJam/Adaptateurs/Manipulation.elm" "module MrJam.Adaptateurs.Manipulation exposing (..)\nimport Html.Attributes as A\nzoom pourcentage = A.style \"zoom\" (String.fromFloat (toFloat (clamp 50 150 pourcentage) / 100))"
                    |> Review.Test.expectNoErrors
        , test "nom d’attribut libre refusé" <|
            \() ->
                rejected "MrJam.Adaptateurs.Manipulation"
                    "commun/MrJam/Adaptateurs/Manipulation.elm"
                    "module MrJam.Adaptateurs.Manipulation exposing (..)\nimport Html.Attributes as A\nsource nom valeur = A.attribute nom valeur"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.attribute"
        , test "style applicatif déguisé refusé" <|
            \() ->
                rejected "MrJam.Adaptateurs.Manipulation"
                    "commun/MrJam/Adaptateurs/Manipulation.elm"
                    "module MrJam.Adaptateurs.Manipulation exposing (..)\nimport Html.Attributes as A\nprise = A.style \"background\" \"red\""
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "prise dynamique refusée" <|
            \() ->
                rejected "MrJam.Adaptateurs.Manipulation"
                    "commun/MrJam/Adaptateurs/Manipulation.elm"
                    "module MrJam.Adaptateurs.Manipulation exposing (..)\nimport Html.Attributes as A\nprise valeur = A.style \"touch-action\" valeur"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "fantôme peut seulement ignorer le pointeur" <|
            \() ->
                rejected "MrJam.Adaptateurs.Manipulation"
                    "commun/MrJam/Adaptateurs/Manipulation.elm"
                    "module MrJam.Adaptateurs.Manipulation exposing (..)\nimport Html.Attributes as A\nfantome = A.style \"pointer-events\" \"auto\""
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "zoom sans limite refusé" <|
            \() ->
                rejected "MrJam.Adaptateurs.Manipulation"
                    "commun/MrJam/Adaptateurs/Manipulation.elm"
                    "module MrJam.Adaptateurs.Manipulation exposing (..)\nimport Html.Attributes as A\nzoom pourcentage = A.style \"zoom\" (String.fromFloat (toFloat pourcentage / 100))"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "zoom bornes différentes refusé" <|
            \() ->
                rejected "MrJam.Adaptateurs.Manipulation"
                    "commun/MrJam/Adaptateurs/Manipulation.elm"
                    "module MrJam.Adaptateurs.Manipulation exposing (..)\nimport Html.Attributes as A\nzoom pourcentage = A.style \"zoom\" (String.fromFloat (toFloat (clamp 1 999 pourcentage) / 100))"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "zoom chaîne libre refusé" <|
            \() ->
                rejected "MrJam.Adaptateurs.Manipulation"
                    "commun/MrJam/Adaptateurs/Manipulation.elm"
                    "module MrJam.Adaptateurs.Manipulation exposing (..)\nimport Html.Attributes as A\nzoom valeur = A.style \"zoom\" valeur"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "zoom ne change pas une couleur" <|
            \() ->
                rejected "MrJam.Adaptateurs.Manipulation"
                    "commun/MrJam/Adaptateurs/Manipulation.elm"
                    "module MrJam.Adaptateurs.Manipulation exposing (..)\nimport Html.Attributes as A\nzoom pourcentage = A.style \"color\" (String.fromFloat (toFloat (clamp 50 150 pourcentage) / 100))"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "clamp local ne contourne pas la borne" <|
            \() ->
                rejected "MrJam.Adaptateurs.Manipulation"
                    "commun/MrJam/Adaptateurs/Manipulation.elm"
                    "module MrJam.Adaptateurs.Manipulation exposing (..)\nimport Html.Attributes as A\nzoom clamp pourcentage = A.style \"zoom\" (String.fromFloat (toFloat (clamp 50 150 pourcentage) / 100))"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        , test "clamp dans un let ne contourne pas la borne" <|
            \() ->
                rejected "MrJam.Adaptateurs.Manipulation"
                    "commun/MrJam/Adaptateurs/Manipulation.elm"
                    "module MrJam.Adaptateurs.Manipulation exposing (..)\nimport Html.Attributes as A\nzoom pourcentage = let clamp a b x = x in A.style \"zoom\" (String.fromFloat (toFloat (clamp 50 150 pourcentage) / 100))"
                    "Présentation ou échappatoire technique non autorisée."
                    "A.style"
        ]
