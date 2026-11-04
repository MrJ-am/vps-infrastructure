# Build public authority metadata and a control package. No registry insertion,
# signing credential, service activation or production authorization occurs.
{ validator, runtime, closure, proposal, verifierNarHash, validity
, viseRules ? null
, pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}
}:
assert builtins.attrNames validity == ["expires_at" "not_before"];
assert builtins.isInt validity.not_before && builtins.isInt validity.expires_at
  && validity.not_before>0 && validity.expires_at>validity.not_before
  && validity.expires_at - validity.not_before <= 604800;
let
  root=../../ci/continuous-delivery-v1;
  old=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile
    /nix/store/d8bhnl18vsch1zbrvm28w6dvn6acz1k6-mrjam-validation-authority-policy.json));
  storeInput=value: if builtins.isAttrs value && value ? outPath then value else builtins.storePath value;
  verifier=storeInput validator;
  runtimePath=storeInput runtime;
  closurePath=storeInput closure;
  runtimeValue=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile runtimePath));
  reportPath=builtins.storePath runtimeValue.policy;
  report=builtins.fromJSON (builtins.readFile reportPath);
  bubblewrap=builtins.storePath /nix/store/f2bsh1n6snqdldnjdshdy1lw3hnlfxwi-bubblewrap-0.12.0;
  steps=["complete-vise-source-tree" "locked-toolchain-versions" "locked-cargo-npm-elm-dependencies"
    "rust-offline-release-build" "typescript-no-emit" "vise-frontend-build" "vise-component-tests"
    "vise-api-tests-synthetic-postgresql" "vise-schema-and-role-refusals"
    "vise-graceful-stop-and-restart" "vise-restore-current-erasure-ledger" "vise-artifact-content-bound"];
  limits=["Independent release acceptance is not established by this content report."
    "Production deployment is not authorized by this content report."
    "No production database, erasure ledger or backup was used in validation."];
  worker={schema_version=1;rules_revision=report.rules_revision;validator_store=toString verifier;
    bubblewrap_store=toString bubblewrap;closure_file="${closurePath}/store-paths";};
  producer=old.producer // {
    rules_revision=report.rules_revision;verifier=toString verifier;verifier_nar_hash=verifierNarHash;
    closure_sha256=builtins.hashFile "sha256" (closurePath+"/store-paths");
    report_policy_sha256=builtins.hashFile "sha256" reportPath;
    worker_policy_sha256=builtins.hashString "sha256" (builtins.toJSON worker);
    producer_recipe_sha256=builtins.hashFile "sha256" (root+"/admission_producer.py");
    collector_recipe_sha256=builtins.hashFile "sha256" (root+"/admission_collector.py");
    worker_core_sha256=builtins.hashFile "sha256" ../../forgejo/worker.py;
    contract_sha256=builtins.hashFile "sha256" ../../ci/authority-v1/contract.py;
  };
  policy=old // validity // {
    inherit producer;rules_revision=report.rules_revision;
    verifier=producer.verifier;verifier_nar_hash=verifierNarHash;
    closure_sha256=producer.closure_sha256;report_policy_sha256=producer.report_policy_sha256;
    required_steps=steps;not_established=limits;accepted_proposals=[proposal];
    sources=map (s: {inherit (s) id repository revision tree_sha;}) report.sources;
  };
  details={schema_version=2;profile="vise-v1";report_policy=toString reportPath;
    report_policy_sha256=policy.report_policy_sha256;verifier=policy.verifier;
    verifier_nar_hash=verifierNarHash;runtime=toString runtimePath;
    runtime_sha256=builtins.hashFile "sha256" runtimePath;required_steps=steps;};
in import (root+"/admission-services.nix") {
  inherit pkgs policy producer worker details bubblewrap viseRules;
  profile="vise-v1";expectedSteps=12;
  bindings={inherit proposal;validator=verifier;closure=closurePath;};
}
