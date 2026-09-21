{ configuration }:
let
  lib = import <nixpkgs/lib>;
  c = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ (builtins.toPath configuration) ];
  }).config;
  base = import ./logique-config.nix { inherit configuration; };
  routes = [ "= /" "= /app.js" "= /app.css" "= /interface-manifest.json" "^~ /assets/mrjam/" ];
  nettoyer = nom: site: builtins.removeAttrs
    (if nom == "vision.mrj.am" then site // { locations = builtins.removeAttrs site.locations routes; } else site)
    [ "sslCertificate" "sslCertificateKey" ];
in {
  systeme = base.systeme;
  nginx = base.nginx;
  invariant = (builtins.removeAttrs base.invariant [ "sites" ]) // {
    sites = lib.mapAttrs nettoyer c.services.nginx.virtualHosts;
    utilisateurs = lib.mapAttrs (_: u: {
      inherit (u) uid group extraGroups home isSystemUser;
      cles = u.openssh.authorizedKeys.keys;
    }) c.users.users;
  };
}
