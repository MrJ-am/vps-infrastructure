# Bind the complete public application configuration to qualified immutable bytes.
# This builds no application and performs no SQL, credential read or activation.
{ pkgs }:
let
  artifact = (builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile ./application-artifacts.json))).outputs.server;
  runtime = slot: pkgs.callPackage ../../runtime/package.nix {
    inherit slot;
    configFile = ./. + "/runtime-${slot}.json";
    serverStorePath = artifact.store_path;
    serverManifestSha256 = artifact.manifest_sha256;
  };
in { blue = runtime "blue"; green = runtime "green"; }
