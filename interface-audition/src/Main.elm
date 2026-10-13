port module Main exposing (Msg(..), init, main, update)

import Browser
import Browser.Dom
import Dict exposing (Dict)
import Donnees as D
import Element as UI
import Html exposing (Html)
import Json.Decode as Decode
import Json.Encode as E
import MrJam
import MrJam.Animations as Animations
import MrJam.Contexte as Contexte
import MrJam.Documents as Documents
import MrJam.Ecran as Ecran
import MrJam.Mathematiques as Maths
import MrJam.Tableaux as Tableaux
import MrJam.Transitions as T
import Task
import Time
import Url


port demander : E.Value -> Cmd msg


port recevoir : (E.Value -> msg) -> Sub msg


port mouvementReduit : (Bool -> msg) -> Sub msg


port naviguer : String -> Cmd msg


port routeChangee : (String -> msg) -> Sub msg


port visible : (Bool -> msg) -> Sub msg


type alias Critere =
    { id : String, attendu : String, texte : String, maximum : String }


type alias Brouillon =
    { titre : String, consigne : String, attendus : String, attenduIds : List String, criteres : List Critere, cours : String, corrige : String, publication : String, typeActivite : String, propositions : String, revision : Int, modifie : Bool }


type alias Modele =
    { vue : String
    , acteur : String
    , groupes : List E.Value
    , groupe : String
    , admin : Bool
    , donnees : Dict String E.Value
    , drafts : Dict String Brouillon
    , draftsCours : Dict String (Dict String String)
    , edition : String
    , selection : String
    , champs : Dict String String
    , eleves : List String
    , erreur : String
    , avis : String
    , occupe : Bool
    , expire : Bool
    , largeur : Int
    , auPremierPlan : Bool
    , transition : T.Transition Bool
    , aideOuverte : Bool
    , pages : Dict String (List Int)
    , brouillonEnvoye : Maybe Brouillon
    , editionEnvoyee : String
    , champsEnvoyes : Dict String String
    }


type Msg
    = Vue String
    | Route String
    | Groupe String
    | Champ String String
    | Modifier String String
    | CritereChamp Int String String
    | AjouterCritere
    | ChoisirEleve String Bool
    | Editer E.Value
    | NouvelleActivite
    | EditerCours E.Value
    | Calendrier E.Value
    | Consentir Bool
    | Page String Bool
    | EnregistrerActivite
    | Operation String E.Value
    | Reponse E.Value
    | Traces String
    | Annoter E.Value
    | AccepterVersion
    | Reessayer
    | Rafraichir Time.Posix
    | Visibilite Bool
    | Largeur Int
    | Frame Time.Posix
    | Reduction Bool
    | Devoiler
    | Focus (Result Browser.Dom.Error ())


contexte : Contexte.Contexte
contexte =
    Contexte.pour "Audition"


commun : MrJam.Interface String Msg
commun =
    MrJam.pour contexte


vide : Brouillon
vide =
    { titre = "", consigne = "", attendus = "", attenduIds = [], criteres = [ { id = "critere-1", attendu = "attendu-1", texte = "", maximum = "1" } ], cours = "", corrige = "", publication = "", typeActivite = "ouverte", propositions = "4", revision = 0, modifie = False }


main : Program Decode.Value Modele Msg
main =
    Browser.element { init = init, update = update, view = view, subscriptions = subscriptions }


init : Decode.Value -> ( Modele, Cmd Msg )
init flags =
    ( { vue = "accueil", acteur = "", groupes = [], groupe = "", admin = False, donnees = Dict.empty, drafts = Dict.singleton "nouvelle" vide, draftsCours = Dict.empty, edition = "nouvelle", selection = "", champs = Dict.empty, eleves = [], erreur = "", avis = "", occupe = False, expire = False, largeur = D.entier "largeur" flags, auPremierPlan = True, transition = T.reduire (D.booleen "reduit" flags) (T.initialiser False), aideOuverte = False, pages = Dict.empty, brouillonEnvoye = Nothing, editionEnvoyee = "", champsEnvoyes = Dict.empty }
    , Cmd.batch [ demander (E.object [ ( "operation", E.string "initialiser" ) ]), naviguer (D.texte "route" flags) ]
    )


subscriptions : Modele -> Sub Msg
subscriptions m =
    Sub.batch
        [ recevoir Reponse
        , mouvementReduit Reduction
        , routeChangee Route
        , visible Visibilite
        , Ecran.redimensionnements Largeur
        , T.abonnement Frame m.transition
        , if m.auPremierPlan && m.acteur /= "" && m.groupe /= "" && List.member m.vue [ "suivre", "eleve", "seance" ] then
            Time.every 20000 Rafraichir

          else
            Sub.none
        ]


brouillon : Modele -> Brouillon
brouillon m =
    Maybe.withDefault vide (Dict.get m.edition m.drafts)


valeur : String -> Modele -> String
valeur cle m =
    Maybe.withDefault "" (Dict.get cle m.champs)


data : String -> Modele -> E.Value
data cle m =
    Maybe.withDefault E.null (Dict.get cle m.donnees)


connexion : Modele -> String
connexion m =
    let
        retour =
            if List.member m.vue [ "seance", "activite", "cours", "affectation" ] && m.selection /= "" then
                "/#" ++ m.vue ++ "/" ++ m.selection

            else if List.member m.vue [ "preparer", "suivre", "administration", "eleve", "aide" ] then
                "/#" ++ m.vue

            else
                "/#eleve"
    in
    "/auth/connexion?retour=" ++ Url.percentEncode retour


attenduId : Brouillon -> Int -> String
attenduId b i =
    List.drop i b.attenduIds
        |> List.head
        |> Maybe.withDefault
            (List.range 1 65
                |> List.map
                    (\n ->
                        "attendu-"
                            ++ String.fromInt (i + 1)
                            ++ (if n == 1 then
                                    ""

                                else
                                    "-" ++ String.fromInt n
                               )
                    )
                |> List.filter (\id -> not (List.member id b.attenduIds))
                |> List.head
                |> Maybe.withDefault "attendu-nouveau"
            )


debutPage : String -> Modele -> Int
debutPage op m =
    Dict.get (op ++ ":" ++ m.groupe ++ ":" ++ m.selection) m.pages |> Maybe.andThen List.head |> Maybe.withDefault 0


pagination : String -> E.Value -> Modele -> UI.Element Msg
pagination op document m =
    (Documents.pour contexte).pagination
        { debut = debutPage op m
        , total = D.entier "total" document
        , taille = max 1 (List.length (D.liste "elements" document))
        , precedent = Page op False
        , suivant = Page op True
        }


role : Modele -> String
role m =
    m.groupes |> List.filter (\g -> D.texte "id" g == m.groupe) |> List.head |> Maybe.map (D.texte "role") |> Maybe.withDefault ""


