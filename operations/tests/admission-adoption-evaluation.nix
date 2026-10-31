{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../nixos/mrjam-admission-adoption.nix {
      system.stateVersion = "26.05"; boot.loader.grub.enable = false;
      fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
    } ] ++ extra;
  }).config;
  valid = c: lib.all (entry: entry.assertion) c.assertions;
  fixture = { pkgs, ... }: {
    services.postgresql = { enable = true; package = pkgs.postgresql_17;
      authentication = "local all postgres peer\nlocal all all reject\n";
    };
    services.mrjamVisionAdmission = {
      enable = true; artifactStorePath = "/nix/store/00000000000000000000000000000000-synthetic-admission";
      visionDatabase = "vision_synthetic";
      smtpCredentialFile = "/run/keys/synthetic/smtp";
      keycloakCredentialFile = "/run/keys/synthetic/keycloak";
      closureCredentialFile = "/run/keys/synthetic/closure";
      approvalCredentialFile = "/run/keys/synthetic/approval";
    };
    services.mrjamAdmissionAdoption = {
      enable = true; artifactStorePath = "/nix/store/00000000000000000000000000000000-synthetic-adopter";
    };
  };
  off = evaluate [ ]; enabled = evaluate [ fixture ];
  unit = enabled.systemd.services.mrjam-admission-adoption;
  service = unit.serviceConfig;
  checks = {
    disabledInert = !(off.systemd.services ? mrjam-admission-adoption)
      && !(off.users.users ? mrjam-vision-admission);
    fixtureValid = valid enabled;
    stateVersionPreserved = enabled.system.stateVersion == "26.05";
    noAutomaticStart = unit.wantedBy == [ ] && service.Restart == "no" && !unit.restartIfChanged;
    noAutomaticInitialization = enabled.systemd.services.mrjam-vision-admission-initialize.wantedBy == [ ];
    unprivilegedSameIdentity = service.User == "mrjam-vision-admission" && service.Group == service.User
      && enabled.users.users.mrjam-vision-admission.extraGroups == [ ];
    noConcurrentInitializationOrRuntime = unit.conflicts == [ "mrjam-vision-admission.service" "mrjam-vision-admission-initialize.service" ]
      && unit.after == unit.conflicts;
    fixedNoArguments = service.ExecStart == "/nix/store/00000000000000000000000000000000-synthetic-adopter/bin/mrjam-admission-adopt";
    sealedReadOnlyInputs = service.BindReadOnlyPaths == [
      "/var/lib/mrjam-admission-adoption-input/requests.sqlite:/run/mrjam-admission-adoption/requests.sqlite"
      "/var/lib/mrjam-admission-adoption-input/mail.sqlite:/run/mrjam-admission-adoption/mail.sqlite"
    ];
    privateDirectories = service.RuntimeDirectoryMode == "0700" && service.StateDirectoryMode == "0700"
      && service.UMask == "0077" && service.StateDirectory == "mrjam-vision-admission";
    emptyRootStaging = builtins.elem "d /var/lib/mrjam-admission-adoption-input 0700 root root -" enabled.systemd.tmpfiles.rules;
    noNetwork = service.PrivateNetwork && service.IPAddressDeny == "any" && service.RestrictAddressFamilies == [ "AF_UNIX" ];
    noHostCapabilities = service.NoNewPrivileges && service.CapabilityBoundingSet == "" && service.AmbientCapabilities == "";
    finiteBudgets = service.MemoryMax == "512M" && service.CPUQuota == "20%" && service.TasksMax == 8 && service.TimeoutStartSec == 90;
    openAdmissionsRefused = !(valid (evaluate [ fixture { services.mrjamVisionAdmission.admissionsOpen = true; } ]));
    absentIdentityRefused = !(valid (evaluate [ fixture { services.mrjamVisionAdmission.enable = lib.mkForce false; } ]));
    buildContextRefused = !(valid (evaluate [ fixture ({pkgs,...}: { services.mrjamAdmissionAdoption.artifactStorePath = lib.mkForce "${pkgs.hello}"; }) ]));
  };
in if lib.all (value: value) (builtins.attrValues checks) then checks
else throw "Admission adoption module checks failed: ${builtins.toJSON (lib.filterAttrs (_: value: !value) checks)}"
