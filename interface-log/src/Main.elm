port module Main exposing (main)

import Browser
import Element as UI
import Html exposing (Html)
import Json.Decode as D
import Json.Encode as E
import Log.Protocole as P
import MrJam
import MrJam.Contexte as Contexte
import MrJam.Transitions as T
import Time


port demander : E.Value -> Cmd msg


port recevoir : (D.Value -> msg) -> Sub msg


port mouvementReduit : (Bool -> msg) -> Sub msg


port focaliser : String -> Cmd msg


type Vue
    = Connexion
    | Methodes
    | Defis
    | Accueil
    | Consentement
    | Securite
    | Sessions


type Msg
    = Identifiant String
    | Phrase String
    | Code String
    | Nom String
    | Valider
    | Methode P.Methode
    | Action String
    | Reponse D.Value
    | Frame Time.Posix
    | Reduction Bool


type alias Modele =
    { vue : Vue
    , identifiant : String
    , phrase : String
    , code : String
    , nom : String
    , etat : P.Etat
    , profil : D.Value
    , donnees : D.Value
    , erreur : String
    , force : String
    , occupe : Bool
    , transition : T.Transition Bool
    }


main : Program () Modele Msg
main =
    Browser.element { init = init, update = update, view = view, subscriptions = subscriptions }


init : () -> ( Modele, Cmd Msg )
init _ =
    ( { vue = Connexion
      , identifiant = ""
      , phrase = ""
      , code = ""
      , nom = "Ma passkey"
      , etat = P.Refuse
      , profil = E.null
      , donnees = E.null
      , erreur = ""
      , force = ""
      , occupe = True
      , transition = T.initialiser True
      }
    , demander (E.object [ ( "action", E.string "initialiser" ) ])
    )


subscriptions : Modele -> Sub Msg
subscriptions m =
    Sub.batch [ recevoir Reponse, mouvementReduit Reduction, T.abonnement Frame m.transition ]


envoyer : String -> E.Value -> Modele -> ( Modele, Cmd Msg )
envoyer action document m =
    ( { m | occupe = True, erreur = "", phrase = "", code = "", transition = T.aller 120 True m.transition }
    , demander (E.object [ ( "action", E.string action ), ( "document", document ), ( "nom", E.string m.nom ) ])
    )


changer : Vue -> Modele -> Modele
changer vue m =
    { m | vue = vue, transition = T.aller 180 False m.transition }


