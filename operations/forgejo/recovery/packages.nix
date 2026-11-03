{ workspace ? ../../.., historical ? false
, nixpkgs ? /nix/store/ydk30pf7qngrw0ws113m9p005p681rxy-source
}:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  local = workspace + "/.local/ci-artifact-recovery-20261102";
  inputs = builtins.path { path = local + "/runtime-inputs"; name = "mrjam-pinned-build-inputs"; };
  proposal = builtins.path { path = local + "/proposal-fixture"; name = "mrjam-public-source-bundle-5857e70c38d4"; };
  elmCache = pkgs.callPackage (local + "/validator-code/workflow-runner/elm-cache.nix") { materialized = local + "/elm-cache"; };
  validation = import (local + "/validator-code/workflow-runner/qualification-package.nix") {
    inherit nixpkgs elmCache;
    toolchainsSource = if historical then local + "/historical-build-support/toolchains.nix"
      else workspace + "/operations/builds/toolchains.nix";
    frontendBuildSource = workspace + "/operations/builds";
    cargoVendor = inputs + "/cargo-vendor";
    frontendResourceInputs = local + "/frontend-resources";
    policy = local + "/policy.json";
  };
in {
  inherit (validation) verifier closure;
  runner = pkgs.callPackage ../runner-admission.nix {};
  stager = pkgs.callPackage ../staging-package.nix {};
  sourceBundle = pkgs.runCommand "mrjam-public-source-bundle-for-staging" {} ''
    mkdir "$out"
    cp -r --no-preserve=mode,ownership ${proposal}/. "$out/"
  '';
}
