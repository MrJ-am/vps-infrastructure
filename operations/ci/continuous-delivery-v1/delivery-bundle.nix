# Fixed content-only packaging recipe. The protected controller supplies the
# verified capture bindings; this derivation grants no activation authority.
{ artifactRoot, proposal, serverSha256, serverBytes, frontendSha256,
  reportPolicy, reportPolicySha256, toolchainsSha256, slot, configFile,
  pkgs ? import ../../forgejo/locked-toolchain.nix {} }:
let
  server=import ./delivery-server.nix {
    inherit pkgs proposal;rawServer=artifactRoot+"/server";
    expectedSha256=serverSha256;expectedBytes=serverBytes;
  };
  frontends=import ./delivery-frontends.nix {
    inherit pkgs proposal reportPolicy reportPolicySha256 toolchainsSha256;
    archive=artifactRoot+"/frontend.tar";expectedSha256=frontendSha256;
  };
  runtime=import ./delivery-runtime.nix {
    inherit pkgs slot configFile;
    frontendInventory=frontends+"/inventory.json";
    serverStorePath=builtins.unsafeDiscardStringContext (toString server);
    serverManifestSha256=builtins.hashFile "sha256" (server+"/artifact.json");
  };
  descriptor=pkgs.writeText "mrjam-delivery-bundle.json" (builtins.toJSON {
    schema_version=1;proposal_sha256=proposal;inherit slot server frontends runtime;
    payload_sha256={server=serverSha256;frontend=frontendSha256;};
    deployment_authorized=false;
  });
in pkgs.runCommand "mrjam-delivery-bundle-${builtins.substring 0 12 proposal}-${slot}" {
  passthru={inherit server frontends runtime descriptor;};
} ''
  mkdir "$out"
  ln -s ${descriptor} "$out/descriptor.json"
  ln -s ${server} "$out/server"
  ln -s ${frontends} "$out/frontends"
  ln -s ${runtime} "$out/runtime"
''
