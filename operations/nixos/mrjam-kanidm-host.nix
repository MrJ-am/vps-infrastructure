# Adopt the existing identity database; no provisioning, recovery or rename.
{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamKanidmHost;
  locked = import ../forgejo/locked-toolchain.nix { system = pkgs.stdenv.hostPlatform.system; };
  package = locked.kanidm_1_11.override { enableSecretProvisioning = false; };
  immutable = value: value != null && !builtins.hasContext value
    && builtins.match "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+" value != null;
  root = if cfg.artifactStorePath == null then "/INVALID" else cfg.artifactStorePath;
  settings = {
    version = "2";
    domain = "log.mrj.am"; origin = "https://log.mrj.am";
    bindaddress = "127.0.0.1:8443";
    db_path = "/var/lib/kanidm/kanidm.db";
    tls_chain = "/run/credentials/kanidm.service/tls-chain";
    tls_key = "/run/credentials/kanidm.service/tls-key";
    adminbindpath = "/run/kanidmd/admin.sock";
    # Explicitly disabled until the production backup mechanism is qualified.
    # `versions = 0` does not disable scheduling in Kanidm 1.11.2.
    online_backup = { enabled = false; path = "/var/lib/kanidm/backups";
      schedule = "00 22 * * *"; versions = 7; compression = "gzip"; };
    log_level = "info";
  };
  toml = (pkgs.formats.toml { }).generate "mrjam-kanidm-server.toml" settings;
in {
  options.services.mrjamKanidmHost = {
    enable = lib.mkEnableOption "adoption of the existing Kanidm 1.11.2 state";
    startAtBoot = lib.mkEnableOption "start of the adopted identity service at boot";
    artifactStorePath = lib.mkOption { type = lib.types.nullOr lib.types.str; default = null; };
    uid = lib.mkOption { type = lib.types.nullOr lib.types.ints.positive; default = null; };
    gid = lib.mkOption { type = lib.types.nullOr lib.types.ints.positive; default = null; };
    settings = lib.mkOption { type = lib.types.attrs; readOnly = true; default = settings; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = immutable cfg.artifactStorePath && cfg.artifactStorePath == builtins.unsafeDiscardStringContext "${package}";
        message = "mrjamKanidmHost: requires the exact locked Kanidm 1.11.2 artifact."; }
      { assertion = cfg.uid != null && cfg.gid != null;
        message = "mrjamKanidmHost: existing UID/GID are required for adoption."; }
      { assertion = !config.services.kanidm.server.enable && !config.services.kanidm.provision.enable
          && !config.services.kanidm.unix.enable && !config.services.kanidm.client.enable;
        message = "mrjamKanidmHost: upstream rename/provisioning and Unix/client integration must remain disabled."; }
      { assertion = config.users.users.kanidm.extraGroups == [ ];
        message = "mrjamKanidmHost: no supplementary groups are allowed."; }
    ];
    users.groups.kanidm.gid = cfg.gid;
    users.users.kanidm = { isSystemUser = true; uid = cfg.uid; group = "kanidm";
      home = "/var/lib/kanidm"; createHome = false; hashedPassword = "!"; extraGroups = [ ]; };
    environment.etc."kanidm/server.toml".source = toml;
    systemd.services.kanidm = {
      description = "MRJ.am Kanidm — existing database and identity";
      after = [ "network.target" ];
      wantedBy = lib.optional cfg.startAtBoot "multi-user.target";
      restartIfChanged = false; stopIfChanged = false;
      # Never bootstrap an empty directory or invoke `domain rename` at restart.
      preStart = ''
        test -s /var/lib/kanidm/kanidm.db
        test ! -L /var/lib/kanidm/kanidm.db
      '';
      serviceConfig = {
        ExecStart = "${root}/bin/kanidmd server -c ${toml}";
        User = "kanidm"; Group = "kanidm";
        StateDirectory = "kanidm"; StateDirectoryMode = "0700";
        RuntimeDirectory = "kanidmd"; RuntimeDirectoryMode = "0700";
        LoadCredential = [ "tls-chain:/var/lib/acme/log.mrj.am/fullchain.pem" "tls-key:/var/lib/acme/log.mrj.am/key.pem" ];
        UMask = "0077"; NoNewPrivileges = true; PrivateTmp = true; PrivateDevices = true;
        ProtectSystem = "strict"; ProtectHome = true;
        ReadWritePaths = [ "/var/lib/kanidm" ];
        CapabilityBoundingSet = [ ]; AmbientCapabilities = [ ];
        RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
        ProtectKernelTunables = true; ProtectKernelModules = true; ProtectControlGroups = true;
        RestrictSUIDSGID = true; LockPersonality = true;
        Restart = "on-failure"; RestartSec = 5; TimeoutStartSec = 120;
        MemoryMax = "768M"; TasksMax = 128;
        StandardOutput = "null"; StandardError = "null";
      };
    };
  };
}
