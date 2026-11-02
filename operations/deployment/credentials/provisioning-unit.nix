{ config, lib, pkgs, ... }:
let cfg = config.services.mrjamKanidmWorkerProvision;
in {
  options.services.mrjamKanidmWorkerProvision = {
    enable = lib.mkEnableOption "human-authenticated closed worker credential provisioning";
    package = lib.mkOption { type = lib.types.package; };
  };
  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ cfg.package ];
    systemd.services.mrjam-kanidm-worker-provision = {
      description = "Fixed native Kanidm worker capabilities from temporary human sessions";
      # No wantedBy/timer: only the human login entry starts this unit.
      serviceConfig = {
        Type = "oneshot";
        User = "root";
        Group = "root";
        ExecStart = "${cfg.package}/bin/mrjam-kanidm-worker-provision";
        LoadCredential = [
          "identity-session:/run/mrjam-kanidm-worker-login/identity.json"
          "access-session:/run/mrjam-kanidm-worker-login/access.json"
        ];
        UMask = "0077";
        ProtectSystem = "strict";
        ProtectHome = true;
        ReadWritePaths = [ "/var/lib/mrjam-identite" ];
        PrivateTmp = true;
        PrivateDevices = true;
        NoNewPrivileges = true;
        CapabilityBoundingSet = "";
        RestrictAddressFamilies = [ "AF_INET" ];
        IPAddressDeny = "any";
        IPAddressAllow = "127.0.0.1/32";
        RestrictNetworkInterfaces = [ "lo" ];
        RestrictNamespaces = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectKernelLogs = true;
        ProtectControlGroups = true;
        LockPersonality = true;
        LimitCORE = 0;
        MemoryMax = "256M";
        TasksMax = 16;
        TimeoutStartSec = 140;
        StandardOutput = "journal";
        StandardError = "journal";
      };
    };
  };
}