envoyer : String -> E.Value -> Modele -> ( Modele, Cmd Msg )
envoyer op document m =
    if m.occupe then
        ( m, Cmd.none )

    else
        ( { m | occupe = True, erreur = "", avis = "", brouillonEnvoye = Just (brouillon m), editionEnvoyee = m.edition, champsEnvoyes = m.champs }, demander (E.object [ ( "operation", E.string op ), ( "document", document ) ]) )


params : Modele -> List ( String, E.Value ) -> E.Value
params m p =
    E.object (( "groupe", E.string m.groupe ) :: p)


chargerVue : Modele -> Cmd Msg
chargerVue m =
    let
        op =
            case m.vue of
                "preparer" ->
                    "preparations"

                "suivre" ->
                    "rapport"

                "administration" ->
                    "membres"

                "seance" ->
                    "consulter_seance"

                _ ->
                    "travaux"
    in
    if m.acteur /= "" && List.member m.vue [ "seance", "activite", "cours", "affectation" ] && m.selection /= "" && D.texte "id" (data "lien" m) /= m.selection then
        demander (E.object [ ( "operation", E.string "retrouver" ), ( "document", E.object [ ( "id", E.string m.selection ) ] ) ])

    else if m.acteur /= "" && m.vue == "consentement" then
        demander (E.object [ ( "operation", E.string "oauth_demande" ), ( "document", E.object [ ( "id", E.string m.selection ) ] ) ])

    else if m.acteur == "" || m.groupe == "" || List.member m.vue [ "accueil", "aide", "activite", "cours", "affectation" ] then
        Cmd.none

    else if m.vue == "suivre" then
        Cmd.batch
            [ demander
                (E.object
                    [ ( "operation", E.string "rapport" )
                    , ( "document"
                      , params m
                            ([ ( "offset", E.int (debutPage "rapport" m) ) ]
                                ++ (if valeur "filtre-activite" m == "" then
                                        []

                                    else
                                        [ ( "activite", E.string (valeur "filtre-activite" m) ) ]
                                   )
                            )
                      )
                    ]
                )
            , if Dict.member "preparations" m.donnees then
                Cmd.none

              else
                demander (E.object [ ( "operation", E.string "preparations" ), ( "document", params m [] ) ])
            ]

    else
        demander
            (E.object
                [ ( "operation", E.string op )
                , ( "document"
                  , params m
                        (if op == "consulter_seance" then
                            [ ( "id", E.string m.selection ), ( "offset", E.int (debutPage op m) ) ]

                         else
                            [ ( "offset", E.int (debutPage op m) ) ]
                        )
                  )
                ]
            )


