# Reconstructed protections from the reviewed VPS code. This does not select
# or build PHP, create Nextcloud, remove its containment marker or run occ.
{ config, lib, ... }:
let
  cfg = config.services.mrjamNextcloudGuards;
  marker = "!/var/lib/nextcloud-php-security/blocked";
in {
  options.services.mrjamNextcloudGuards.enable = lib.mkEnableOption "retained Nextcloud PHP protections";
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = config.services.nextcloud.enable;
        message = "mrjamNextcloudGuards: requires the independently configured existing Nextcloud service."; }
      { assertion = lib.versions.majorMinor config.services.nextcloud.phpPackage.version == "8.4"
          && lib.versionAtLeast config.services.nextcloud.phpPackage.version "8.4.27";
        message = "mrjamNextcloudGuards: preserve the PHP 8.4 branch and at least the received 8.4.27 patch; package build qualification remains separate."; }
      { assertion = config.services.nextcloud.phpOptions."session.upload_progress.enabled" == "Off"
          && config.services.phpfpm.pools.nextcloud.settings."php_admin_flag[session.upload_progress.enabled]" == false;
        message = "mrjamNextcloudGuards: upload progress must stay disabled in CLI and FPM."; }
      { assertion = config.systemd.services.phpfpm-nextcloud.unitConfig.ConditionPathExists == marker
          && config.systemd.services.nextcloud-cron.unitConfig.ConditionPathExists == marker;
        message = "mrjamNextcloudGuards: the persistent containment marker must still block FPM and cron; removing it requires a separate qualified operation."; }
    ];
    services.phpfpm.phpOptions = lib.mkAfter ''
      session.upload_progress.enabled = Off
    '';
    services.nextcloud.phpOptions."session.upload_progress.enabled" = lib.mkForce "Off";
    services.phpfpm.pools.nextcloud.settings."php_admin_flag[session.upload_progress.enabled]" = false;
    systemd.services.phpfpm-nextcloud.unitConfig.ConditionPathExists = marker;
    systemd.services.nextcloud-cron.unitConfig.ConditionPathExists = marker;
  };
}
