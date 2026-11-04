{lib,pkgs,mrjamPromotionConfig ? {},...}:
let
  enabled=mrjamPromotionConfig.enableVise or false;
  package=import ./promotion-service.nix ({inherit pkgs;} // mrjamPromotionConfig);
in {
  systemd.services.mrjam-promotion={
    description="Resume a signed, protected root delivery plan";
    after=["network-online.target" "nginx.service" "postgresql.service" "forgejo.service"];
    wants=["network-online.target"];
    unitConfig=lib.optionalAttrs (!enabled) {
      ConditionPathExists="/var/lib/mrjam-promotion/plan.json";
    };
    restartIfChanged=false;stopIfChanged=false;
    serviceConfig={
      Type="oneshot";User="root";UMask="0077";
      StateDirectory="mrjam-promotion";StateDirectoryMode="0700";
      LoadCredential=["forgejo-observer:/var/lib/mrjam-ci-credentials/forgejo-policy-token"];
      ExecStart="${package}/bin/mrjam-promotion";
      TimeoutStartSec=600;Restart="on-failure";RestartSec=30;
      MemoryMax="768M";CPUQuota="50%";TasksMax=128;
      StandardOutput="journal";StandardError="null";
    };
  };
  systemd.timers.mrjam-promotion={
    wantedBy=["timers.target"];
    timerConfig={OnBootSec="30s";OnUnitInactiveSec="30s";AccuracySec="5s";};
  };
}