update : Msg -> Modele -> ( Modele, Cmd Msg )
update msg m =
    case msg of
        Vue v ->
            ( m, naviguer v )

        Route route ->
            let
                parts =
                    String.split "/"
                        (String.dropLeft
                            (if String.startsWith "#" route then
                                1

                             else
                                0
                            )
                            route
                        )

                brut =
                    Maybe.withDefault "accueil" (List.head parts)

                estConsentement =
                    String.startsWith "autorisation-mcp=" brut

                v =
                    if estConsentement then
                        "consentement"

                    else if brut == "enseignant" then
                        "preparer"

                    else
                        brut

                suivant =
                    { m
                        | vue =
                            if v == "" then
                                "accueil"

                            else
                                v
                        , selection =
                            if estConsentement then
                                String.dropLeft (String.length "autorisation-mcp=") brut

                            else
                                Maybe.withDefault m.selection (List.head (List.drop 1 parts))
                        , avis = ""
                    }
            in
            ( suivant, chargerVue suivant )

        Groupe g ->
            let
                suivant =
                    { m | groupe = g, selection = "", eleves = [] }
            in
            ( suivant, chargerVue suivant )

        Champ cle v ->
            ( { m | champs = Dict.insert cle v m.champs }, Cmd.none )

        Modifier cle v ->
            let
                b =
                    brouillon m

                nouveau =
                    case cle of
                        "titre" ->
                            { b | titre = v, modifie = True }

                        "consigne" ->
                            { b | consigne = v, modifie = True }

                        "attendus" ->
                            { b | attendus = v, modifie = True }

                        "type" ->
                            { b | typeActivite = v, modifie = True }

                        "propositions" ->
                            { b | propositions = v, modifie = True }

                        "cours" ->
                            { b | cours = v, modifie = True }

                        "corrige" ->
                            { b | corrige = v, modifie = True }

                        _ ->
                            { b | publication = v, modifie = True }
            in
            ( { m | drafts = Dict.insert m.edition nouveau m.drafts }, Cmd.none )

        CritereChamp indice cle v ->
            let
                b =
                    brouillon m

                modifier i c =
                    if i /= indice then
                        c

                    else if cle == "maximum" then
                        { c | maximum = v }

                    else if cle == "attendu" then
                        { c | attendu = v }

                    else
                        { c | texte = v }
            in
            ( { m | drafts = Dict.insert m.edition { b | criteres = List.indexedMap modifier b.criteres, modifie = True } m.drafts }, Cmd.none )

        AjouterCritere ->
            let
                b =
                    brouillon m

                c =
                    { id = "critere-" ++ String.fromInt (List.length b.criteres + 1), attendu = attenduId b 0, texte = "", maximum = "1" }
            in
            ( { m | drafts = Dict.insert m.edition { b | criteres = b.criteres ++ [ c ], modifie = True } m.drafts }, Cmd.none )

        ChoisirEleve eleve choix ->
            ( { m
                | eleves =
                    if choix then
                        eleve :: List.filter ((/=) eleve) m.eleves

                    else
                        List.filter ((/=) eleve) m.eleves
              }
            , Cmd.none
            )

        NouvelleActivite ->
            ( { m | edition = "nouvelle", avis = "Le brouillon précédent est conservé." }, Cmd.none )

        EditerCours cours ->
            let
                d =
                    D.champ "document" cours

                id =
                    D.texte "id" cours

                archives =
                    Dict.insert (valeur "cours-id" m) (Dict.filter (\k _ -> String.startsWith "cours-" k) m.champs) m.draftsCours

                champsCours =
                    Dict.get id archives
                        |> Maybe.withDefault (Dict.fromList [ ( "cours-id", id ), ( "cours-revision", String.fromInt (D.entier "revision" cours) ), ( "cours-titre", D.texte "titre" d ), ( "cours-contenu", D.texte "contenu" d ) ])
            in
            ( { m | champs = Dict.union champsCours (Dict.filter (\k _ -> not (String.startsWith "cours-" k)) m.champs), draftsCours = archives }, naviguer "preparer" )

        Calendrier affectation ->
            let
                d =
                    D.champ "document" affectation
            in
            ( { m | champs = Dict.insert "affectation-id" (D.texte "id" affectation) (Dict.insert "affectation-revision" (String.fromInt (D.entier "revision" affectation)) (Dict.insert "echeance" (String.dropRight 4 (date (D.entier "echeance" d))) m.champs)), edition = D.texte "activite" d, eleves = List.filterMap (\v -> Decode.decodeValue Decode.string v |> Result.toMaybe) (D.liste "eleves" d) }, naviguer "preparer" )

        Consentir decision ->
            envoyer "oauth_consentement"
                (E.object
                    [ ( "id", E.string m.selection )
                    , ( "decision"
                      , E.string
                            (if decision then
                                "autoriser"

                             else
                                "refuser"
                            )
                      )
                    ]
                )
                m

        Page op avancer ->
            let
                cle =
                    op ++ ":" ++ m.groupe ++ ":" ++ m.selection

                historique =
                    Maybe.withDefault [ 0 ] (Dict.get cle m.pages)

                source =
                    if op == "consulter_seance" then
                        D.champ "traces" (data "seance" m)

                    else
                        data op m

                positions =
                    if avancer then
                        D.entier "suivant" source :: historique

                    else
                        List.drop 1 historique

                suivant =
                    { m
                        | pages =
                            Dict.insert cle
                                (if List.isEmpty positions then
                                    [ 0 ]

                                 else
                                    positions
                                )
                                m.pages
                    }
            in
            envoyer op
                (params m
                    ([ ( "offset", E.int (debutPage op suivant) ) ]
                        ++ (if op == "consulter_seance" then
                                [ ( "id", E.string m.selection ) ]

                            else
                                []
                           )
                    )
                )
                suivant

        Editer a ->
            let
                id =
                    D.texte "id" a

                d =
                    D.champ "document" a

                b =
                    { titre = D.texte "titre" d
                    , consigne = D.texte "consigne" d
                    , attendus = String.join "\n" (List.map (D.texte "texte") (D.liste "attendus" d))
                    , attenduIds = List.map (D.texte "id") (D.liste "attendus" d)
                    , criteres = List.map (\c -> { id = D.texte "id" c, attendu = D.texte "attendu" c, texte = D.texte "texte" c, maximum = String.fromFloat (D.decimal "maximum" c) }) (D.liste "criteres" d)
                    , cours = D.texte "cours" d
                    , corrige = D.texte "corrige" d
                    , publication =
                        if D.entier "publication_corrige" d > 0 then
                            String.dropRight 4 (date (D.entier "publication_corrige" d))

                        else
                            ""
                    , typeActivite =
                        if D.texte "type" d == "qcm" then
                            "qcm"

                        else
                            "ouverte"
                    , propositions =
                        if D.entier "propositions" d > 1 then
                            String.fromInt (D.entier "propositions" d)

                        else
                            "4"
                    , revision = D.entier "revision" a
                    , modifie = False
                    }
            in
            ( { m
                | edition = id
                , drafts =
                    if Dict.member id m.drafts then
                        m.drafts

                    else
                        Dict.insert id b m.drafts
              }
            , if m.vue == "activite" then
                naviguer "preparer"

              else
                Cmd.none
            )

        AccepterVersion ->
            let
                b =
                    brouillon m

                actuel =
                    D.liste "elements" (data "preparations" m) |> List.filter (\a -> D.texte "id" a == m.edition) |> List.head

                rev =
                    Maybe.withDefault b.revision (Maybe.map (D.entier "revision") actuel)
            in
            ( { m | drafts = Dict.insert m.edition { b | revision = rev } m.drafts, avis = "Version serveur adoptée explicitement. Votre saisie est conservée ; vérifiez les différences avant d'enregistrer." }, Cmd.none )

        EnregistrerActivite ->
            let
                b =
                    brouillon m

                attendu i t =
                    E.object [ ( "id", E.string (attenduId b i) ), ( "texte", E.string t ) ]

                critere c =
                    E.object [ ( "id", E.string c.id ), ( "attendu", E.string c.attendu ), ( "texte", E.string c.texte ), ( "maximum", Maybe.withDefault E.null (Maybe.map E.float (String.toFloat c.maximum)) ) ]

                d =
                    E.object
                        ([ ( "titre", E.string b.titre ), ( "consigne", E.string b.consigne ), ( "attendus", E.list identity (List.indexedMap attendu (String.lines b.attendus)) ), ( "criteres", E.list critere b.criteres ), ( "type", E.string b.typeActivite ), ( "corrige", E.string b.corrige ) ]
                            ++ (if b.typeActivite == "qcm" then
                                    [ ( "propositions", Maybe.withDefault E.null (Maybe.map E.int (String.toInt b.propositions)) ) ]

                                else
                                    []
                               )
                            ++ (if b.cours == "" then
                                    []

                                else
                                    [ ( "cours", E.string b.cours ) ]
                               )
                            ++ (if b.publication == "" then
                                    []

                                else
                                    [ ( "publication_corrige", E.string b.publication ) ]
                               )
                        )
            in
            envoyer "activite"
                (params m
                    ([ ( "document", d ) ]
                        ++ (if m.edition == "nouvelle" then
                                []

                            else
                                [ ( "id", E.string m.edition ), ( "revision", E.int b.revision ) ]
                           )
                    )
                )
                m

        Operation op p ->
            envoyer op p m

        Reessayer ->
            ( { m | occupe = True }, demander (E.object [ ( "operation", E.string "reessayer" ) ]) )

        Reponse response ->
            let
                op =
                    D.texte "operation" response

                d =
                    D.champ "document" response

                statut =
                    D.entier "statut" response

                erreur =
                    D.texte "erreur" response
            in
            if D.texte "groupe" response /= "" && D.texte "groupe" response /= m.groupe then
                ( { m | occupe = False }, Cmd.none )

            else if erreur /= "" || statut >= 400 then
                ( { m
                    | occupe = False
                    , expire = statut == 401
                    , erreur =
                        expliquer
                            (if erreur /= "" then
                                erreur

                             else
                                D.texte "erreur" d
                            )
                  }
                , Cmd.none
                )

            else if op == "initialiser" || op == "contexte" then
                let
                    gs =
                        D.liste "elements" d

                    groupe =
                        if List.any (\g -> D.texte "id" g == m.groupe) gs then
                            m.groupe

                        else
                            Maybe.withDefault "" (Maybe.map (D.texte "id") (List.head gs))

                    suivant =
                        { m | acteur = D.texte "acteur" d, groupes = gs, groupe = groupe, admin = D.booleen "administrateur" d, occupe = False, expire = False }
                in
                ( suivant, chargerVue suivant )

            else if op == "retrouver" then
                let
                    suivant =
                        { m | groupe = D.texte "groupe" d, donnees = Dict.insert "detail" (D.champ "objet" d) (Dict.insert "lien" d m.donnees), occupe = False }
                in
                ( suivant, chargerVue suivant )

            else
                let
                    estSeance =
                        List.member op [ "ouvrir_seance", "consulter_seance", "adopter_contexte", "consigner", "transition" ]

                    b =
                        Maybe.withDefault (Maybe.withDefault vide m.brouillonEnvoye) (Dict.get m.editionEnvoyee m.drafts)

                    modifieApresEnvoi =
                        Maybe.withDefault False (Maybe.map ((/=) b) m.brouillonEnvoye)

                    suivant =
                        { m
                            | occupe = False
                            , erreur = ""
                            , donnees =
                                Dict.insert
                                    (if estSeance then
                                        "seance"

                                     else
                                        op
                                    )
                                    d
                                    m.donnees
                            , drafts =
                                if op == "activite" then
                                    Dict.insert (D.texte "id" d) { b | revision = D.entier "revision" d, modifie = modifieApresEnvoi } m.drafts

                                else
                                    m.drafts
                            , edition =
                                if op == "activite" && m.edition == m.editionEnvoyee then
                                    D.texte "id" d

                                else
                                    m.edition
                            , champs =
                                if op == "cours" && valeur "cours-id" m == Maybe.withDefault "" (Dict.get "cours-id" m.champsEnvoyes) then
                                    Dict.insert "cours-id" (D.texte "id" d) (Dict.insert "cours-revision" (String.fromInt (D.entier "revision" d)) m.champs)

                                else
                                    m.champs
                            , avis =
                                if op == "supprimer_groupe" then
                                    "Suppression confirmée par le serveur."

                                else if List.member op [ "activite", "cours", "affecter", "habiliter", "creer_groupe", "supprimer_groupe", "rectifier", "remediation" ] then
                                    if modifieApresEnvoi || m.champs /= m.champsEnvoyes then
                                        "Enregistrement confirmé. Votre nouvelle saisie reste à enregistrer."

                                    else
                                        "Enregistré par le serveur."

                                else
                                    m.avis
                        }
                in
                ( suivant
                , if op == "ouvrir_seance" then
                    naviguer ("seance/" ++ D.texte "id" (D.champ "seance" d))

                  else if List.member op [ "activite", "cours", "affecter", "habiliter", "creer_groupe", "supprimer_groupe", "rectifier", "remediation" ] then
                    Cmd.batch [ chargerVue suivant, demander (E.object [ ( "operation", E.string "contexte" ), ( "document", E.object [] ) ]) ]

                  else
                    Cmd.none
                )

        Traces id ->
            ( { m | selection = id }, naviguer ("seance/" ++ id) )

        Annoter tentative ->
            ( { m | champs = Dict.insert "critere" (Maybe.withDefault "" (Maybe.map (D.texte "critere") (List.head (D.liste "observations" tentative)))) (Dict.insert "tentative" (D.texte "id" tentative) m.champs), avis = "Choisissez un critère et justifiez la rectification." }, Task.attempt Focus (Browser.Dom.focus "annotation") )

        Rafraichir _ ->
            ( m
            , if m.occupe || m.erreur /= "" then
                Cmd.none

              else
                chargerVue m
            )

        Visibilite v ->
            ( { m | auPremierPlan = v }, Cmd.none )

        Largeur largeur ->
            ( { m | largeur = largeur }, Cmd.none )

        Frame t ->
            ( { m | transition = T.mettreAJour t m.transition }, Cmd.none )

        Reduction v ->
            ( { m | transition = T.reduire v m.transition }, Cmd.none )

        Devoiler ->
            ( { m | aideOuverte = not m.aideOuverte, transition = T.aller 180 (not m.aideOuverte) m.transition }, Cmd.none )

        Focus _ ->
            ( m, Cmd.none )


