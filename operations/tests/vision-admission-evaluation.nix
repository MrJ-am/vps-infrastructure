{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../nixos/mrjam-vision-admission.nix {
      system.stateVersion = "26.05"; boot.loader.grub.enable = false;
      fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
    } ] ++ extra;
  }).config;
  valid = c: lib.all (entry: entry.assertion) c.assertions;
  fixture = { pkgs, ... }: {
    services.postgresql = { enable = true; package = pkgs.postgresql_17;
      authentication = "local all postgres peer\nlocal all all reject\n";
      identMap = "existing_map existing_user existing_role\n";
    };
    services.mrjamVisionAdmission = {
      enable = true;
      artifactStorePath = "/nix/store/00000000000000000000000000000000-synthetic-vision-admission";
      visionDatabase = "vision_synthetic";
      smtpCredentialFile = "/run/keys/synthetic/smtp";
      keycloakCredentialFile = "/run/keys/synthetic/keycloak";
      closureCredentialFile = "/run/keys/synthetic/closure";
      approvalCredentialFile = "/run/keys/synthetic/approval";
    };
  };
  off = evaluate [ ]; enabled = evaluate [ fixture ];
  service = enabled.systemd.services.mrjam-vision-admission;
  initialize = enabled.systemd.services.mrjam-vision-admission-initialize;
  pg = enabled.services.postgresql;
  checks = {
    disabledInert = !off.services.postgresql.enable && !(off.systemd.services ? mrjam-vision-admission);
    fixtureValid = valid enabled;
    stateVersionPreserved = enabled.system.stateVersion == "26.05";
    privateUser = enabled.users.users.mrjam-vision-admission.extraGroups == [ ]
      && enabled.users.users.mrjam-vision-admission.isSystemUser
      && enabled.users.users.mrjam-vision-admission.hashedPassword == "!";
    noAutomaticStart = service.wantedBy == [ ] && initialize.wantedBy == [ ]
      && service.serviceConfig.Restart == "no" && !(enabled.systemd.timers ? mrjam-vision-admission);
    closedByDefault = !enabled.services.mrjamVisionAdmission.admissionsOpen;
    explicitReadiness = lib.hasInfix " check-local --config " service.serviceConfig.ExecStartPre
      && lib.hasInfix " serve --config " service.serviceConfig.ExecStart;
    explicitExclusiveInitialization = lib.hasInfix " initialize-state --config " initialize.serviceConfig.ExecStart
      && initialize.conflicts == [ "mrjam-vision-admission.service" ];
    initializationWithoutNetwork = initialize.serviceConfig.PrivateNetwork && initialize.serviceConfig.IPAddressDeny == "any"
      && initialize.serviceConfig.RestrictAddressFamilies == [ "AF_UNIX" ];
    leastCredentials = initialize.serviceConfig.LoadCredential == [ "smtp:/run/keys/synthetic/smtp" ]
      && service.serviceConfig.LoadCredential == [ "smtp:/run/keys/synthetic/smtp" "keycloak:/run/keys/synthetic/keycloak"
        "closure:/run/keys/synthetic/closure" "approval:/run/keys/synthetic/approval" ];
    privateDurableState = service.serviceConfig.StateDirectory == "mrjam-vision-admission"
      && service.serviceConfig.StateDirectoryMode == "0700" && service.serviceConfig.UMask == "0077";
    budgets = service.serviceConfig.MemoryMax == "256M" && service.serviceConfig.TasksMax == 32
      && service.serviceConfig.CPUQuota == "20%" && service.serviceConfig.TimeoutStartSec == 60;
    noHostCapabilities = service.serviceConfig.CapabilityBoundingSet == "" && service.serviceConfig.NoNewPrivileges;
    fixedPeerRoles = lib.hasInfix ''local "vision_synthetic" "vision_admission" peer map=mrjam_rust_slots'' pg.authentication
      && lib.hasInfix ''local "vision_synthetic" "vision_administration" peer map=mrjam_rust_slots'' pg.authentication
      && lib.hasInfix "mrjam_rust_slots mrjam-vision-admission vision_admission" pg.identMap
      && lib.hasInfix "mrjam_rust_slots mrjam-vision-admission vision_administration" pg.identMap;
    noDatabaseOrRoleCreation = pg.ensureDatabases == [ ] && pg.ensureUsers == [ ];
    oldHbaPreserved = lib.hasInfix "local all postgres peer\nlocal all all reject\n" pg.authentication;
    privilegedDatabaseRefused = !(valid (evaluate [ fixture { services.mrjamVisionAdmission.visionDatabase = lib.mkForce "postgres"; } ]));
    wrongRoleRefused = !(valid (evaluate [ fixture { services.mrjamPostgresqlAccess.workers.visionAdmission.role = lib.mkForce "vision"; } ]));
    traversalRefused = !(valid (evaluate [ fixture { services.mrjamVisionAdmission.approvalCredentialFile = lib.mkForce "/var/lib/secrets/.."; } ]));
    sharedCredentialReferenceRefused = !(valid (evaluate [ fixture { services.mrjamVisionAdmission.approvalCredentialFile = lib.mkForce "/run/keys/synthetic/closure"; } ]));
    otherIdentityRefused = !(valid (evaluate [ fixture { services.postgresql.identMap = lib.mkAfter "mrjam_rust_slots other_user vision_admission\n"; } ]));
    buildContextRefused = !(valid (evaluate [ fixture ({pkgs,...}: { services.mrjamVisionAdmission.artifactStorePath = lib.mkForce "${pkgs.hello}"; }) ]));
  };
in if lib.all (value: value) (builtins.attrValues checks) then checks
else throw "Admission module checks failed: ${builtins.toJSON (lib.filterAttrs (_: value: !value) checks)}"
