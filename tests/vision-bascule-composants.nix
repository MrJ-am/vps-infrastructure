let
  resultat = import ../scripts/vision-bascule-composants.nix {
    configuration = toString ./vision-bascule-base.nix;
    source = toString ../vendor/vision/source;
    fournisseur = builtins.toFile "vision-fournisseur-bascule-test" "qualification";
  };
in
assert resultat.resume.garde_activation;
assert !resultat.resume.preconditions_validees;
assert !resultat.resume.generation_constructible;
assert !resultat.resume.inscriptions;
assert !resultat.resume.activation;
assert resultat.resume.hors_vision_identite_conserve;
{ gardeFerme = true; composantsSansActivation = true; routageExterneConserve = true; }
