let
  essai = configuration: fournisseur: import ../scripts/vision-essai-generation.nix {
    configuration = toString configuration;
    source = toString ../vendor/vision/source;
    sourceInterface = toString ../vendor/vision-interface;
    inherit fournisseur;
  };
  actuel = essai ./vision-essai-base.nix (builtins.toFile "vision-fournisseur-bascule-test" "qualification");
  ancien = essai ./vision-bascule-base-ancienne.nix (builtins.toFile "vision-fournisseur-ancien-test" "qualification");
in
assert actuel.systeme.drvPath != "" && ancien.systeme.drvPath != "";
assert actuel.resume.preconditions_validees && ancien.resume.preconditions_validees;
assert !actuel.resume.activation && !ancien.resume.inscriptions;
assert actuel.resume.hors_vision_identite_conserve && ancien.resume.hors_vision_identite_conserve;
assert actuel.resume.recipient_age == "age1p95t4z0aafq7j4fl7cc9f0cjz8j03dtlmz56kec4lj6vwxrvzpqqnc53cc";
{ generation_constructible_sans_activation = true; ancien_et_actuel = true; }
