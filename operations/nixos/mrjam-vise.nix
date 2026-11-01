# ViSe remains independent: no monolith, SSO, common theme or shared identities.
# Installs a staged unit only; no automatic start, SQL or backup operation.
{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamVise;
  locked = import ../forgejo/locked-toolchain.nix { system = pkgs.stdenv.hostPlatform.system; };
  adoptionCheck = locked.callPackage ../vise/adoption-check.nix { };
  storeRoot = value: value != null && !builtins.hasContext value &&
    builtins.match "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+" value != null;
  hba = ''
    local "etp_carnet" "etp_carnet" peer
    local all "etp_carnet" reject
    host all "etp_carnet" 0.0.0.0/0 reject
    host all "etp_carnet" ::0/0 reject
  '';
  effective = builtins.filter (line: lib.hasInfix "\"etp_carnet\"" line)
    (lib.splitString "\n" config.services.postgresql.authentication);
  expected = builtins.filter (line: line != "") (lib.splitString "\n" hba);
in {
  imports = [ ./mrjam-postgresql-policy.nix ];
  options.services.mrjamVise = {
    enable = lib.mkEnableOption "staged adoption of the independent ViSe service";
    artifactRoot = lib.mkOption {
      type = lib.types.nullOr lib.types.str; default = null;
      description = "Exact prequalified store output containing server and dist; no build dependency or mutable release path.";
    };
    adoption = {
      uid = lib.mkOption { type = lib.types.nullOr lib.types.ints.positive; default = null; };
      gid = lib.mkOption { type = lib.types.nullOr lib.types.ints.positive; default = null; };
    };
    backup.enable = lib.mkEnableOption "future coherent, restore-qualified ViSe backup (blocked)";
  };
  config = lib.mkMerge [
    { assertions = [{ assertion = !cfg.backup.enable;
        message = "mrjamVise: backup activation blocked until coherent database/deletion-ledger capture and restore are qualified; the received sequential dump/copy is not a coherence proof."; }]; }
    (lib.mkIf cfg.enable {
      assertions = [
        { assertion = storeRoot cfg.artifactRoot;
          message = "mrjamVise: an exact prequalified store root without derivation context is required."; }
        { assertion = cfg.adoption.uid != null && cfg.adoption.gid != null;
          message = "mrjamVise: existing UID/GID must be established before adopting etp_carnet."; }
        { assertion = config.services.postgresql.enable && lib.versions.major config.services.postgresql.package.version == "17";
          message = "mrjamVise: requires the separately configured shared PostgreSQL 17 instance; it never selects or starts a second database."; }
        { assertion = config.services.mrjamPostgresqlPolicy.blocks.vise == hba
            && lib.sort builtins.lessThan effective == lib.sort builtins.lessThan expected;
          message = "mrjamVise: dedicated peer and rejection rules must remain exact, without a conflicting ViSe rule."; }
        { assertion = config.users.users.etp_carnet.extraGroups == [ ];
          message = "mrjamVise: the existing application identity must not acquire supplementary groups."; }
      ];
      users.groups.etp_carnet.gid = cfg.adoption.gid;
      users.users.etp_carnet = {
        isSystemUser = true; uid = cfg.adoption.uid; group = "etp_carnet";
        createHome = false; extraGroups = [ ]; hashedPassword = "!";
      };
      services.mrjamPostgresqlPolicy.blocks.vise = hba;
      systemd.services.vise = {
        description = "ViSe — independent encrypted ETP notebook (staged)";
        after = [ "postgresql.service" ]; requires = [ "postgresql.service" ];
        wantedBy = [ ]; restartIfChanged = false; stopIfChanged = false;
        # The qualified adoption binary accepts an existing schema without DDL.
        # Require that schema and its restricted runtime role, and never create
        # a missing deletion ledger during adoption of persistent state.
        preStart = ''
          ${adoptionCheck}/bin/mrjam-vise-check-adoption
        '';
        environment = {
          CARNET_BIND = "127.0.0.1:3017";
          CARNET_DIST = "${if cfg.artifactRoot == null then "/INVALID" else cfg.artifactRoot}/dist";
          CARNET_DB_HOST = "/run/postgresql";
          CARNET_DB_NAME = "etp_carnet"; CARNET_DB_USER = "etp_carnet";
          CARNET_DB_PASSWORD = "";
          CARNET_SCHEMA_MODE = "existing-v1";
          CARNET_PUBLIC_URL = "https://vise.mrj.am"; CARNET_SECURE_COOKIE = "true";
          CARNET_DELETION_LEDGER = "/var/lib/etp-carnet/deletions.log";
        };
        serviceConfig = {
          ExecStart = "${if cfg.artifactRoot == null then "/INVALID" else cfg.artifactRoot}/server";
          User = "etp_carnet"; Group = "etp_carnet";
          StateDirectory = "etp-carnet"; StateDirectoryMode = "0700";
          UMask = "0077"; NoNewPrivileges = true; PrivateTmp = true;
          ProtectSystem = "strict"; ProtectHome = true;
          RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
          CapabilityBoundingSet = [ ]; AmbientCapabilities = [ ];
          Restart = "on-failure"; MemoryMax = "512M"; TasksMax = 128;
          TimeoutStopSec = "infinity"; SendSIGKILL = false;
          StandardOutput = "null"; StandardError = "null";
        };
      };
    })
  ];
}
