{ lib, ... }:
{
  # Avis PHP du 23 octobre 2026 : protection avant le parsing des requêtes.
  # php.ini global pour les pools FPM et wrapper CLI/cron de Nextcloud.
  services.phpfpm.phpOptions = lib.mkAfter ''
    session.upload_progress.enabled = Off
  '';
  services.nextcloud.phpOptions."session.upload_progress.enabled" = lib.mkForce "Off";
  services.phpfpm.pools.nextcloud.settings."php_admin_flag[session.upload_progress.enabled]" = false;
}
