# Socle synthétique ancien : les nouvelles options d'identité sont absentes.
{ config, lib, pkgs, ... }@args:
let base = import ../hosts/hostinger/configuration.nix args;
in lib.recursiveUpdate base {
  imports = [
    ../hosts/hostinger/hardware-configuration.nix
    ../apps/matheval.nix ../apps/vision.nix ../apps/vision-interface.nix ../apps/nextcloud.nix
    ./fixtures/amorcage-ancien/gateway.nix ./fixtures/amorcage-ancien/postgresql.nix
    ../apps/logique.nix ../vendor/vision-embeddings/embeddings.nix ../modules/identite-amorcage.nix
  ];
  infrastructure.amorcageIdentite.enable = true;
  infrastructure.postgresql.visionSemantique = true;
  services.vision.bootstrapSource = lib.mkDefault ../vendor/vision/source;
  services.visionEmbeddings.source = lib.mkForce
    (builtins.storePath (builtins.toFile "vision-fournisseur-ancien-test" "qualification"));
}
