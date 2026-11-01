{ lib, ... }: { imports = [ "/root/vision-identite-amorcage-essais/ac3d8e0ab466a536c9ac3190d360e163d364b8fb/configuration-avant.nix" "/root/vision-identite-amorcage-operations/25f685900a9b65cb7cef872f0b55bcb21e35567d/source/modules/identite-amorcage.nix" ];
infrastructure.amorcageIdentite.enable = true;
services.visionEmbeddings.source = lib.mkForce (builtins.storePath "/nix/store/20nds4zvi1pcnljpwnwzcsysvyk15g11-vision-fournisseur-c0bfcac");
}
