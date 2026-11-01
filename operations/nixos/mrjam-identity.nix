# Native session broker; adopts the existing SQLite state without bootstrap.
{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamIdentity;
  root = if cfg.artifactStorePath == null then "/INVALID" else cfg.artifactStorePath;
  state = "/var/lib/mrjam-metier/log/sessions.sqlite";
  projection = "/run/mrjam-identity/aliases.sqlite";
  runtime = pkgs.writeText "mrjam-identity-runtime.json" (builtins.toJSON ({
    schema_version = 1;
    listen = "127.0.0.1:3002";
    state_database = state;
    kanidm_endpoint = "127.0.0.1:8443";
    kanidm_ca_file = "/etc/ssl/certs/ca-certificates.crt";
    clients = map (host: { inherit host; client_id = "mrjam-vision";
      secret_file = "/run/credentials/mrjam-identity.service/kanidm-vision";
    }) [ "vision.mrj.am" "audition.mrj.am" ];
    principal_database = { host = "/run/postgresql"; port = 5432;
      database = "vision"; user = "vision_identite"; };
  } // lib.optionalAttrs (cfg.principalRegistration != null) {
    principal_registration = cfg.principalRegistration // {
      socket = "/run/mrjam-identity/admission.sock";
    };
  }));
  hba = ''
    local vision vision_identite peer map=mrjam_native_identity
    local all vision_identite reject
    host all vision_identite 0.0.0.0/0 reject
    host all vision_identite ::0/0 reject
  '';
  identityMap = "mrjam_native_identity mrjam-metier vision_identite";
  sandbox = {
    User = "mrjam-metier"; Group = "mrjam-log-readers";
    UMask = "0077"; NoNewPrivileges = true;
    ProtectSystem = "strict"; ProtectHome = true; PrivateTmp = true;
    PrivateDevices = true; ProtectProc = "invisible"; ProcSubset = "pid";
    ProtectKernelTunables = true; ProtectKernelModules = true;
    ProtectKernelLogs = true; ProtectControlGroups = true; ProtectClock = true;
    RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" ];
    IPAddressDeny = "any"; IPAddressAllow = "localhost";
    RestrictNamespaces = true; RestrictRealtime = true; RestrictSUIDSGID = true;
    LockPersonality = true; MemoryDenyWriteExecute = true;
    CapabilityBoundingSet = ""; AmbientCapabilities = "";
    ReadWritePaths = [ "/var/lib/mrjam-metier/log" "/run/mrjam-identity" ];
    InaccessiblePaths = [ "-/var/lib/forgejo" "-/var/lib/kanidm" "-/var/lib/nextcloud"
      "-/var/lib/postgresql" "-/var/lib/mrjam-metier/courriel"
      "-/var/lib/mrjam-metier/secrets" "-/var/backup" "-/var/backups"
      "-/run/nix" "-/run/docker.sock" ];
    TasksMax = 64; MemoryMax = "256M"; CPUQuota = "50%";
    StandardOutput = "null"; StandardError = "null";
  };
