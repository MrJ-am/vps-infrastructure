let
  lib = import <nixpkgs/lib>;
  eval = extra: (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ ../hosts/hostinger/configuration.nix extra ];
  }).config;
  base = eval {};
  cible = eval ({ ... }: {
    infrastructure.identite.enable = true;
    infrastructure.identite.preconditionsValidees = true;
    infrastructure.visionMultiutilisateur.enable = true;
    infrastructure.courriel.enable = true;
    infrastructure.visionCycle.enable = true;
  });
  vh = cible.services.nginx.virtualHosts;
in
assert builtins.all (a: a.assertion) cible.assertions;
assert !base.infrastructure.identite.enable;
assert !base.infrastructure.visionMultiutilisateur.enable;
assert !cible.infrastructure.identite.inscriptionsOuvertes;
assert cible.services.postgresql.settings.listen_addresses == "";
assert !cible.services.postgresql.enableTCPIP;
assert cible.services.postgresql.dataDir == base.services.postgresql.dataDir;
assert cible.services.keycloak.database.host == "/run/postgresql";
assert cible.services.keycloak.settings.http-host == "127.0.0.1";
assert cible.systemd.services.keycloak.serviceConfig.MemoryMax == "2G";
assert cible.systemd.services.vision-gestion.serviceConfig.User == "vision_administration";
assert cible.systemd.services.vision-cycle.serviceConfig.User == "vision_cycle";
assert lib.hasInfix "auth_request /_mrj_session" vh."vision.mrj.am".locations."= /api/web/effacer_compte".extraConfig;
assert vh."vision.mrj.am".locations."= /api/web/effacer_compte".proxyPass == "http://127.0.0.1:3026";
assert cible.systemd.services.mrj-auth.environment.MRJ_AUTH_MODE == "oidc";
assert lib.hasInfix "vision_identite peer map=mrj_identite" cible.services.postgresql.authentication;
assert lib.hasInfix "auth_request /_vision_administration" vh."vision.mrj.am".locations."/api/gestion/".extraConfig;
assert lib.hasInfix "$vision_gestion_method" vh."vision.mrj.am".locations."= /_vision_administration".extraConfig;
assert !(lib.hasInfix "auth_basic" vh."vision.mrj.am".locations."= /mcp".extraConfig);
assert vh."compte.mrj.am".locations."/".return == "404";
assert vh."vision.mrj.am".locations."= /".root == base.services.nginx.virtualHosts."vision.mrj.am".locations."= /".root;
{ postgresTCP = false; inscriptions = false; rolesSepares = true; sourceKeycloak = cible.services.keycloak.package.version; }
