{ configuration, moduleInterface, moduleAudition, site, paquetMetier }:
let
  pkgs = import <nixpkgs> { system = "x86_64-linux"; }; lib = pkgs.lib;
  eval = modules: (import <nixpkgs/nixos/lib/eval-config.nix> { system = "x86_64-linux"; inherit modules; }).config;
  b = eval [ (builtins.toPath configuration) ];
  module = import (builtins.toPath moduleInterface) {
    authentication = b.services.postgresql.authentication;
    timers = b.systemd.timers;
    units = b.systemd.units;
    inherit site paquetMetier moduleAudition;
  };
  c = eval [ (builtins.toPath configuration) module ];
  permise = n: builtins.elem n [ "mrjam-metier.service" "nginx.service" "nginx-config-reload.service" "postgresql.service" ]
    || lib.hasInfix "audition.mrj.am" n || n == "acme-setup.service"
    || (lib.hasPrefix "acme-account-" n && lib.hasSuffix ".target" n);
  protege = cfg: {
    units = lib.mapAttrs (_: u: u.text) (lib.filterAttrs (n: _: !permise n) cfg.systemd.units);
    metier = builtins.removeAttrs cfg.systemd.services.mrjam-metier.serviceConfig [ "ExecStart" ];
    env = builtins.removeAttrs cfg.systemd.services.mrjam-metier.environment [ "AUDITION_DSN" ];
    autresHotes = lib.mapAttrs (_: v: {
      inherit (v) enableACME forceSSL serverName serverAliases listenAddresses extraConfig root;
      locations = lib.mapAttrs (_: loc: {
        inherit (loc) proxyPass root alias return tryFiles index basicAuthFile extraConfig;
      }) v.locations;
    }) (builtins.removeAttrs cfg.services.nginx.virtualHosts [ "audition.mrj.am" ]);
    postgres = { package = toString cfg.services.postgresql.finalPackage;
      settings = builtins.removeAttrs cfg.services.postgresql.settings [ "hba_file" "ident_file" ];
      inherit (cfg.services.postgresql) ensureDatabases ensureUsers; };
    kernel = toString cfg.boot.kernelPackages.kernel;
    firewall = cfg.networking.firewall.allowedTCPPorts;
    acme = { defaults = cfg.security.acme.defaults; certs = builtins.removeAttrs cfg.security.acme.certs [ "audition.mrj.am" ]; };
  };
in {
  avant = toString b.system.build.toplevel; apres = toString c.system.build.toplevel;
  invariants = protege b == protege c;
  differences = builtins.filter (n: (protege b).${n} != (protege c).${n}) (builtins.attrNames (protege b));
  unitesDifferentes = builtins.attrNames (lib.filterAttrs (n: u: !(permise n)
    && (!(builtins.hasAttr n b.systemd.units) || u.text != b.systemd.units.${n}.text)) c.systemd.units);
  assertions = builtins.all (a: a.assertion) c.assertions;
  nativeActif = b.infrastructure.log.enable && c.infrastructure.log.enable
    && !c.services.keycloak.enable && !c.systemd.services.mrj-auth.enable;
  paquetAvant = toString b.infrastructure.metier.paquet; paquetApres = toString c.infrastructure.metier.paquet;
  exeAvant = b.systemd.services.mrjam-metier.serviceConfig.ExecStart;
  exeApres = c.systemd.services.mrjam-metier.serviceConfig.ExecStart;
  nginx = c.systemd.services.nginx.serviceConfig.ExecStart;
  postgres = toString c.services.postgresql.finalPackage;
  authenticationAvant = b.services.postgresql.authentication;
  authenticationApres = c.services.postgresql.authentication;
  identMapAvant = b.services.postgresql.identMap; identMapApres = c.services.postgresql.identMap;
  auditionDsn = c.systemd.services.mrjam-metier.environment.AUDITION_DSN;
  kanidmCommande = c.systemd.services.kanidm.serviceConfig.ExecStart;
  host = { inherit (c.services.nginx.virtualHosts."audition.mrj.am") enableACME forceSSL; };
}
