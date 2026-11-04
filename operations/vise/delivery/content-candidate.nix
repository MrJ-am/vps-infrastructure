# Root-produced data binding only. No candidate code is evaluated by Nix.
# The result authorizes neither a merge nor production activation.
{ bindingFile, pkgs ? import ../../forgejo/locked-toolchain.nix {} }:
let
  b=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile bindingFile));
  keys=["schema_version" "profile" "proposal_sha256" "artifact_root" "source" "report_policy"
    "report_policy_sha256" "server_sha256" "server_bytes" "frontend_sha256" "verification_sha256"];
  hex=value: builtins.isString value && builtins.match "[0-9a-f]{64}" value!=null;
  store=value: builtins.isString value && builtins.match "/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+" value!=null;
  artifacts=builtins.path {path=b.artifact_root;name="mrjam-vise-captured-artifacts";};
  source=builtins.storePath b.source;
  policy=builtins.storePath b.report_policy;
  sourcePolicy=builtins.fromJSON (builtins.readFile policy);
  bundle=import ./content-package.nix {
    inherit pkgs;artifactRoot=artifacts;proposal=b.proposal_sha256;
    serverSha256=b.server_sha256;serverBytes=b.server_bytes;frontendSha256=b.frontend_sha256;
  };
  adopted=pkgs.writeText "mrjam-vise-adopted-source.json" (builtins.toJSON {
    schema_version=1;inherit source policy;proposal_sha256=b.proposal_sha256;
  });
  descriptor=pkgs.writeText "mrjam-vise-delivery-candidate.json" (builtins.toJSON {
    schema_version=2;profile="vise-v1";proposal_sha256=b.proposal_sha256;
    inherit bundle adopted source policy;
    binding_sha256=builtins.hashFile "sha256" bindingFile;
    verification_sha256=b.verification_sha256;deployment_authorized=false;
  });
in assert builtins.attrNames b==pkgs.lib.sort builtins.lessThan keys;
assert b.schema_version==2 && b.profile=="vise-v1";
assert builtins.all hex [b.proposal_sha256 b.report_policy_sha256 b.server_sha256 b.frontend_sha256 b.verification_sha256];
assert builtins.all store [b.source b.report_policy];
assert builtins.isString b.artifact_root && builtins.substring 0 1 b.artifact_root=="/";
assert sourcePolicy.schema_version==2 && sourcePolicy.profile=="vise-v1";
assert builtins.hashFile "sha256" (source+"/manifest.json")==b.proposal_sha256;
assert builtins.hashFile "sha256" policy==b.report_policy_sha256;
assert builtins.hashFile "sha256" (artifacts+"/server")==b.server_sha256;
assert builtins.hashFile "sha256" (artifacts+"/frontend.tar")==b.frontend_sha256;
assert builtins.hashFile "sha256" (artifacts+"/verification.json")==b.verification_sha256;
pkgs.runCommand "mrjam-vise-delivery-candidate-${builtins.substring 0 12 b.proposal_sha256}" {
  passthru={inherit bundle adopted descriptor;};
} ''
  mkdir "$out"
  ln -s ${descriptor} "$out/descriptor.json"
  ln -s ${bundle} "$out/bundle"
  ln -s ${adopted} "$out/adopted.json"
''
