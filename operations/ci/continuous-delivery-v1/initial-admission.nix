let
  pkgs=import ../../forgejo/locked-toolchain.nix {};
  control=import ./admission-package.nix {inherit pkgs;};
in import ./admission-publication.nix {inherit pkgs control;}