update : Msg -> Modele -> ( Modele, Cmd Msg )
update msg m =
    case msg of
        Identifiant v ->
            ( { m | identifiant = v }, Cmd.none )

        Phrase v ->
            ( { m
                | phrase = v
                , force =
                    if m.vue == Securite then
                        "Vérification par Kanidm…"

                    else
                        m.force
              }
            , if m.vue == Securite then
                demander (E.object [ ( "action", E.string "force" ), ( "document", E.string v ) ])

              else
                Cmd.none
            )

        Code v ->
            ( { m | code = v }, Cmd.none )

        Nom v ->
            ( { m | nom = v }, Cmd.none )

        Frame now ->
            ( { m | transition = T.mettreAJour now m.transition }, Cmd.none )

        Reduction reduite ->
            ( { m | transition = T.reduire reduite m.transition }, Cmd.none )

        Methode methode ->
            if m.occupe then
                ( m, Cmd.none )

            else
                envoyer "auth" (P.commencer methode) m

        Valider ->
            if m.occupe then
                ( m, Cmd.none )

            else
                case m.vue of
                    Connexion ->
                        envoyer "auth" (P.initialiser m.identifiant) m

                    Defis ->
                        case m.etat of
                            P.Continuer defis ->
                                if List.member P.SaisirTotp defis then
                                    case P.totp m.code of
                                        Just document ->
                                            envoyer "auth" document m

                                        Nothing ->
                                            ( { m | erreur = "Saisissez les six chiffres du code." }, Cmd.none )

                                else if List.member P.SaisirRecuperation defis then
                                    envoyer "auth" (E.object [ ( "step", E.object [ ( "cred", E.object [ ( "backupcode", E.string m.code ) ] ) ] ) ]) m

                                else
                                    envoyer "auth" (P.phrase m.phrase) m

                            _ ->
                                ( m, Cmd.none )

                    Securite ->
                        envoyer "modifier" (E.object [ ( "password", E.string m.phrase ) ]) m

                    _ ->
                        ( m, Cmd.none )

        Action action ->
            if m.occupe then
                ( m, Cmd.none )

            else
                case action of
                    "accueil" ->
                        ( changer Accueil { m | donnees = E.null, phrase = "", code = "" }, Cmd.none )

                    "totp" ->
                        envoyer "modifier" (E.string "totpgenerate") m

                    "verifier-totp" ->
                        case P.totp m.code of
                            Just _ ->
                                case String.toInt m.code of
                                    Just code ->
                                        envoyer "modifier" (E.object [ ( "totpverify", E.list identity [ E.int code, E.string m.nom ] ) ]) m

                                    Nothing ->
                                        ( m, Cmd.none )

                            Nothing ->
                                ( { m | erreur = "Saisissez les six chiffres du code." }, Cmd.none )

                    "passkey" ->
                        envoyer "creer-passkey" E.null m

                    "connexion-passkey" ->
                        envoyer "auth-passkey" m.donnees m

                    "codes" ->
                        envoyer "modifier" (E.string "backupcodegenerate") m

                    "annuler-mfa" ->
                        envoyer "modifier" (E.string "cancelmfareg") m

                    _ ->
                        envoyer action E.null m

        Reponse valeur ->
            let
                action =
                    texte [ "action" ] valeur

                statut =
                    entier [ "status" ] valeur

                data =
                    champ [ "document" ] valeur

                suivant =
                    { m | occupe = False, transition = T.aller 180 False m.transition }
            in
            if action == "force" then
                ( { m
                    | force =
                        if statut == 200 then
                            "Force suffisante selon Kanidm."

                        else
                            "Force insuffisante selon Kanidm : ajoutez des mots peu prévisibles."
                  }
                , Cmd.none
                )

            else if statut >= 400 then
                ( { suivant
                    | erreur =
                        if statut == 401 then
                            "Une vérification récente est nécessaire. Reconnectez-vous pour cette opération."

                        else if statut == 503 then
                            "Résultat non confirmé. Ne répétez pas une modification ; consultez son état."

                        else
                            "Kanidm a refusé cette opération. Votre politique de sécurité reste appliquée."
                  }
                , Cmd.none
                )

            else if action == "auth" || action == "reauth" then
                case P.lire (E.encode 0 data) of
                    Ok (P.Choisir methodes) ->
                        case methodes of
                            [ methode ] ->
                                envoyer "auth" (P.commencer methode) { suivant | etat = P.Choisir methodes }

                            _ ->
                                ( changer Methodes { suivant | etat = P.Choisir methodes }, focaliser "log-choix" )

                    Ok (P.Continuer defis) ->
                        ( changer Defis { suivant | etat = P.Continuer defis, donnees = data }, focaliser "log-champ" )

                    Ok P.Connecte ->
                        envoyer "apres-connexion" E.null suivant

                    _ ->
                        ( changer Connexion { suivant | erreur = "Connexion refusée. Vérifiez vos informations." }, focaliser "log-champ" )

            else if action == "connexion" then
                ( changer Connexion suivant, focaliser "log-champ" )

            else if action == "profil" then
                ( changer Accueil { suivant | profil = data }, Cmd.none )

            else if action == "oauth" then
                ( changer Consentement { suivant | donnees = data }, focaliser "log-choix" )

            else if action == "sessions" then
                ( changer Sessions { suivant | donnees = data }, Cmd.none )

            else if List.member action [ "ouvrir", "recuperer", "modifier", "statut", "creer-passkey" ] then
                ( changer Securite { suivant | donnees = data }, focaliser "log-champ" )

            else if List.member action [ "enregistrer", "annuler" ] then
                envoyer "profil" E.null { suivant | donnees = E.null }

            else
                ( suivant, Cmd.none )


champ : List String -> D.Value -> D.Value
champ path v =
    Result.withDefault E.null (D.decodeValue (D.at path D.value) v)


texte : List String -> D.Value -> String
texte path v =
    Result.withDefault "" (D.decodeValue (D.at path D.string) v)


entier : List String -> D.Value -> Int
entier path v =
    Result.withDefault 0 (D.decodeValue (D.at path D.int) v)


vrai : List String -> D.Value -> Bool
vrai path v =
    Result.withDefault False (D.decodeValue (D.at path D.bool) v)


liste : D.Value -> List D.Value
liste v =
    Result.withDefault [] (D.decodeValue (D.list D.value) v)


commun : MrJam.Interface String Msg
commun =
    MrJam.pour (Contexte.pour "Log")


