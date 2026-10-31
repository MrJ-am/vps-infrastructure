{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamVisionArchive;
  storePath = lib.types.strMatching "/nix/store/[a-z0-9]{32}-[A-Za-z0-9+._?=-]+";
  credentialReference = lib.types.strMatching "/(var/lib|run)/[A-Za-z0-9_./-]+";
  publicConfig = unit: pkgs.writeText "mrjam-vision-archive-${unit}.json" (builtins.toJSON {
    schema_version = 1;
    journal_database = cfg.journalDatabase;
    state_file = "/var/lib/mrjam-vision-archive/courriels.sqlite";
    smtp_file = "/run/credentials/${unit}.service/smtp";
    recipient_file = "/run/credentials/${unit}.service/recipient";
    age_program = "${pkgs.age}/bin/age";
    age_recipient = cfg.ageRecipient;
  });
  unit = name: command: {
    description = "MRJ.am Vision archive ${command}";
    restartIfChanged = false;
    # Initialisation is never implicit and neither unit starts on module import.
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${cfg.artifactStorePath}/bin/vision-archive ${command} --config ${publicConfig name}";
      User = "mrjam-vision-archive";
      Group = "mrjam-vision-archive";
      StateDirectory = "mrjam-vision-archive";
      StateDirectoryMode = "0700";
      LoadCredential = [ "smtp:${cfg.smtpCredentialFile}" "recipient:${cfg.recipientCredentialFile}" ];
      UMask = "0077";
      StandardInput = "null";
      StandardOutput = "null";
      StandardError = "journal"; # The CLI emits only a closed fixed error code.
      NoNewPrivileges = true;
      CapabilityBoundingSet = "";
      AmbientCapabilities = "";
      ProtectSystem = "strict";
      ProtectHome = true;
      PrivateTmp = true;
      PrivateDevices = true;
      ProtectKernelTunables = true;
      ProtectKernelModules = true;
      ProtectKernelLogs = true;
      ProtectControlGroups = true;
      RestrictSUIDSGID = true;
      RestrictRealtime = true;
      LockPersonality = true;
      RestrictNamespaces = true;
      RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
      InaccessiblePaths = [ "-/var/lib/forgejo" "-/var/lib/postgresql" "-/var/lib/kanidm"
        "-/var/lib/nextcloud" "-/var/backup" "-/var/backups" "-/var/run/docker.sock" ];
      MemoryMax = "256M";
      CPUQuota = "20%";
      TasksMax = 32;
      RuntimeMaxSec = 900;
      TimeoutStartSec = 905;
      TimeoutStopSec = 30;
      KillMode = "control-group";
      LimitCORE = 0;
    };
  };
in {
  imports = [ ./mrjam-postgresql-access.nix ];
  options.services.mrjamVisionArchive = {
    enable = lib.mkEnableOption "prebuilt Vision archive worker";
    artifactStorePath = lib.mkOption { type = storePath; description = "Exact prebuilt independently qualified closure with bin/vision-archive."; };
    journalDatabase = lib.mkOption { type = lib.types.strMatching "[a-z][a-z0-9_]{0,62}"; };
    ageRecipient = lib.mkOption { type = lib.types.strMatching "age1[a-z0-9]{58}"; description = "Public age recipient only; private restoration key stays outside the store and Cloud."; };
    smtpCredentialFile = lib.mkOption { type = credentialReference; };
    recipientCredentialFile = lib.mkOption { type = credentialReference; };
    timer.enable = lib.mkEnableOption "periodic archive processing after explicit state adoption";
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = config.services.mrjamPostgresqlAccess.enable
          && config.services.mrjamPostgresqlAccess.workers.visionArchive == {
            database = cfg.journalDatabase; role = "vision_journal_archiviste";
          };
        message = "Vision archive requires its exact dedicated PostgreSQL peer mapping."; }
      { assertion = builtins.all (path: !(lib.hasInfix "/../" path) && !(lib.hasInfix "/./" path)
          && !(lib.hasInfix "//" path) && !(lib.hasSuffix "/" path)) [ cfg.smtpCredentialFile cfg.recipientCredentialFile ];
        message = "Vision archive refuses ambiguous credential references."; }
    ];
    users.groups.mrjam-vision-archive = { };
    users.users.mrjam-vision-archive = {
      isSystemUser = true;
      group = "mrjam-vision-archive";
      extraGroups = [ ];
      createHome = false;
      home = "/var/empty";
      hashedPassword = "!";
    };
    services.mrjamPostgresqlAccess = {
      enable = lib.mkDefault true;
      workers.visionArchive = { database = cfg.journalDatabase; role = "vision_journal_archiviste"; };
    };
    systemd.services.mrjam-vision-archive = (unit "mrjam-vision-archive" "run-once") // {
      after = [ "postgresql.service" "network.target" ];
      requires = [ "postgresql.service" ];
    };
    systemd.services.mrjam-vision-archive-initialize = (unit "mrjam-vision-archive-initialize" "initialize-state") // {
      conflicts = [ "mrjam-vision-archive.service" ];
    };
    systemd.timers.mrjam-vision-archive = lib.mkIf cfg.timer.enable {
      wantedBy = [ "timers.target" ];
      timerConfig = { OnBootSec = "2m"; OnUnitInactiveSec = "1m"; AccuracySec = "15s"; };
    };
  };
}
