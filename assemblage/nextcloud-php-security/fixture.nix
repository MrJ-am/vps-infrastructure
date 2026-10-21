{ lib, pkgs, ... }:
{
  options.services.vision.backupRecipient = lib.mkOption {
    type = lib.types.str;
    default = "age1fixture-local-non-production";
  };
  config = {
    system.stateVersion = "26.05";
    boot.isContainer = true;
    networking.hostName = "php-security-fixture";
    services.nextcloud = {
      enable = true;
      hostName = "cloud.mrj.am";
      package = pkgs.nextcloud34;
      configureRedis = true;
      database.createLocally = false;
      config = {
        dbtype = "pgsql";
        dbhost = "/run/postgresql";
        dbuser = "nextcloud";
        dbname = "nextcloud";
        adminpassFile = "/run/fixture-secret";
      };
      settings = {
        user_oidc.auto_provision = false;
        token_auth_enforced = true;
        hide_login_form = true;
        log_type = "systemd";
      };
    };
    services.nginx.virtualHosts."cloud.mrj.am".extraConfig = ''
      if ($request_method = POST) { return 403; }
    '';
    services.nginx.virtualHosts."vision.mrj.am".locations."/".return = "200";
    services.postgresql.enable = true;
    services.kanidm.package = pkgs.kanidm_1_11;
    systemd.services.mrjam-metier.serviceConfig.ExecStart = "${pkgs.coreutils}/bin/true";
  };
}
