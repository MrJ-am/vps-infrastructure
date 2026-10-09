{ configuration }:
let
  c = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ (builtins.toPath configuration) ];
  }).config;
  pkgs = import <nixpkgs> { system = "x86_64-linux"; };
in {
  systeme = toString c.system.build.toplevel;
  postgres_paquet = toString c.services.postgresql.finalPackage;
  postgres_majeure = pkgs.lib.versions.major c.services.postgresql.package.version;
  postgres_tcp = c.services.postgresql.enableTCPIP;
  postgres_ecoute = c.services.postgresql.settings.listen_addresses;
  keycloak_version = pkgs.keycloak.version;
  recipient_age = c.services.vision.backupRecipient;
}
