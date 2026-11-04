# Package path is supplied by the protected host state, never by a proposal.
{packagePath}:
{lib,...}:
let package=builtins.storePath packagePath;
in assert builtins.match "/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+" packagePath!=null;
{
  systemd.services.mrjam-delivery-preparation={
    description="Prepare independently verified delivery generations";
    after=["network-online.target" "forgejo.service"];
    wants=["network-online.target"];
    serviceConfig={
      Type="oneshot";User="root";UMask="0077";
      ExecStart="${package}/bin/mrjam-delivery-prepare";
      StateDirectory="mrjam-delivery-preparation";StateDirectoryMode="0700";
      LoadCredential=["forgejo-observer:/var/lib/mrjam-ci-credentials/forgejo-policy-token"];
      TimeoutStartSec=1800;MemoryMax="3G";CPUQuota="50%";TasksMax=128;LimitCORE=0;
      ProtectSystem="strict";ProtectHome=true;PrivateTmp=true;PrivateDevices=true;
      NoNewPrivileges=true;CapabilityBoundingSet=["CAP_DAC_READ_SEARCH"];
      ProtectKernelTunables=true;ProtectKernelModules=true;ProtectControlGroups=true;
      RestrictSUIDSGID=true;LockPersonality=true;RestrictNamespaces=true;
      RestrictAddressFamilies=["AF_UNIX" "AF_INET"];IPAddressDeny=["any"];IPAddressAllow=["localhost"];
      InaccessiblePaths=["-/var/lib/postgresql" "-/var/lib/kanidm" "-/var/lib/nextcloud" "-/var/lib/forgejo"
        "-/var/lib/vise" "-/var/lib/mrjam-github-app" "-/var/lib/mrjam-ci-credentials" "-/var/lib/mrjam-delivery-credentials"
        "-/var/lib/mrjam-validation-authority/signing-key" "-/var/lib/mrjam-forgejo-runner/registration"
        "-/var/lib/mrjam-cutover/vise-adoption-20261103" "-/run/postgresql" "-/run/mrjam-identity" "-/run/secrets"
        "-/run/mrjam-validation-authority" "-/run/mrjam-validation-collector"
        "-/run/systemd/private" "-/run/dbus/system_bus_socket"];
      StandardOutput="journal";StandardError="null";
    };
  };
  systemd.timers.mrjam-delivery-preparation={
    wantedBy=["timers.target"];
    timerConfig={OnBootSec="1min";OnUnitInactiveSec="60s";RandomizedDelaySec="5s";};
  };
}
