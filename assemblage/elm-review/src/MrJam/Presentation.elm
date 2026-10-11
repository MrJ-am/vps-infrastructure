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
import Elm.Syntax.Pattern as Pattern
import Elm.Syntax.Range exposing (Range)
import Review.ModuleNameLookupTable as Lookup exposing (ModuleNameLookupTable)
import Review.Project.Dependency as Dependency exposing (Dependency)
import Review.Rule as Rule exposing (Error, Rule)


type alias Context =
    { lookup : ModuleNameLookupTable
    , moduleName : List String
    , path : String
    , function : String
    , zoomArgumentUnique : Bool
    , sharedUsed : Bool
    , presentation : Maybe Range
    , attributes : List Range
    , assertions : List Range
    , resets : List Range
    , nodes : List Range
    , events : List Range
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
            , zoomArgumentUnique = False
            , sharedUsed = False
            , presentation = Nothing
            , attributes = []
            , assertions = []
            , resets = []
            , nodes = []
            , events = []
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
                || (String.startsWith "MrJam.Adaptateurs." origin && not (shared context))
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
            ( [], { context | function = Node.value declaration |> .name |> Node.value, zoomArgumentUnique = (Node.value declaration |> .arguments |> List.map Node.value) == [ Pattern.VarPattern "pourcentage" ], attributes = [], assertions = [], resets = [], nodes = [], events = [] } )

        _ ->
            ( [], { context | function = "", zoomArgumentUnique = False, attributes = [], assertions = [], resets = [], nodes = [], events = [] } )


{-| Chaque exception est un couple module/fonction, et un ensemble de symboles
appelables. Aucun module entier exempté, aucun nom d'attribut arbitraire exposé.
La présence dans commun/ est également nécessaire : impossible de nommer un
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

                ( "MrJam.Adaptateurs.Accessibilite", "nomGroupe" ) ->
                    List.member symbol [ "Element.htmlAttribute", "Html.Attributes.attribute" ]

                ( "MrJam.Adaptateurs.Accessibilite", "controle" ) ->
                    List.member symbol [ "Element.htmlAttribute", "Html.Attributes.attribute" ]

                ( "MrJam.Adaptateurs.Accessibilite", "depliement" ) ->
                    List.member symbol [ "Element.htmlAttribute", "Html.Attributes.attribute" ]

                ( "MrJam.Adaptateurs.Accessibilite", "tabulation" ) ->
                    List.member symbol [ "Element.htmlAttribute", "Html.Attributes.tabindex" ]

                ( "MrJam.Adaptateurs.Accessibilite", "infoBulle" ) ->
                    List.member symbol [ "Element.htmlAttribute", "Html.Attributes.title" ]

                ( "MrJam.Adaptateurs.Selection", "native" ) ->
                    List.member symbol [ "Element.html", "Html.select", "Html.option", "Html.text", "Html.Attributes.value", "Html.Attributes.selected", "Html.Attributes.attribute", "Html.Attributes.style", "Html.Events.onInput" ]

                ( "MrJam.Adaptateurs.Dialogue", "natif" ) ->
                    List.member symbol [ "Html.node", "Html.Attributes.id", "Html.Attributes.attribute", "Html.Attributes.style", "Html.Events.preventDefaultOn" ]

                ( "MrJam.Adaptateurs.Dialogue", "assembler" ) ->
                    symbol == "Html.div"

                ( "MrJam.Adaptateurs.Dialogue", "integrer" ) ->
                    symbol == "Element.html"

                ( "MrJam.Adaptateurs.Manipulation", fonction ) ->
                    List.member fonction [ "source", "cible", "piece", "bloc", "test", "sousFormule", "formule", "chemin", "defilement", "fond", "depot", "fantome", "prise", "zoom" ]
                        && List.member symbol [ "Element.htmlAttribute", "Html.Attributes.attribute", "Html.Attributes.style" ]

                ( "MrJam.Adaptateurs.Constructions", "repere" ) ->
                    List.member symbol [ "Element.htmlAttribute", "Html.Attributes.attribute" ]

                ( "MrJam.Adaptateurs.Constructions", fonction ) ->
                    List.member fonction [ "encocheEntete", "encochePied", "objet", "neutre", "selectionne", "incorrect" ]
                        && List.member symbol [ "Element.htmlAttribute", "Html.Attributes.style" ]

                ( "MrJam.Adaptateurs.Complement", "natif" ) ->
                    List.member symbol [ "Element.html", "Html.details", "Html.summary" ]

                ( "MrJam.Adaptateurs.Video", "format" ) ->
                    List.member symbol [ "Element.htmlAttribute", "Html.Attributes.style" ]

                ( "MrJam.Adaptateurs.Video", "lecteur" ) ->
                    List.member symbol [ "Element.html", "Html.node", "Html.iframe", "Html.Attributes.src", "Html.Attributes.title", "Html.Attributes.attribute", "Html.Attributes.style", "Html.Events.on" ]

                ( "MrJam.Adaptateurs.Mathematiques", "expression" ) ->
                    List.member symbol [ "Element.html", "Html.node", "Html.Attributes.attribute" ]

                ( "MrJam.Adaptateurs.Texte", "litteral" ) ->
                    List.member symbol [ "Element.htmlAttribute", "Html.Attributes.style" ]

                ( "MrJam.Adaptateurs.Texte", "texte" ) ->
                    List.member symbol [ "Element.html", "Html.text" ]

                ( "MrJam.Adaptateurs.Texte", "emphase" ) ->
                    List.member symbol [ "Element.html", "Html.em", "Html.text" ]

                ( "MrJam.Adaptateurs.Typographie", fonction ) ->
                    List.member fonction [ "signature", "signatureEnLigne", "marque", "point", "titreVitrine", "titreSecondaireVitrine" ]
                        && List.member symbol [ "Element.htmlAttribute", "Html.Attributes.class", "Html.Attributes.style", "Html.Attributes.attribute" ]

                ( "MrJam.Adaptateurs.Atelier", fonction ) ->
                    List.member fonction [ "suivi", "selection" ]
                        && List.member symbol [ "Element.htmlAttribute", "Html.Attributes.attribute" ]

                ( "MrJam.Adaptateurs.Curseur", "natif" ) ->
                    List.member symbol [ "Element.html", "Html.input", "Html.Attributes.type_", "Html.Attributes.id", "Html.Attributes.min", "Html.Attributes.max", "Html.Attributes.step", "Html.Attributes.value", "Html.Attributes.attribute", "Html.Events.onInput" ]

                ( "MrJam.Adaptateurs.Dessin", fonction ) ->
                    List.member symbol (dessinSymboles fonction)

                ( "MrJam.Adaptateurs.Diagrammes", fonction ) ->
                    List.member symbol (diagrammeSymboles fonction)

                ( "MrJam.Adaptateurs.Pictogramme", "traits" ) ->
                    List.member symbol [ "Element.html", "Svg.svg", "Svg.path", "Svg.Attributes.viewBox", "Svg.Attributes.width", "Svg.Attributes.height", "Svg.Attributes.fill", "Svg.Attributes.stroke", "Svg.Attributes.strokeWidth", "Svg.Attributes.strokeLinecap", "Svg.Attributes.strokeLinejoin", "Svg.Attributes.d", "Html.Attributes.attribute" ]

                ( "MrJam.Adaptateurs.Saisie", fonction ) ->
                    List.member fonction [ "nombre", "date", "dateHeure", "identifie", "soumettre", "echap", "intrinseque" ]
                        && (symbol
                                == "Element.htmlAttribute"
                                || String.startsWith "Html.Attributes." symbol
                                || List.member symbol [ "Html.Events.on", "Html.Events.preventDefaultOn" ]
                           )

                _ ->
                    not (List.isEmpty (accessibiliteAttributs context))
                        && List.member symbol [ "Element.htmlAttribute", "Html.Attributes.attribute" ]
           )


{-| Rendu vectoriel spécialisé, capacités par fonction ; aucune API SVG libre.
-}
dessinSymboles : String -> List String
dessinSymboles fonction =
    case fonction of
        "quadrillage" ->
            [ "Element.html", "Svg.svg", "Svg.defs", "Svg.pattern", "Svg.circle", "Svg.rect", "Svg.Attributes.id", "Svg.Attributes.patternUnits", "Svg.Attributes.width", "Svg.Attributes.height", "Svg.Attributes.cx", "Svg.Attributes.cy", "Svg.Attributes.r", "Svg.Attributes.fill", "Svg.Attributes.opacity", "Html.Attributes.attribute" ]

        "definitions" ->
            [ "Svg.defs" ]

        "definition" ->
            [ "Svg.Attributes.cx", "Svg.Attributes.cy", "Svg.Attributes.d", "Svg.Attributes.id", "Svg.Attributes.r", "Svg.Attributes.transform", "Svg.circle", "Svg.g", "Svg.path" ]

        "masque" ->
            [ "Html.Attributes.attribute", "Svg.Attributes.fill", "Svg.Attributes.height", "Svg.Attributes.id", "Svg.Attributes.maskUnits", "Svg.Attributes.transform", "Svg.Attributes.width", "Svg.Attributes.x", "Svg.Attributes.y", "Svg.defs", "Svg.mask", "Svg.rect", "Svg.use" ]

        "vue" ->
            [ "Element.html", "Html.Attributes.attribute", "Html.Attributes.style", "Svg.Attributes.colorInterpolation", "Svg.Attributes.cx", "Svg.Attributes.cy", "Svg.Attributes.fill", "Svg.Attributes.gradientUnits", "Svg.Attributes.height", "Svg.Attributes.id", "Svg.Attributes.mask", "Svg.Attributes.maskContentUnits", "Svg.Attributes.maskUnits", "Svg.Attributes.offset", "Svg.Attributes.opacity", "Svg.Attributes.r", "Svg.Attributes.stopColor", "Svg.Attributes.stroke", "Svg.Attributes.strokeDasharray", "Svg.Attributes.strokeWidth", "Svg.Attributes.viewBox", "Svg.Attributes.width", "Svg.Attributes.x", "Svg.Attributes.x1", "Svg.Attributes.x2", "Svg.Attributes.y", "Svg.Attributes.y1", "Svg.Attributes.y2", "Svg.circle", "Svg.defs", "Svg.desc", "Svg.g", "Svg.image", "Svg.line", "Svg.linearGradient", "Svg.mask", "Svg.rect", "Svg.stop", "Svg.svg", "Svg.text", "Svg.title" ]

        "renderPiece" ->
            [ "Html.Attributes.attribute", "Svg.Attributes.fill", "Svg.Attributes.id", "Svg.Attributes.opacity", "Svg.Attributes.stroke", "Svg.Attributes.transform", "Svg.g", "Svg.use" ]

        _ ->
            []


diagrammeSymboles : String -> List String
diagrammeSymboles fonction =
    case fonction of
        "clavier" ->
            []

        "courbe" ->
            [ "Html.Attributes.attribute", "Svg.Attributes.d", "Svg.Attributes.fill", "Svg.Attributes.opacity", "Svg.Attributes.stroke", "Svg.Attributes.strokeDasharray", "Svg.Attributes.strokeWidth", "Svg.path", "Svg.text", "Svg.title" ]

        "legende" ->
            [ "Element.html", "Html.Attributes.attribute", "Svg.Attributes.height", "Svg.Attributes.stroke", "Svg.Attributes.strokeDasharray", "Svg.Attributes.strokeWidth", "Svg.Attributes.viewBox", "Svg.Attributes.width", "Svg.Attributes.x1", "Svg.Attributes.x2", "Svg.Attributes.y1", "Svg.Attributes.y2", "Svg.line", "Svg.svg" ]

        "plan" ->
            [ "Element.html", "Html.Attributes.attribute", "Html.Attributes.style", "Html.Events.preventDefaultOn", "Svg.Attributes.cx", "Svg.Attributes.cy", "Svg.Attributes.d", "Svg.Attributes.fill", "Svg.Attributes.height", "Svg.Attributes.preserveAspectRatio", "Svg.Attributes.r", "Svg.Attributes.stroke", "Svg.Attributes.strokeDasharray", "Svg.Attributes.strokeOpacity", "Svg.Attributes.strokeWidth", "Svg.Attributes.viewBox", "Svg.Attributes.width", "Svg.Attributes.x1", "Svg.Attributes.x2", "Svg.Attributes.y1", "Svg.Attributes.y2", "Svg.circle", "Svg.g", "Svg.line", "Svg.path", "Svg.rect", "Svg.svg", "Svg.text", "Svg.title" ]

        "geometrie" ->
            [ "Element.html", "Html.Attributes.attribute", "Svg.Attributes.cx", "Svg.Attributes.cy", "Svg.Attributes.dominantBaseline", "Svg.Attributes.fill", "Svg.Attributes.fontSize", "Svg.Attributes.height", "Svg.Attributes.points", "Svg.Attributes.r", "Svg.Attributes.stroke", "Svg.Attributes.strokeDasharray", "Svg.Attributes.strokeWidth", "Svg.Attributes.textAnchor", "Svg.Attributes.viewBox", "Svg.Attributes.width", "Svg.Attributes.x", "Svg.Attributes.x1", "Svg.Attributes.x2", "Svg.Attributes.y", "Svg.Attributes.y1", "Svg.Attributes.y2", "Svg.circle", "Svg.g", "Svg.line", "Svg.polygon", "Svg.svg", "Svg.text", "Svg.text_" ]

        "limite" ->
            [ "Element.html", "Element.htmlAttribute", "Html.Attributes.attribute" ]

        "carte" ->
            [ "Element.html", "Element.htmlAttribute", "Html.Attributes.attribute" ]

        _ ->
            []


accessibiliteAttributs : Context -> List ( String, Maybe String )
accessibiliteAttributs context =
    if shared context && context.moduleName == [ "MrJam", "Adaptateurs", "Mathematiques" ] && context.function == "expression" then
        [ ( "formula", Nothing ), ( "display-mode", Just "true" ) ]

    else if shared context && context.moduleName == [ "MrJam", "Adaptateurs", "Video" ] && context.function == "lecteur" then
        [ ( "generation", Nothing ), ( "allow", Just "autoplay; encrypted-media; picture-in-picture; fullscreen" ), ( "allowfullscreen", Just "" ), ( "referrerpolicy", Just "strict-origin-when-cross-origin" ) ]

    else if shared context && context.moduleName == [ "MrJam", "Adaptateurs", "Diagrammes" ] then
        case context.function of
            "courbe" ->
                [ ( "vector-effect", Just "non-scaling-stroke" ), ( "data-frontiere-role", Nothing ), ( "data-h", Nothing ) ]

            "legende" ->
                [ ( "aria-hidden", Just "true" ) ]

            "plan" ->
                [ ( "data-palette-plan", Just "true" ), ( "role", Just "group" ), ( "tabindex", Just "0" ), ( "aria-label", Just "Plan L × C" ), ( "aria-describedby", Just "aide-plan valeurs-palette" ), ( "aria-roledescription", Just "sélecteur à deux axes" ), ( "data-gamut-region", Just "true" ), ( "vector-effect", Just "non-scaling-stroke" ), ( "aria-hidden", Just "true" ), ( "data-gamut-frontiere", Just "true" ), ( "data-palette-curseur", Just "true" ) ]

            "geometrie" ->
                [ ( "data-tetrade", Nothing ), ( "data-sommet", Nothing ), ( "role", Just "img" ), ( "aria-label", Just "Plan OKLab a,b : deux carrés décalés de 45 degrés" ) ]

            "limite" ->
                [ ( "data-limite-commune", Nothing ), ( "data-limitantes", Nothing ) ]

            "carte" ->
                [ ( "data-role-palette", Nothing ), ( "data-l", Nothing ), ( "data-c", Nothing ), ( "data-h", Nothing ) ]

            _ ->
                []

    else if shared context && context.moduleName == [ "MrJam", "Adaptateurs", "Dessin" ] then
        case context.function of
            "quadrillage" ->
                [ ( "aria-hidden", Just "true" ), ( "focusable", Just "false" ) ]

            "masque" ->
                [ ( "href", Nothing ), ( "data-trou", Nothing ) ]

            "vue" ->
                [ ( "href", Nothing ), ( "role", Just "img" ), ( "aria-labelledby", Nothing ), ( "data-svg", Nothing ), ( "data-background", Just "true" ), ( "data-degrade-global", Just "true" ) ]

            "renderPiece" ->
                [ ( "href", Nothing ), ( "data-instance", Nothing ), ( "data-opacity", Nothing ), ( "data-mirror", Nothing ) ]

            _ ->
                []

    else if shared context && context.moduleName == [ "MrJam", "Adaptateurs", "Atelier" ] then
        case context.function of
            "suivi" ->
                [ ( "data-progress", Nothing ), ( "data-running", Nothing ) ]

            "selection" ->
                [ ( "data-selected", Nothing ) ]

            _ ->
                []

    else if shared context && context.moduleName == [ "MrJam", "Adaptateurs", "Curseur" ] && context.function == "natif" then
        [ ( "aria-label", Nothing ), ( "aria-valuetext", Nothing ) ]

    else if shared context && context.moduleName == [ "MrJam", "Adaptateurs", "Manipulation" ] then
        case context.function of
            "source" ->
                [ ( "data-atelier-source", Nothing ) ]

            "cible" ->
                [ ( "data-atelier-cible", Nothing ) ]

            "piece" ->
                [ ( "data-atelier-piece", Nothing ) ]

            "bloc" ->
                [ ( "data-bloc", Nothing ) ]

            "test" ->
                [ ( "data-testid", Nothing ) ]

            "sousFormule" ->
                [ ( "data-sous-formule", Nothing ) ]

            "formule" ->
                [ ( "data-formule", Nothing ) ]

            "chemin" ->
                [ ( "data-chemin", Nothing ) ]

            "fond" ->
                [ ( "data-atelier-fond", Nothing ) ]

            "defilement" ->
                [ ( "data-atelier-defile", Just "canevas" ) ]

            "depot" ->
                [ ( "data-depot-actif", Just "true" ) ]

            "fantome" ->
                [ ( "data-mrjam-fantome", Just "" ), ( "inert", Just "" ) ]

            _ ->
                []

    else if shared context && context.moduleName == [ "MrJam", "Adaptateurs", "Constructions" ] && context.function == "repere" then
        [ ( "data-mrjam-construction", Nothing ) ]

    else if shared context && context.moduleName == [ "MrJam", "Adaptateurs", "Typographie" ] && context.function == "marque" then
        [ ( "data-mrjam-marque", Just "" ) ]

    else if shared context && context.moduleName == [ "MrJam", "Adaptateurs", "Pictogramme" ] && context.function == "traits" then
        [ ( "aria-hidden", Just "true" ), ( "focusable", Just "false" ) ]

    else if shared context && context.moduleName == [ "MrJam", "Adaptateurs", "Accessibilite" ] then
        case context.function of
            "etat" ->
                [ ( "role", Just "status" ) ]

            "tableau" ->
                [ ( "role", Just "table" ) ]

            "rangee" ->
                [ ( "role", Just "row" ) ]

            "cellule" ->
                [ ( "role", Just "cell" ) ]

            "enteteColonne" ->
                [ ( "role", Just "columnheader" ) ]

            "region" ->
                [ ( "role", Just "region" ) ]

            "image" ->
                [ ( "role", Just "img" ) ]

            "banniere" ->
                [ ( "role", Just "banner" ) ]

            "liste" ->
                [ ( "role", Just "list" ) ]

            "elementListe" ->
                [ ( "role", Just "listitem" ) ]

            "dialogue" ->
                [ ( "role", Just "dialog" ) ]

            "modale" ->
                [ ( "aria-modal", Just "true" ) ]

            "gestionDialogue" ->
                [ ( "data-mrjam-dialogue", Just "" ) ]

            "fermerDialogue" ->
                [ ( "data-mrjam-fermer", Just "" ) ]

            "compagnon" ->
                [ ( "data-mrjam-compagnon", Just "" ) ]

            "masque" ->
                [ ( "aria-hidden", Just "true" ) ]

            "inactif" ->
                [ ( "aria-disabled", Just "true" ) ]

            "occupe" ->
                [ ( "aria-busy", Just "true" ) ]

            "pageCourante" ->
                [ ( "aria-current", Just "page" ) ]

            "selectionnee" ->
                [ ( "aria-selected", Nothing ) ]

            "pressee" ->
                [ ( "aria-pressed", Nothing ) ]

            "desactive" ->
                [ ( "aria-disabled", Nothing ) ]

            "progression" ->
                [ ( "role", Just "progressbar" ), ( "aria-valuemin", Just "0" ), ( "aria-valuemax", Just "100" ), ( "aria-valuenow", Nothing ) ]

            _ ->
                []

    else
        []


valeurAccessibilite : Context -> String -> Node Expression -> Bool
valeurAccessibilite context nom node =
    case List.filter (Tuple.first >> (==) nom) (accessibiliteAttributs context) |> List.head of
        Just ( _, Just attendu ) ->
            case Node.value node of
                Expression.Application [ _, _, valeur ] ->
                    Node.value valeur == Expression.Literal attendu

                _ ->
                    False

        _ ->
            True


expressionVisitor : Node Expression -> Context -> ( List (Error {}), Context )
expressionVisitor node context =
    case Node.value node of
        Expression.LetExpression _ ->
            ( [], { context | zoomArgumentUnique = False } )

        Expression.LambdaExpression _ ->
            ( [], { context | zoomArgumentUnique = False } )

        Expression.Application (callee :: attribute :: _) ->
            if nativeReset context node || nativeZoom context node then
                ( [], { context | resets = Node.range callee :: context.resets } )

            else if nativeNode context node then
                ( [], { context | nodes = Node.range callee :: context.nodes } )

            else if nativeCancel context node then
                ( [], { context | events = Node.range callee :: context.events } )

            else if nativeInput context node || nativeClass context node then
                ( [], { context | attributes = Node.range callee :: context.attributes } )

            else if String.startsWith "tests/" context.path && Lookup.moduleNameFor context.lookup callee == Just [ "Test", "Html", "Selector" ] && isAttribute callee then
                -- Oracle synthétique, pas un attribut transmis à une vue : seul
                -- l'argument direct d'une assertion de l'API de test est permis.
                ( [], { context | assertions = assertionAttribute context attribute ++ context.assertions } )

            else
                case ( Node.value callee, Node.value attribute ) of
                    ( Expression.FunctionOrValue _ "attribute", Expression.Literal literal ) ->
                        let
                            expected =
                                case ( String.join "." context.moduleName, context.function ) of
                                    ( "MrJam.Adaptateurs.Accessibilite", "decritPar" ) ->
                                        [ "aria-describedby" ]

                                    ( "MrJam.Adaptateurs.Accessibilite", "nomGroupe" ) ->
                                        [ "aria-label" ]

                                    ( "MrJam.Adaptateurs.Accessibilite", "controle" ) ->
                                        [ "aria-controls" ]

                                    ( "MrJam.Adaptateurs.Accessibilite", "depliement" ) ->
                                        [ "aria-expanded" ]

                                    ( "MrJam.Adaptateurs.Selection", "native" ) ->
                                        [ "aria-label" ]

                                    ( "MrJam.Adaptateurs.Dialogue", "natif" ) ->
                                        [ "aria-label", "data-mrjam-modale" ]

                                    _ ->
                                        []
                        in
                        if
                            Lookup.moduleNameFor context.lookup callee
                                == Just [ "Html", "Attributes" ]
                                && List.member literal (expected ++ List.map Tuple.first (accessibiliteAttributs context))
                                && valeurAccessibilite context literal node
                        then
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
                            List.member symbol [ "Html.Attributes.classList", "Html.Attributes.property" ]
                                || (symbol == "Html.Attributes.class" && not (List.member (Node.range node) context.attributes))
                                || (symbol == "Html.Attributes.style" && not (List.member (Node.range node) context.resets))
                                || (origin == "Animator" && List.member name [ "div", "node", "css", "toCss" ])
                                || (List.member symbol [ "Html.div", "Html.node", "Html.iframe", "Html.details", "Html.summary", "Html.em" ] && not (List.member (Node.range node) context.nodes))
                                || (symbol == "Html.Events.preventDefaultOn" && not (List.member (Node.range node) context.events))
                                || (context.moduleName
                                        == [ "MrJam", "Adaptateurs", "Saisie" ]
                                        && ((origin == "Html.Attributes" && not (List.member (Node.range node) (context.attributes ++ context.resets)))
                                                || (origin == "Html.Events" && not (List.member (Node.range node) context.events))
                                           )
                                   )
                                || (context.moduleName
                                        == [ "MrJam", "Adaptateurs", "Curseur" ]
                                        && origin
                                        == "Html.Attributes"
                                        && name
                                        /= "attribute"
                                        && not (List.member (Node.range node) context.attributes)
                                   )
                                || (context.moduleName
                                        == [ "MrJam", "Adaptateurs", "Video" ]
                                        && ((origin == "Html.Attributes" && not (List.member (Node.range node) (context.attributes ++ context.resets)))
                                                || (origin == "Html.Events" && not (List.member (Node.range node) context.events))
                                           )
                                   )
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
                        if List.member name [ "aria-controls", "aria-expanded", "aria-describedby", "role", "aria-selected", "aria-pressed", "aria-disabled", "aria-busy", "aria-valuemin", "aria-valuemax", "aria-valuenow" ] then
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


nativeReset : Context -> Node Expression -> Bool
nativeReset context node =
    let
        resets =
            case ( context.moduleName, context.function ) of
                ( [ "MrJam", "Adaptateurs", "Diagrammes" ], "plan" ) ->
                    [ ( "touch-action", "none" ), ( "cursor", "crosshair" ), ( "overflow", "visible" ), ( "pointer-events", "none" ) ]

                ( [ "MrJam", "Adaptateurs", "Dessin" ], "vue" ) ->
                    [ ( "pointer-events", "none" ), ( "mix-blend-mode", "difference" ) ]

                ( [ "MrJam", "Adaptateurs", "Manipulation" ], "prise" ) ->
                    [ ( "touch-action", "none" ), ( "cursor", "grab" ), ( "user-select", "none" ), ( "-webkit-user-select", "none" ), ( "-webkit-touch-callout", "none" ) ]

                ( [ "MrJam", "Adaptateurs", "Manipulation" ], "fantome" ) ->
                    [ ( "pointer-events", "none" ) ]

                ( [ "MrJam", "Adaptateurs", "Video" ], "format" ) ->
                    [ ( "aspect-ratio", "16/9" ) ]

                ( [ "MrJam", "Adaptateurs", "Video" ], "lecteur" ) ->
                    [ ( "display", "block" ), ( "width", "100%" ), ( "aspect-ratio", "16/9" ), ( "border", "0" ) ]

                ( [ "MrJam", "Adaptateurs", "Selection" ], "native" ) ->
                    [ ( "font", "inherit" ), ( "color", "inherit" ), ( "background", "transparent" ), ( "border", "0" ), ( "padding", "0" ), ( "width", "100%" ), ( "box-sizing", "border-box" ) ]

                ( [ "MrJam", "Adaptateurs", "Saisie" ], "intrinseque" ) ->
                    [ ( "width", "max-content" ), ( "max-width", "100%" ), ( "flex-basis", "auto" ) ]

                ( [ "MrJam", "Adaptateurs", "Dialogue" ], "natif" ) ->
                    [ ( "background", "transparent" ), ( "border", "0" ), ( "padding", "0" ) ]

                ( [ "MrJam", "Adaptateurs", "Texte" ], "litteral" ) ->
                    [ ( "white-space", "pre-wrap" ), ( "overflow-wrap", "anywhere" ) ]

                ( [ "MrJam", "Adaptateurs", "Constructions" ], "encocheEntete" ) ->
                    [ ( "clip-path", "polygon(0 0,15px 0,21px 5px,38px 5px,44px 0,100% 0,100% 100%,0 100%)" ) ]

                ( [ "MrJam", "Adaptateurs", "Constructions" ], "encochePied" ) ->
                    [ ( "clip-path", "polygon(0 0,100% 0,100% calc(100% - 5px),44px calc(100% - 5px),38px 100%,21px 100%,15px calc(100% - 5px),0 calc(100% - 5px))" ) ]

                ( [ "MrJam", "Adaptateurs", "Constructions" ], "objet" ) ->
                    [ ( "clip-path", "polygon(10px 0,calc(100% - 10px) 0,100% 50%,calc(100% - 10px) 100%,10px 100%,0 50%)" ), ( "filter", "drop-shadow(0 1px 0 oklch(0.55163012 0.13717295 144.68276832))" ) ]

                ( [ "MrJam", "Adaptateurs", "Constructions" ], "neutre" ) ->
                    [ ( "filter", "drop-shadow(0 1px 0 oklch(0.69802785 0.14003027 82.64614801))" ) ]

                ( [ "MrJam", "Adaptateurs", "Constructions" ], "selectionne" ) ->
                    [ ( "filter", "drop-shadow(0 0 2px oklch(0.52094715 0.13971434 251.30770236)) drop-shadow(0 0 2px oklch(0.52094715 0.13971434 251.30770236))" ) ]

                ( [ "MrJam", "Adaptateurs", "Constructions" ], "incorrect" ) ->
                    [ ( "filter", "drop-shadow(0 0 2px oklch(0.50049969 0.17361526 28.26574628))" ) ]

                ( [ "MrJam", "Adaptateurs", "Typographie" ], "signature" ) ->
                    [ ( "line-height", "1.183" ) ]

                ( [ "MrJam", "Adaptateurs", "Typographie" ], "marque" ) ->
                    [ ( "line-height", "1.183" ), ( "white-space", "nowrap" ), ( "font-synthesis", "none" ), ( "user-select", "text" ) ]

                ( [ "MrJam", "Adaptateurs", "Typographie" ], "point" ) ->
                    [ ( "line-height", "0" ), ( "vertical-align", "-0.005em" ) ]

                ( [ "MrJam", "Adaptateurs", "Typographie" ], "titreVitrine" ) ->
                    [ ( "line-height", "1.06" ) ]

                ( [ "MrJam", "Adaptateurs", "Typographie" ], "titreSecondaireVitrine" ) ->
                    [ ( "line-height", "1.13" ) ]

                _ ->
                    []
    in
    shared context
        && (case Node.value node of
                Expression.Application [ callee, key, value ] ->
                    Lookup.moduleNameFor context.lookup callee
                        == Just [ "Html", "Attributes" ]
                        && (case ( Node.value callee, Node.value key, Node.value value ) of
                                ( Expression.FunctionOrValue _ "style", Expression.Literal name, Expression.Literal literal ) ->
                                    List.member ( name, literal ) resets

                                _ ->
                                    False
                           )

                _ ->
                    False
           )


nativeNode : Context -> Node Expression -> Bool
nativeNode context node =
    shared context
        && (case Node.value node of
                Expression.Application (callee :: argument :: _) ->
                    Lookup.moduleNameFor context.lookup callee
                        == Just [ "Html" ]
                        && (case ( ( context.moduleName, context.function ), Node.value callee, Node.value argument ) of
                                ( ( [ "MrJam", "Adaptateurs", "Dialogue" ], "natif" ), Expression.FunctionOrValue _ "node", Expression.Literal "dialog" ) ->
                                    True

                                ( ( [ "MrJam", "Adaptateurs", "Mathematiques" ], "expression" ), Expression.FunctionOrValue _ "node", Expression.Literal "math-tex" ) ->
                                    case Node.value node of
                                        Expression.Application [ _, _, _, children ] ->
                                            Node.value children == Expression.ListExpr []

                                        _ ->
                                            False

                                ( ( [ "MrJam", "Adaptateurs", "Video" ], "lecteur" ), Expression.FunctionOrValue _ "node", Expression.Literal "course-video" ) ->
                                    case Node.value node of
                                        Expression.Application [ _, _, _, children ] ->
                                            case Node.value children of
                                                Expression.ListExpr [ child ] ->
                                                    case Node.value child of
                                                        Expression.Application [ frame, _, empty ] ->
                                                            Lookup.moduleNameFor context.lookup frame
                                                                == Just [ "Html" ]
                                                                && (case Node.value frame of
                                                                        Expression.FunctionOrValue _ "iframe" ->
                                                                            True

                                                                        _ ->
                                                                            False
                                                                   )
                                                                && Node.value empty
                                                                == Expression.ListExpr []

                                                        _ ->
                                                            False

                                                _ ->
                                                    False

                                        _ ->
                                            False

                                ( ( [ "MrJam", "Adaptateurs", "Video" ], "lecteur" ), Expression.FunctionOrValue _ "iframe", _ ) ->
                                    case Node.value node of
                                        Expression.Application [ _, _, children ] ->
                                            Node.value children == Expression.ListExpr []

                                        _ ->
                                            False

                                ( ( [ "MrJam", "Adaptateurs", "Dialogue" ], "assembler" ), Expression.FunctionOrValue _ "div", Expression.ListExpr [] ) ->
                                    True

                                ( ( [ "MrJam", "Adaptateurs", "Complement" ], "natif" ), Expression.FunctionOrValue _ name, Expression.ListExpr [] ) ->
                                    List.member name [ "details", "summary" ]

                                ( ( [ "MrJam", "Adaptateurs", "Texte" ], "emphase" ), Expression.FunctionOrValue _ "em", Expression.ListExpr [] ) ->
                                    True

                                _ ->
                                    False
                           )

                _ ->
                    False
           )


nativeClass : Context -> Node Expression -> Bool
nativeClass context node =
    shared context
        && context.moduleName
        == [ "MrJam", "Adaptateurs", "Typographie" ]
        && (case Node.value node of
                Expression.Application [ callee, valeur ] ->
                    Lookup.moduleNameFor context.lookup callee
                        == Just [ "Html", "Attributes" ]
                        && (case ( context.function, Node.value callee, Node.value valeur ) of
                                ( fonction, Expression.FunctionOrValue _ "class", Expression.Literal "mrjam" ) ->
                                    List.member fonction [ "signature", "signatureEnLigne" ]

                                ( "point", Expression.FunctionOrValue _ "class", Expression.Literal "echo-point" ) ->
                                    True

                                _ ->
                                    False
                           )

                _ ->
                    False
           )


nativeCancel : Context -> Node Expression -> Bool
nativeCancel context node =
    shared context
        && (case Node.value node of
                Expression.Application (callee :: event :: _) ->
                    Lookup.moduleNameFor context.lookup callee
                        == Just [ "Html", "Events" ]
                        && (case ( ( context.moduleName, context.function ), Node.value callee, Node.value event ) of
                                ( ( [ "MrJam", "Adaptateurs", "Diagrammes" ], "plan" ), Expression.FunctionOrValue _ "preventDefaultOn", Expression.Literal "keydown" ) ->
                                    True

                                ( ( [ "MrJam", "Adaptateurs", "Dialogue" ], "natif" ), Expression.FunctionOrValue _ "preventDefaultOn", Expression.Literal "cancel" ) ->
                                    True

                                ( ( [ "MrJam", "Adaptateurs", "Saisie" ], "soumettre" ), Expression.FunctionOrValue _ "preventDefaultOn", Expression.Literal "keydown" ) ->
                                    True

                                ( ( [ "MrJam", "Adaptateurs", "Video" ], "lecteur" ), Expression.FunctionOrValue _ "on", Expression.Literal "video-etat" ) ->
                                    True

                                ( ( [ "MrJam", "Adaptateurs", "Saisie" ], "echap" ), Expression.FunctionOrValue _ "on", Expression.Literal "keydown" ) ->
                                    True

                                _ ->
                                    False
                           )

                _ ->
                    False
           )


nativeInput : Context -> Node Expression -> Bool
nativeInput context node =
    if shared context && context.moduleName == [ "MrJam", "Adaptateurs", "Curseur" ] && context.function == "natif" then
        case Node.value node of
            Expression.Application (callee :: arguments) ->
                Lookup.moduleNameFor context.lookup callee
                    == Just [ "Html", "Attributes" ]
                    && (case ( Node.value callee, List.map Node.value arguments ) of
                            ( Expression.FunctionOrValue _ "type_", [ Expression.Literal "range" ] ) ->
                                True

                            ( Expression.FunctionOrValue _ nom, [ _ ] ) ->
                                List.member nom [ "id", "min", "max", "step", "value" ]

                            _ ->
                                False
                       )

            _ ->
                False

    else if shared context && context.moduleName == [ "MrJam", "Adaptateurs", "Video" ] && context.function == "lecteur" then
        case Node.value node of
            Expression.Application [ callee, _ ] ->
                Lookup.moduleNameFor context.lookup callee
                    == Just [ "Html", "Attributes" ]
                    && (case Node.value callee of
                            Expression.FunctionOrValue _ name ->
                                List.member name [ "src", "title" ]

                            _ ->
                                False
                       )

            _ ->
                False

    else
        shared context
            && context.moduleName
            == [ "MrJam", "Adaptateurs", "Saisie" ]
            && (case Node.value node of
                    Expression.Application (callee :: arguments) ->
                        Lookup.moduleNameFor context.lookup callee
                            == Just [ "Html", "Attributes" ]
                            && (case ( context.function, Node.value callee, List.map Node.value arguments ) of
                                    ( fonction, Expression.FunctionOrValue _ "type_", [ Expression.Literal valeur ] ) ->
                                        List.member ( fonction, valeur ) [ ( "nombre", "number" ), ( "date", "date" ), ( "dateHeure", "datetime-local" ) ]

                                    ( fonction, Expression.FunctionOrValue _ "step", [ Expression.Literal "any" ] ) ->
                                        List.member fonction [ "nombre", "date", "dateHeure" ]

                                    ( "identifie", Expression.FunctionOrValue _ "attribute", [ Expression.Literal "autocapitalize", Expression.Literal "off" ] ) ->
                                        True

                                    ( "identifie", Expression.FunctionOrValue _ nom, [ Expression.FunctionOrValue [] "False" ] ) ->
                                        List.member nom [ "spellcheck", "autocomplete" ]

                                    ( "identifie", Expression.FunctionOrValue _ nom, [ _ ] ) ->
                                        List.member nom [ "placeholder", "maxlength" ]

                                    _ ->
                                        False
                               )

                    _ ->
                        False
               )


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


{-| Une seule propriété dynamique : zoom, valeur canonique bornée 50–150%.
L'AST impose le clamp et les conversions, aucune chaîne CSS libre.
-}
nativeZoom : Context -> Node Expression -> Bool
nativeZoom context node =
    shared context
        && context.moduleName
        == [ "MrJam", "Adaptateurs", "Manipulation" ]
        && context.function
        == "zoom"
        && context.zoomArgumentUnique
        && (case Node.value node of
                Expression.Application [ callee, key, value ] ->
                    Lookup.moduleNameFor context.lookup callee
                        == Just [ "Html", "Attributes" ]
                        && Node.value key
                        == Expression.Literal "zoom"
                        && (case Node.value callee of
                                Expression.FunctionOrValue _ "style" ->
                                    zoomString context (unparenthesize value)

                                _ ->
                                    False
                           )

                _ ->
                    False
           )


unparenthesize : Node Expression -> Node Expression
unparenthesize node =
    case Node.value node of
        Expression.ParenthesizedExpression inner ->
            unparenthesize inner

        _ ->
            node


zoomString : Context -> Node Expression -> Bool
zoomString context node =
    case Node.value node of
        Expression.Application [ convert, argument ] ->
            Lookup.moduleNameFor context.lookup convert
                == Just [ "String" ]
                && Node.value convert
                == Expression.FunctionOrValue [ "String" ] "fromFloat"
                && (case Node.value (unparenthesize argument) of
                        Expression.OperatorApplication "/" _ numerator denominator ->
                            Node.value denominator
                                == Expression.Integer 100
                                && (case Node.value numerator of
                                        Expression.Application [ conversion, range ] ->
                                            Node.value conversion
                                                == Expression.FunctionOrValue [] "toFloat"
                                                && (case Node.value (unparenthesize range) of
                                                        Expression.Application [ bound, lower, upper, input ] ->
                                                            Node.value bound
                                                                == Expression.FunctionOrValue [] "clamp"
                                                                && Node.value lower
                                                                == Expression.Integer 50
                                                                && Node.value upper
                                                                == Expression.Integer 150
                                                                && Node.value input
                                                                == Expression.FunctionOrValue [] "pourcentage"

                                                        _ ->
                                                            False
                                                   )

                                        _ ->
                                            False
                                   )

                        _ ->
                            False
                   )

        _ ->
            False