expliquer : String -> String
expliquer code =
    case code of
        "session_expiree" ->
            "Votre session a expiré. Votre saisie est conservée. Reconnectez-vous puis réessayez."

        "conflit_revision" ->
            "Une modification a été enregistrée entre-temps. Votre saisie est conservée ; relisez la version serveur avant de la reprendre."

        "proposition_non_validee" ->
            "Cette proposition du LLM doit être relue et enregistrée par un enseignant avant prescription."

        "rapport_trop_large_preciser_activite" ->
            "Choisissez une activité pour afficher cette grande classe."

        "contexte_modifie" ->
            "Les consignes ont changé. Relisez les nouvelles règles et adoptez explicitement le contexte avant de continuer."

        "date_invalide" ->
            "Indiquez une date et une heure UTC au format AAAA-MM-JJ HH:MM."

        "groupe_interdit" ->
            "Vous n'êtes pas habilité pour cette opération dans ce groupe."

        "seance_incomplete" ->
            "La séance ne peut pas être terminée : des productions ou observations manquent."

        "criteres_non_observes" ->
            "Tous les critères doivent être observés avant de terminer ; interrompez la séance si le travail reste incomplet."

        "reseau" ->
            "Le suivi n'est pas confirmé. Votre saisie est conservée. Relisez l'état puis réessayez l'enregistrement."

        "verification_renforcee_requise" ->
            "Cette action sensible exige une confirmation récente avec Log. Votre saisie est conservée."

        _ ->
            "L'opération n'a pas été confirmée. Vérifiez les champs et vos droits, puis réessayez."


view : Modele -> Html Msg
view m =
    Documents.espaceMarque "Audition"
        []
        Nothing
        ([ UI.wrappedRow [ UI.width UI.fill, UI.spacing 8 ]
            ([ commun.boutonSecondaire "Accueil" (Vue "accueil"), commun.boutonSecondaire "Aide" (Vue "aide") ]
                ++ (if m.acteur == "" then
                        [ commun.lien "Se connecter avec Log" (connexion m) ]

                    else if role m == "eleve" then
                        [ commun.boutonSecondaire "Mon travail" (Vue "eleve") ]

                    else if role m == "enseignant" then
                        [ commun.boutonSecondaire "Travaux affectés" (Vue "eleve") ]

                    else
                        []
                   )
                ++ (if role m == "enseignant" then
                        [ commun.boutonSecondaire "Préparer" (Vue "preparer"), commun.boutonSecondaire "Suivre la classe" (Vue "suivre") ]

                    else
                        []
                   )
                ++ (if m.admin then
                        [ commun.boutonSecondaire "Administration" (Vue "administration") ]

                    else
                        []
                   )
            )
         , if m.acteur /= "" then
            commun.selecteur "Groupe" (List.map (\g -> ( D.texte "id" g, D.texte "nom" g )) m.groupes) m.groupe Groupe

           else
            UI.none
         , if m.acteur /= "" then
            commun.texteSecondaire ("Compte métier : " ++ m.acteur)

           else
            UI.none
         , if m.erreur /= "" then
            commun.avis MrJam.Erreur m.erreur

           else
            UI.none
         , if m.erreur /= "" then
            commun.boutonSecondaire "Réessayer après vérification" Reessayer

           else
            UI.none
         , if m.expire then
            commun.lienExterne "Reconnexion — votre saisie reste ouverte ici" (connexion m)

           else
            UI.none
         , if m.erreur == expliquer "verification_renforcee_requise" then
            commun.lienExterne "Reconfirmer mon identité avec Log" (connexion m ++ "&verification=renforcee")

           else
            UI.none
         , if m.avis /= "" then
            commun.avis MrJam.Information m.avis

           else
            UI.none
         , if m.occupe then
            commun.texteSecondaire "Enregistrement ou chargement en cours…"

           else
            UI.none
         ]
            ++ (case m.vue of
                    "preparer" ->
                        if role m /= "enseignant" then
                            [ commun.avis MrJam.Information "Connectez-vous avec Log et choisissez un groupe où vous êtes enseignant." ]

                        else if not (Dict.member "preparations" m.donnees) then
                            [ commun.texteSecondaire "Chargement des prescriptions du groupe…" ]

                        else
                            preparation m

                    "suivre" ->
                        rapport m

                    "administration" ->
                        administration m

                    "eleve" ->
                        travail m

                    "seance" ->
                        seance m

                    "consentement" ->
                        consentement m

                    "activite" ->
                        detail m

                    "cours" ->
                        detail m

                    "affectation" ->
                        detail m

                    "aide" ->
                        aide m

                    _ ->
                        accueil m
               )
            ++ (if m.acteur /= "" then
                    [ commun.boutonSecondaire "Se déconnecter" (Operation "deconnexion" (E.object [])) ]

                else
                    []
               )
        )


