{ nixpkgs, materialized }:
let pkgs = import nixpkgs { system = "x86_64-linux"; };
in pkgs.callPackage ./. {
  inherit materialized;
  sourceLock = ./sources-runtime-20261031.lock.json;
  expectedManifestSha256 = "6c4c957933bac12ded038377f3346a800366201a0ae743bce06dd21f87ab50b8";
}
