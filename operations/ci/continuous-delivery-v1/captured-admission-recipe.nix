# Explicit code inventory: no workspace, private exports or candidate Nix enters
# the protected constructor's installed recipe.
{ pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {} }:
let
  root=../../..;
  delivery=map (name: "operations/ci/continuous-delivery-v1/"+name) [
    "captured-admission.nix" "proposal-bindings.nix" "aligned-validator.nix"
    "admission-package.nix" "admission-services.nix" "admission-publication.nix"
    "admission_publish.py" "admission_registry.py" "admission_control.py"
    "admission_producer.py" "admission_collector.py" "admission_exporter.py"
    "admission_signer.py" "admission_client.py"
  ];
  vise=map (name: "operations/vise/delivery/"+name) [
    "captured-admission.nix" "proposal-bindings.nix" "authority-package.nix"
    "canonical-validator.nix" "build-probe.nix" "build-probe.py" "database-probe.py" "runtime-probe.py"
    "validate.py" "build_stage.py" "source_policy.py" "source_scope.py"
    "dependency_binding.py" "synthetic_database.py" "runtime_entry.py"
    "runtime_stage.py" "artifacts.py" "authority_profile.py"
  ];
  files=delivery++vise++[
    "operations/vise/schema-v1.sql" "operations/vise/adopt-runtime-role.sql"
    "operations/vise/check_adoption.py" "operations/vise/schema-contract.json"
    "flake.lock" "operations/forgejo/locked-toolchain.nix"
    "operations/forgejo/worker.py" "operations/forgejo/stage_sources.py"
    "operations/ci/authority-v1/contract.py"
    "operations/ci/authority-credentials-v2/reader.py"
    "operations/ci/authority-report-details-v3/descriptor.json"
  ];
  # Literal store paths inside copied Nix text are not runtime references.
  # Keep the constructor's fixed evaluation inputs reachable after transfer
  # and garbage collection, including inputs absent from the final validator.
  evaluationInputs=map builtins.storePath [
    /nix/store/p2494a4mh5nsp77sfzrfd8zhinz34bmp-mrjam-validate
    /nix/store/0py92lckwf8la1w2pq6d0cgd42xnpywr-mrjam-verifier-runtime.json
    /nix/store/ivbh7z3jxnh58sc15klrmhg4z8jhiqf4-cargo-vendor-dir
    /nix/store/d8bhnl18vsch1zbrvm28w6dvn6acz1k6-mrjam-validation-authority-policy.json
    /nix/store/f2bsh1n6snqdldnjdshdy1lw3hnlfxwi-bubblewrap-0.12.0
    /nix/store/fya253x5ky7rhfz6rkgdwjr1fzf7fy71-openssl-3.6.5-bin
    /nix/store/l6c4bjcvy4r6yyh2fyj4y7347dxzv6vg-overrides
    /nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1
    /nix/store/0ddv9m7ylgn7ri86p9n0z0yy1gn2nxh7-mrjam-vise-validation-dependencies-1
    /nix/store/a46dz5ayfq3h5rksc6h6bsa5blzdnj40-mrjam-vise-0.2.0-8c8ef66f943c-tests
    /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source
  ];
in pkgs.runCommand "mrjam-protected-admission-recipe" {} ''
  mkdir -p "$out"
  mkdir "$out/evaluation-inputs"
  ${pkgs.lib.concatMapStringsSep "\n" (path: ''
    ln -s ${path} "$out/evaluation-inputs/$(basename '${path}')"
  '') evaluationInputs}
  ${pkgs.lib.concatMapStringsSep "\n" (name: ''
    mkdir -p "$out/$(dirname '${name}')"
    cp ${root + ("/"+name)} "$out/${name}"
  '') files}
''
