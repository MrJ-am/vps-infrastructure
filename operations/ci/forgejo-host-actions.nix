# Separate post-cutover variant: bounded Actions is disabled by default.
# The first-cutover source module remains immutable.
# Runnable adoption module. No upstream secret bootstrap, SQL migration or SSO
# account creation is attached to installation or service restart.
{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamForgejoHost;
  preparation = config.services.mrjamForgejo.preparation;
  locked = import ../forgejo/locked-toolchain.nix { system = pkgs.stdenv.hostPlatform.system; };
  schemaCheck = locked.callPackage ../forgejo/schema-check.nix { };
  root = if cfg.artifactStorePath == null then "/INVALID" else cfg.artifactStorePath;
  immutable = value: value != null && !builtins.hasContext value
    && builtins.match "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+" value != null;
  credentials = {
    FORGEJO__SECURITY__SECRET_KEY__FILE = "/var/lib/forgejo/custom/conf/secret_key";
    FORGEJO__SECURITY__INTERNAL_TOKEN__FILE = "/var/lib/forgejo/custom/conf/internal_token";
    FORGEJO__OAUTH2__JWT_SECRET__FILE = "/var/lib/forgejo/custom/conf/oauth2_jwt_secret";
  };
  settings = lib.recursiveUpdate preparation.settings ({
    DEFAULT = { RUN_USER = "forgejo"; RUN_MODE = "prod"; WORK_PATH = "/var/lib/forgejo"; };
    database.AUTO_MIGRATION = false;
    repository.ROOT = "/var/lib/forgejo/repositories";
    server.APP_DATA_PATH = "/var/lib/forgejo/data";
    # This key belongs to [server]. REQUIRE_SIGNIN_VIEW alone keeps a public home.
    server.LANDING_PAGE = "login";
    log.MODE = "console";
    actions.ENABLED = cfg.enableBoundedActions;
  } // lib.optionalAttrs (cfg.retainedQuotas != null) {
    quota.ENABLED = true;
    "quota.default".TOTAL = cfg.retainedQuotas.totalStorage;
    repository = { ROOT = "/var/lib/forgejo/repositories";
      MAX_CREATION_LIMIT = cfg.retainedQuotas.maxRepositories; };
  });
  ini = (pkgs.formats.ini { }).generate "mrjam-forgejo-public-settings.ini" settings;
  hba = ''
    local forgejo forgejo peer
    local all forgejo reject
    host all forgejo 0.0.0.0/0 reject
    host all forgejo ::0/0 reject
  '';
