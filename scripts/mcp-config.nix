{ configuration }:
let
  lib = import <nixpkgs/lib>;
  c = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ (builtins.toPath configuration) ];
  }).config;
  base = import ./logique-config.nix { inherit configuration; };
  # Les chemins TLS sont dérivés par Nginx depuis ACME, comparé séparément.
  nettoyer = nom: site: builtins.removeAttrs
    (if nom == "vision.mrj.am"
     then site // { locations = builtins.removeAttrs site.locations [ "= /mcp" "= /_vision_mcp_token"\n       "= /.well-known/oauth-protected-resource"\n       "= /.well-known/oauth-protected-resource/mcp"\n       "= /.well-known/oauth-authorization-server"\n       "^~ /oauth/" "@vision-mcp-authentication-required" ]; }
     else site) [ "sslCertificate" "sslCertificateKey" ];
in {
  inherit (base) systeme nginx;
  invariant = (builtins.removeAttrs base.invariant [ "sites" "services" ]) // {
    services = map (nom: c.systemd.units."${nom}.service".text)
      [ "sshd" "postgresql" "postgresql-setup" "matheval" "vision"
        "vision-migrate" "postgresqlBackup-matheval" "postgresqlBackup-vision" ];
    authentification = {
      configuration = builtins.removeAttrs c.systemd.services.mrj-auth.serviceConfig [ "ExecStart" ];
      inherit (c.systemd.services.mrj-auth) environment after wantedBy;
    };
    sites = lib.mapAttrs nettoyer c.services.nginx.virtualHosts;
    utilisateurs = lib.mapAttrs (_: u: {
      inherit (u) uid group extraGroups home isSystemUser;
      cles = u.openssh.authorizedKeys.keys;
    }) c.users.users;
    certificats = c.security.acme.certs;
  };
}
