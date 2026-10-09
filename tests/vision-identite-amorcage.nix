let
  candidat = import ../scripts/vision-identite-amorcage.nix {
    configuration = toString ../hosts/hostinger/logique.nix;
  };
  r = candidat.resume;
  ordinaire = (import ../scripts/vision-mrjam-composants.nix {}).resume;
in
assert r.unites_conservees && r.hotes_conserves && r.postgres_production_conserve && r.parefeu_conserve;
assert r.cluster_independant && !r.postgres_tcp && !r.inscriptions && !r.mode_vision_oidc;
assert !r.preconditions_validees && !r.activation && !r.identite_humaine;
assert r.keycloak_version == "26.7.3" && r.paquet == ordinaire.keycloak;
assert r.systeme_actif != r.systeme_amorcage;
assert !ordinaire.preconditions_validees && !ordinaire.generation_constructible;
{ amorcageDistinct = true; paquetQualifieConserve = true; modeOrdinaireFerme = true; }
