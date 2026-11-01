{ config, lib, pkgs, ... }:
let cfg = config.infrastructure.courriel; in {
  options.infrastructure.courriel = {
    enable = lib.mkEnableOption "courriels transactionnels Proton et file privée durable";
    secret = lib.mkOption { type = lib.types.str; default = "/var/lib/mrjam-identite/proton-smtp.json"; };
  };
  config = lib.mkIf cfg.enable {
    users.groups.mrjam-courriel = {};
    users.users.mrjam-courriel = { isSystemUser = true; group = "mrjam-courriel"; };
    systemd.services.mrjam-courriel = {
      description = "Reprendre les courriels transactionnels en attente";
      environment = {
        MRJ_SMTP_SECRET = "/run/credentials/mrjam-courriel.service/smtp";
        MRJ_COURRIEL_FILE = "/var/lib/mrjam-courriel/file.sqlite";
      };
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${pkgs.python3}/bin/python3 ${../services/mrjam-courriel/courriel.py}";
        User = "mrjam-courriel"; Group = "mrjam-courriel";
        StateDirectory = "mrjam-courriel"; StateDirectoryMode = "0700";
        LoadCredential = [ "smtp:${cfg.secret}" ];
        UMask = "0077"; TimeoutStartSec = "8min";
        NoNewPrivileges = true; PrivateTmp = true; PrivateDevices = true;
        ProtectSystem = "strict"; ProtectHome = true;
        ProtectKernelTunables = true; ProtectKernelModules = true;
        ProtectControlGroups = true; RestrictSUIDSGID = true;
        CapabilityBoundingSet = "";
        RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
        MemoryMax = "64M"; TasksMax = 8;
      };
    };
    systemd.timers.mrjam-courriel = {
      wantedBy = [ "timers.target" ];
      timerConfig = { OnBootSec = "2min"; OnUnitInactiveSec = "1min"; };
    };
  };
}