in {
  imports = [ ./mrjam-postgresql-policy.nix ];
  options.services.mrjamIdentity = {
    enable = lib.mkEnableOption "native Kanidm session broker using retained state";
    startAtBoot = lib.mkEnableOption "explicit promotion of the native identity service";
    artifactStorePath = lib.mkOption { type = lib.types.nullOr lib.types.str; default = null; };
    uid = lib.mkOption { type = lib.types.nullOr lib.types.ints.positive; default = null; };
    gid = lib.mkOption { type = lib.types.nullOr lib.types.ints.positive; default = null; };
    readersGid = lib.mkOption { type = lib.types.nullOr lib.types.ints.positive; default = null; };
    credentialFile = lib.mkOption { type = lib.types.str;
      default = "/var/lib/mrjam-identite/kanidm-vision.secret"; };
    principalRegistration = lib.mkOption {
      type = lib.types.nullOr (lib.types.submodule { options = {
        uid = lib.mkOption { type = lib.types.ints.positive; };
        gid = lib.mkOption { type = lib.types.ints.positive; };
      }; });
      default = null;
      description = "Exact native admission peer; insertion/idempotent replay only, no session access.";
    };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = cfg.artifactStorePath != null && !builtins.hasContext cfg.artifactStorePath
          && builtins.match "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+" root != null;
        message = "mrjamIdentity: independently qualified prebuilt native broker required."; }
      { assertion = cfg.uid != null && cfg.gid != null && cfg.readersGid != null
          && cfg.readersGid != cfg.gid;
        message = "mrjamIdentity: retained state identity and separate alias-reader group must be bound explicitly."; }
      { assertion = cfg.credentialFile == "/var/lib/mrjam-identite/kanidm-vision.secret";
        message = "mrjamIdentity: preserve the reviewed native client credential reference."; }
      { assertion = config.services.postgresql.enable && config.services.mrjamKanidmHost.enable;
        message = "mrjamIdentity: requires the adopted PostgreSQL and Kanidm services."; }
      { assertion = cfg.principalRegistration == null || (
          cfg.principalRegistration.uid != cfg.uid && cfg.principalRegistration.gid != cfg.readersGid
          && (config.users.users.mrjam-vision-admission.uid or null) == cfg.principalRegistration.uid
          && (config.users.groups.mrjam-vision-admission.gid or null) == cfg.principalRegistration.gid);
        message = "mrjamIdentity: registration must bind the dedicated declared admission identity."; }
      { assertion = config.services.mrjamPostgresqlPolicy.blocks.identity == hba;
        message = "mrjamIdentity: peer authentication must remain limited to the identity role."; }
      { assertion = builtins.filter (line: lib.hasPrefix "mrjam_native_identity " line)
          (lib.splitString "\n" config.services.postgresql.identMap) == [ identityMap ];
        message = "mrjamIdentity: no additional peer identity may use the reserved SQL map."; }
    ];
    system.extraDependencies = [ (builtins.storePath root) ];
    users.groups.mrjam-metier.gid = cfg.gid;
    users.groups.mrjam-log-readers.gid = cfg.readersGid;
    users.users.mrjam-metier = { uid = cfg.uid; group = "mrjam-metier";
      isSystemUser = true; createHome = false; hashedPassword = "!"; };
    services.mrjamPostgresqlPolicy.blocks.identity = hba;
    services.postgresql.identMap = lib.mkBefore (identityMap + "\n");
    systemd.services.mrjam-identity = {
      description = "MRJ.am native browser and MCP identity";
      wantedBy = lib.optional cfg.startAtBoot "multi-user.target";
      requires = [ "postgresql.service" "kanidm.service" ];
      after = [ "postgresql.service" "kanidm.service" ];
      restartIfChanged = false; stopIfChanged = false;
      unitConfig.AssertPathExists = state;
      serviceConfig = sandbox // {
        Type = "simple";
        ExecStart = "${root}/bin/mrjam-identity serve --config ${runtime}";
        LoadCredential = [ "kanidm-vision:${cfg.credentialFile}" ];
        SupplementaryGroups = lib.optional (cfg.principalRegistration != null) "mrjam-vision-admission";
        RuntimeDirectory = "mrjam-identity";
        # Admission can traverse to its 0660 socket without reading the 0640
        # aliases owned by the separate reader group, or listing this directory.
        RuntimeDirectoryMode = if cfg.principalRegistration == null then "2750" else "2751";
        RuntimeDirectoryPreserve = true;
        Restart = "on-failure"; RestartSec = 3;
        SocketBindDeny = "any"; SocketBindAllow = "ipv4:tcp:3002";
      };
    };
    systemd.services.mrjam-identity-aliases = {
      description = "Publish only subject/mail aliases for the Log frontend";
      wantedBy = lib.optional cfg.startAtBoot "multi-user.target";
      requires = [ "mrjam-identity.service" ]; after = [ "mrjam-identity.service" ];
      before = [ "mrjam-rust-blue.service" "mrjam-rust-green.service" ];
      restartIfChanged = false; stopIfChanged = false;
      serviceConfig = sandbox // {
        Type = "oneshot";
        ExecStart = "${root}/bin/mrjam-identity project-aliases --source ${state} --destination ${projection}";
        ReadWritePaths = [ "/run/mrjam-identity" ];
        ReadOnlyPaths = [ "/var/lib/mrjam-metier/log" ];
        RestrictAddressFamilies = [ "AF_UNIX" ];
        PrivateNetwork = true; TimeoutStartSec = 30;
      };
    };
    systemd.timers.mrjam-identity-aliases = {
      wantedBy = lib.optional cfg.startAtBoot "timers.target";
      timerConfig = { OnBootSec = "10s"; OnUnitActiveSec = "30s";
        AccuracySec = "1s"; Unit = "mrjam-identity-aliases.service"; };
    };
  };
}
