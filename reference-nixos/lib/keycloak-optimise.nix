{ pkgs }:
# Paquet optimisé du mode commun, sans dépendre d'une machine, d'un secret
# ou de sa génération. Le test d'amorçage exige la même dérivation que le module.
let
  c = (import (pkgs.path + "/nixos/lib/eval-config.nix") {
    inherit pkgs; system = "x86_64-linux";
    modules = [ {
      system.stateVersion = "26.05";
      services.keycloak = {
        enable = true;
        package = import ../services/keycloak-mrjam/paquet.nix { inherit pkgs; };
        plugins = (with pkgs.keycloak.plugins; [ junixsocket-common junixsocket-native-common ]) ++
          [ (import ../services/keycloak-mrjam { inherit pkgs; }) ];
        database = { type = "postgresql"; host = "/run/postgresql"; createLocally = false;
          name = "mrjam_identite"; username = "keycloak"; passwordFile = null; };
        settings = {
          hostname = "https://log.mrj.am";
          http-enabled = true; http-host = "127.0.0.1"; http-port = 8085;
          proxy-headers = "xforwarded"; hostname-strict = true;
          health-enabled = true; metrics-enabled = false; log-level = "warn";
          spi-password-hashing--argon2--memory = "19456";
          spi-password-hashing--argon2--iterations = "2";
          spi-password-hashing--argon2--parallelism = "1";
        };
      };
    } ];
  }).config;
in
builtins.head (builtins.filter (p: (p.pname or "") == "keycloak") c.environment.systemPackages)
