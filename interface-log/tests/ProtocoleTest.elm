module ProtocoleTest exposing (tests)

import Expect
import Json.Decode as Decode
import Log.Protocole as Protocole exposing (Defi(..), Etat(..), Methode(..))
import Test exposing (Test, describe, test)


tests : Test
tests =
    describe "Contrat JSON Kanidm verrouillé"
        [ test "phrase Unicode, espaces et longueur conservés" <|
            \_ ->
                let
                    original =
                        "  雪 é 🔑 " ++ String.repeat 200 "λ " ++ "  "
                in
                Protocole.phrase original
                    |> Decode.decodeValue (Decode.at [ "step", "cred", "password" ] Decode.string)
                    |> Expect.equal (Ok original)
        , test "connexion cookie sans élévation implicite" <|
            \_ ->
                Protocole.initialiser "personne@example.test"
                    |> Decode.decodeValue
                        (Decode.at [ "step", "init2" ]
                            (Decode.map3 (\a b c -> ( a, b, c ))
                                (Decode.field "username" Decode.string)
                                (Decode.field "issue" Decode.string)
                                (Decode.field "privileged" Decode.bool)
                            )
                        )
                    |> Expect.equal (Ok ( "personne@example.test", "cookie", False ))
        , test "zéro TOTP distinct d'une réponse absente" <|
            \_ ->
                ( Protocole.totp "000000"
                    |> Maybe.map (Decode.decodeValue (Decode.at [ "step", "cred", "totp" ] Decode.int))
                , Protocole.totp ""
                )
                    |> Expect.equal ( Just (Ok 0), Nothing )
        , test "refus des codes ambigus" <|
            \_ ->
                List.map Protocole.totp [ " 12345", "１２３４５６", "1234567", "-12345", "123.45" ]
                    |> Expect.equal (List.repeat 5 Nothing)
        , test "méthodes fortes proposées par l'IdP" <|
            \_ ->
                Decode.decodeString Protocole.decoder "{\"state\":{\"choose\":[\"passwordmfa\",\"passkey\"]}}"
                    |> Expect.equal (Ok (Choisir [ PhraseTotp, Passkey ]))
        , test "TOTP avant phrase, sans ordre inventé par le client" <|
            \_ ->
                Decode.decodeString Protocole.decoder "{\"state\":{\"continue\":[\"totp\"]}}"
                    |> Expect.equal (Ok (Continuer [ SaisirTotp ]))
        , test "succès sans conservation du jeton natif" <|
            \_ ->
                Decode.decodeString Protocole.decoder "{\"state\":{\"success\":\"jeton-synthetique\"}}"
                    |> Expect.equal (Ok Connecte)
        , test "refus et mécanismes inconnus sans fallback faible" <|
            \_ ->
                Expect.all
                    [ \_ -> Decode.decodeString Protocole.decoder "{\"state\":{\"denied\":\"motif\"}}" |> Expect.equal (Ok Refuse)
                    , \_ -> Decode.decodeString Protocole.decoder "{\"state\":{\"choose\":[\"anonymous\"]}}" |> Expect.err
                    , \_ -> Decode.decodeString Protocole.decoder "{\"state\":{\"continue\":[\"inconnu\"]}}" |> Expect.err
                    ]
                    ()
        , test "réponse ambiguë refusée, diagnostic sans jeton" <|
            \_ ->
                List.map Protocole.lire
                    [ "{\"state\":{\"success\":\"synthetique\",\"denied\":\"refus\"}}"
                    , "{\"state\":{\"success\":{\"token\":\"synthetique\"}}}"
                    , "{\"state\":{\"future\":\"synthetique\"}}"
                    ]
                    |> Expect.equal (List.repeat 3 (Err ()))
        ]
