{ ... }:
{
  # Le marqueur survit au reboot ; le système corrigé peut seul le retirer.
  systemd.services.phpfpm-nextcloud.unitConfig.ConditionPathExists =
    "!/var/lib/nextcloud-php-security/blocked";
  systemd.services.nextcloud-cron.unitConfig.ConditionPathExists =
    "!/var/lib/nextcloud-php-security/blocked";
}
