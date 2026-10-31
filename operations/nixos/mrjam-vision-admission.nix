{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamVisionAdmission;
  unitName = "mrjam-vision-admission";
  storePath = lib.types.strMatching "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+";
  credentialReference = lib.types.strMatching "/(run/secrets|run/keys|var/lib)/[A-Za-z0-9_./-]+";
  publicConfig = name: pkgs.writeText "${name}.json" (builtins.toJSON {
    schema_version = 1; vision_database = cfg.visionDatabase; admissions_open = cfg.admissionsOpen;
    state_file = "/var/lib/${unitName}/admissions.sqlite";
    smtp_file = "/run/credentials/${name}.service/smtp";
    keycloak_file = "/run/credentials/${name}.service/keycloak";
    closure_file = "/run/credentials/${name}.service/closure";
    approval_file = "/run/credentials/${name}.service/approval";
  });
  mappings = {
    visionAdmission = { database = cfg.visionDatabase; role = "vision_admission"; };
    visionAdmissionAdministration = { database = cfg.visionDatabase; role = "vision_administration"; };
  };
  references = [ cfg.smtpCredentialFile cfg.keycloakCredentialFile cfg.closureCredentialFile cfg.approvalCredentialFile ];
  unit = initialize: let name = unitName + lib.optionalString initialize "-initialize";
    command = "${cfg.artifactStorePath}/bin/vision-admission";
    args = "--config ${publicConfig name}";
  in {
    description = "MRJ.am Vision ${if initialize then "explicit admission state initialization" else "private durable admissions"}";
    restartIfChanged = false;
    serviceConfig = {
      Type = if initialize then "oneshot" else "exec";
      ExecStart = "${command} ${if initialize then "initialize-state" else "serve"} ${args}";
      Restart = "no";
      User = unitName; Group = unitName;
      StateDirectory = unitName; StateDirectoryMode = "0700";
      LoadCredential = [ "smtp:${cfg.smtpCredentialFile}" ] ++ lib.optionals (!initialize) [
        "keycloak:${cfg.keycloakCredentialFile}" "closure:${cfg.closureCredentialFile}"
        "approval:${cfg.approvalCredentialFile}" ];
      UMask = "0077"; StandardInput = "null"; StandardOutput = "null"; StandardError = "journal";
      NoNewPrivileges = true; CapabilityBoundingSet = ""; AmbientCapabilities = "";
      ProtectSystem = "strict"; ProtectHome = true; PrivateTmp = true; PrivateDevices = true;
      PrivateIPC = true; ProtectKernelTunables = true; ProtectKernelModules = true;
      ProtectKernelLogs = true; ProtectControlGroups = true; ProtectProc = "invisible";
      ProcSubset = "pid"; RestrictSUIDSGID = true; RestrictRealtime = true;
      RestrictNamespaces = true; LockPersonality = true; MemoryDenyWriteExecute = true;
      RestrictAddressFamilies = if initialize then [ "AF_UNIX" ] else [ "AF_UNIX" "AF_INET" "AF_INET6" ];
      # Normal SMTP needs outbound TLS. This is not a destination/domain ACL.
      InaccessiblePaths = [ "-/var/lib/forgejo" "-/var/lib/postgresql" "-/var/lib/kanidm"
        "-/var/lib/nextcloud" "-/var/backup" "-/var/backups" "-/var/run/docker.sock" ];
      MemoryAccounting = true; MemoryMax = "256M"; CPUQuota = "20%"; TasksMax = 32;
      TimeoutStartSec = if initialize then 90 else 60;
      TimeoutStopSec = 30; KillMode = "control-group"; LimitCORE = 0;
    } // (if initialize then { PrivateNetwork = true; IPAddressDeny = "any"; }
      else { ExecStartPre = "${command} check-local ${args}"; });
  };
in {
  imports = [ ./mrjam-postgresql-access.nix ];
  options.services.mrjamVisionAdmission = {
    enable = lib.mkEnableOption "prebuilt private durable admission service";
    artifactStorePath = lib.mkOption { type = storePath; description = "Exact separately qualified prebuilt closure with bin/vision-admission."; };
    visionDatabase = lib.mkOption { type = lib.types.strMatching "[a-z][a-z0-9_]{0,62}"; };
    admissionsOpen = lib.mkEnableOption "public admission handlers and periodic processing after explicit adoption";
    smtpCredentialFile = lib.mkOption { type = credentialReference; };
    keycloakCredentialFile = lib.mkOption { type = credentialReference; };
    closureCredentialFile = lib.mkOption { type = credentialReference; };
    approvalCredentialFile = lib.mkOption { type = credentialReference; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = !(builtins.hasContext cfg.artifactStorePath);
        message = "Vision admission requires a previously built artifact without construction context."; }
      { assertion = config.services.mrjamPostgresqlAccess.enable && lib.all
          (name: config.services.mrjamPostgresqlAccess.workers.${name} == mappings.${name})
          (builtins.attrNames mappings);
        message = "Vision admission requires its exact dedicated PostgreSQL peer mappings."; }
      { assertion = lib.all (path: lib.all (part: part != "." && part != "..") (lib.splitString "/" path)
          && !(lib.hasInfix "//" path) && !(lib.hasSuffix "/" path)) references
          && builtins.length (lib.unique references) == 4;
        message = "Vision admission requires unambiguous, separate credential references."; }
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
  };
}
