let
  lib = import <nixpkgs/lib>;
  eval = extra: (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ ../hosts/hostinger/configuration.nix extra ];
  }).config;
  base = eval {};
  cible = eval ({ pkgs, ... }: {
    infrastructure.identite.enable = true;
    infrastructure.identite.preconditionsValidees = true;
    infrastructure.visionMultiutilisateur.enable = true;
    infrastructure.courriel.enable = true;
    infrastructure.visionCycle.enable = true;
    infrastructure.admission.enable = true;
    infrastructure.fermeture.enable = true;
    infrastructure.metier = {
      enable = true;
      # Seulement validation Nix : ne qualifie jamais un exécutable métier.
      paquet = pkgs.writeShellScriptBin "mrjam-metier" "exit 125";
      bankVersion = "fixture-synthetique";
    };
  });
  vh = cible.services.nginx.virtualHosts;
  conf = cible.systemd.services.mrjam-metier;
in
assert builtins.all (a: a.assertion) cible.assertions;
assert !base.infrastructure.metier.enable;
assert builtins.all (n: !cible.systemd.services.${n}.enable)
  [ "vision" "matheval" "vision-gestion" "vision-cycle" "mrjam-admission" "mrjam-fermeture" "mrjam-courriel" "vision-purge" ];
assert !cible.systemd.timers.vision-purge.enable && !cible.systemd.timers.mrjam-courriel.enable;
assert cible.systemd.services.mrj-auth.enable && cible.services.keycloak.enable;
assert cible.systemd.timers.mrjam-sauvegarde.enable;
assert cible.services.postgresql.dataDir == base.services.postgresql.dataDir;
assert !cible.services.postgresql.enableTCPIP;
assert lib.hasInfix "peer map=mrjam_metier" cible.services.postgresql.authentication;
assert lib.hasInfix "mrjam_metier mrjam-metier matheval_app" cible.services.postgresql.identMap;
assert !(lib.hasInfix "keycloak" conf.environment.VISION_DSN);
assert conf.serviceConfig.User == "mrjam-metier";
assert conf.serviceConfig.RuntimeDirectoryMode == "0750";
assert conf.serviceConfig.StateDirectoryMode == "0700";
assert vh."vision.mrj.am".locations."= /mcp".proxyPass == "http://unix:/run/mrjam-metier/http.sock:";
assert lib.hasInfix "auth_request /_vision_mcp_token" vh."vision.mrj.am".locations."= /mcp".extraConfig;
assert lib.hasInfix "auth_request /_vision_administration" vh."vision.mrj.am".locations."/api/gestion/".extraConfig;
assert lib.hasInfix "auth_request /_mrj_session" vh."vision.mrj.am".locations."/api/web/".extraConfig;
assert lib.hasInfix ''proxy_set_header X-Mrjam-Service "vision"'' vh."vision.mrj.am".locations."/api/web/".extraConfig;
assert vh."principiipetit.io".locations."/matheval/".proxyPass == null;
assert vh."principiipetit.io".locations."^~ /matheval/api/".proxyPass == "http://unix:/run/mrjam-metier/http.sock:";
assert builtins.length vh."mrjam-fermeture-interne".listen == 1;
assert (builtins.head vh."mrjam-fermeture-interne".listen).addr == "127.0.0.1";
assert (builtins.head vh."mrjam-fermeture-interne".listen).port == 3028;
assert !(builtins.head vh."mrjam-fermeture-interne".listen).ssl;
assert !(lib.hasInfix "fermeture-interne" vh."log.mrj.am".locations."/".extraConfig);
{
  metierProcessus = 1;
  frontendMatheval = "statique";
  backendTCP = false;
  identite = "Keycloak provisoire, auth_request existant";
  productionQualifiee = false;
}
