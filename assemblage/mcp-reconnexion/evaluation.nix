{ configuration, moduleInterface, site, paquetMetier }:
let
  pkgs = import <nixpkgs> { system = "x86_64-linux"; }; lib = pkgs.lib;
  eval = modules: (import <nixpkgs/nixos/lib/eval-config.nix> { system = "x86_64-linux"; inherit modules; }).config;
  b = eval [ (builtins.toPath configuration) ];
  c = eval [ (builtins.toPath configuration) (import (builtins.toPath moduleInterface) { inherit site paquetMetier; }) ];
  protege = cfg: {
    units = lib.mapAttrs (_: u: u.text) (builtins.removeAttrs cfg.systemd.units
      [ "mrjam-metier.service" "nginx.service" "nginx-config-reload.service" ]);
    metier = builtins.removeAttrs cfg.systemd.services.mrjam-metier.serviceConfig [ "ExecStart" ];
    env = builtins.removeAttrs cfg.systemd.services.mrjam-metier.environment [ "VISION_DOCUMENT_ROOT" ];
    hotes = lib.mapAttrs (nom: v: {
      inherit (v) enableACME forceSSL serverName serverAliases listenAddresses extraConfig;
      locations = lib.mapAttrs (_: loc: {
        inherit (loc) proxyPass return tryFiles index basicAuthFile extraConfig;
        root = if nom == "vision.mrj.am" && loc.root == cfg.infrastructure.metier.documentVision
          then "DOCUMENT_VISION" else loc.root;
        alias = if nom == "vision.mrj.am" && loc.alias == cfg.infrastructure.metier.documentVision + "/manifest.json"
          then "DOCUMENT_VISION/manifest.json" else loc.alias;
      }) v.locations;
    }) cfg.services.nginx.virtualHosts;
    postgres = { package = toString cfg.services.postgresql.finalPackage;
      authentication = cfg.services.postgresql.authentication; identMap = cfg.services.postgresql.identMap; };
    kernel = toString cfg.boot.kernelPackages.kernel;
    firewall = cfg.networking.firewall.allowedTCPPorts;
  };
in {
  avant = toString b.system.build.toplevel;
  apres = toString c.system.build.toplevel;
  invariants = protege b == protege c
    && c.systemd.services.mrjam-metier.environment.VISION_DOCUMENT_ROOT == toString site;
  assertions = builtins.all (a: a.assertion) c.assertions;
  nativeActif = b.infrastructure.log.enable && c.infrastructure.log.enable
    && !c.services.keycloak.enable && !c.systemd.services.mrj-auth.enable;
  paquetAvant = toString b.infrastructure.metier.paquet;
  paquetApres = toString c.infrastructure.metier.paquet;
  exeAvant = b.systemd.services.mrjam-metier.serviceConfig.ExecStart;
  exeApres = c.systemd.services.mrjam-metier.serviceConfig.ExecStart;
  nginx = c.systemd.services.nginx.serviceConfig.ExecStart;
}
