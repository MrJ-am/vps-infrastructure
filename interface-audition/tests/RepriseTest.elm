module RepriseTest exposing (tests)

import Dict
import Expect
import Json.Encode as E
import Main
import Test exposing (Test, describe, test)


tests : Test
tests =
    describe "Saisie et reprise après échec"
        [ test "une session expirée garde le brouillon" <|
            \_ ->
                let
                    initial =
                        Tuple.first (Main.init (E.object []))

                    saisi =
                        Tuple.first (Main.update (Main.Modifier "consigne" "Justifier sans utiliser le corrigé.") initial)

                    expire =
                        Tuple.first (Main.update (Main.Reponse (E.object [ ( "operation", E.string "activite" ), ( "statut", E.int 401 ), ( "erreur", E.string "session_expiree" ) ])) saisi)
                in
                Expect.equal ( True, Just "Justifier sans utiliser le corrigé." )
                    ( expire.expire, Maybe.map .consigne (Dict.get "nouvelle" expire.drafts) )
        , test "un conflit conserve les critères et la saisie" <|
            \_ ->
                let
                    initial =
                        Tuple.first (Main.init (E.object []))

                    saisi =
                        Tuple.first (Main.update (Main.Modifier "titre" "Une production ouverte") initial)

                    conflit =
                        Tuple.first (Main.update (Main.Reponse (E.object [ ( "operation", E.string "activite" ), ( "statut", E.int 409 ), ( "erreur", E.string "conflit_revision" ) ])) saisi)
                in
                Expect.equal saisi.drafts conflit.drafts
        , test "changer de groupe ne détruit pas le brouillon" <|
            \_ ->
                let
                    initial =
                        Tuple.first (Main.init (E.object []))

                    saisi =
                        Tuple.first (Main.update (Main.Modifier "titre" "Travail en préparation") initial)

                    autre =
                        Tuple.first (Main.update (Main.Groupe "autre-groupe") saisi)
                in
                Expect.equal saisi.drafts autre.drafts
        , test "une saisie postérieure à l'envoi reste un brouillon après confirmation" <|
            \_ ->
                let
                    initial =
                        Tuple.first (Main.init (E.object []))

                    saisi =
                        Tuple.first (Main.update (Main.Modifier "titre" "Version envoyée") initial)

                    envoye =
                        Tuple.first (Main.update Main.EnregistrerActivite saisi)

                    modifie =
                        Tuple.first (Main.update (Main.Modifier "titre" "Nouvelle saisie") envoye)

                    confirme =
                        Tuple.first (Main.update (Main.Reponse (E.object [ ( "operation", E.string "activite" ), ( "statut", E.int 200 ), ( "document", E.object [ ( "id", E.string "a1" ), ( "revision", E.int 1 ) ] ) ])) modifie)
                in
                Expect.equal ( Just "Nouvelle saisie", Just True )
                    ( Maybe.map .titre (Dict.get "a1" confirme.drafts), Maybe.map .modifie (Dict.get "a1" confirme.drafts) )
        , test "le retour à la préparation garde la saisie confirmée" <|
            \_ ->
                let
                    initial =
                        Tuple.first (Main.init (E.object []))

                    saisi =
                        Tuple.first (Main.update (Main.Modifier "titre" "Mon activité") initial)

                    envoye =
                        Tuple.first (Main.update Main.EnregistrerActivite saisi)

                    confirme =
                        Tuple.first (Main.update (Main.Reponse (E.object [ ( "operation", E.string "activite" ), ( "statut", E.int 200 ), ( "document", E.object [ ( "id", E.string "a1" ), ( "revision", E.int 1 ) ] ) ])) envoye)

                    aide =
                        Tuple.first (Main.update (Main.Route "#aide") confirme)

                    retour =
                        Tuple.first (Main.update (Main.Route "#preparer") aide)
                in
                Expect.equal ( "a1", Just "Mon activité" )
                    ( retour.edition, Maybe.map .titre (Dict.get retour.edition retour.drafts) )
        , test "changer de cours conserve les deux saisies" <|
            \_ ->
                let
                    cours id titre =
                        E.object [ ( "id", E.string id ), ( "revision", E.int 1 ), ( "document", E.object [ ( "titre", E.string titre ), ( "contenu", E.string "Texte" ) ] ) ]

                    a =
                        Tuple.first (Main.update (Main.EditerCours (cours "c1" "Premier cours")) (Tuple.first (Main.init (E.object []))))

                    saisi =
                        Tuple.first (Main.update (Main.Champ "cours-titre" "Saisie du premier") a)

                    b =
                        Tuple.first (Main.update (Main.EditerCours (cours "c2" "Autre cours")) saisi)

                    saisiB =
                        Tuple.first (Main.update (Main.Champ "cours-contenu" "Saisie du second") b)

                    retour =
                        Tuple.first (Main.update (Main.EditerCours (cours "c1" "Titre serveur")) saisiB)
                in
                Expect.equal ( Just "Saisie du premier", Just "Saisie du second" )
                    ( Dict.get "cours-titre" retour.champs, Dict.get "c2" retour.draftsCours |> Maybe.andThen (Dict.get "cours-contenu") )
        , test "une édition garde les identifiants attendus et le type QCM" <|
            \_ ->
                let
                    activite =
                        E.object [ ( "id", E.string "a1" ), ( "revision", E.int 2 ), ( "document", E.object [ ( "titre", E.string "Choisir" ), ( "type", E.string "qcm" ), ( "propositions", E.int 3 ), ( "publication_corrige", E.int 1792000000 ), ( "attendus", E.list identity [ E.object [ ( "id", E.string "raisonnement" ), ( "texte", E.string "Justifier" ) ] ] ), ( "criteres", E.list identity [] ) ] ) ]

                    edite =
                        Tuple.first (Main.update (Main.Editer activite) (Tuple.first (Main.init (E.object []))))
                in
                Expect.equal { ids = Just [ "raisonnement" ], typeActivite = Just "qcm", propositions = Just "3", publie = True }
                    { ids = Dict.get "a1" edite.drafts |> Maybe.map .attenduIds, typeActivite = Dict.get "a1" edite.drafts |> Maybe.map .typeActivite, propositions = Dict.get "a1" edite.drafts |> Maybe.map .propositions, publie = Dict.get "a1" edite.drafts |> Maybe.map (.publication >> (/=) "") |> Maybe.withDefault False }
        ]