controle : Modele -> String -> Msg -> UI.Element Msg
controle m label msg =
    if m.occupe then
        commun.boutonEnCours label

    else
        commun.bouton label msg


champSaisi : String -> String -> (String -> Msg) -> UI.Element Msg
champSaisi libelle valeur message =
    commun.champIdentifieSoumis { identifiant = "log-champ", libelle = libelle, aide = Nothing, exemple = Nothing, limite = Nothing } valeur message Valider


view : Modele -> Html Msg
view m =
    commun.page "Log"
        [ UI.el
            [ UI.width UI.fill
            , UI.alpha
                (T.nombre
                    (\occupe ->
                        if occupe then
                            0.82

                        else
                            1
                    )
                    m.transition
                )
            ]
            (commun.section (titre m.vue)
                (contenu m
                    ++ (if m.erreur == "" then
                            []

                        else
                            [ commun.avis MrJam.Erreur m.erreur ]
                       )
                )
            )
        ]


titre : Vue -> String
titre vue =
    case vue of
        Connexion ->
            "Connexion"

        Methodes ->
            "Votre méthode de connexion"

        Defis ->
            "Vérification"

        Accueil ->
            "Votre compte commun"

        Consentement ->
            "Autoriser une application"

        Securite ->
            "Sécurité de votre compte"

        Sessions ->
            "Vos sessions"


contenu : Modele -> List (UI.Element Msg)
contenu m =
    case m.vue of
        Connexion ->
            [ commun.texteSecondaire "Connectez-vous avec votre adresse électronique ou votre identifiant. L’accès aux services est réservé aux personnes invitées.", MrJam.soumissionDansChamps Valider (commun.identifiant "Adresse électronique ou identifiant" m.identifiant Identifiant), controle m "Continuer" Valider ]

        Methodes ->
            case m.etat of
                P.Choisir methodes ->
                    List.map (\methode -> controle m (nomMethode methode) (Methode methode)) methodes

                _ ->
                    []

        Defis ->
            case m.etat of
                P.Continuer defis ->
                    if List.member P.SaisirTotp defis then
                        [ champSaisi "Code de votre authentificateur" m.code Code, controle m "Vérifier" Valider ]

                    else if List.member P.SaisirRecuperation defis then
                        [ champSaisi "Code de récupération" m.code Code, controle m "Vérifier" Valider ]

                    else if List.member P.SaisirPhrase defis then
                        [ MrJam.soumissionDansChamps Valider (commun.motDePasse "Phrase de passe" m.phrase Phrase), controle m "Se connecter" Valider ]

                    else
                        [ commun.texteSecondaire "Utilisez votre passkey ou clé de sécurité. Le navigateur demandera votre confirmation.", controle m "Utiliser ma passkey" (Action "connexion-passkey") ]

                _ ->
                    []

        Accueil ->
            [ UI.text (texte [ "displayname" ] m.profil)
            , commun.texteSecondaire ("Expiration de la session Log : " ++ texte [ "expiration_log" ] m.profil)
            , commun.lien "Ouvrir Vision" "https://vision.mrj.am/"
            , controle m "Gérer mes authentificateurs" (Action "ouvrir")
            , controle m "Vérifier à nouveau mon identité" (Action "reauth")
            , controle m "Voir mes sessions" (Action "sessions")
            , controle m "Me déconnecter de Log" (Action "deconnexion")
            ]

        Consentement ->
            let
                c =
                    champ [ "ConsentRequested" ] m.donnees
            in
            [ UI.text ("Application : " ++ texte [ "client_name" ] c)
            , commun.texteSecondaire ("Accès demandés : " ++ String.join ", " (List.map (\v -> Result.withDefault "" (D.decodeValue D.string v)) (liste (champ [ "scopes" ] c))))
            , controle m "Autoriser" (Action "consentir")
            , commun.boutonSecondaire "Refuser" (Action "refuser")
            ]

        Securite ->
            [ commun.texteSecondaire "Les modifications ne deviennent effectives qu’après Enregistrer. Kanidm impose la politique de votre compte ; un administrateur doit conserver TOTP ou une passkey appropriée."
            , MrJam.soumissionDansChamps Valider (commun.nouveauMotDePasse "Nouvelle phrase de passe" m.phrase Phrase)
            , commun.texteSecondaire m.force
            , controle m "Appliquer cette phrase" Valider
            , commun.champ "Nom de l’authentificateur" m.nom Nom
            , MrJam.actions [ controle m "Ajouter TOTP" (Action "totp"), controle m "Ajouter une passkey" (Action "passkey"), controle m "Générer des codes de récupération" (Action "codes") ]
            ]
                ++ reglageMfa m
                ++ authentificateurs m
                ++ avertissements m
                ++ [ if vrai [ "can_commit" ] m.donnees then
                        controle m "Enregistrer" (Action "enregistrer")

                     else
                        commun.boutonInactif "Enregistrer — politique non satisfaite"
                   , commun.boutonSecondaire "Actualiser l’état" (Action "statut")
                   , commun.boutonSecondaire "Annuler l’enrôlement en cours" (Action "annuler-mfa")
                   , commun.boutonSecondaire "Annuler les modifications" (Action "annuler")
                   ]

        Sessions ->
            List.map
                (\s ->
                    commun.carte
                        [ UI.text ("Session " ++ String.left 8 (texte [ "session_id" ] s))
                        , UI.text ("Créée : " ++ texte [ "debut" ] s)
                        , UI.text ("Expiration : " ++ texte [ "expiration" ] s)
                        , controle m "Révoquer cette session" (Action ("revoquer:" ++ texte [ "session_id" ] s))
                        ]
                )
                (liste m.donnees)
                ++ [ commun.boutonSecondaire "Retour au compte" (Action "accueil") ]


