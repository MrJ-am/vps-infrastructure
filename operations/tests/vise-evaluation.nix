{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  store = "/nix/store/00000000000000000000000000000000-vise-synthetic";
  context = builtins.getContext (builtins.toFile "vise-synthetic-context" "invented");
  baselineHba = "local all postgres peer\nlocal all all peer\n";
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../nixos/mrjam-vise.nix ({ pkgs, ... }: {
      system.stateVersion = "24.11";
      boot.loader.grub.enable = false;
      fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
      services.postgresql.package = pkgs.postgresql_17;
    }) extra ];
  }).config;
  setup = { services.mrjamVise = { enable = true; artifactRoot = store; adoption = { uid = 978; gid = 978; }; };
    services.postgresql = { enable = true; authentication = baselineHba; }; };
  disabled = evaluate { };
  baseline = evaluate { services.postgresql = { enable = true; authentication = baselineHba; }; };
  enabled = evaluate setup;
  unit = enabled.systemd.services.vise;
  passes = config: lib.all (a: a.assertion) config.assertions;
  bad = extra: evaluate { imports = [ setup extra ]; };
  result = {
    disabledInert = passes disabled && !(disabled.users.users ? etp_carnet) && !(disabled.systemd.services ? vise);
    noImplicitPostgres = !disabled.services.postgresql.enable;
    enabledAssertionsPass = builtins.all (a: a.assertion) enabled.assertions;
    fixedIdentity = unit.serviceConfig.User == "etp_carnet" && unit.serviceConfig.Group == "etp_carnet";
    existingUidGidPreserved = enabled.users.users.etp_carnet.uid == 978 && enabled.users.groups.etp_carnet.gid == 978;
    noSupplementaryGroups = enabled.users.users.etp_carnet.extraGroups == [ ];
    noPasswordOrHome = enabled.users.users.etp_carnet.hashedPassword == "!" && !enabled.users.users.etp_carnet.createHome;
    prebuiltOnly = unit.serviceConfig.ExecStart == store + "/server" && unit.environment.CARNET_DIST == store + "/dist";
    fixedPrivateListener = unit.environment.CARNET_BIND == "127.0.0.1:3017";
    fixedDatabase = unit.environment.CARNET_DB_NAME == "etp_carnet" && unit.environment.CARNET_DB_USER == "etp_carnet";
    localPeerWithoutSecret = unit.environment.CARNET_DB_HOST == "/run/postgresql" && unit.environment.CARNET_DB_PASSWORD == "";
    sameOriginAndLedger = unit.environment.CARNET_PUBLIC_URL == "https://vise.mrj.am"
      && unit.environment.CARNET_DELETION_LEDGER == "/var/lib/etp-carnet/deletions.log";
    noAutostartOrAutomaticRestart = unit.wantedBy == [ ] && !unit.restartIfChanged && !unit.stopIfChanged;
    noBootstrapSql = enabled.services.postgresql.ensureDatabases == [ ] && enabled.services.postgresql.ensureUsers == [ ]
      && !(enabled.systemd.services ? vise-provision);
    schemaAndLedgerPreflight = lib.hasInfix "/bin/mrjam-vise-check-adoption" unit.preStart;
    existingSchemaWithoutDdl = unit.environment.CARNET_SCHEMA_MODE == "existing-v1";
    gracefulStopWithoutForcedKill = unit.serviceConfig.TimeoutStopSec == "infinity" && !unit.serviceConfig.SendSIGKILL;
    noBackupOrTimer = !(enabled.systemd.services ? vise-backup) && !(enabled.systemd.timers ? vise-backup);
    noRouteOpened = !enabled.services.nginx.enable
      && builtins.attrNames enabled.services.nginx.virtualHosts == builtins.attrNames baseline.services.nginx.virtualHosts;
    noSsoDependency = unit.requires == [ "postgresql.service" ] && !enabled.services.kanidm.server.enable;
    oldHbaTailUnchanged = lib.hasSuffix baseline.services.postgresql.authentication
      enabled.services.postgresql.authentication;
    peerRuleFirst = lib.hasPrefix ''local "etp_carnet" "etp_carnet" peer'' enabled.services.postgresql.authentication;
    otherDatabasesDenied = lib.hasInfix ''local all "etp_carnet" reject'' enabled.services.postgresql.authentication;
    tcpDenied = lib.hasInfix ''host all "etp_carnet" 0.0.0.0/0 reject'' enabled.services.postgresql.authentication
      && lib.hasInfix ''host all "etp_carnet" ::0/0 reject'' enabled.services.postgresql.authentication;
    privateState = unit.serviceConfig.StateDirectory == "etp-carnet" && unit.serviceConfig.StateDirectoryMode == "0700" && unit.serviceConfig.UMask == "0077";
    boundedResources = unit.serviceConfig.MemoryMax == "512M" && unit.serviceConfig.TasksMax == 128;
    rawApplicationLogsDisabled = unit.serviceConfig.StandardOutput == "null" && unit.serviceConfig.StandardError == "null";
    missingArtifactRejected = !passes (bad { services.mrjamVise.artifactRoot = lib.mkForce null; });
    mutableReleaseRejected = !passes (bad { services.mrjamVise.artifactRoot = lib.mkForce "/var/lib/vise/releases/fake"; });
    hiddenBuildDependencyRejected = !passes (bad { services.mrjamVise.artifactRoot = lib.mkForce (builtins.appendContext store context); });
    missingUidRejected = !passes (bad { services.mrjamVise.adoption.uid = lib.mkForce null; });
    missingGidRejected = !passes (bad { services.mrjamVise.adoption.gid = lib.mkForce null; });
    supplementaryGroupRejected = !passes (bad { users.users.etp_carnet.extraGroups = [ "wheel" ]; });
    missingPostgresRejected = !passes (bad { services.postgresql.enable = lib.mkForce false; });
    overridingHbaRejected = !passes (bad { services.postgresql.authentication = lib.mkForce baselineHba; });
    duplicateApplicationRuleRejected = !passes (bad { services.postgresql.authentication = ''local "etp_carnet" "etp_carnet" trust''; });
    unqualifiedBackupRejected = !passes (bad { services.mrjamVise.backup.enable = true; });
    compatibilityUnchanged = enabled.system.stateVersion == "24.11";
  };
in assert builtins.all (v: v) (builtins.attrValues result); result
