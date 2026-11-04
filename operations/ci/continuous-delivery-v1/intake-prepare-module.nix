{config,lib,pkgs,...}:
let cfg=config.services.mrjamIntakePreparation;
in {
  options.services.mrjamIntakePreparation={
    enable=lib.mkEnableOption "prepare exact queued sources without granting admission";
    adopted=lib.mkOption {type=lib.types.path;default=import ./adopted-source-bootstrap.nix {inherit pkgs;};};
    package=lib.mkOption {type=lib.types.package;default=import ./intake-prepare.nix {inherit pkgs;};};
  };
  config=lib.mkIf cfg.enable {
    assertions=[{assertion=config.services.mrjamGithubDiscovery.enable;
      message="Exact source preparation requires the protected discovery queue.";}];
    environment.etc."mrjam-delivery-adopted.json".source=cfg.adopted;
    systemd.services.mrjam-intake-prepare={
      description="Prepare exact queued source objects, without admission or deployment";
      after=["network-online.target" "mrjam-github-discovery.service"];
      wants=["network-online.target"];
      environment.MRJAM_ADOPTED_BASE="/etc/mrjam-delivery-adopted.json";
      serviceConfig={
        Type="oneshot";DynamicUser=true;User="mrjam-github-discovery";
        StateDirectory="mrjam-github-discovery";StateDirectoryMode="0700";
        LoadCredential=["github-app:${config.services.mrjamGithubDiscovery.credentialFile}"];
        ExecStart="${cfg.package}/bin/mrjam-intake-prepare";
        TimeoutStartSec=840;UMask="0077";
        ProtectSystem="strict";ProtectHome=true;PrivateDevices=true;
        TemporaryFileSystem=["/tmp:rw,size=512M,mode=1777"];
        ProtectKernelTunables=true;ProtectKernelModules=true;ProtectControlGroups=true;
        NoNewPrivileges=true;CapabilityBoundingSet="";RestrictSUIDSGID=true;
        LockPersonality=true;RestrictNamespaces=true;
        RestrictAddressFamilies=["AF_UNIX" "AF_INET" "AF_INET6"];
        SystemCallArchitectures="native";
        MemoryMax="768M";MemoryHigh="384M";TasksMax=32;CPUQuota="20%";
        LimitCORE=0;StandardOutput="journal";StandardError="null";
      };
    };
    systemd.timers.mrjam-intake-prepare={
      wantedBy=["timers.target"];
      timerConfig={OnBootSec="3min";OnUnitInactiveSec="2min";RandomizedDelaySec="15s";};
    };
  };
}
