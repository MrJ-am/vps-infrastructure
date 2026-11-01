# Exact materialization prepared from source 65bbd8c53a1f6d2efda453a5c82d66c49df26699.
# Its integrity is mandatory; this is not the installed VPS revision.
{ nixpkgs, materialized }:
import ./package.nix {
  inherit nixpkgs materialized;
  expectedManifestSha256 = "f119430d6c3163faece432c1c4cc84449f3e9cd0ffc9866b2136f9b4dcccdfc6";
}
