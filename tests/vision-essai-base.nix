# Socle actuel complet sans lire le répertoire de publication du vrai VPS.
{ lib, ... }: {
  imports = [ ../hosts/hostinger/logique.nix ../vendor/vision-embeddings/embeddings.nix
    ../modules/identite-amorcage.nix ];
  infrastructure.amorcageIdentite.enable = true;
  infrastructure.postgresql.visionSemantique = true;
  services.visionEmbeddings.enable = true;
  services.visionEmbeddings.source = lib.mkForce
    (builtins.storePath (builtins.toFile "vision-fournisseur-bascule-test" "qualification"));
  systemd.services.vision-migrate.restartIfChanged = false;
}
