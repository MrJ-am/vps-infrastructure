{packagePath}:
{lib,...}:
let package=builtins.storePath packagePath;
in assert builtins.match "/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+" packagePath!=null;
{
  systemd.services.mrjam-delivery-staging={
    description="Qualify a protected delivery off traffic before acceptance";
    after=["network-online.target" "nginx.service" "postgresql.service" "forgejo.service"];
    wants=["network-online.target"];
    restartIfChanged=false;stopIfChanged=false;
    serviceConfig={
      Type="oneshot";User="root";UMask="0077";
      StateDirectory="mrjam-staging";StateDirectoryMode="0700";
      LoadCredential=["forgejo-observer:/var/lib/mrjam-ci-credentials/forgejo-policy-token"];
      ExecStart="${package}/bin/mrjam-delivery-stage";
      TimeoutStartSec=1200;MemoryMax="768M";CPUQuota="50%";TasksMax=128;LimitCORE=0;
      StandardOutput="journal";StandardError="null";
    };
  };
  systemd.timers.mrjam-delivery-staging={
    wantedBy=["timers.target"];
    timerConfig={OnBootSec="1min";OnUnitInactiveSec="30s";RandomizedDelaySec="5s";};
  };
}
