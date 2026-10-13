{ configuration, correction }:
let
  pkgs = import <nixpkgs> { system = "x86_64-linux"; };
  lib = pkgs.lib;
  eval = modules: (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux"; inherit modules;
  }).config;
  b = eval [ (builtins.toPath configuration) ];
  c = eval [ (builtins.toPath configuration) (builtins.toPath correction) ];
  protege = cfg: {
    units = lib.mapAttrs (_: u: u.text) (builtins.removeAttrs cfg.systemd.units
      [ "nginx.service" "nginx-config-reload.service" ]);
    hotes = lib.mapAttrs (nom: v: {
      inherit (v) enableACME forceSSL serverName serverAliases listenAddresses;
      extraConfig = if nom == "log.mrj.am" then "" else v.extraConfig;
      locations = lib.mapAttrs (chemin: loc: {
        inherit (loc) proxyPass root alias return tryFiles index basicAuthFile;
        extraConfig = if nom == "log.mrj.am" && chemin == "/" then "" else loc.extraConfig;
      }) v.locations;
    }) cfg.services.nginx.virtualHosts;
    postgres = { package = toString cfg.services.postgresql.finalPackage;
      authentication = cfg.services.postgresql.authentication; identMap = cfg.services.postgresql.identMap; };
    kernel = toString cfg.boot.kernelPackages.kernel;
    firewall = cfg.networking.firewall.allowedTCPPorts;
    paquet = toString cfg.infrastructure.metier.paquet;
  };
in {
  avant = toString b.system.build.toplevel;
  apres = toString c.system.build.toplevel;
  invariants = protege b == protege c;
  assertions = builtins.all (a: a.assertion) c.assertions;
  nativeActif = b.infrastructure.log.enable && c.infrastructure.log.enable
    && !c.services.keycloak.enable && !c.systemd.services.mrj-auth.enable;
  extraAvant = b.services.nginx.virtualHosts."log.mrj.am".extraConfig;
  extraApres = c.services.nginx.virtualHosts."log.mrj.am".extraConfig;
  proxyAvant = b.services.nginx.virtualHosts."log.mrj.am".locations."/".extraConfig;
  proxyApres = c.services.nginx.virtualHosts."log.mrj.am".locations."/".extraConfig;
  nginx = c.systemd.services.nginx.serviceConfig.ExecStart;
}
