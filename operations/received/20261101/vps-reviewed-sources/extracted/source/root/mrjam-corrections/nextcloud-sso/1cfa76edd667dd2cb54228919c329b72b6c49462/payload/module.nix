# Native Nextcloud OIDC client; keep the existing account, files and app tokens.
{ config, lib, pkgs, ... }:
{
  assertions = [
    { assertion = config.services.nextcloud.package.version == "34.0.4";
      message = "Requalifier le raccordement OIDC pour cette version Nextcloud."; }
    { assertion = pkgs.nextcloud34Packages.apps.user_oidc.name == "nextcloud-app-user_oidc-8.10.1";
      message = "Requalifier la nouvelle version du module OIDC."; }
    { assertion = config.services.kanidm.server.enable;
      message = "Le Kanidm existant est requis."; }
  ];
  services.nextcloud.extraApps.user_oidc = pkgs.nextcloud34Packages.apps.user_oidc;
  services.nextcloud.settings = {
    user_oidc = {
      auto_provision = false;
      use_pkce = true;
      enable_default_claims = false;
      login_label = "Se connecter avec Log";
      single_logout = false;
    };
    hide_login_form = true;
    lost_password_link = "disabled";
    "auth.webauthn.enabled" = false;
    token_auth_enforced = true;
  };
  # allow_multiple_user_backends only redirects GET /login. The native direct=1
  # escape hatch must not accept a password POST, including via index.php.
  # Login Flow v2 and DAV stay available for native application tokens.
  services.nginx.appendHttpConfig = lib.mkAfter ''
    map "$request_method:$uri" $nextcloud_local_password {
      default 0;
      ~^POST:/(index.php/)?login/?$ 1;
      ~^POST:/(index.php/)?lostpassword/ 1;
    }
  '';
  services.nginx.virtualHosts."cloud.mrj.am".extraConfig = lib.mkAfter ''
    if ($nextcloud_local_password) { return 403; }
  '';
}
