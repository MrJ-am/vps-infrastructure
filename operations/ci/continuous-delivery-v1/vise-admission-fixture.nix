# Invented IPC profile. It does not compile or qualify a ViSe application.
{ pkgs, anchor, baseProducer, bubblewrap }:
let
  repeat=n: text: pkgs.lib.concatStrings (pkgs.lib.replicate n text);
  rules=repeat 40 "f";
  steps=["complete-vise-source-tree" "locked-toolchain-versions" "locked-cargo-npm-elm-dependencies"
    "rust-offline-release-build" "typescript-no-emit" "vise-frontend-build" "vise-component-tests"
    "vise-api-tests-synthetic-postgresql" "vise-schema-and-role-refusals" "vise-graceful-stop-and-restart"
    "vise-restore-current-erasure-ledger" "vise-artifact-content-bound"];
  limits=["Independent release acceptance is not established by this content report."
    "Production deployment is not authorized by this content report."
    "No production database, erasure ledger or backup was used in validation."];
  identities=[{id="vise";repository="MrJ-am/etp-vie-affective";revision=repeat 40 "a";tree_sha=repeat 40 "c";}];
  reportPolicy=pkgs.writeText "invented-vise-policy.json" (builtins.toJSON {
    schema_version=2;status="proposed-not-independently-adopted";profile="vise-v1";
    rules_revision=rules;sources=map (s: s // {root="sources/vise";tree_json="trees/vise.json";}) identities;
    frontends=[];rust_manifests={"components/vise/backend/Cargo.toml"=repeat 64 "d";
      "components/vise/backend/Cargo.lock"=repeat 64 "e";};
    out_of_scope=["platform: unchanged releases are not requalified by the ViSe pipeline"];
  });
  receiptPolicy=pkgs.writeText "invented-vise-receipt.json" (builtins.toJSON {
    rules_revision=rules;sources=identities;required_steps=steps;not_established=limits;
    report_policy=toString reportPolicy;
  });
  text="Invented second profile for IPC tests only\n";
  manifest=builtins.toJSON {schema_version=1;rules_revision=rules;
    files=[{path="invented.txt";bytes=builtins.stringLength text;sha256=builtins.hashString "sha256" text;}];};
  proposal=builtins.hashString "sha256" manifest;
  source=pkgs.runCommand "invented-vise-ipc-source" {} ''
    mkdir "$out"
    cp ${pkgs.writeText "manifest.json" manifest} "$out/manifest.json"
    cp ${pkgs.writeText "invented.txt" text} "$out/invented.txt"
  '';
  validator=pkgs.runCommand "invented-vise-ipc-validator-not-deployable" {nativeBuildInputs=[pkgs.makeWrapper];} ''
    mkdir -p "$out/lib" "$out/bin"
    cp ${./admission-fixture-validator.py} "$out/lib/validator.py"
    substituteInPlace "$out/lib/validator.py" --replace-fail '@report-policy@' '${receiptPolicy}' \
      --replace-fail 'hashlib.sha256(policy_raw).hexdigest()' 'hashlib.sha256(Path(policy["report_policy"]).read_bytes()).hexdigest()'
    makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-validate" --add-flags '-I -S' --add-flags "$out/lib/validator.py"
  '';
  closure=pkgs.closureInfo {rootPaths=[validator];};
  hashFile=pkgs.runCommand "invented-vise-ipc-nar-hash" {} ''
    ${pkgs.nix}/bin/nix-hash --type sha256 --base64 ${validator} > "$out"
  '';
  narHash="sha256-"+pkgs.lib.removeSuffix "\n" (builtins.readFile hashFile);
  support=pkgs.writeText "invented-vise-support" "Not executable; IPC metadata fixture only\n";
  api=pkgs.writeTextDir "api-tests.mjs" "// Invented IPC fixture, not API tests\n";
  runtime=pkgs.writeText "invented-vise-runtime.json" (builtins.toJSON {
    policy=toString reportPolicy;vise_dependencies=toString support;vise_schema=toString support;
    vise_adopt_role=toString support;vise_adoption_check=toString support;vise_schema_contract=toString support;
    vise_runtime_entry=toString support;vise_api_tests="${api}/api-tests.mjs";
  });
  worker={schema_version=1;rules_revision=rules;validator_store=toString validator;
    bubblewrap_store=toString bubblewrap;closure_file="${closure}/store-paths";};
  producer=baseProducer // {rules_revision=rules;verifier=toString validator;verifier_nar_hash=narHash;
    closure_sha256=builtins.hashFile "sha256" (closure+"/store-paths");
    report_policy_sha256=builtins.hashFile "sha256" reportPolicy;
    worker_policy_sha256=builtins.hashString "sha256" (builtins.toJSON worker);};
  policy=anchor // {inherit producer;rules_revision=rules;verifier=producer.verifier;
    expires_at=anchor.expires_at - 86400;
    verifier_nar_hash=narHash;closure_sha256=producer.closure_sha256;report_policy_sha256=producer.report_policy_sha256;
    accepted_proposals=[proposal];sources=identities;required_steps=steps;not_established=limits;};
  details={schema_version=2;profile="vise-v1";report_policy=toString reportPolicy;
    report_policy_sha256=policy.report_policy_sha256;verifier=policy.verifier;verifier_nar_hash=narHash;
    runtime=toString runtime;runtime_sha256=builtins.hashFile "sha256" runtime;required_steps=steps;};
in import ./admission-services.nix {
  inherit pkgs policy producer worker details bubblewrap;
  bindings={inherit proposal source validator closure;};profile="vise-v1";expectedSteps=12;
}