detail : Modele -> List (UI.Element Msg)
detail m =
    let
        o =
            data "detail" m

        d =
            D.champ "document" o
    in
    [ commun.section
        (if m.vue == "affectation" then
            "Travail affecté"

         else
            D.texte "titre" d
        )
        [ Maths.document
            (if m.vue == "cours" then
                D.texte "contenu" d

             else
                D.texte "consigne" d
            )
        , if m.vue == "affectation" then
            commun.bouton "Ouvrir ma séance" (Operation "ouvrir_seance" (params m [ ( "affectation", E.string m.selection ) ]))

          else
            UI.none
        , if role m == "enseignant" && m.vue == "activite" then
            commun.boutonSecondaire "Préparer cette activité" (Editer o)

          else
            UI.none
        ]
    ]


consentement : Modele -> List (UI.Element Msg)
consentement m =
    let
        demande =
            data "oauth_demande" m
    in
    [ commun.section "Autoriser votre tuteur"
        [ MrJam.paragraphe ("Le connecteur « " ++ D.texte "client" demande ++ " » demande l'accès à Audition.")
        , MrJam.paragraphe "Il pourra consulter votre travail et enregistrer les traces pédagogiques autorisées pour votre compte. Les rattachements et droits serveur continuent de s'appliquer à chaque opération."
        , commun.texteSecondaire ("Retour vers : " ++ D.texte "redirect_uri" demande)
        , if m.occupe then
            commun.boutonEnCours "Autorisation en cours…"

          else
            commun.bouton "Autoriser ce connecteur" (Consentir True)
        , commun.boutonSecondaire "Refuser" (Consentir False)
        ]
    ]


accueil : Modele -> List (UI.Element Msg)
accueil m =
    [ commun.section "Comprendre ce que chacun sait faire"
        [ MrJam.paragraphe "L'enseignant prépare le travail. L'élève réfléchit avec son LLM. Audition restitue les productions, les difficultés, les aides et les remédiations pour mieux accompagner chaque apprentissage."
        , MrJam.paragraphe "Mathématiques et physique au lycée, raisonnements et productions ouvertes, avec un modèle également utilisable dans le supérieur."
        , commun.lien "Commencer" "/auth/connexion?retour=%2F%23eleve"
        ]
    , commun.section "Trois acteurs, un travail partagé"
        [ MrJam.paragraphe "1. L'enseignant définit cours, exercices, attendus, critères et échéances, puis affecte le travail."
        , MrJam.paragraphe "2. L'élève ouvre sa séance et connecte le LLM de son choix. Le tuteur laisse répondre, propose des indices et trace les aides."
        , MrJam.paragraphe "3. L'enseignant consulte les constats, retrouve les traces et ajuste l'accompagnement. Une absence de trace reste une absence d'observation."
        ]
    , commun.section "Un partage expliqué"
        [ MrJam.paragraphe "L'enseignant rattaché au groupe voit les productions liées au travail affecté, les observations justifiées, les aides et les rectifications. Audition n'aspire pas votre conversation privée."
        , MrJam.paragraphe "Les interprétations du LLM sont attribuées et révisables. Une solution fournie n'est jamais présentée comme une réussite autonome."
        , MrJam.paragraphe "Audition ne vend pas de jetons et n'impose aucun fournisseur. La disponibilité d'un connecteur dépend de votre LLM et de votre offre."
        , commun.boutonSecondaire "Guide de démarrage" (Vue "aide")
        , commun.boutonDevoiler "details-suivi"
            (if m.aideOuverte then
                "Masquer les détails"

             else
                "Détails du suivi"
            )
            m.aideOuverte
            Devoiler
        , Documents.repere "details-suivi" <|
            Animations.deploiement
                (if m.largeur < 600 then
                    280

                 else
                    160
                )
                m.transition
                (MrJam.paragraphe "Les heures d'activité et de réception sont conservées en UTC. Les consignes et barèmes restent versionnés. Les rapports distinguent non observé, difficulté, réussite aidée et réussite autonome.")
        ]
    ]


aide : Modele -> List (UI.Element Msg)
aide _ =
    [ commun.section "Connecter votre LLM"
        [ MrJam.paragraphe "Connectez-vous avec Log puis ouvrez un travail affecté. Dans votre LLM, ajoutez un connecteur MCP distant avec l'adresse https://audition.mrj.am/mcp et choisissez l'authentification OAuth. Autorisez le connecteur avec votre propre compte Log."
        , MrJam.paragraphe "Demandez au tuteur de lire votre contexte Audition, de vous annoncer le cadre et d'ouvrir votre séance avant de commencer. N'utilisez jamais un jeton partagé entre élèves."
        , MrJam.paragraphe "Mistral : consultez la disponibilité des connecteurs personnalisés dans votre offre. Aucun essai réel avec un compte élève Mistral n'a été effectué pour cette version."
        , commun.lienExterne "Documentation et offres Mistral" "https://mistral.ai/pricing/"
        ]
    , commun.section "Résoudre un problème de connexion"
        [ MrJam.paragraphe "Connecteur absent : vérifiez l'offre et les droits de votre compte fournisseur. Connexion refusée : reconnectez-vous avec Log et vérifiez votre rattachement au groupe. Catalogue ancien : reconnectez le connecteur et relisez les outils."
        , MrJam.paragraphe "Après une interruption ou un délai dépassé, demandez de relire la séance avant de reprendre. Un enregistrement non confirmé reste signalé comme tel. Un problème de connexion ne devient pas une difficulté scolaire."
        ]
    ]