in {
  disabledModules = [ ../nixos/mrjam-forgejo-host.nix ];
  imports = [ ../nixos/mrjam-forgejo.nix ../nixos/mrjam-postgresql-policy.nix ./modules.nix ];
  options.services.mrjamForgejoHost = {
    enable = lib.mkEnableOption "adoption of the existing Forgejo identity with a prequalified artifact";
    enableBoundedActions = lib.mkEnableOption "Actions after explicit installation of the bounded validation chain";
    startAtBoot = lib.mkEnableOption "start of the adopted Forgejo service at boot";
    artifactStorePath = lib.mkOption { type = lib.types.nullOr lib.types.str; default = null; };
    uid = lib.mkOption { type = lib.types.nullOr lib.types.ints.positive; default = null; };
    gid = lib.mkOption { type = lib.types.nullOr lib.types.ints.positive; default = null; };
    retainedQuotas = lib.mkOption {
      type = lib.types.nullOr (lib.types.submodule { options = {
        maxRepositories = lib.mkOption { type = lib.types.ints.between (-1) 2147483647; };
        totalStorage = lib.mkOption { type = lib.types.strMatching "(-1|[0-9]+( ?(B|KiB|MiB|GiB|TiB))?)"; };
      }; });
      default = null;
      description = "Explicit preservation of quota defaults from the reviewed installed source; per-account SQL overrides remain untouched.";
    };
    settings = lib.mkOption { type = lib.types.attrs; readOnly = true; default = settings; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = !cfg.enableBoundedActions || (
          config.services.mrjamForgejoRunner.enable
          && config.services.mrjamValidationWorker.enable
          && config.services.mrjamValidationCollector.enable
          && config.services.mrjamValidationStaging.enable
          && config.services.mrjamForgejoPolicy.enable
          && config.services.mrjamForgejoPolicy.phase == "operate-validation"
        );
        message = "mrjamForgejoHost: Actions requires the explicitly configured bounded runner, worker, collector, staging and operational policy."; }

      { assertion = immutable cfg.artifactStorePath;
        message = "mrjamForgejoHost: a prequalified immutable artifact without build context is required."; }
      { assertion = cfg.artifactStorePath == builtins.unsafeDiscardStringContext "${locked.forgejo}";
        message = "mrjamForgejoHost: the artifact must match the locked 17.0.1 schema contract."; }
      { assertion = cfg.uid != null && cfg.gid != null;
        message = "mrjamForgejoHost: the existing Forgejo UID/GID must be established before adoption."; }
      { assertion = !config.services.forgejo.enable;
        message = "mrjamForgejoHost: the upstream bootstrap/migration service must not be enabled alongside adoption."; }
      { assertion = config.services.postgresql.enable && lib.versions.major config.services.postgresql.package.version == "17";
        message = "mrjamForgejoHost: the existing PostgreSQL 17 instance must be configured separately."; }
      { assertion = config.users.users.forgejo.extraGroups == [ ];
        message = "mrjamForgejoHost: Forgejo must not acquire supplementary groups."; }
      { assertion = config.services.mrjamPostgresqlPolicy.blocks.forgejo == hba;
        message = "mrjamForgejoHost: the closed peer policy must not be extended or overridden."; }
    ];
    services.mrjamPostgresqlPolicy.blocks.forgejo = hba;
    users.groups.forgejo.gid = cfg.gid;
    users.users.forgejo = { isSystemUser = true; uid = cfg.uid; group = "forgejo";
      home = "/var/lib/forgejo"; createHome = false; hashedPassword = "!"; extraGroups = [ ]; };
    systemd.tmpfiles.rules = [
      "d /var/lib/forgejo/custom/templates/custom 0750 forgejo forgejo - -"
      "L+ /var/lib/forgejo/custom/templates/custom/footer.tmpl - - - - ${preparation}/review/footer.tmpl"
    ];
    systemd.services.forgejo = {
      description = "MRJ.am Forgejo — existing identity and schema, explicit adoption";
      after = [ "network.target" "postgresql.service" ]; requires = [ "postgresql.service" ];
      wantedBy = lib.optional cfg.startAtBoot "multi-user.target";
      restartIfChanged = false; stopIfChanged = false;
      path = [ pkgs.git pkgs.gnupg ];
      environment = { USER = "forgejo"; HOME = "/var/lib/forgejo";
        FORGEJO_WORK_DIR = "/var/lib/forgejo"; FORGEJO_CUSTOM = "/var/lib/forgejo/custom"; }
        // credentials;
      preStart = ''
        set -eu
        umask 0077
        test -d /var/lib/forgejo/repositories
        test ! -L /var/lib/forgejo/repositories
        ${schemaCheck}/bin/mrjam-forgejo-check-schema
        # These existing paths may be writable by Forgejo. Read as Forgejo,
        # never through a privileged LoadCredential that could follow a link.
        ${lib.concatMapStringsSep "\n" (path: "test -r ${path} && test -s ${path} && test ! -L ${path}") (builtins.attrValues credentials)}
        ${pkgs.coreutils}/bin/install -m 0600 ${ini} /run/mrjam-forgejo/app.ini
        ${root}/bin/environment-to-ini --config /run/mrjam-forgejo/app.ini
        ${pkgs.coreutils}/bin/chmod 0400 /run/mrjam-forgejo/app.ini
      '';
      serviceConfig = {
        Type = "notify"; User = "forgejo"; Group = "forgejo";
        WorkingDirectory = "/var/lib/forgejo";
        ExecStart = "${root}/bin/forgejo web --config /run/mrjam-forgejo/app.ini --pid /run/mrjam-forgejo/forgejo.pid";
        RuntimeDirectory = "mrjam-forgejo"; RuntimeDirectoryMode = "0700";
        StateDirectory = "forgejo"; StateDirectoryMode = "0750";
        UMask = "0077"; NoNewPrivileges = true; PrivateTmp = true; PrivateDevices = true;
        ProtectSystem = "strict"; ProtectHome = true; ReadWritePaths = [ "/var/lib/forgejo" ];
        CapabilityBoundingSet = [ ]; AmbientCapabilities = [ ];
        RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
        ProtectKernelTunables = true; ProtectKernelModules = true; ProtectControlGroups = true;
        RestrictSUIDSGID = true; LockPersonality = true;
        Restart = "on-failure"; RestartSec = 5; TimeoutStartSec = 120;
        MemoryMax = "768M"; TasksMax = 256;
        StandardOutput = "null"; StandardError = "null";
      };
    };
  };
}
