{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../nixos/mrjam-forgejo-policy.nix {
      system.stateVersion = "26.05"; # Test fixture only.
      services.mrjamForgejoPolicy = {
        rulesRevision = "1111111111111111111111111111111111111111";
        controllerRevision = "2222222222222222222222222222222222222222";
        tokenFile = lib.mkDefault "/run/credentials-synthetic/forgejo-policy";
      };
    } extra ];
  }).config;
  disabled = evaluate { };
  enabled = evaluate { services.mrjamForgejoPolicy.enable = true; };
  unit = enabled.systemd.services.mrjam-forgejo-policy;
  service = unit.serviceConfig;
  passes = c: builtins.all (a: a.assertion || !(lib.hasPrefix "mrjamForgejoPolicy:" a.message)) c.assertions;
  results = {
    disabledInert = !(disabled.systemd.services ? mrjam-forgejo-policy) && !(disabled.environment.etc ? "mrjam-forgejo/policy.json");
    planFixturePasses = passes enabled;
    noAutomaticStart = unit.wantedBy == [ ] && unit.restartIfChanged == false;
    noImplicitForgejoProvisioning = !enabled.services.forgejo.enable && !enabled.services.postgresql.enable;
    fixedLocalNetwork = service.IPAddressDeny == "any" && service.IPAddressAllow == "localhost";
    immutableEntrypoint = lib.hasInfix "/bin/python3 -I -S /nix/store/" service.ExecStart && lib.hasSuffix " plan" service.ExecStart;
    credentialByReferenceOnly = service.LoadCredential == [ "forgejo-token:/run/credentials-synthetic/forgejo-policy" ];
    noPrivilegedIdentity = service.DynamicUser && service.CapabilityBoundingSet == "" && service.NoNewPrivileges;
    noCandidateWorkspace = service.ReadWritePaths == [ "/var/lib/mrjam-forgejo-policy" ];
    fixedResourceLimits = service.MemoryMax == "128M" && service.TasksMax == 8 && service.TimeoutStartSec == 185;
    noPlanApplyRejected = !(passes (evaluate { services.mrjamForgejoPolicy = { enable = true; mode = "apply"; }; }));
    duplicateReposRejected = !(passes (evaluate { services.mrjamForgejoPolicy = { enable = true; repositories = [ "mrjam-validation" "mrjam-validation" ]; }; }));
    traversalCredentialRejected = !(passes (evaluate { services.mrjamForgejoPolicy = { enable = true; tokenFile = "/run/../private"; }; }));
  };
in assert builtins.all (x: x) (builtins.attrValues results); results