preparation : Modele -> List (UI.Element Msg)
preparation m =
    let
        b =
            brouillon m

        preparations =
            data "preparations" m

        attente =
            if m.occupe then
                commun.boutonEnCours "Enregistrement…"

            else
                commun.bouton "Enregistrer l'activité" EnregistrerActivite

        critere i c =
            commun.carte [ commun.champ ("Critère " ++ String.fromInt (i + 1)) c.texte (CritereChamp i "texte"), commun.selecteur "Attendu de ce critère" (List.indexedMap (\n t -> ( attenduId b n, t )) (String.lines b.attendus)) c.attendu (CritereChamp i "attendu"), commun.champ "Barème maximum" c.maximum (CritereChamp i "maximum") ]
    in
    [ commun.section "Cours"
        [ commun.boutonSecondaire "Nouveau cours" (EditerCours (E.object []))
        , UI.wrappedRow [ UI.spacing 8 ] (List.map (\c -> commun.boutonSecondaire (D.texte "titre" (D.champ "document" c)) (EditerCours c)) (D.liste "cours" preparations))
        , commun.champ "Titre du cours" (valeur "cours-titre" m) (Champ "cours-titre")
        , commun.zoneTexte "Contenu du cours — texte et $TeX$" (valeur "cours-contenu" m) (Champ "cours-contenu")
        , commun.bouton "Enregistrer le cours"
            (Operation "cours"
                (params m
                    ([ ( "document", E.object [ ( "titre", E.string (valeur "cours-titre" m) ), ( "contenu", E.string (valeur "cours-contenu" m) ) ] ) ]
                        ++ (if valeur "cours-id" m == "" then
                                []

                            else
                                [ ( "id", E.string (valeur "cours-id" m) ), ( "revision", E.int (Maybe.withDefault 0 (String.toInt (valeur "cours-revision" m))) ) ]
                           )
                    )
                )
            )
        ]
    , commun.section "Préparer ou modifier une activité"
        ([ commun.boutonSecondaire "Nouvelle activité" NouvelleActivite
         , UI.wrappedRow [ UI.spacing 8 ] (List.map (\a -> commun.boutonSecondaire (D.texte "titre" (D.champ "document" a)) (Editer a)) (D.liste "elements" preparations))
         , commun.champ "Titre de l'activité" b.titre (Modifier "titre")
         , commun.zoneTexte "Consigne — texte et $TeX$" b.consigne (Modifier "consigne")
         , Maths.document b.consigne
         , commun.zoneTexte "Attendus — un par ligne" b.attendus (Modifier "attendus")
         , commun.selecteur "Type de production" [ ( "ouverte", "Production ouverte ou raisonnement" ), ( "qcm", "QCM à une seule bonne réponse" ) ] b.typeActivite (Modifier "type")
         , if b.typeActivite == "qcm" then
            commun.champ "Nombre de propositions équiprobables" b.propositions (Modifier "propositions")

           else
            UI.none
         , commun.selecteur "Cours associé" (( "", "Aucun" ) :: List.map (\c -> ( D.texte "id" c, D.texte "titre" (D.champ "document" c) )) (D.liste "cours" preparations)) b.cours (Modifier "cours")
         ]
            ++ List.indexedMap critere b.criteres
            ++ [ commun.boutonSecondaire "Ajouter un critère" AjouterCritere
               , commun.zoneTexte "Corrigé réservé à l'enseignant" b.corrige (Modifier "corrige")
               , commun.champ "Publication du corrigé (AAAA-MM-JJ HH:MM UTC, vide = privé)" b.publication (Modifier "publication")
               , attente
               , if b.modifie then
                    commun.texteSecondaire "Brouillon conservé, pas encore enregistré."

                 else
                    commun.texteSecondaire "Aucune modification en attente."
               , commun.boutonSecondaire "Relire la version serveur" (Operation "preparations" (params m []))
               , commun.boutonSecondaire "Adopter la version serveur pour mon brouillon" AccepterVersion
               ]
        )
    , commun.section "Affecter le travail"
        ([ MrJam.paragraphe "L'activité enregistrée ci-dessus sera affectée aux élèves sélectionnés."
         , commun.champ "Échéance (AAAA-MM-JJ HH:MM UTC)" (valeur "echeance" m) (Champ "echeance")
         ]
            ++ List.map
                (\e ->
                    let
                        id =
                            D.texte "acteur" e
                    in
                    commun.caseACocher id (List.member id m.eleves) (ChoisirEleve id)
                )
                (D.liste "eleves" preparations)
            ++ [ if m.edition == "nouvelle" then
                    commun.boutonInactif "Enregistrez d'abord l'activité"

                 else
                    commun.bouton "Affecter"
                        (Operation "affecter"
                            (params m
                                ([ ( "activite", E.string m.edition ), ( "eleves", E.list E.string m.eleves ), ( "echeance", E.string (valeur "echeance" m) ) ]
                                    ++ (if valeur "affectation-id" m == "" then
                                            []

                                        else
                                            [ ( "id", E.string (valeur "affectation-id" m) ), ( "revision", E.int (Maybe.withDefault 0 (String.toInt (valeur "affectation-revision" m))) ) ]
                                       )
                                )
                            )
                        )
               ]
        )
    ]


travail : Modele -> List (UI.Element Msg)
travail m =
    let
        t =
            data "travaux" m

        carte travailAffecte =
            let
                a =
                    D.champ "activite" travailAffecte

                aff =
                    D.champ "affectation" travailAffecte

                s =
                    D.champ "seance" travailAffecte
            in
            commun.carte
                [ MrJam.sousTitre (D.texte "titre" (D.champ "document" a))
                , Maths.document (D.texte "consigne" (D.champ "document" a))
                , commun.texteSecondaire ("Échéance : " ++ date (D.entier "echeance" (D.champ "document" aff)))
                , if role m == "enseignant" then
                    commun.boutonSecondaire "Modifier le calendrier" (Calendrier aff)

                  else
                    UI.none
                , if role m == "eleve" then
                    commun.bouton
                        (if D.texte "id" s == "" then
                            "Commencer"

                         else
                            "Retrouver ma séance"
                        )
                        (Operation "ouvrir_seance" (params m [ ( "affectation", E.string (D.texte "id" aff) ) ]))

                  else
                    UI.none
                ]
    in
    [ commun.section "Votre prochaine étape" [ MrJam.paragraphe "Ouvrez un travail puis utilisez votre LLM connecté à Audition. Les aides reçues font partie du suivi et permettent de mieux vous accompagner." ]
    , if D.entier "total" t == 0 then
        commun.avis MrJam.Information "Aucun travail affecté dans ce groupe. Votre enseignant pourra vous en proposer."

      else
        UI.column [ UI.width UI.fill, UI.spacing 16 ] (List.map carte (D.liste "elements" t))
    , pagination "travaux" t m
    ]


