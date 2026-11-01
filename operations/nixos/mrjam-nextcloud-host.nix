# Adopt existing Nextcloud state with explicit upgrades, never on unit restart.
{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamNextcloudHost;
  packages = import ../hosts/mrjam-vps/preserved-packages.nix { system = pkgs.stdenv.hostPlatform.system; };
  hba = ''
    local nextcloud nextcloud peer
    local all nextcloud reject
    host all nextcloud 0.0.0.0/0 reject
    host all nextcloud ::0/0 reject
  '';
in {
  imports = [ ./mrjam-nextcloud-guards.nix ./mrjam-postgresql-policy.nix ];
  options.services.mrjamNextcloudHost = {
    enable = lib.mkEnableOption "declarative adoption of Nextcloud 34.0.4 and its existing OIDC client";
    startAtBoot = lib.mkEnableOption "start of the adopted Nextcloud services at boot";
    uid = lib.mkOption { type = lib.types.nullOr lib.types.ints.positive; default = null; };
    gid = lib.mkOption { type = lib.types.nullOr lib.types.ints.positive; default = null; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = cfg.uid != null && cfg.gid != null;
        message = "mrjamNextcloudHost: establish the existing Nextcloud UID/GID before adoption."; }
      { assertion = config.services.postgresql.enable && lib.versions.major config.services.postgresql.package.version == "17";
        message = "mrjamNextcloudHost: requires the independently configured shared PostgreSQL 17 instance."; }
      { assertion = config.services.mrjamPostgresqlPolicy.blocks.nextcloud == hba;
        message = "mrjamNextcloudHost: closed peer authentication must not be extended or overridden."; }
      { assertion = config.services.mrjamKanidmHost.enable or false;
        message = "mrjamNextcloudHost: preserve the separately adopted Kanidm identity service."; }
      { assertion = config.services.nextcloud.config.adminuser == null && config.services.nextcloud.config.adminpassFile == null
          && !config.services.nextcloud.database.createLocally;
        message = "mrjamNextcloudHost: account/database bootstrap is outside adoption."; }
    ];
    users.users.nextcloud.uid = cfg.uid;
    users.groups.nextcloud.gid = cfg.gid;
    services.mrjamPostgresqlPolicy.blocks.nextcloud = hba;
    services.mrjamNextcloudGuards.enable = true;
    services.nextcloud = {
      enable = true;
      package = packages.nextcloud; phpPackage = packages.php;
      hostName = "cloud.mrj.am"; https = true; configureRedis = true;
      maxUploadSize = "2G";
      phpOptions.memory_limit = lib.mkForce "512M";
      poolSettings = {
        "pm" = "dynamic"; "pm.max_children" = "4"; "pm.start_servers" = "2";
        "pm.min_spare_servers" = "1"; "pm.max_spare_servers" = "2";
        "pm.max_requests" = "500"; "pm.status_path" = "/status";
      };
      extraApps = packages.nextcloudApps;
      extraAppsEnable = false; appstoreEnable = false; autoUpdateApps.enable = false;
      database.createLocally = false;
      config = { dbtype = "pgsql"; dbhost = "/run/postgresql"; dbname = "nextcloud";
        dbuser = "nextcloud"; adminuser = null; adminpassFile = null; };
      settings = {
        default_phone_region = "FR"; maintenance_window_start = 2; log_type = "systemd";
        user_oidc = { auto_provision = false; use_pkce = true; enable_default_claims = false;
          login_label = "Se connecter avec Log"; single_logout = false; };
        hide_login_form = true; lost_password_link = "disabled";
        "auth.webauthn.enabled" = false; token_auth_enforced = true;
      };
    };
    # Keep the official webroot, PHP extensions, Redis and config generation.
    # Replace only the implicit install/upgrade/database-repair entrypoints.
    systemd.services.nextcloud-setup = {
      wantedBy = lib.mkForce (lib.optional cfg.startAtBoot "multi-user.target");
      wants = lib.mkForce [ ];
      after = [ "postgresql.service" "redis-nextcloud.service" ];
      requires = [ "postgresql.service" "redis-nextcloud.service" ];
      restartIfChanged = false; stopIfChanged = false;
      script = lib.mkForce ''
        set -eu
        test -s /var/lib/nextcloud/config/config.php
        ${lib.getExe config.services.nextcloud.occ} status --exit-code >/dev/null
      '';
      serviceConfig = { StandardOutput = "null"; StandardError = "null"; UMask = "0077"; };
    };
    systemd.services.nextcloud-update-db.enable = lib.mkForce false;
    systemd.services.phpfpm-nextcloud = {
      wantedBy = lib.mkForce (lib.optional cfg.startAtBoot "multi-user.target");
      requires = [ "nextcloud-setup.service" ]; after = [ "nextcloud-setup.service" ];
      restartIfChanged = false; stopIfChanged = false;
      serviceConfig = { StandardOutput = "null"; StandardError = "null"; };
    };
    systemd.services.redis-nextcloud = {
      wantedBy = lib.mkForce (lib.optional cfg.startAtBoot "multi-user.target");
      restartIfChanged = false; stopIfChanged = false;
    };
    systemd.timers.nextcloud-cron.wantedBy = lib.mkForce (lib.optional cfg.startAtBoot "timers.target");
    services.nginx.appendHttpConfig = lib.mkAfter ''
      map "$request_method:$uri" $nextcloud_local_password {
        default 0;
        ~^POST:/(index.php/)?login/?$ 1;
        ~^POST:/(index.php/)?lostpassword/ 1;
      }
    '';
    services.nginx.virtualHosts."cloud.mrj.am" = {
      forceSSL = true; enableACME = false;
      sslCertificate = "/var/lib/acme/cloud.mrj.am/fullchain.pem";
      sslCertificateKey = "/var/lib/acme/cloud.mrj.am/key.pem";
      extraConfig = lib.mkAfter ''
        if ($nextcloud_local_password) { return 403; }
        access_log off;
        error_log /dev/null crit;
      '';
    };
  };
}
