# Socle synthétique pour évaluer le garde ; aucune activation.
{ lib, ... }: {
  imports = [ ../hosts/hostinger/vision-semantique.nix ../modules/identite-amorcage.nix ];
  infrastructure.amorcageIdentite.enable = true;
  services.vision.bootstrapSource = lib.mkForce ../vendor/vision/source;
  services.visionEmbeddings.source = lib.mkForce
    (builtins.storePath (builtins.toFile "vision-fournisseur-bascule-test" "qualification"));
}
