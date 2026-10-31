{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamVisionCycle;
  unitName = "mrjam-vision-cycle";
  storePath = lib.types.strMatching "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+";
  credentialReference = lib.types.strMatching "/(run/secrets|run/keys|var/lib)/[A-Za-z0-9_./-]+";
  publicConfig = name: pkgs.writeText "${name}.json" (builtins.toJSON {
    schema_version = 1;
    vision_database = cfg.visionDatabase;
    journal_database = cfg.journalDatabase;
    state_file = "/var/lib/${unitName}/courriels.sqlite";
    smtp_file = "/run/credentials/${name}.service/smtp";
    keycloak_file = "/run/credentials/${name}.service/keycloak";
  });
  mappings = {
    visionCycle = { database = cfg.visionDatabase; role = "vision_cycle"; };
    visionCycleJournal = { database = cfg.journalDatabase; role = "vision_journal_writer"; };
  };
  unit = initialize: let name = unitName + lib.optionalString initialize "-initialize"; in {
    description = "MRJ.am Vision notice cycle ${if initialize then "explicit state initialization" else "bounded pass"}";
    restartIfChanged = false;
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${cfg.artifactStorePath}/bin/vision-cycle ${if initialize then "initialize-state" else "run-once"} --config ${publicConfig name}";
      User = unitName; Group = unitName;
      StateDirectory = unitName; StateDirectoryMode = "0700";
      LoadCredential = [ "smtp:${cfg.smtpCredentialFile}" ]
        ++ lib.optional (!initialize) "keycloak:${cfg.keycloakCredentialFile}";
      UMask = "0077"; StandardInput = "null"; StandardOutput = "null";
      StandardError = "journal"; # Only a fixed closed CLI error code.
      NoNewPrivileges = true; CapabilityBoundingSet = ""; AmbientCapabilities = "";
      ProtectSystem = "strict"; ProtectHome = true; PrivateTmp = true; PrivateDevices = true;
      PrivateIPC = true; ProtectKernelTunables = true; ProtectKernelModules = true;
      ProtectKernelLogs = true; ProtectControlGroups = true; ProtectProc = "invisible";
      ProcSubset = "pid"; RestrictSUIDSGID = true; RestrictRealtime = true;
      RestrictNamespaces = true; LockPersonality = true; MemoryDenyWriteExecute = true;
      RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
      InaccessiblePaths = [ "-/var/lib/forgejo" "-/var/lib/postgresql" "-/var/lib/kanidm"
        "-/var/lib/nextcloud" "-/var/backup" "-/var/backups" "-/var/run/docker.sock" ];
      MemoryAccounting = true; MemoryMax = "256M"; CPUQuota = "20%"; TasksMax = 32;
      TimeoutStartSec = 900; TimeoutStopSec = 30; KillMode = "control-group"; LimitCORE = 0;
    };
  };
in {
  imports = [ ./mrjam-postgresql-access.nix ];
  options.services.mrjamVisionCycle = {
    enable = lib.mkEnableOption "prebuilt bounded notice and deferred erasure worker";
    artifactStorePath = lib.mkOption { type = storePath; description = "Exact independently qualified prebuilt closure containing bin/vision-cycle."; };
    visionDatabase = lib.mkOption { type = lib.types.strMatching "[a-z][a-z0-9_]{0,62}"; };
    journalDatabase = lib.mkOption { type = lib.types.strMatching "[a-z][a-z0-9_]{0,62}"; };
    smtpCredentialFile = lib.mkOption { type = credentialReference; };
    keycloakCredentialFile = lib.mkOption { type = credentialReference; };
    timer.enable = lib.mkEnableOption "periodic notice cycle after explicit adoption";
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = !(builtins.hasContext cfg.artifactStorePath);
        message = "Vision cycle requires a previously built artifact, without a Nix construction context."; }
      { assertion = cfg.visionDatabase != cfg.journalDatabase;
        message = "Vision cycle requires separate content and durable erasure-journal databases."; }
      { assertion = config.services.mrjamPostgresqlAccess.enable && lib.all
          (name: config.services.mrjamPostgresqlAccess.workers.${name} == mappings.${name})
          (builtins.attrNames mappings);
        message = "Vision cycle requires its exact dedicated PostgreSQL peer capabilities."; }
      { assertion = lib.all (path: lib.all (part: part != "." && part != "..") (lib.splitString "/" path)
          && !(lib.hasInfix "//" path) && !(lib.hasSuffix "/" path))
          [ cfg.smtpCredentialFile cfg.keycloakCredentialFile ];
        message = "Vision cycle refuses ambiguous credential references."; }
    ];
    users.groups.${unitName} = { };
    users.users.${unitName} = {
      isSystemUser = true; group = unitName; extraGroups = [ ];
      createHome = false; home = "/var/empty"; hashedPassword = "!";
    };
    services.mrjamPostgresqlAccess = { enable = lib.mkDefault true; workers = mappings; };
    systemd.services.${unitName} = (unit false) // {
      after = [ "postgresql.service" "network.target" ]; requires = [ "postgresql.service" ];
    };
    systemd.services."${unitName}-initialize" = (unit true) // { conflicts = [ "${unitName}.service" ]; };
    systemd.timers.${unitName} = lib.mkIf cfg.timer.enable {
      wantedBy = [ "timers.target" ];
      timerConfig = { OnBootSec = "4m"; OnUnitInactiveSec = "1m"; AccuracySec = "15s"; };
    };
  };
}
