{ pkgs }:
# Recette existante du Nixpkgs de l'assemblage, sans mise à niveau générale.
# Hashes publiés par NixOS/nixpkgs c79f17227ea6bed328437e4d38827bc0b22f7f33.
# Source v1.11.2 = commit 547933867e87da737e79d26942dc9261adaa5ee9.
pkgs.callPackage (import (pkgs.path + "/pkgs/servers/kanidm/generic.nix") {
  version = "1.11.2";
  hash = "sha256-W7LkbHu2jS5pB63eTvmKsypOzL/bzm/5ssnzlpME6jc=";
  cargoHash = "sha256-pn1g0sesG9YtFf/qUvrSHW/m+2rHEyeZGzW1V5XRT+Y=";
}) { enableSecretProvisioning = false; }
