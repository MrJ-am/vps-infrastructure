{ pkgs ? import ../../forgejo/locked-toolchain.nix {} }:
let
  original = builtins.storePath /nix/store/zjwbgmna6pyw7p151pzrgm20wi2jzfqv-mrjam-public-source-bundle-for-staging;
  previous = builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile (original + "/manifest.json")));
  policy = builtins.fromJSON (builtins.readFile ./policy.json);
  manifest = builtins.toJSON (previous // { rules_revision = policy.rules_revision; }) + "\n";
  source = pkgs.runCommand "mrjam-public-proposed-sources-b02-readiness-v1" {} ''
    mkdir "$out"
    cp -r --no-preserve=mode,ownership ${original}/. "$out/"
    chmod u+w "$out/manifest.json"
    cp ${pkgs.writeText "manifest.json" manifest} "$out/manifest.json"
  '';
in assert builtins.hashFile "sha256" (original + "/manifest.json") == "5857e70c38d41bb739b460a131d5eef6696985eb247ba9c9420a7605e51e5087";
assert policy.rules_revision == "b02bdf1b5d63dcf0e0610723788a7ca7e384932c";
{ inherit source; sha256 = builtins.hashString "sha256" manifest; rulesRevision = policy.rules_revision; proposedNotAdopted = true; }
