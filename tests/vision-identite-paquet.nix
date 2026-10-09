let
  pkgs = import <nixpkgs> {};
  # Reproduire l'entrée 26.7.2 du VPS, sans modifier ses dépendances.
  ancien = pkgs.keycloak.overrideAttrs (_: {
    version = "26.7.2";
    src = pkgs.fetchzip {
      url = "https://github.com/keycloak/keycloak/releases/download/26.7.2/keycloak-26.7.2.zip";
      hash = "sha256-D4Hj4OHX8veFjIDbvbQN0E7C2oHVpbD2U4TV1Z8fZ8Y=";
    };
  });
  cible = import ../services/keycloak-mrjam/paquet.nix { pkgs = pkgs // { keycloak = ancien; }; };
  avecPlugins = cible.override {
    confFile = pkgs.writeText "qualification-keycloak.conf" "db=postgres\n";
    plugins = [ cible.plugins.junixsocket-common ];
  };
  configuration = import ../scripts/vision-identite-paquet.nix {};
  r = configuration.resume;
  refus = builtins.tryEval (import ../services/keycloak-mrjam/paquet.nix {
    pkgs = pkgs // { keycloak = ancien // { version = "27.0.0"; }; };
  });
in
assert !refus.success;
assert ancien.version == "26.7.2";
assert cible.version == "26.7.3";
assert avecPlugins.version == "26.7.3";
assert avecPlugins.src == cible.src;
assert avecPlugins.patches == ancien.patches;
assert builtins.length avecPlugins.enabledPlugins == 1;
assert r.version == "26.7.3" && r.jdbc_unix;
assert !r.activation && !r.inscriptions && !r.preconditions_validees;
assert builtins.length r.plugins == 5;
{ version = r.version; sourceConserveeApresPlugins = true;
  recetteConfigureeNixos = true; gardeActivationConservee = true; }