rapport : Modele -> List (UI.Element Msg)
rapport m =
    let
        r =
            data "rapport" m

        lignes =
            D.liste "elements" r

        attendus =
            List.concatMap
                (\l -> List.map (\a -> ( cleAttendu l (D.texte "id" a), D.texte "titre" l ++ " · v" ++ String.fromInt (D.entier "activite_version" l) ++ " · " ++ D.texte "texte" a )) (D.liste "attendus" l))
                lignes
                |> List.foldl
                    (\attendu ids ->
                        if List.any (\a -> Tuple.first a == Tuple.first attendu) ids then
                            ids

                        else
                            ids ++ [ attendu ]
                    )
                    []

        cleAttendu ligne id =
            D.texte "activite" ligne ++ ":" ++ String.fromInt (D.entier "activite_version" ligne) ++ ":" ++ id

        cellule cle ligne =
            let
                criteres =
                    D.liste "criteres" ligne |> List.filter (\c -> cleAttendu ligne (D.texte "attendu" c) == cle) |> List.map (D.texte "id")

                observations =
                    D.liste "observations" ligne |> List.filter (\o -> List.member (D.texte "critere" o) criteres)
            in
            MrJam.paragraphe
                (if List.isEmpty criteres then
                    "Non prescrit dans cette activité"

                 else if List.isEmpty observations then
                    "Non observé"

                 else
                    String.join " · " (List.map (\o -> etat (D.texte "etat" o)) observations)
                )

        colonnes =
            Tableaux.principale "Élève / activité" (\l -> MrJam.paragraphe (D.texte "eleve" l ++ " — " ++ D.texte "titre" l ++ " (v" ++ String.fromInt (D.entier "activite_version" l) ++ ")")) :: List.map (\( id, libelle ) -> Tableaux.colonne libelle (cellule id)) attendus
    in
    [ commun.selecteur "Activité à suivre" (( "", "Toutes les activités" ) :: List.map (\a -> ( D.texte "id" a, D.texte "titre" (D.champ "document" a) )) (D.liste "elements" (data "preparations" m))) (valeur "filtre-activite" m) (Champ "filtre-activite")
    , commun.boutonSecondaire "Appliquer le filtre"
        (Operation "rapport"
            (params m
                (if valeur "filtre-activite" m == "" then
                    []

                 else
                    [ ( "activite", E.string (valeur "filtre-activite" m) ) ]
                )
            )
        )
    , commun.section "Élèves × attendus" [ (Tableaux.pour contexte).tableau "Observations de la classe" colonnes lignes, pagination "rapport" r m, commun.texteSecondaire (D.texte "methode" r) ]
    , commun.section "Difficultés communes"
        (if List.isEmpty (D.liste "difficultes" r) then
            [ MrJam.paragraphe "Aucune difficulté constatée dans les traces disponibles. Les éléments non observés restent inconnus." ]

         else
            List.map (\d -> MrJam.paragraphe (D.texte "critere" d ++ " : " ++ String.fromInt (D.entier "difficultes" d) ++ " observations")) (D.liste "difficultes" r)
        )
    , commun.section "Retrouver les traces"
        (List.map
            (\l ->
                let
                    id =
                        D.texte "id" (D.champ "seance" l)
                in
                if id == "" then
                    commun.texteSecondaire (D.texte "eleve" l ++ " — aucune séance observée")

                else
                    commun.boutonSecondaire (D.texte "eleve" l ++ " — " ++ D.texte "titre" l) (Traces id)
            )
            lignes
        )
    , commun.section "Effectifs et méthode"
        (List.map
            (\i ->
                MrJam.paragraphe
                    (D.texte "critere" i
                        ++ " : "
                        ++ String.fromInt (D.entier "reussites_autonomes" i)
                        ++ " réussites sans aide, "
                        ++ String.fromInt (D.entier "reussites_aidees" i)
                        ++ " avec aide ; "
                        ++ String.fromInt (D.entier "effectif" i)
                        ++ " observations définies sur "
                        ++ String.fromInt (D.entier "prescrits" i)
                        ++ " prescriptions. "
                        ++ D.texte "affichage" i
                        ++ ". "
                        ++ (if D.champ "reference_hasard" i == E.null then
                                "Aucune référence de hasard ; ce score ne mesure pas une probabilité de maîtrise."

                            else
                                "Logit recentré sur la référence de hasard du QCM."
                           )
                    )
            )
            (D.liste "elements" (D.champ "indicateurs" r))
        )
    ]


seance : Modele -> List (UI.Element Msg)
seance m =
    let
        r =
            data "seance" m

        s =
            D.champ "seance" r

        d =
            D.champ "document" s

        a =
            D.champ "activite" r

        base =
            [ ( "id", E.string (D.texte "id" s) ), ( "revision", E.int (D.entier "revision" s) ) ]

        commande action label =
            commun.boutonSecondaire label (Operation "transition" (params m (base ++ [ ( "action", E.string action ) ])))

        trace t =
            commun.carte
                [ Maths.document (D.texte "production" t)
                , commun.texteSecondaire ("Activité : " ++ date (D.entier "activite_a" t) ++ " · Réception : " ++ date (D.entier "recu_a" t))
                , MrJam.paragraphe ("Aides : " ++ String.join " · " (List.map (\h -> D.texte "nature" h ++ " — " ++ D.texte "contenu" h) (D.liste "aides" t)))
                , MrJam.paragraphe (String.join "\n" (List.map (\o -> etat (D.texte "etat" o) ++ " — " ++ D.texte "justification" o) (D.liste "observations" t)))
                , if role m == "enseignant" then
                    commun.boutonSecondaire "Annoter cette tentative" (Annoter t)

                  else
                    UI.none
                ]
    in
    [ if D.texte "id" (D.champ "cours" r) /= "" then
        commun.section "Cours associé" [ Maths.document (D.texte "contenu" (D.champ "document" (D.champ "cours" r))) ]

      else
        UI.none
    , commun.section "La séance et son cadre"
        [ MrJam.sousTitre (D.texte "titre" (D.champ "document" a))
        , Maths.document (D.texte "consigne" (D.champ "document" a))
        , commun.texteSecondaire ("Consignes version " ++ String.fromInt (D.entier "activite_version" r) ++ " · " ++ etat (D.texte "etat" d))
        , if D.booleen "contexte_modifie" r then
            commun.avis MrJam.Avertissement "Les consignes ont évolué. Relisez la nouvelle version avant de l'adopter."

          else
            UI.none
        , if D.booleen "contexte_modifie" r then
            Maths.document (D.texte "consigne" (D.champ "document" (D.champ "nouvelle_activite" r)))

          else
            UI.none
        , if D.booleen "contexte_modifie" r && role m == "eleve" then
            commun.bouton "Adopter les nouvelles consignes" (Operation "adopter_contexte" (params m (base ++ [ ( "activite_version", E.int (D.entier "version_actuelle" r) ) ])))

          else
            UI.none
        , commun.boutonSecondaire "Relire l'état réel" (Operation "consulter_seance" (params m [ ( "id", E.string m.selection ) ]))
        , if role m == "eleve" then
            UI.wrappedRow [ UI.spacing 8 ] [ commande "interrompre" "Interrompre", commande "reprendre" "Reprendre", commande "terminer" "Terminer" ]

          else
            UI.none
        ]
    , commun.section "Productions et aides partagées"
        (if List.isEmpty (D.liste "elements" (D.champ "traces" r)) then
            [ MrJam.paragraphe "Aucune production enregistrée. Connectez votre LLM puis commencez le travail ; aucune réussite ou difficulté n'est déduite de cette absence." ]

         else
            List.map trace (D.liste "elements" (D.champ "traces" r))
        )
    , pagination "consulter_seance" (D.champ "traces" r) m
    , commun.section "Retours de l'enseignant" (List.map (\c -> MrJam.paragraphe (D.texte "annotation" c ++ " — " ++ D.texte "justification" c ++ " (" ++ D.texte "auteur" c ++ ", " ++ date (D.entier "recu_a" c) ++ ")")) (D.liste "rectifications" d))
    ]
        ++ (if role m /= "enseignant" then
                []

            else
                [ commun.section "Annoter ou rectifier"
                    [ commun.champIdentifie { identifiant = "annotation", libelle = "Justification de l'annotation ou rectification", aide = Just "La production initiale est conservée.", exemple = Nothing, limite = Just 4000 } (valeur "justification" m) (Champ "justification")
                    , commun.selecteur "Critère concerné" (List.map (\c -> ( D.texte "id" c, D.texte "texte" c )) (D.liste "criteres" (D.champ "document" a))) (valeur "critere" m) (Champ "critere")
                    , commun.selecteur "Nouvelle interprétation (facultative)" [ ( "", "Conserver l’interprétation et annoter" ), ( "non_observe", "Non observé" ), ( "en_cours", "En cours" ), ( "difficulte", "Difficulté constatée" ), ( "reussite_aidee", "Réussite avec aide" ), ( "reussite_autonome", "Réussite sans aide" ) ] (valeur "etat-rectification" m) (Champ "etat-rectification")
                    , commun.champ "Points rectifiés" (valeur "points-rectification" m) (Champ "points-rectification")
                    , commun.champ "Annotation" (valeur "annotation" m) (Champ "annotation")
                    , commun.bouton "Enregistrer l’annotation ou la rectification"
                        (Operation "rectifier"
                            (params m
                                (base
                                    ++ [ ( "tentative", E.string (valeur "tentative" m) ), ( "observation", E.string (valeur "critere" m) ), ( "justification", E.string (valeur "justification" m) ), ( "annotation", E.string (valeur "annotation" m) ) ]
                                    ++ (if valeur "etat-rectification" m == "" then
                                            []

                                        else
                                            [ ( "etat", E.string (valeur "etat-rectification" m) ), ( "points", Maybe.withDefault E.null (Maybe.map E.float (String.toFloat (valeur "points-rectification" m))) ) ]
                                       )
                                )
                            )
                        )
                    , commun.zoneTexte "Consigne de remédiation" (valeur "remediation" m) (Champ "remediation")
                    , commun.champ "Échéance de remédiation (AAAA-MM-JJ HH:MM UTC)" (valeur "remediation-date" m) (Champ "remediation-date")
                    , commun.bouton "Prescrire la remédiation" (Operation "remediation" (params m [ ( "activite", E.string (D.texte "activite" d) ), ( "eleves", E.list E.string [ D.texte "eleve" d ] ), ( "origine", E.string m.selection ), ( "consigne", E.string (valeur "remediation" m) ), ( "echeance", E.string (valeur "remediation-date" m) ) ]))
                    ]
                ]
           )


