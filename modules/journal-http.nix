# Journal séparé : une attaque HTTP ne chasse pas les traces SSH/PostgreSQL.
{ config, lib, ... }:
{
  environment.etc."systemd/journald@http.conf".text = ''
    [Journal]
    Storage=persistent
    Compress=yes
    SystemMaxUse=128M
    SystemKeepFree=1G
    SystemMaxFileSize=8M
    SystemMaxFiles=16
    RuntimeMaxUse=16M
    RuntimeKeepFree=64M
    RuntimeMaxFileSize=4M
    MaxRetentionSec=14day
    MaxFileSec=1day
    RateLimitIntervalSec=30s
    RateLimitBurst=1000
    ForwardToSyslog=no
    ForwardToKMsg=no
    ForwardToConsole=no
    ForwardToWall=no
    ReadKMsg=no
  '';
  systemd.services."systemd-journald@http" = {
    restartTriggers = [ config.environment.etc."systemd/journald@http.conf".source ];
    stopIfChanged = false;
  };
  systemd.services.nginx.serviceConfig = {
    LogNamespace = "http";
    LogRateLimitIntervalSec = "30s";
    LogRateLimitBurst = 1000;
  };
  # Les erreurs par requête peuvent recopier URL/utilisateur dans le format natif.
  # Les statuts 4xx/5xx restent dans le journal structuré ; seuls les incidents
  # critiques conservent le diagnostic natif, également borné.
  services.nginx.logError = "stderr crit";
  services.nginx.commonHttpConfig = lib.mkAfter (builtins.readFile ../lib/journal-http.conf);
}
