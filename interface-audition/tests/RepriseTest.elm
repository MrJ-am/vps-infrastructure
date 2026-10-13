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
        , test "réconcilier un conflit de cours conserve le texte et adopte sa révision" <|
            \_ ->
                let
                    c revision =
                        E.object [ ( "id", E.string "c1" ), ( "revision", E.int revision ), ( "document", E.object [ ( "titre", E.string "Titre serveur" ), ( "contenu", E.string "Cours serveur" ) ] ) ]

                    edite =
                        Tuple.first (Main.update (Main.EditerCours (c 1)) (Tuple.first (Main.init (E.object []))))

                    saisi =
                        Tuple.first (Main.update (Main.Champ "cours-contenu" "Ma nouvelle démonstration") edite)

                    conflit =
                        Tuple.first (Main.update (Main.Reponse (E.object [ ( "operation", E.string "cours" ), ( "statut", E.int 409 ), ( "erreur", E.string "conflit_revision" ) ])) saisi)

                    relu =
                        Tuple.first (Main.update (Main.Reponse (E.object [ ( "operation", E.string "preparations" ), ( "statut", E.int 200 ), ( "document", E.object [ ( "cours", E.list identity [ c 2 ] ) ] ) ])) conflit)

                    adopte =
                        Tuple.first (Main.update Main.AccepterCoursVersion relu)
                in
                Expect.equal ( Just "2", Just "Ma nouvelle démonstration" ) ( Dict.get "cours-revision" adopte.champs, Dict.get "cours-contenu" adopte.champs )
        , test "réconcilier un calendrier conserve l'échéance saisie" <|
            \_ ->
                let
                    a revision =
                        E.object [ ( "id", E.string "f1" ), ( "nature", E.string "affectation" ), ( "revision", E.int revision ), ( "document", E.object [ ( "activite", E.string "a1" ), ( "echeance", E.int 1792000000 ), ( "eleves", E.list E.string [ "alice" ] ) ] ) ]

                    edite =
                        Tuple.first (Main.update (Main.Calendrier (a 1)) (Tuple.first (Main.init (E.object []))))

                    saisi =
                        Tuple.first (Main.update (Main.Champ "echeance" "2026-11-10 12:00") edite)

                    relu =
                        Tuple.first (Main.update (Main.Reponse (E.object [ ( "operation", E.string "retrouver" ), ( "statut", E.int 200 ), ( "document", E.object [ ( "groupe", E.string "g1" ), ( "objet", a 2 ) ] ) ])) saisi)

                    adopte =
                        Tuple.first (Main.update Main.AccepterCalendrierVersion relu)
                in
                Expect.equal ( Just "2", Just "2026-11-10 12:00", [ "alice" ] ) ( Dict.get "affectation-revision" adopte.champs, Dict.get "echeance" adopte.champs, adopte.eleves )
        ]
