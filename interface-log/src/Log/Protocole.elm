module Log.Protocole exposing (Defi(..), Etat(..), Methode(..), commencer, decoder, initialiser, lire, phrase, totp)

{-| Adaptateur JSON du protocole officiel Kanidm 1.11.2.
La décision de politique, les défis et leur vérification appartiennent à l'IdP.
Ce module ne conserve aucun jeton et n'effectue aucune requête ni journalisation.
-}

import Json.Decode as Decode exposing (Decoder)
import Json.Encode as Encode


type Methode
    = Phrase
    | PhraseTotp
    | PhraseRecuperation
    | PhraseCle
    | Passkey


type Defi
    = SaisirPhrase
    | SaisirTotp
    | SaisirRecuperation
    | PresenterPasskey Decode.Value
    | PresenterCle Decode.Value


type Etat
    = Choisir (List Methode)
    | Continuer (List Defi)
    | Refuse
    | Connecte


initialiser : String -> Encode.Value
initialiser identifiant =
    etape "init2"
        (Encode.object
            [ ( "username", Encode.string identifiant )
            , ( "issue", Encode.string "cookie" )
            , ( "privileged", Encode.bool False )
            ]
        )


commencer : Methode -> Encode.Value
commencer methode =
    etape "begin"
        (Encode.string
            (case methode of
                Phrase ->
                    "password"

                PhraseTotp ->
                    "passwordmfa"

                PhraseRecuperation ->
                    "passwordbackupcode"

                PhraseCle ->
                    "passwordsecuritykey"

                Passkey ->
                    "passkey"
            )
        )


phrase : String -> Encode.Value
phrase valeur =
    -- Aucun trim, changement de casse ou normalisation Unicode.
    etape "cred" (Encode.object [ ( "password", Encode.string valeur ) ])


totp : String -> Maybe Encode.Value
totp valeur =
    -- Kanidm attend un u32 : 000000 est une réponse, pas une absence.
    if String.length valeur == 6 && String.all (\c -> c >= '0' && c <= '9') valeur then
        String.toInt valeur
            |> Maybe.map (\code -> etape "cred" (Encode.object [ ( "totp", Encode.int code ) ]))

    else
        Nothing


etape : String -> Encode.Value -> Encode.Value
etape nom valeur =
    Encode.object [ ( "step", Encode.object [ ( nom, valeur ) ] ) ]


decoder : Decoder Etat
decoder =
    Decode.field "state"
        (Decode.keyValuePairs Decode.value
            |> Decode.andThen
                (\paires ->
                    case paires of
                        [ ( nom, valeur ) ] ->
                            let
                                contenu =
                                    case nom of
                                        "choose" ->
                                            Decode.list methodeDecoder |> Decode.map Choisir

                                        "continue" ->
                                            Decode.list defiDecoder |> Decode.map Continuer

                                        "denied" ->
                                            Decode.string |> Decode.map (\_ -> Refuse)

                                        "success" ->
                                            Decode.string |> Decode.map (\_ -> Connecte)

                                        _ ->
                                            Decode.fail "État non pris en charge"
                            in
                            case Decode.decodeValue contenu valeur of
                                Ok etat ->
                                    Decode.succeed etat

                                Err _ ->
                                    Decode.fail "Réponse native invalide"

                        _ ->
                            Decode.fail "État natif ambigu"
                )
        )


{-| Utiliser cette frontière dans le transport : une Decode.Error contient le
JSON original et peut donc contenir un jeton. Ne pas l'afficher ni la conserver.
-}
lire : String -> Result () Etat
lire reponse =
    Decode.decodeString decoder reponse |> Result.mapError (\_ -> ())


methodeDecoder : Decoder Methode
methodeDecoder =
    Decode.string
        |> Decode.andThen
            (\nom ->
                case nom of
                    "password" ->
                        Decode.succeed Phrase

                    "passwordmfa" ->
                        Decode.succeed PhraseTotp

                    "passwordbackupcode" ->
                        Decode.succeed PhraseRecuperation

                    "passwordsecuritykey" ->
                        Decode.succeed PhraseCle

                    "passkey" ->
                        Decode.succeed Passkey

                    _ ->
                        Decode.fail "Mécanisme non pris en charge"
            )


defiDecoder : Decoder Defi
defiDecoder =
    Decode.oneOf
        [ Decode.string
            |> Decode.andThen
                (\nom ->
                    case nom of
                        "password" ->
                            Decode.succeed SaisirPhrase

                        "totp" ->
                            Decode.succeed SaisirTotp

                        "backupcode" ->
                            Decode.succeed SaisirRecuperation

                        _ ->
                            Decode.fail "Défi non pris en charge"
                )
        , Decode.field "passkey" Decode.value |> Decode.map PresenterPasskey
        , Decode.field "securitykey" Decode.value |> Decode.map PresenterCle
        ]
