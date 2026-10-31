{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamVisionReplay;
  unit = "mrjam-vision-replay";
  storePath = lib.types.strMatching "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+";
  credentialReference = lib.types.strMatching "/(run/secrets|run/keys|var/lib)/[A-Za-z0-9_./-]+";
  publicConfig = pkgs.writeText "mrjam-vision-replay.json" (builtins.toJSON {
    schema_version = 1;
    vision_database = cfg.visionDatabase;
    journal_database = cfg.journalDatabase;
    keycloak_file = "/run/credentials/${unit}.service/keycloak";
    admissions_file = "/run/credentials/${unit}.service/admissions";
  });
  mappings = {
    visionReplayJournal = { database = cfg.journalDatabase; role = "vision_journal_rejeu"; };
    visionReplayCycle = { database = cfg.visionDatabase; role = "vision_cycle"; };
    visionReplayClosure = { database = cfg.visionDatabase; role = "vision_fermeture"; };
  };
in {
  imports = [ ./mrjam-postgresql-access.nix ];
  options.services.mrjamVisionReplay = {
    enable = lib.mkEnableOption "bounded prebuilt Vision normal replay worker";
    artifactStorePath = lib.mkOption { type = storePath; description = "Exact independently qualified closure containing bin/vision-replay; no build dependency."; };
    visionDatabase = lib.mkOption { type = lib.types.strMatching "[a-z][a-z0-9_]{0,62}"; };
    journalDatabase = lib.mkOption { type = lib.types.strMatching "[a-z][a-z0-9_]{0,62}"; };
    keycloakCredentialFile = lib.mkOption { type = credentialReference; description = "Existing private credential for the fixed historical closure client; IdP compatibility must be established before adoption."; };
    admissionsCredentialFile = lib.mkOption { type = credentialReference; };
    timer.enable = lib.mkEnableOption "periodic normal replay after prerequisite adoption";
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = !(builtins.hasContext cfg.artifactStorePath);
        message = "Vision replay requires a previously built artifact, without a Nix construction context."; }
      { assertion = cfg.visionDatabase != cfg.journalDatabase;
        message = "Vision replay requires separate content and durable erasure-journal databases."; }
      { assertion = config.services.mrjamPostgresqlAccess.enable && lib.all
          (name: config.services.mrjamPostgresqlAccess.workers.${name} == mappings.${name})
          (builtins.attrNames mappings);
        message = "Vision replay requires its three exact dedicated PostgreSQL peer capabilities."; }
      { assertion = lib.all (path: !(lib.hasInfix "/../" path) && !(lib.hasInfix "/./" path)
          && !(lib.hasInfix "//" path) && !(lib.hasSuffix "/" path))
          [ cfg.keycloakCredentialFile cfg.admissionsCredentialFile ];
        message = "Vision replay refuses ambiguous credential references."; }
    ];
    users.groups.${unit} = { };
    users.users.${unit} = {
      isSystemUser = true; group = unit; extraGroups = [ ];
      createHome = false; home = "/var/empty"; hashedPassword = "!";
    };
    services.mrjamPostgresqlAccess = { enable = lib.mkDefault true; workers = mappings; };
    systemd.services.${unit} = {
      description = "MRJ.am Vision normal replay of acknowledged erasure intentions";
      after = [ "postgresql.service" ];
      requires = [ "postgresql.service" ];
      restartIfChanged = false;
      # No restoration verb, schema creation, initialisation or implicit startup.
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${cfg.artifactStorePath}/bin/vision-replay run-once --config ${publicConfig}";
        User = unit; Group = unit;
        LoadCredential = [ "keycloak:${cfg.keycloakCredentialFile}" "admissions:${cfg.admissionsCredentialFile}" ];
        UMask = "0077"; StandardInput = "null"; StandardOutput = "null";
        StandardError = "journal"; # CLI emits a fixed closed code only.
        NoNewPrivileges = true; CapabilityBoundingSet = ""; AmbientCapabilities = "";
        ProtectSystem = "strict"; ProtectHome = true; PrivateTmp = true; PrivateDevices = true;
        PrivateIPC = true; ProtectKernelTunables = true; ProtectKernelModules = true;
        ProtectKernelLogs = true; ProtectControlGroups = true; ProtectProc = "invisible";
        ProcSubset = "pid"; RestrictSUIDSGID = true; RestrictRealtime = true;
        RestrictNamespaces = true; LockPersonality = true; MemoryDenyWriteExecute = true;
        RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" ];
        IPAddressDeny = "any"; IPAddressAllow = "localhost";
        InaccessiblePaths = [ "-/var/lib/forgejo" "-/var/lib/postgresql" "-/var/lib/kanidm"
          "-/var/lib/nextcloud" "-/var/backup" "-/var/backups" "-/var/run/docker.sock" ];
        MemoryAccounting = true; MemoryMax = "256M"; CPUQuota = "20%"; TasksMax = 32;
        TimeoutStartSec = 900; TimeoutStopSec = 30; KillMode = "control-group"; LimitCORE = 0;
      };
    };
    systemd.timers.${unit} = lib.mkIf cfg.timer.enable {
      wantedBy = [ "timers.target" ];
      timerConfig = { OnBootSec = "3m"; OnUnitInactiveSec = "1m"; AccuracySec = "15s"; };
    };
  };
}