administration : Modele -> List (UI.Element Msg)
administration m =
    [ commun.section "Groupes et habilitations"
        [ commun.champ "Nom du nouveau groupe" (valeur "groupe-nom" m) (Champ "groupe-nom")
        , commun.bouton "Créer le groupe" (Operation "creer_groupe" (E.object [ ( "nom", E.string (valeur "groupe-nom" m) ) ]))
        , commun.champ "Identité métier centrale à rattacher" (valeur "acteur" m) (Champ "acteur")
        , commun.selecteur "Habilitation"
            [ ( "enseignant", "Enseignant" ), ( "eleve", "Élève" ), ( "retirer", "Retirer le rattachement" ) ]
            (if valeur "role" m == "" then
                "eleve"

             else
                valeur "role" m
            )
            (Champ "role")
        , commun.bouton "Confirmer le rattachement"
            (Operation "habiliter"
                (params m
                    [ ( "acteur", E.string (valeur "acteur" m) )
                    , ( "role"
                      , E.string
                            (if valeur "role" m == "" then
                                "eleve"

                             else
                                valeur "role" m
                            )
                      )
                    ]
                )
            )
        , MrJam.paragraphe "Ces actions sont tracées. Les identités et authentificateurs restent administrés par Log. Un administrateur technique n'obtient pas un accès aux productions."
        , (Tableaux.pour contexte).tableau "Rattachements" [ Tableaux.principale "Identité" (\e -> MrJam.paragraphe (D.texte "acteur" e)), Tableaux.colonne "Rôle" (\e -> MrJam.paragraphe (D.texte "role" e)) ] (D.liste "elements" (data "membres" m))
        , commun.boutonSecondaire "Diagnostic du service" (Operation "diagnostic" (E.object []))
        , commun.texteSecondaire (D.texte "base" (data "diagnostic" m))
        ]
    , commun.section "Supprimer un groupe et ses traces"
        [ commun.avis MrJam.Avertissement "La suppression efface les contenus, versions, séances et rattachements de ce groupe. Son auteur et la date restent dans l'audit technique. Cette action exige la confirmation de l'identifiant du groupe."
        , commun.texteSecondaire ("Identifiant du groupe sélectionné : " ++ m.groupe)
        , commun.champ "Recopier l'identifiant pour confirmer la suppression" (valeur "suppression-confirmation" m) (Champ "suppression-confirmation")
        , if m.groupe /= "" && valeur "suppression-confirmation" m == m.groupe then
            commun.bouton "Supprimer ce groupe et ses données"
                (Operation "supprimer_groupe" (params m [ ( "confirmation", E.string (valeur "suppression-confirmation" m) ) ]))

          else
            commun.boutonInactif "Confirmez l'identifiant du groupe"
        ]
    ]


etat : String -> String
etat v =
    case v of
        "non_observe" ->
            "Non observé"

        "en_cours" ->
            "En cours"

        "difficulte" ->
            "Difficulté constatée"

        "reussite_aidee" ->
            "Réussite avec aide"

        "reussite_autonome" ->
            "Réussite sans aide"

        "interrompue" ->
            "Interrompue"

        "terminee" ->
            "Terminée"

        _ ->
            "État à consulter"


date : Int -> String
date secondes =
    let
        t =
            Time.millisToPosix (secondes * 1000)

        pad =
            String.padLeft 2 '0' << String.fromInt

        mois =
            case Time.toMonth Time.utc t of
                Time.Jan ->
                    1

                Time.Feb ->
                    2

                Time.Mar ->
                    3

                Time.Apr ->
                    4

                Time.May ->
                    5

                Time.Jun ->
                    6

                Time.Jul ->
                    7

                Time.Aug ->
                    8

                Time.Sep ->
                    9

                Time.Oct ->
                    10

                Time.Nov ->
                    11

                Time.Dec ->
                    12
    in
    String.fromInt (Time.toYear Time.utc t) ++ "-" ++ pad mois ++ "-" ++ pad (Time.toDay Time.utc t) ++ " " ++ pad (Time.toHour Time.utc t) ++ ":" ++ pad (Time.toMinute Time.utc t) ++ " UTC"
