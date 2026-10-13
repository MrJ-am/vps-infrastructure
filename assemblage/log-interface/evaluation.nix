{ configuration, moduleInterface, site, paquetMetier }:
let
  pkgs = import <nixpkgs> { system = "x86_64-linux"; }; lib = pkgs.lib;
  eval = modules: (import <nixpkgs/nixos/lib/eval-config.nix> { system = "x86_64-linux"; inherit modules; }).config;
  b = eval [ (builtins.toPath configuration) ];
  module = import (builtins.toPath moduleInterface) {
    locations = b.services.nginx.virtualHosts."log.mrj.am".locations;
    inherit site paquetMetier;
  };
  c = eval [ (builtins.toPath configuration) module ];
  protege = cfg: {
    units = lib.mapAttrs (_: u: u.text) (builtins.removeAttrs cfg.systemd.units
      [ "mrjam-metier.service" "nginx.service" "nginx-config-reload.service" ]);
    metier = builtins.removeAttrs cfg.systemd.services.mrjam-metier.serviceConfig [ "ExecStart" ];
    env = cfg.systemd.services.mrjam-metier.environment;
    autresHotes = lib.mapAttrs (_: v: {
      inherit (v) enableACME forceSSL serverName serverAliases listenAddresses extraConfig;
      locations = lib.mapAttrs (_: loc: {
        inherit (loc) proxyPass root alias return tryFiles index basicAuthFile extraConfig;
      }) v.locations;
    }) (builtins.removeAttrs cfg.services.nginx.virtualHosts [ "log.mrj.am" ]);
    logTls = let v=cfg.services.nginx.virtualHosts."log.mrj.am"; in {
      inherit (v) enableACME forceSSL serverName serverAliases listenAddresses extraConfig;
    };
    postgres = { package = toString cfg.services.postgresql.finalPackage;
      authentication = cfg.services.postgresql.authentication; identMap = cfg.services.postgresql.identMap; };
    kernel = toString cfg.boot.kernelPackages.kernel;
    firewall = cfg.networking.firewall.allowedTCPPorts;
  };
in {
  avant = toString b.system.build.toplevel;
  apres = toString c.system.build.toplevel;
  invariants = protege b == protege c;
  assertions = builtins.all (a: a.assertion) c.assertions;
  nativeActif = b.infrastructure.log.enable && c.infrastructure.log.enable
    && !c.services.keycloak.enable && !c.systemd.services.mrj-auth.enable;
  paquetAvant = toString b.infrastructure.metier.paquet;
  paquetApres = toString c.infrastructure.metier.paquet;
  exeAvant = b.systemd.services.mrjam-metier.serviceConfig.ExecStart;
  exeApres = c.systemd.services.mrjam-metier.serviceConfig.ExecStart;
  locationsAvant = builtins.attrNames b.services.nginx.virtualHosts."log.mrj.am".locations;
  locationsApres = builtins.attrNames c.services.nginx.virtualHosts."log.mrj.am".locations;
  nginx = c.systemd.services.nginx.serviceConfig.ExecStart;
}
