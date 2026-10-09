let
  c = import ../scripts/vision-mrjam-composants.nix {};
  r = c.resume;
in
assert r.garde_activation && !r.generation_constructible;
assert !r.preconditions_validees && !r.inscriptions && !r.activation && !r.postgres_tcp;
assert r.jdbc_unix && r.keycloak_version == "26.7.3";
assert builtins.length (builtins.attrNames r.unites) == 7;
assert r.unites."mrj-auth".utilisateur == "mrj-auth";
assert r.unites."vision-gestion".utilisateur == "vision_administration";
assert r.unites."mrjam-admission".utilisateur == "vision_admission";
assert r.unites."mrjam-fermeture".utilisateur == "vision_fermeture";
assert c.lot.name == "vision-mrjam-composants";
{ composants = 7; generationConstructible = false; gardeActivation = true; }
