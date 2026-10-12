{ paquetMetier }:
let
  e = import ../scripts/log-evaluation.nix {
    configuration = toString ./log-evaluation-base.nix;
    paquet = paquetMetier;
    documentVision = "/srv/qualification/vision-nouveau";
    ressourcesMatheval = "/srv/qualification/matheval-nouveau";
    bankVersion = "fixture-nouveau";
    kanidm = "/nix/store/0aqnq3k20yq30hf0bch64ghy3nj9bd66-kanidm-1.11.2";
  };
  r = e.rapport;
in
assert r.assertions;
assert r.avant != r.amorcage && r.amorcage != r.apres;
assert r.protegeAvant == r.protegeAmorcage && r.protegeAvant == r.protegeApres;
assert r.postgresAccesAvant.authentication == r.postgresAccesApres.authentication;
{ superposition_active = true; amorcage_et_final_evalues = true; services_preserves = true; production = false; }
