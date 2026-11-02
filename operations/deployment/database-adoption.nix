# Explicit, fixed database operations, invoked only after the paired snapshot.
# No unit is enabled at boot or pulled in by a normal application start.
{ config, lib, pkgs, ... }:
let
  psql = "${config.services.postgresql.package}/bin/psql -X -w -q --set=ON_ERROR_STOP=1 --host=/run/postgresql";
  journal = ./journal-bootstrap;
  sources = builtins.fromJSON (builtins.readFile (journal + "/source.json"));
  auditionSchema = import ./audition-schema-v2/package.nix { inherit pkgs; };
  forgejo = config.services.mrjamForgejoHost.artifactStorePath;
  ini = (pkgs.formats.ini { }).generate "forgejo-explicit-migration.ini" config.services.mrjamForgejoHost.settings;
  common = {
    Type = "oneshot";
    NoNewPrivileges = true;
    CapabilityBoundingSet = "";
    AmbientCapabilities = "";
    PrivateTmp = true;
    PrivateDevices = true;
    ProtectSystem = "strict";
    ProtectHome = true;
    ProtectKernelTunables = true;
    ProtectKernelModules = true;
    ProtectKernelLogs = true;
    ProtectControlGroups = true;
    ProtectProc = "invisible";
    ProcSubset = "pid";
    RestrictNamespaces = true;
    RestrictRealtime = true;
    RestrictSUIDSGID = true;
    LockPersonality = true;
    LimitCORE = 0;
    UMask = "0077";
    StandardInput = "null";
    StandardOutput = "null";
    StandardError = "null";
    TimeoutStartSec = 600;
    TimeoutStopSec = 60;
    MemoryMax = "512M";
    TasksMax = 64;
    RestrictAddressFamilies = [ "AF_UNIX" ];
    PrivateNetwork = true;
  };
  sqlOperation = script: {
    wantedBy = [ ];
    restartIfChanged = false;
    stopIfChanged = false;
    requires = [ "postgresql.service" ];
    after = [ "postgresql.service" ];
    inherit script;
    environment.PGOPTIONS = "-c statement_timeout=120000 -c lock_timeout=5000";
    serviceConfig = common // {
      User = "postgres";
      Group = "postgres";
      InaccessiblePaths = [ "-/var/lib/forgejo" "-/var/lib/kanidm" "-/var/lib/nextcloud"
        "-/var/lib/mrjam-identite" "-/var/lib/mrjam-metier" "-/var/lib/mrjam-worker-credentials"
        "-/var/backup" "-/var/backups" "-/run/nix" ];
    };
  };
in {
  assertions = [
    { assertion = sources.repository == "MrJ-am/vision"
        && sources.commit == "3c39cf5c776bf8f8b027d79daea69a825a0f337e"
        && lib.all (name: builtins.hashFile "sha256" (journal + "/${name}") == sources.files.${name}) (builtins.attrNames sources.files);
      message = "Database adoption requires the separately qualified exact native journal sources."; }
    { assertion = config.services.mrjamForgejoHost.enable && config.services.postgresql.enable;
      message = "Explicit database adoption requires the existing-state host modules."; }
  ];
  systemd.services.mrjam-adopt-matheval = (sqlOperation ''
    ${psql} --dbname=matheval --file=${./adopt-matheval.sql}
  '') // { conflicts = [ "mrjam-rust-blue.service" "mrjam-rust-green.service" ]; };

  systemd.services.mrjam-bootstrap-journal = (sqlOperation ''
    ${psql} --dbname=postgres --file=${journal}/bootstrap-journal/01-roles.sql
    ${psql} --dbname=postgres --file=${journal}/bootstrap-journal/02-database.sql
    ${psql} --dbname=vision_journal --file=${journal}/bootstrap-journal/03-schema.psql
    ${psql} --dbname=vision_journal --file=${./journal-public-schema-usage.sql}
    ${psql} --dbname=vision --file=${./vision-admin-public-schema-usage.sql}
    ${psql} --dbname=vision --file=${auditionSchema}/adopt.sql
  '') // { conflicts = [ "mrjam-rust-blue.service" "mrjam-rust-green.service"
    "mrjam-vision-admission.service" "mrjam-vision-cycle.service" "mrjam-vision-closure.service"
    "mrjam-vision-archive.service" "mrjam-vision-replay.service" ]; };

  systemd.services.mrjam-adopt-forgejo-role = (sqlOperation ''
    ${psql} --dbname=forgejo --file=${../forgejo/adopt-runtime-role.sql}
  '') // { conflicts = [ "forgejo.service" ]; };

  systemd.services.mrjam-upgrade-forgejo-schema = {
    wantedBy = [ ];
    restartIfChanged = false;
    stopIfChanged = false;
    requires = [ "postgresql.service" ];
    after = [ "postgresql.service" ];
    conflicts = [ "forgejo.service" ];
    environment = {
      USER = "forgejo";
      HOME = "/var/lib/forgejo";
      FORGEJO_WORK_DIR = "/var/lib/forgejo";
      FORGEJO_CUSTOM = "/var/lib/forgejo/custom";
      FORGEJO__SECURITY__SECRET_KEY__FILE = "/var/lib/forgejo/custom/conf/secret_key";
      FORGEJO__SECURITY__INTERNAL_TOKEN__FILE = "/var/lib/forgejo/custom/conf/internal_token";
      FORGEJO__OAUTH2__JWT_SECRET__FILE = "/var/lib/forgejo/custom/conf/oauth2_jwt_secret";
    };
    preStart = ''
      set -eu
      test -d /var/lib/forgejo/repositories
      test ! -L /var/lib/forgejo/repositories
      for name in secret_key internal_token oauth2_jwt_secret; do
        test -s /var/lib/forgejo/custom/conf/$name
        test ! -L /var/lib/forgejo/custom/conf/$name
      done
      ${pkgs.coreutils}/bin/install -m 0600 ${ini} /run/mrjam-forgejo-schema/app.ini
      ${forgejo}/bin/environment-to-ini --config /run/mrjam-forgejo-schema/app.ini
      ${pkgs.coreutils}/bin/chmod 0400 /run/mrjam-forgejo-schema/app.ini
    '';
    serviceConfig = common // {
      User = "forgejo";
      Group = "forgejo";
      WorkingDirectory = "/var/lib/forgejo";
      RuntimeDirectory = "mrjam-forgejo-schema";
      RuntimeDirectoryMode = "0700";
      ExecStart = "${forgejo}/bin/forgejo migrate --config /run/mrjam-forgejo-schema/app.ini";
      # Migration may update fixed Forgejo work paths as well as its database.
      ReadWritePaths = [ "/var/lib/forgejo" ];
      InaccessiblePaths = [ "-/var/lib/kanidm" "-/var/lib/nextcloud" "-/var/lib/postgresql"
        "-/var/lib/mrjam-metier" "-/var/lib/mrjam-identite" "-/var/backup" "-/var/backups"
        "-/run/nix" ];
    };
  };
}
