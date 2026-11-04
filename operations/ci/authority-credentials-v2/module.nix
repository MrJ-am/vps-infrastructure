# Reuse the frozen v1 options, identities, protocol and all unit restrictions.
# Only its exact package recipe is replaced; no caller-selected recipe exists.
args@{ pkgs, ... }:
let
  packageScope = pkgs // {
    callPackage = recipe: supplied:
      assert recipe == ../authority-v1/package.nix;
      import ./package.nix ({ inherit pkgs; } // supplied);
  };
in import ../authority-v1/module.nix (args // { pkgs = packageScope; })
