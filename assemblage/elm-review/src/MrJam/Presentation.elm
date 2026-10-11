module MrJam.Presentation exposing (rule)

{-| Frontières de présentation : symboles résolus par elm-review, jamais par
recherche textuelle d'un alias. La commande centrale place les sources partagées
verrouillées dans commun/, les applications dans application/.
-}

import Dict exposing (Dict)
import Elm.Syntax.Declaration as Declaration exposing (Declaration)
import Elm.Syntax.Expression as Expression exposing (Expression)
import Elm.Syntax.Import exposing (Import)
import Elm.Syntax.Node as Node exposing (Node)
import Elm.Syntax.Range exposing (Range)
import Review.ModuleNameLookupTable as Lookup exposing (ModuleNameLookupTable)
import Review.Project.Dependency as Dependency exposing (Dependency)
import Review.Rule as Rule exposing (Error, Rule)


type alias Context =
    { lookup : ModuleNameLookupTable
    , moduleName : List String
    , path : String
    , function : String
    , sharedUsed : Bool
    , presentation : Maybe Range
    , attributes : List Range
    , assertions : List Range
    , dependencyModules : List String
    }


rule : Rule
rule =
    Rule.newProjectRuleSchema "MrJam.Presentation" []
        |> Rule.withDependenciesProjectVisitor dependenciesVisitor
        |> Rule.withModuleVisitor moduleVisitor
        |> Rule.withModuleContextUsingContextCreator
            { fromProjectToModule = initialContext
            , fromModuleToProject = Rule.initContextCreator (\_ -> [])
            , foldProjectContexts = (++)
            }
        |> Rule.fromProjectRuleSchema


moduleVisitor : Rule.ModuleRuleSchema {} Context -> Rule.ModuleRuleSchema { hasAtLeastOneVisitor : () } Context
moduleVisitor schema =
    schema
        |> Rule.withImportVisitor importVisitor
        |> Rule.withDeclarationEnterVisitor declarationVisitor
        |> Rule.withExpressionEnterVisitor expressionVisitor
        |> Rule.withFinalModuleEvaluation finalVisitor


initialContext : Rule.ContextCreator (List String) Context
initialContext =
    Rule.initContextCreator
        (\lookup moduleName path dependencyModules ->
            { lookup = lookup
            , moduleName = moduleName
            , path = path
            , function = ""
            , sharedUsed = False
            , presentation = Nothing
            , attributes = []
            , assertions = []
            , dependencyModules = dependencyModules
            }
        )
        |> Rule.withModuleNameLookupTable
        |> Rule.withModuleName
        |> Rule.withFilePath


shared : Context -> Bool
shared context =
    String.startsWith "commun/" context.path


diagnostic : String -> Range -> Error {}
diagnostic message range =
    Rule.error
        { message = message
        , details = [ "Composer le socle style-mrjam/elm-ui ; les capacités absentes passent par un adaptateur nommé, borné et testé dans l'infrastructure." ]
        }
        range


dependenciesVisitor : Dict String Dependency -> List String -> ( List (Error { useErrorForModule : () }), List String )
dependenciesVisitor dependencies _ =
    ( []
    , Dict.values dependencies |> List.concatMap (Dependency.modules >> List.map .name)
    )


importVisitor : Node Import -> Context -> ( List (Error {}), Context )
importVisitor node context =
    let
        origin =
            Node.value node |> .moduleName |> Node.value |> String.join "."

        forbidden =
            origin
                == "Html.Styled"
                || String.startsWith "Html.Styled." origin
                || origin
                == "Css"
                || String.startsWith "Css." origin
                || ((origin == "Animator" || String.startsWith "Animator." origin)
                        && not (shared context && context.moduleName == [ "MrJam", "Transitions" ])
                   )
                || (origin == "MrJam.Theme" && not (shared context))
                || (shared context
                        && not (origin == "MrJam" || String.startsWith "MrJam." origin)
                        && not (List.member origin context.dependencyModules)
                        -- Ces deux noms sont aussi les stubs AST des tests.
                        && not (List.member origin [ "Element", "Animator" ])
                   )
    in
    if forbidden then
        ( [ diagnostic "Frontière du socle partagé contournée." (Node.range node) ], context )

    else
        ( [], context )


declarationVisitor : Node Declaration -> Context -> ( List (Error {}), Context )
declarationVisitor node context =
    case Node.value node of
        Declaration.FunctionDeclaration { declaration } ->
            ( [], { context | function = Node.value declaration |> .name |> Node.value, attributes = [], assertions = [] } )

        _ ->
            ( [], { context | function = "", attributes = [], assertions = [] } )


{-| Chaque exception est un couple module/fonction, et un ensemble de symboles
appelables. Aucun module entier exempté, aucun nom d'attribut arbitraire exposé.+La présence dans commun/ est également nécessaire : impossible de nommer un
module applicatif MrJam.Adaptateurs.\* pour obtenir cette capacité.
-}
adapterAllows : Context -> String -> Bool
adapterAllows context symbol =
    shared context
        && (case ( String.join "." context.moduleName, context.function ) of
                ( "MrJam.Adaptateurs.Accessibilite", "identifiant" ) ->
                    List.member symbol [ "Element.htmlAttribute", "Html.Attributes.id" ]

                ( "MrJam.Adaptateurs.Accessibilite", "decritPar" ) ->
                    List.member symbol [ "Element.htmlAttribute", "Html.Attributes.attribute" ]

                ( "MrJam.Adaptateurs.Accessibilite", "controle" ) ->
                    List.member symbol [ "Element.htmlAttribute", "Html.Attributes.attribute" ]

                ( "MrJam.Adaptateurs.Accessibilite", "depliement" ) ->
                    List.member symbol [ "Element.htmlAttribute", "Html.Attributes.attribute" ]

                ( "MrJam.Adaptateurs.Accessibilite", "tabulation" ) ->
                    List.member symbol [ "Element.htmlAttribute", "Html.Attributes.tabindex" ]

                _ ->
                    False
           )


