{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../nixos/mrjam-validation-staging.nix {
      system.stateVersion = "26.05"; # Invented fixture only.
      services.mrjamValidationWorker = {
        rulesRevision = "1111111111111111111111111111111111111111";
        validator = pkgs.writeShellScriptBin "mrjam-validate" "exit 2";
      };
    } extra ];
  }).config;
  entry = { sha256 = lib.concatStrings (lib.replicate 64 "a"); source = pkgs.writeTextDir "manifest.json" "INVALID_FIXTURE_ONLY"; };
  disabled = evaluate { };
  enable = {
    services.mrjamValidationWorker.enable = true;
    services.mrjamValidationStaging = { enable = true; proposals = [ entry ]; };
  };
  enabled = evaluate enable;
  service = enabled.systemd.services.mrjam-validation-staging;
  conf = service.serviceConfig;
  bad = more: evaluate (lib.recursiveUpdate enable more);
  refused = conf: builtins.any (a: !a.assertion && lib.hasPrefix "mrjamValidationStaging" a.message) conf.assertions;
  catalog = builtins.fromJSON (builtins.unsafeDiscardStringContext enabled.environment.etc."mrjam-validation-staging/catalog.json".text);
  results = {
    inertDisabled = !(disabled.systemd.services ? mrjam-validation-staging) && !(disabled.environment.etc ? "mrjam-validation-staging/catalog.json") && !(disabled.users.users ? mrjam-validation-worker);
    noImplicitStart = service.wantedBy == [ ] && !service.restartIfChanged && !service.stopIfChanged;
    noWorkerAutoStart = enabled.systemd.sockets.mrjam-validation-worker.wantedBy == [ ];
    fixedNoArgumentEntry = lib.hasSuffix "/bin/mrjam-validation-stage-sources" conf.ExecStart && conf.StandardInput == "null";
    noCapabilities = conf.User == "root" && conf.CapabilityBoundingSet == "" && conf.AmbientCapabilities == "" && conf.NoNewPrivileges;
    singleWritableRoot = conf.ProtectSystem == "strict" && conf.ReadWritePaths == [ "/var/lib/mrjam-validation-input" ];
    noNetwork = conf.PrivateNetwork && conf.RestrictAddressFamilies == [ "AF_UNIX" ] && conf.IPAddressDeny == "any";
    noCredentials = !(conf ? LoadCredential) && builtins.elem "-/run/credentials" conf.InaccessiblePaths;
    noCollectorAccess = builtins.elem "-/var/lib/mrjam-validation-collector" conf.InaccessiblePaths;
    rootReadonlyCatalog = enabled.environment.etc."mrjam-validation-staging/catalog.json".mode == "0444" && enabled.environment.etc."mrjam-validation-staging/catalog.json".uid == 0;
    rulesComeFromWorker = catalog.rules_revision == enabled.services.mrjamValidationWorker.rulesRevision && (builtins.head catalog.proposals).sha256 == entry.sha256;
    boundedResources = conf.MemoryMax == "192M" && conf.CPUQuota == "20%" && conf.TasksMax == 16 && conf.TimeoutStartSec == 120;
    closedOutputs = conf.StandardOutput == "journal" && conf.StandardError == "null";
    missingWorkerRefused = refused (bad { services.mrjamValidationWorker.enable = false; });
    emptyCatalogRefused = refused (bad { services.mrjamValidationStaging.proposals = [ ]; });
    duplicateCatalogRefused = refused (bad { services.mrjamValidationStaging.proposals = [ entry entry ]; });
    oversizedCatalogRefused = refused (bad { services.mrjamValidationStaging.proposals = [ entry entry entry ]; });
  };
in assert builtins.all (v: v) (builtins.attrValues results); results
