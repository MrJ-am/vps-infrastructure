module ReviewConfig exposing (config)

import MrJam.Presentation
import NoUnused.Dependencies
import Review.Rule exposing (Rule)


config : List Rule
config =
    [ MrJam.Presentation.rule
    , NoUnused.Dependencies.rule
    ]