expressionVisitor : Node Expression -> Context -> ( List (Error {}), Context )
expressionVisitor node context =
    case Node.value node of
        Expression.Application (callee :: attribute :: _) ->
            if String.startsWith "tests/" context.path && Lookup.moduleNameFor context.lookup callee == Just [ "Test", "Html", "Selector" ] && isAttribute callee then
                -- Oracle synthétique, pas un attribut transmis à une vue : seul
                -- l'argument direct d'une assertion de l'API de test est permis.
                ( [], { context | assertions = assertionAttribute context attribute ++ context.assertions } )

            else
                case ( Node.value callee, Node.value attribute ) of
                    ( Expression.FunctionOrValue _ "attribute", Expression.Literal literal ) ->
                        let
                            expected =
                                case context.function of
                                    "decritPar" ->
                                        "aria-describedby"

                                    "controle" ->
                                        "aria-controls"

                                    "depliement" ->
                                        "aria-expanded"

                                    _ ->
                                        ""
                        in
                        if Lookup.moduleNameFor context.lookup callee == Just [ "Html", "Attributes" ] && expected /= "" && expected == literal then
                            ( [], { context | attributes = Node.range callee :: context.attributes } )

                        else
                            ( [], context )

                    _ ->
                        ( [], context )

        Expression.FunctionOrValue _ name ->
            case Lookup.moduleNameFor context.lookup node of
                Just moduleName ->
                    let
                        origin =
                            String.join "." moduleName

                        symbol =
                            origin ++ "." ++ name

                        restricted =
                            origin
                                == "Html"
                                || String.startsWith "Html." origin
                                || origin
                                == "VirtualDom"
                                || origin
                                == "Svg"
                                || String.startsWith "Svg." origin
                                || List.member symbol [ "Element.html", "Element.htmlAttribute" ]

                        alwaysForbidden =
                            List.member symbol [ "Html.Attributes.style", "Html.Attributes.class", "Html.Attributes.classList", "Html.Attributes.property" ]
                                || (origin == "Animator" && List.member name [ "div", "node", "css", "toCss" ])
                                || (symbol == "Html.Attributes.attribute" && not (List.member (Node.range node) (context.attributes ++ context.assertions)))
                                || (String.startsWith "Svg.Attributes." symbol && List.member name [ "style", "class", "classList" ])
                                || (origin == "Element.Input" && not (shared context))

                        animation =
                            List.member symbol [ "Browser.Events.onAnimationFrame", "Browser.Events.onAnimationFrameDelta" ]
                                && not (shared context && context.moduleName == [ "MrJam", "Transitions" ])

                        layout =
                            origin == "Element" && List.member name [ "layout", "layoutWith", "el", "row", "column", "wrappedRow", "paragraph", "textColumn", "table" ]

                        next =
                            { context
                                | sharedUsed = context.sharedUsed || origin == "MrJam" || String.startsWith "MrJam." origin
                                , presentation =
                                    if layout then
                                        Just (Node.range node)

                                    else
                                        context.presentation
                            }
                    in
                    if alwaysForbidden || animation || (restricted && not (adapterAllows context symbol || List.member (Node.range node) context.assertions)) then
                        ( [ diagnostic "Présentation ou échappatoire technique non autorisée." (Node.range node) ], next )

                    else
                        ( [], next )

                Nothing ->
                    ( [], context )

        _ ->
            ( [], context )


assertionAttribute : Context -> Node Expression -> List Range
assertionAttribute context node =
    case Node.value node of
        Expression.ParenthesizedExpression inner ->
            assertionAttribute context inner

        Expression.Application (callee :: argument :: _) ->
            if Lookup.moduleNameFor context.lookup callee /= Just [ "Html", "Attributes" ] then
                []

            else
                case ( Node.value callee, Node.value argument ) of
                    ( Expression.FunctionOrValue _ "attribute", Expression.Literal name ) ->
                        if List.member name [ "aria-controls", "aria-expanded", "aria-describedby" ] then
                            [ Node.range callee ]

                        else
                            []

                    ( Expression.FunctionOrValue _ "tabindex", _ ) ->
                        [ Node.range callee ]

                    _ ->
                        []

        _ ->
            []


isAttribute : Node Expression -> Bool
isAttribute node =
    case Node.value node of
        Expression.FunctionOrValue _ "attribute" ->
            True

        _ ->
            False


finalVisitor : Context -> List (Error {})
finalVisitor context =
    let
        spoofed =
            not (shared context) && List.head context.moduleName == Just "MrJam"
    in
    if spoofed then
        [ diagnostic "Le namespace MrJam appartient aux sources communes verrouillées."
            { start = { row = 1, column = 1 }, end = { row = 1, column = 7 } }
        ]

    else
        case context.presentation of
            Just range ->
                if not (shared context) && not context.sharedUsed then
                    [ diagnostic "La vue doit composer le socle partagé." range ]

                else
                    []

            Nothing ->
                []
