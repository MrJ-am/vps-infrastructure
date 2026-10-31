{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  lib = pkgs.lib;
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../nixos/mrjam-forgejo-runner.nix ../../nixos/mrjam-validation-worker.nix ../../nixos/mrjam-validation-collector.nix {
      system.stateVersion = "26.05"; # Disposable evaluation only.
      networking.nftables.enable = lib.mkDefault true;
      services.mrjamValidationWorker = {
        enable = lib.mkDefault true;
        rulesRevision = lib.mkDefault "1111111111111111111111111111111111111111";
        validator = pkgs.writeShellScriptBin "mrjam-validate" "exit 2";
      };
      services.mrjamForgejoRunner = {
        rulesRevision = "1111111111111111111111111111111111111111";
        registrationTokenFile = lib.mkDefault "/run/synthetic/registrar";
      };
      services.mrjamValidationCollector = { enable = lib.mkDefault true; rulesRevision = "1111111111111111111111111111111111111111"; };
    } extra ];
  }).config;
  disabled = evaluate { };
  enabled = evaluate { services.mrjamForgejoRunner.enable = true; };
  runner = enabled.systemd.services.mrjam-forgejo-runner;
  registrar = enabled.systemd.services.mrjam-forgejo-registration;
  passes = c: builtins.all (a: a.assertion || !(lib.hasPrefix "mrjamForgejoRunner:" a.message)) c.assertions;
  results = {
    disabledInert = !(disabled.systemd.services ? mrjam-forgejo-runner) && !(disabled.users.users ? mrjam-forgejo-registration);
    fixturePasses = passes enabled;
    noAutomaticStart = runner.wantedBy == [ ] && registrar.wantedBy == [ ] && !runner.restartIfChanged && !registrar.restartIfChanged;
    specializedAdmissionBeforeCandidate = enabled.services.mrjamForgejoRunner.coordinatorPackage.admissionProtocol == 1
      && runner.serviceConfig.ExecStart == "${enabled.services.mrjamForgejoRunner.coordinatorPackage}/bin/forgejo-runner daemon --config %d/runner-config";
    separateIdentities = runner.serviceConfig.User != registrar.serviceConfig.User && runner.serviceConfig.User != enabled.systemd.services."mrjam-validation-worker@".serviceConfig.User;
    noContainerGroup = enabled.users.users.mrjam-forgejo-runner.extraGroups == [ "mrjam-validation-requesters" ];
    fixedCollectorSocketOnly = runner.serviceConfig.BindReadOnlyPaths == [ "/run/mrjam-validation-collector/request.sock" ];
    separateArtifactOwner = enabled.systemd.services."mrjam-validation-collector@".serviceConfig.User != runner.serviceConfig.User;
    rootContainsOnlyPublicRuntime = lib.hasPrefix "/nix/store/" (toString runner.serviceConfig.RootDirectory) && !(lib.elem "/nix/store" runner.serviceConfig.BindReadOnlyPaths);
    privateCredentialsByReference = runner.serviceConfig.LoadCredential == [
      "runner-token:/var/lib/mrjam-forgejo-registration/registration/runner-token"
      "runner-config:/var/lib/mrjam-forgejo-registration/registration/connection.json"
    ];
    noRegistrationTokenInDaemon = !(lib.any (value: lib.hasInfix "/run/synthetic/registrar" value) runner.serviceConfig.LoadCredential);
    fixedNftDestination = lib.hasInfix "ip daddr 127.0.0.1 tcp dport 3004 accept" enabled.networking.nftables.tables.mrjam-forgejo-coordinator.content;
    noArbitraryNetwork = runner.serviceConfig.IPAddressDeny == "any" && runner.serviceConfig.IPAddressAllow == "localhost";
    boundedCoordinator = runner.serviceConfig.MemoryMax == "512M" && runner.serviceConfig.CPUQuota == "25%" && runner.serviceConfig.TasksMax == 64;
    missingFirewallRejected = !(passes (evaluate { services.mrjamForgejoRunner.enable = true; networking.nftables.enable = false; }));
    missingWorkerRejected = !(passes (evaluate { services.mrjamForgejoRunner.enable = true; services.mrjamValidationWorker.enable = false; }));
    missingCollectorRejected = !(passes (evaluate { services.mrjamForgejoRunner.enable = true; services.mrjamValidationCollector.enable = false; }));
    mismatchedRulesRejected = !(passes (evaluate { services.mrjamForgejoRunner.enable = true; services.mrjamValidationWorker.rulesRevision = "2222222222222222222222222222222222222222"; }));
    credentialTraversalRejected = !(passes (evaluate { services.mrjamForgejoRunner = { enable = true; registrationTokenFile = "/run/../token"; }; }));
  };
in assert builtins.all (x: x) (builtins.attrValues results); results
