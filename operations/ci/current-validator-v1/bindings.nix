{ pkgs ? import ../../forgejo/locked-toolchain.nix {} }:
let
  validator = import ./package.nix { inherit pkgs; };
  staging = import ./staging.nix { inherit pkgs; };
  closure = pkgs.closureInfo { rootPaths = [ validator ]; };
in { inherit validator staging closure; }
