{ config, lib, pkgs, ... }:
let cfg=config.services.mrjamGithubDiscovery;
in {
  options.services.mrjamGithubDiscovery = {
    enable=lib.mkEnableOption "read-only discovery of Cloud proposals, without admission or deployment";
    package=lib.mkOption { type=lib.types.package; default=import ./github-proposals.nix { inherit pkgs; }; };
    credentialFile=lib.mkOption { type=lib.types.str; default="/var/lib/mrjam-github-app/app-credentials.json"; };
  };
  config=lib.mkIf cfg.enable {
    assertions=[{ assertion=cfg.credentialFile=="/var/lib/mrjam-github-app/app-credentials.json";
      message="GitHub discovery uses only its independently installed App identity."; }];
    systemd.services.mrjam-github-discovery={
      description="Observe GitHub proposals without granting delivery authority";
      after=["network-online.target"]; wants=["network-online.target"];
      serviceConfig={
        Type="oneshot"; DynamicUser=true; User="mrjam-github-discovery";
        StateDirectory="mrjam-github-discovery"; StateDirectoryMode="0700";
        LoadCredential=["github-app:${cfg.credentialFile}"];
        ExecStart="${cfg.package}/bin/mrjam-github-discover";
        TimeoutStartSec=180; UMask="0077";
        ProtectSystem="strict"; ProtectHome=true; PrivateTmp=true; PrivateDevices=true;
        ProtectKernelTunables=true; ProtectKernelModules=true; ProtectControlGroups=true;
        NoNewPrivileges=true; CapabilityBoundingSet=""; RestrictSUIDSGID=true;
        LockPersonality=true; RestrictNamespaces=true;
        RestrictAddressFamilies=["AF_UNIX" "AF_INET" "AF_INET6"];
        SystemCallArchitectures="native";
        MemoryMax="128M"; TasksMax=32; CPUQuota="20%";
        StandardOutput="journal"; StandardError="null";
      };
    };
    systemd.timers.mrjam-github-discovery={
      wantedBy=["timers.target"];
      timerConfig={ OnBootSec="2min"; OnUnitInactiveSec="5min"; RandomizedDelaySec="30s"; };
    };
  };
}
