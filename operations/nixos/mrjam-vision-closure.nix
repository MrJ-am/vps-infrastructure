{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamVisionClosure;
  unit = "mrjam-vision-closure";
  storePath = lib.types.strMatching "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+";
  credentialReference = lib.types.strMatching "/(run/secrets|run/keys|var/lib)/[A-Za-z0-9_./-]+";
  publicConfig = pkgs.writeText "${unit}.json" (builtins.toJSON {
    schema_version = 1;
    vision_database = cfg.visionDatabase; journal_database = cfg.journalDatabase;
    admissions_file = "/run/credentials/${unit}.service/admissions";
  });
  mappings = {
    visionClosure = { database = cfg.visionDatabase; role = "vision_fermeture"; };
    visionClosureJournal = { database = cfg.journalDatabase; role = "vision_journal_fermeture"; };
  };
in {
  imports = [ ./mrjam-postgresql-access.nix ];
  options.services.mrjamVisionClosure = {
    enable = lib.mkEnableOption "prebuilt private common-identity closure hook";
    artifactStorePath = lib.mkOption { type = storePath; description = "Exact prebuilt independently qualified closure containing bin/vision-closure."; };
    visionDatabase = lib.mkOption { type = lib.types.strMatching "[a-z][a-z0-9_]{0,62}"; };
    journalDatabase = lib.mkOption { type = lib.types.strMatching "[a-z][a-z0-9_]{0,62}"; };
    admissionsCredentialFile = lib.mkOption { type = credentialReference; description = "Existing credential shared by the native closure hook and fixed admissions purge protocol."; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = !(builtins.hasContext cfg.artifactStorePath);
        message = "Vision closure requires a previously built artifact without construction context."; }
      { assertion = cfg.visionDatabase != cfg.journalDatabase;
        message = "Vision closure requires separate content and durable erasure-journal databases."; }
      { assertion = config.services.mrjamPostgresqlAccess.enable && lib.all
          (name: config.services.mrjamPostgresqlAccess.workers.${name} == mappings.${name})
          (builtins.attrNames mappings);
        message = "Vision closure requires its exact two peer mappings."; }
      { assertion = lib.all (part: part != "." && part != "..") (lib.splitString "/" cfg.admissionsCredentialFile)
          && !(lib.hasInfix "//" cfg.admissionsCredentialFile) && !(lib.hasSuffix "/" cfg.admissionsCredentialFile);
        message = "Vision closure refuses ambiguous credential references."; }
    ];
    users.groups.${unit} = { };
    users.users.${unit} = {
      isSystemUser = true; group = unit; extraGroups = [ ];
      createHome = false; home = "/var/empty"; hashedPassword = "!";
    };
    services.mrjamPostgresqlAccess = { enable = lib.mkDefault true; workers = mappings; };
    systemd.services.${unit} = {
      description = "MRJ.am Vision private common-identity closure hook";
      after = [ "postgresql.service" ]; requires = [ "postgresql.service" ];
      restartIfChanged = false;
      # No automatic start, schema or state creation, routing or IdP hook adoption.
      serviceConfig = {
        Type = "exec";
        ExecStartPre = "${cfg.artifactStorePath}/bin/vision-closure check-local --config ${publicConfig}";
        ExecStart = "${cfg.artifactStorePath}/bin/vision-closure serve --config ${publicConfig}";
        User = unit; Group = unit;
        LoadCredential = [ "admissions:${cfg.admissionsCredentialFile}" ];
        UMask = "0077"; StandardInput = "null"; StandardOutput = "null";
        StandardError = "journal"; # CLI emits fixed closed errors only.
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
        TimeoutStartSec = 60; TimeoutStopSec = 30; KillMode = "control-group"; LimitCORE = 0;
        Restart = "no";
      };
    };
  };
}
