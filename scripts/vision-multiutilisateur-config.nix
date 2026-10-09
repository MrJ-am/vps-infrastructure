{ configuration, fournisseur ? null }:
let
  lib = import <nixpkgs/lib>;
  c = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ (builtins.toPath configuration) ]
      ++ lib.optional (fournisseur != null) ({ lib, ... }: {
        # Référence conservée au store actif, sans recréer un chemin brut.
        services.visionEmbeddings.source = lib.mkForce (builtins.storePath fournisseur);
      });
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
  fournisseur_source = if c.services ? visionEmbeddings && c.services.visionEmbeddings.enable
    then toString c.services.visionEmbeddings.source else null;
}
