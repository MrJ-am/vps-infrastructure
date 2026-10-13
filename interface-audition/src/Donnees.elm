module Donnees exposing (booleen, champ, decimal, entier, liste, objet, texte)

import Json.Decode as D
import Json.Encode as E


texte : String -> E.Value -> String
texte cle valeur =
    Result.withDefault "" (D.decodeValue (D.field cle D.string) valeur)


entier : String -> E.Value -> Int
entier cle valeur =
    Result.withDefault 0 (D.decodeValue (D.field cle D.int) valeur)


decimal : String -> E.Value -> Float
decimal cle valeur =
    Result.withDefault 0 (D.decodeValue (D.field cle D.float) valeur)


booleen : String -> E.Value -> Bool
booleen cle valeur =
    Result.withDefault False (D.decodeValue (D.field cle D.bool) valeur)


champ : String -> E.Value -> E.Value
champ cle valeur =
    Result.withDefault E.null (D.decodeValue (D.field cle D.value) valeur)


liste : String -> E.Value -> List E.Value
liste cle valeur =
    Result.withDefault [] (D.decodeValue (D.field cle (D.list D.value)) valeur)


objet : List ( String, E.Value ) -> E.Value
objet =
    E.object