reglageMfa : Modele -> List (UI.Element Msg)
reglageMfa m =
    let
        secret =
            texte [ "totp_secret" ] m.donnees

        codes =
            liste (champ [ "mfaregstate", "BackupCodes" ] m.donnees)
    in
    if secret /= "" then
        [ commun.texteSecondaire ("Secret TOTP à enregistrer dans votre authentificateur : " ++ secret)
        , commun.texteSecondaire ("Algorithme " ++ String.toUpper (texte [ "mfaregstate", "TotpCheck", "algo" ] m.donnees) ++ " ; " ++ String.fromInt (entier [ "mfaregstate", "TotpCheck", "digits" ] m.donnees) ++ " chiffres ; période " ++ String.fromInt (entier [ "mfaregstate", "TotpCheck", "step" ] m.donnees) ++ " secondes.")
        , commun.champIdentifieSoumis { identifiant = "log-champ", libelle = "Code de vérification", aide = Nothing, exemple = Nothing, limite = Nothing } m.code Code (Action "verifier-totp")
        , controle m "Confirmer TOTP" (Action "verifier-totp")
        ]

    else if not (List.isEmpty codes) then
        [ commun.texteSecondaire "Conservez ces codes dans un endroit sûr. Ils ne seront pas affichés après la fermeture."
        , MrJam.pile (List.map (\v -> UI.text (Result.withDefault "" (D.decodeValue D.string v))) codes)
        ]

    else
        []


avertissements : Modele -> List (UI.Element Msg)
avertissements m =
    if List.isEmpty (liste (champ [ "warnings" ] m.donnees)) then
        []

    else
        [ commun.avis MrJam.Avertissement "Des exigences de sécurité restent à satisfaire avant l’enregistrement. Ajoutez et vérifiez TOTP ou une passkey conforme à votre politique." ]


nomMethode : P.Methode -> String
nomMethode methode =
    case methode of
        P.Phrase ->
            "Phrase de passe"

        P.PhraseTotp ->
            "Phrase de passe et TOTP"

        P.PhraseRecuperation ->
            "Phrase de passe et code de récupération"

        P.PhraseCle ->
            "Phrase de passe et clé de sécurité"

        P.Passkey ->
            "Passkey"


authentificateurs : Modele -> List (UI.Element Msg)
authentificateurs m =
    let
        passkeys =
            liste (champ [ "passkeys" ] m.donnees)

        totps =
            case liste (champ [ "primary", "type_", "PasswordMfa" ] m.donnees) of
                labels :: _ ->
                    liste labels

                _ ->
                    []
    in
    List.map (\p -> commun.carte [ UI.text (texte [ "tag" ] p), commun.boutonDestructif "Retirer cette passkey" (Action ("retirer-passkey:" ++ texte [ "uuid" ] p)) ]) passkeys
        ++ List.map
            (\v ->
                let
                    label =
                        Result.withDefault "" (D.decodeValue D.string v)
                in
                commun.carte [ UI.text label, commun.boutonDestructif "Retirer cet authentificateur TOTP" (Action ("retirer-totp:" ++ label)) ]
            )
            totps
