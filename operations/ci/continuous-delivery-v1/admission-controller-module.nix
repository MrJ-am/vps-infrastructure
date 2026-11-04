{config,lib,pkgs,...}:
let cfg=config.services.mrjamAdmissionController;
in {
  options.services.mrjamAdmissionController={
    enable=lib.mkEnableOption "protected orchestration of source admission and independent CI";
    package=lib.mkOption {type=lib.types.package;default=import ./admission-controller.nix {inherit pkgs;};};
  };
  config=lib.mkIf cfg.enable {
    assertions=[{assertion=config.services.mrjamIntakePreparation.enable;
      message="The admission controller consumes the exact-source preparation bridge.";}];
    systemd.tmpfiles.rules=["d /var/lib/mrjam-intake-decisions 0755 root root -"];
    systemd.services.mrjam-intake-prepare.environment.MRJAM_INTAKE_DECISIONS="/var/lib/mrjam-intake-decisions";
    systemd.services.mrjam-admission-controller={
      description="Admit exact sources and obtain independently signed validation artifacts";
      after=["network-online.target" "mrjam-intake-prepare.service" "forgejo.service"];
      wants=["network-online.target"];
      serviceConfig={
        Type="oneshot";User="root";
        StateDirectory="mrjam-intake-admission";StateDirectoryMode="0700";
        LoadCredential=["github-app:/var/lib/mrjam-github-app/app-credentials.json"
          "forgejo-dispatch:/var/lib/mrjam-ci-credentials/forgejo-registration-token"];
        ExecStart="${cfg.package}/bin/mrjam-admission-controller";
        TimeoutStartSec=720;UMask="0077";
        ProtectSystem="strict";ProtectHome=true;PrivateDevices=true;PrivateTmp=true;
        ProtectKernelTunables=true;ProtectKernelModules=true;ProtectControlGroups=true;
        NoNewPrivileges=true;CapabilityBoundingSet=["CAP_DAC_READ_SEARCH"];
        RestrictSUIDSGID=true;LockPersonality=true;RestrictNamespaces=true;
        RestrictAddressFamilies=["AF_UNIX" "AF_INET" "AF_INET6"];
        SystemCallArchitectures="native";
        ReadWritePaths=["/var/lib/mrjam-cutover/first-deployment/transaction.lock"
          "/var/lib/mrjam-validation-input" "/var/lib/mrjam-validation-admissions" "/var/lib/mrjam-intake-decisions"];
        InaccessiblePaths=["-/var/lib/postgresql" "-/var/lib/kanidm" "-/var/lib/nextcloud"
          "-/var/lib/mrjam-validation-authority/signing-key" "-/var/lib/mrjam-github-app"
          "-/var/lib/mrjam-ci-credentials" "-/var/lib/mrjam-forgejo-runner/registration"
          "-/var/lib/mrjam-cutover/vise-adoption-20261103"];
        MemoryMax="768M";TasksMax=64;CPUQuota="50%";LimitCORE=0;
        StandardOutput="journal";StandardError="null";
      };
    };
    systemd.timers.mrjam-admission-controller={
      wantedBy=["timers.target"];
      timerConfig={OnBootSec="4min";OnUnitInactiveSec="20s";RandomizedDelaySec="5s";};
    };
  };
}
