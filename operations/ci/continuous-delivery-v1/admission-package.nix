# One immutable control package; root registry entries select admitted recipes.
# Building this package does not insert an entry or activate a service.
{ pkgs ? import ../../forgejo/locked-toolchain.nix {}
, bindings ? import ./aligned-bindings.nix { inherit pkgs; }
, verifierNarHash ? "sha256-OknmBbQlj9TDJuFNbN8ENKbC2TqnfWOI9cwtPHa6MzA="
, validity ? null
, retainOverlay ? false
, extraAnchors ? {}
, viseRules ? null
, signatureRulesRevision ? null
}:
assert validity == null || (builtins.isAttrs validity
  && builtins.attrNames validity == ["expires_at" "not_before"]
  && builtins.isInt validity.not_before && builtins.isInt validity.expires_at
  && validity.not_before > 0 && validity.expires_at > validity.not_before
  && validity.expires_at - validity.not_before <= 604800);
let
  previous=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile /nix/store/d8bhnl18vsch1zbrvm28w6dvn6acz1k6-mrjam-validation-authority-policy.json));
  oldDetails=builtins.fromJSON (builtins.unsafeDiscardStringContext
    (builtins.readFile ../authority-report-details-v3/descriptor.json));
  bubblewrap=builtins.storePath /nix/store/f2bsh1n6snqdldnjdshdy1lw3hnlfxwi-bubblewrap-0.12.0;
  runtime=builtins.storePath (builtins.unsafeDiscardStringContext (toString bindings.validator.runtime));
  runtimeValue=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile runtime));
  reportPolicy=builtins.storePath runtimeValue.policy;
  report=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile reportPolicy));
  signatureSources=builtins.filter (source:
    source.id=="signature" || source.repository=="MrJ-am/Signature") report.sources;
  signatureSelected=signatureRulesRevision!=null;
  requiredSteps=assert (if signatureSelected then
    builtins.isString signatureRulesRevision
    && builtins.match "[0-9a-f]{40}" signatureRulesRevision!=null
    && report.rules_revision==signatureRulesRevision
    && builtins.length signatureSources==1
    && (builtins.head signatureSources).id=="signature"
    && (builtins.head signatureSources).repository=="MrJ-am/Signature"
    && runtimeValue ? signature_python && runtimeValue ? signature_support
    else signatureSources==[] && report.rules_revision==previous.rules_revision);
    if signatureSelected then import ../../signature/delivery/authority-steps.nix previous.required_steps
    else builtins.filter (name: name!="rust-reviewed-readiness-overlay") previous.required_steps;
  narHash=verifierNarHash;
  worker={
    schema_version=1; rules_revision=report.rules_revision;
    validator_store=toString bindings.validator;
    bubblewrap_store=toString bubblewrap;
    closure_file="${bindings.closure}/store-paths";
  };
  producer=previous.producer // {
    rules_revision=report.rules_revision;
    verifier=toString bindings.validator; verifier_nar_hash=narHash;
    closure_sha256=builtins.unsafeDiscardStringContext (builtins.hashString "sha256" (builtins.readFile (bindings.closure+"/store-paths")));
    report_policy_sha256=builtins.hashFile "sha256" reportPolicy;
    worker_policy_sha256=builtins.hashString "sha256" (builtins.toJSON worker);
    producer_recipe_sha256=builtins.hashFile "sha256" ./admission_producer.py;
    collector_recipe_sha256=builtins.hashFile "sha256" ./admission_collector.py;
    worker_core_sha256=builtins.hashFile "sha256" ../../forgejo/worker.py;
    contract_sha256=builtins.hashFile "sha256" ../authority-v1/contract.py;
  };
  policy=previous // (if validity==null then {} else validity) // {
    inherit producer;
    rules_revision=report.rules_revision;
    verifier=producer.verifier; verifier_nar_hash=narHash;
    closure_sha256=producer.closure_sha256;
    report_policy_sha256=producer.report_policy_sha256;
    required_steps=requiredSteps;
    sources=map (source: {inherit (source) id repository revision tree_sha;}) report.sources;
    accepted_proposals=[bindings.proposal];
  };
  details=oldDetails // (if retainOverlay then {
    overlay_manifest="${builtins.storePath /nix/store/l6c4bjcvy4r6yyh2fyj4y7347dxzv6vg-overrides}/manifest.json";
  } else {}) // {
    report_policy=toString reportPolicy; report_policy_sha256=policy.report_policy_sha256;
    verifier=policy.verifier; verifier_nar_hash=narHash;
    runtime=toString runtime; runtime_sha256=builtins.hashFile "sha256" runtime;
    required_steps=policy.required_steps;
  };
in import ./admission-services.nix {
  inherit pkgs policy producer worker details bindings bubblewrap extraAnchors viseRules;
  expectedSteps=if signatureSelected then 82 else 74;
}
