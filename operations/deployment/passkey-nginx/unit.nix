{ config, lib, ... }:
let cfg=config.services.mrjamPasskeyNginxRoute;
in {
  options.services.mrjamPasskeyNginxRoute = {
    enable=lib.mkEnableOption "sealed temporary HTTPS route for human worker provisioning";
    package=lib.mkOption { type=lib.types.package; };
  };
  config=lib.mkIf cfg.enable {
    systemd.services.mrjam-passkey-nginx-route = {
      description="Temporary same-origin provisioning route with automatic restoration";
      # Deliberately no WantedBy: explicit bounded installation/start only.
      serviceConfig = {
        Type="exec";
        User="root";
        Group="root";
        ExecStart="${cfg.package}/bin/mrjam-passkey-nginx-route apply";
        ExecStopPost="${cfg.package}/bin/mrjam-passkey-nginx-route rollback";
        RuntimeMaxSec=900;
        TimeoutStopSec=150;
        UMask="0077";
        PrivateTmp=true;
        PrivateDevices=true;
        ProtectHome=true;
        ProtectSystem="strict";
        ReadWritePaths=[ "/run" "/var/log/nginx" "/var/cache/nginx" ];
        RestrictAddressFamilies=[ "AF_UNIX" "AF_INET" "AF_INET6" ];
        IPAddressDeny="any";
        NoNewPrivileges=true;
        # This Nginx version also probes configured privileged binds during -t.
        CapabilityBoundingSet=[ "CAP_CHOWN" "CAP_DAC_READ_SEARCH" "CAP_DAC_OVERRIDE" "CAP_NET_BIND_SERVICE" ];
        LimitCORE=0;
        MemoryMax="256M";
        TasksMax=16;
        StandardOutput="journal";
        StandardError="null";
      };
    };
  };
}
