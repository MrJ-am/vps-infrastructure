{ config, lib, pkgs, ... }:
let cfg = config.services.mrjamKanidmPasskeyPortal;
in {
  options.services.mrjamKanidmPasskeyPortal = {
    enable = lib.mkEnableOption "temporary human passkey provisioning portal";
    package = lib.mkOption { type = lib.types.package; };
  };
  config = lib.mkIf cfg.enable {
    systemd.services.mrjam-kanidm-passkey-portal = {
      description = "Temporary human passkey entry for the fixed worker provisioner";
      # No WantedBy, socket activation, restart policy or timer.
      serviceConfig = {
        Type = "simple";
        User = "root";
        Group = "root";
        ExecStart = "${cfg.package}/bin/mrjam-kanidm-passkey-portal";
        UMask = "0077";
        ProtectSystem = "strict";
        ProtectHome = true;
        # Both exact runtime directories are created exclusively by the
        # reviewed process. /run stays writable to create them; no arbitrary
        # filesystem target is accepted by the HTTP interface.
        ReadWritePaths = [ "/run" ];
        PrivateTmp = true;
        PrivateDevices = true;
        NoNewPrivileges = true;
        CapabilityBoundingSet = [ "CAP_CHOWN" ];
        RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" ];
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
        RuntimeMaxSec = 1100;
        # Drain a fixed provisioning job (145s) then revoke at most eight
        # dedicated sessions (5s each), with a bounded shutdown margin.
        TimeoutStopSec = 240;
        StandardOutput = "journal";
        StandardError = "journal";
      };
    };
  };
}
