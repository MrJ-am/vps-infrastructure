{lib,pkgs,...}:
let
  package=import ./acceptance-services.nix {inherit pkgs;};
  stages=["mirror" "review" "merge" "sync"];
in {
  systemd.services=lib.genAttrs (map (stage: "mrjam-acceptance-${stage}") stages) (name:
    let stage=lib.removePrefix "mrjam-acceptance-" name;
    in {
      description="Protected delivery acceptance: ${stage}";
      after=["network-online.target" "forgejo.service"];
      wants=["network-online.target"];
      serviceConfig={
        Type="oneshot";User="root";UMask="0077";
        StateDirectory="mrjam-acceptance";StateDirectoryMode="0700";
        LoadCredential=["github-app:/var/lib/mrjam-github-app/app-credentials.json"
          "forgejo-observer:/var/lib/mrjam-ci-credentials/forgejo-policy-token"]
          ++lib.optional (stage!="sync") "forgejo-role:/var/lib/mrjam-delivery-credentials/forgejo-${stage}-token";
        ExecStart="${package}/bin/mrjam-acceptance-${stage}";
        TimeoutStartSec=600;MemoryMax="768M";CPUQuota="25%";TasksMax=64;LimitCORE=0;
        ProtectSystem="strict";ProtectHome=true;PrivateDevices=true;
        TemporaryFileSystem=["/tmp:rw,size=512M,mode=1777"];
        ProtectKernelTunables=true;ProtectKernelModules=true;ProtectControlGroups=true;
        NoNewPrivileges=true;CapabilityBoundingSet=["CAP_DAC_READ_SEARCH"];
        RestrictSUIDSGID=true;RestrictNamespaces=true;LockPersonality=true;
        RestrictAddressFamilies=["AF_UNIX" "AF_INET" "AF_INET6"];
        InaccessiblePaths=["-/var/lib/postgresql" "-/var/lib/kanidm" "-/var/lib/nextcloud" "-/var/lib/forgejo"
          "-/var/lib/vise" "-/var/lib/mrjam-validation-authority/signing-key"
          "-/var/lib/mrjam-github-app" "-/var/lib/mrjam-ci-credentials" "-/var/lib/mrjam-delivery-credentials"
          "-/var/lib/mrjam-forgejo-runner/registration" "-/var/lib/mrjam-cutover/vise-adoption-20261103"
          "-/run/postgresql" "-/run/mrjam-identity" "-/run/secrets"
          "-/run/mrjam-validation-authority" "-/run/mrjam-validation-collector"
          "-/run/systemd/private" "-/run/dbus/system_bus_socket" "-/nix/var/nix/daemon-socket"];
        StandardOutput="journal";StandardError="null";
      };
    });
  systemd.timers=lib.genAttrs (map (stage: "mrjam-acceptance-${stage}") stages) (_: {
    wantedBy=["timers.target"];
    timerConfig={OnBootSec="1min";OnUnitInactiveSec="30s";RandomizedDelaySec="5s";};
  });
}
