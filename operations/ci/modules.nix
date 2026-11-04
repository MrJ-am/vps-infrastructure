# Scope the five CI modules, authority and coordinator to their own toolchain.
# Host NixOS modules and pkgs remain unchanged. No module is enabled here.
{ config, lib, pkgs, ... }:
let
  locked = import ../forgejo/locked-toolchain.nix { system = "x86_64-linux"; };
  paths = [
    ../nixos/mrjam-forgejo-policy.nix
    ../nixos/mrjam-forgejo-runner.nix
    ../nixos/mrjam-validation-worker.nix
    ../nixos/mrjam-validation-collector.nix
    ../nixos/mrjam-validation-staging.nix
    ./authority-credentials-v2/module.nix
    ./coordinator-v1/module.nix
  ];
  # Explicit keys let the staging import and the direct worker import converge.
  # Disable unscoped imports of these exact files, including an existing host
  # import, so their options can never be declared with a second package set.
  scoped = path: args@{ config, lib, ... }:
    let original = import path (args // { pkgs = locked; });
        imports = original.imports or [ ];
    in assert lib.all (item: builtins.elem item paths) imports;
      original // {
        _file = toString path;
        key = "mrjam-ci-locked:${toString path}";
        imports = map scoped imports;
      };
  runner = config.services.mrjamForgejoRunner;
  policy = config.services.mrjamForgejoPolicy;
  staging = config.services.mrjamValidationStaging;
in {
  disabledModules = paths;
  imports = map scoped paths;
  config.assertions = lib.optionals runner.enable [
    { assertion = pkgs.stdenv.hostPlatform.system == "x86_64-linux";
      message = "mrjamCI: only the qualified x86_64-linux toolchain is admitted."; }
    { assertion = policy.enable && policy.phase == "operate-validation"
        && policy.rulesRevision == runner.rulesRevision;
      message = "mrjamCI: the runner requires a policy for the same protected rules revision and operate-validation phase."; }
    { assertion = staging.enable;
      message = "mrjamCI: the runner requires explicitly selected immutable source staging."; }
    { assertion = lib.all (instance: !instance.enable)
        (builtins.attrValues config.services.gitea-actions-runner.instances);
      message = "mrjamCI: an upstream generic Actions runner must not accompany the bounded coordinator."; }
  ];
}
