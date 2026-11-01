{ nixpkgs, materialized }:
import ./package.nix {
  inherit nixpkgs materialized;
  sourceLock = ./sources-adoption-20261101.lock.json;
  expectedManifestSha256 = "b0c8a52571c4e1c3b89b5c72b82f15a55bb968d4d1a1a95ca3c433c9ef2b651f";
}
