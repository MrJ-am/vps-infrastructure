{ configuration }:
let
  lib = import <nixpkgs/lib>;
  c = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ (builtins.toPath configuration) ];
  }).config;
  base = import ./logique-config.nix { inherit configuration; };
in {
  inherit (base) systeme nginx;
  journal = c.systemd.services.nginx.serviceConfig.LogNamespace or "";
  # La seule évolution autorisée concerne les sorties de journal de Nginx.
  invariant = base.invariant // {
    sites = lib.mapAttrs (_: s: builtins.removeAttrs s [ "sslCertificate" "sslCertificateKey" ])
      c.services.nginx.virtualHosts;
    certificats = c.security.acme.certs;
    nginx = {
      inherit (c.services.nginx) package eventsConfig appendHttpConfig
        prependConfig appendConfig config httpConfig streamConfig;
      commun = lib.filter (l: l != "") (lib.splitString "\n"
        (lib.replaceStrings [ (builtins.readFile ../lib/journal-http.conf) ] [ "" ]
          c.services.nginx.commonHttpConfig));
    };
    utilisateurs = lib.mapAttrs (_: u: {
      inherit (u) uid group extraGroups home isSystemUser;
      cles = u.openssh.authorizedKeys.keys;
    }) c.users.users;
  };
}
