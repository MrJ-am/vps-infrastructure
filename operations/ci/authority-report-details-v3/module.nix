# Keep the v1 options, identities, transport and unit restrictions byte-identical.
args@{ pkgs, ... }:
let packageScope = pkgs // {
  callPackage = recipe: supplied:
    assert recipe == ../authority-v1/package.nix;
    import ./package.nix ({ inherit pkgs; } // supplied);
};
in import ../authority-v1/module.nix (args // { pkgs = packageScope; })
