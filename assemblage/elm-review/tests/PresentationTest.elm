module PresentationTest exposing (tests)

import MrJam.Presentation
import Review.Project as Project
import Review.Test
import Review.Test.Dependencies as Dependencies
import Test exposing (Test, describe, test)


details : List String
details =
    [ "Composer le socle style-mrjam/elm-ui ; les capacités absentes passent par un adaptateur nommé, borné et testé dans l'infrastructure." ]


review path source =
    Dependencies.projectWithElmCore
        |> Project.addDependency Dependencies.elmHtml
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
        ]
