{ nixpkgs, policyFile, build ? null }:
let
  locked = import ../../forgejo/locked-toolchain.nix {};
  lib = locked.lib;
  input = builtins.fromJSON (builtins.readFile policyFile);
  validator = locked.writeShellScriptBin "mrjam-validate" "exit 2 # synthetic inert source";
  policy = builtins.removeAttrs (input // { verifier = toString validator; }) [ "producer" ];
  coordinator = args@{ config, lib, ... }: import ./module.nix (args // { pkgs = locked; });
  fixture = {
    system.stateVersion = "26.05";
    boot.loader.grub.enable = false;
    fileSystems."/" = { device = "synthetic"; fsType = "ext4"; };
    networking.nftables.enable = true;
    services.mrjamForgejoPolicy = { enable = true; mode = "plan"; phase = "operate-validation";
      rulesRevision = policy.rules_revision; controllerRevision = "2222222222222222222222222222222222222222"; tokenFile = "/run/synthetic/policy"; };
    services.mrjamForgejoRunner = { enable = true; rulesRevision = policy.rules_revision;
      coordinatorUid = policy.requester_uid; registrarUid = policy.requester_uid + 1; registrationTokenFile = "/run/synthetic/registration"; };
    services.mrjamValidationWorker = { enable = true; rulesRevision = policy.rules_revision; inherit validator; };
    services.mrjamValidationCollector = { enable = true; rulesRevision = policy.rules_revision; };
    users.users.mrjam-validation-collector.uid = policy.collector_uid;
    services.mrjamValidationStaging = { enable = true; proposals = [ { sha256 = lib.concatStrings (lib.replicate 64 "a"); source = locked.writeTextDir "manifest.json" "INVALID_SYNTHETIC_SOURCE"; } ]; };
    services.mrjamValidationAuthority = { enable = true; inherit policy; signingKeyFile = "/var/lib/mrjam-validation-authority/invented-key"; };
  };
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") { system = "x86_64-linux"; modules = [ ../modules.nix fixture ] ++ extra; }).config;
  base = evaluate [];
  disabled = evaluate [ coordinator ];
  enabled = evaluate [ coordinator { services.mrjamValidationCoordinatorAttestation.enable = true; } ];
  old = base.systemd.services.mrjam-forgejo-runner;
  new = enabled.systemd.services.mrjam-forgejo-runner;
  unitContract = unit: { inherit (unit) serviceConfig environment after requires wantedBy restartIfChanged stopIfChanged; };
  results = {
    assertionsPass = lib.all (item: item.assertion) enabled.assertions;
    disabledUnitExact = unitContract disabled.systemd.services.mrjam-forgejo-runner == unitContract old;
    onlyThreeServiceConfigFieldsChange = builtins.removeAttrs old.serviceConfig [ "ExecStart" "RootDirectory" "BindReadOnlyPaths" ] == builtins.removeAttrs new.serviceConfig [ "ExecStart" "RootDirectory" "BindReadOnlyPaths" ];
    onlyAuthoritySocketAdded = lib.sort builtins.lessThan new.serviceConfig.BindReadOnlyPaths == lib.sort builtins.lessThan (old.serviceConfig.BindReadOnlyPaths ++ [ "/run/mrjam-validation-authority/request.sock" ]);
    entryPointFixed = new.serviceConfig.ExecStart == "${enabled.services.mrjamValidationCoordinatorAttestation.package}/bin/forgejo-runner daemon --config %d/runner-config";
    rootDistinct = new.serviceConfig.RootDirectory != old.serviceConfig.RootDirectory;
    rootIsStore = lib.hasPrefix "/nix/store/" (toString new.serviceConfig.RootDirectory);
    noHostStoreMount = !(lib.any (path: path == "/nix/store" || lib.hasPrefix "/nix/store:" path) new.serviceConfig.BindReadOnlyPaths);
    noNewCredential = new.serviceConfig.LoadCredential == old.serviceConfig.LoadCredential;
    noAutomaticActivation = new.wantedBy == [] && enabled.systemd.sockets.mrjam-validation-authority.wantedBy == [];
    signerUnchanged = unitContract enabled.systemd.services.mrjam-validation-authority == unitContract base.systemd.services.mrjam-validation-authority;
    collectorUnchanged = unitContract enabled.systemd.services."mrjam-validation-collector@" == unitContract base.systemd.services."mrjam-validation-collector@";
    workerUnchanged = unitContract enabled.systemd.services."mrjam-validation-worker@" == unitContract base.systemd.services."mrjam-validation-worker@";
    nftUnchanged = enabled.networking.nftables.tables == base.networking.nftables.tables;
    originalRunnerPackagePreserved = enabled.services.mrjamForgejoRunner.coordinatorPackage == base.services.mrjamForgejoRunner.coordinatorPackage;
  };
in if build == "runner" then enabled.services.mrjamValidationCoordinatorAttestation.package
else if build == "root" then enabled.services.mrjamValidationCoordinatorAttestation.root
else {
  inherit results;
  all_passed = lib.all (x: x) (builtins.attrValues results);
  package = enabled.services.mrjamValidationCoordinatorAttestation.package.outPath;
  root = enabled.services.mrjamValidationCoordinatorAttestation.root.outPath;
  original_root = base.services.mrjamForgejoRunner.coordinatorRoot.outPath;
  original_runner = base.services.mrjamForgejoRunner.coordinatorPackage.outPath;
  authority_package = enabled.services.mrjamValidationAuthority.package.outPath;
}
