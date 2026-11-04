# Fixed recipe consuming a root-produced JSON binding, never candidate Nix.
# Builds content only. Neither this result nor its descriptor authorizes merge,
# staging, routing, schema changes, or activation.
{ bindingFile, pkgs ? import ../../forgejo/locked-toolchain.nix {} }:
let
  b=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile bindingFile));
  keys=["schema_version" "proposal_sha256" "slot" "artifact_root" "source" "report_policy"
    "report_policy_sha256" "server_sha256" "server_bytes" "frontend_sha256" "toolchains_sha256" "runtime"];
  hex=value: builtins.isString value && builtins.match "[0-9a-f]{64}" value!=null;
  store=value: builtins.isString value && builtins.match "/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+" value!=null;
  artifacts=builtins.path {path=b.artifact_root;name="mrjam-delivery-captured-artifacts";};
  source=builtins.storePath b.source;
  policy=builtins.storePath b.report_policy;
  runtime=builtins.storePath b.runtime;
  bundle=import ./delivery-bundle.nix {
    inherit pkgs;artifactRoot=artifacts;proposal=b.proposal_sha256;
    serverSha256=b.server_sha256;serverBytes=b.server_bytes;frontendSha256=b.frontend_sha256;
    reportPolicy=policy;reportPolicySha256=b.report_policy_sha256;toolchainsSha256=b.toolchains_sha256;
    slot=b.slot;configFile=runtime+"/runtime.json";
  };
  adopted=pkgs.writeText "mrjam-adopted-source.json" (builtins.toJSON {
    schema_version=1;inherit source policy;proposal_sha256=b.proposal_sha256;
  });
  descriptor=pkgs.writeText "mrjam-delivery-candidate.json" (builtins.toJSON {
    schema_version=1;proposal_sha256=b.proposal_sha256;slot=b.slot;
    inherit bundle adopted;source=source;policy=policy;
    binding_sha256=builtins.hashFile "sha256" bindingFile;
    deployment_authorized=false;
  });
in assert builtins.attrNames b==pkgs.lib.sort builtins.lessThan keys;
assert b.schema_version==1 && builtins.elem b.slot ["blue" "green"];
assert builtins.all hex [b.proposal_sha256 b.report_policy_sha256 b.server_sha256 b.frontend_sha256 b.toolchains_sha256];
assert builtins.all store [b.source b.report_policy b.runtime];
assert builtins.isString b.artifact_root && builtins.substring 0 1 b.artifact_root=="/";
assert builtins.hashFile "sha256" (source+"/manifest.json")==b.proposal_sha256;
assert builtins.hashFile "sha256" policy==b.report_policy_sha256;
assert builtins.hashFile "sha256" (artifacts+"/server")==b.server_sha256;
assert builtins.hashFile "sha256" (artifacts+"/frontend.tar")==b.frontend_sha256;
pkgs.runCommand "mrjam-delivery-candidate-${builtins.substring 0 12 b.proposal_sha256}-${b.slot}" {
  passthru={inherit bundle adopted descriptor;};
} ''
  mkdir "$out"
  ln -s ${descriptor} "$out/descriptor.json"
  ln -s ${bundle} "$out/bundle"
  ln -s ${adopted} "$out/adopted.json"
''
