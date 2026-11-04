{ ... }:
let
  package = "/nix/store/gf10wjnkw745qf9kz3agfximnk74v683-mrjam-worker-credential-adaptation-1";
in {
  system.extraDependencies = [ (builtins.storePath package) ];
  systemd.services.mrjam-worker-credentials-adapt = {
    description = "Explicit adaptation of the three existing private worker credentials";
    wantedBy = [ ];
    restartIfChanged = false;
    stopIfChanged = false;
    unitConfig.AssertPathIsDirectory = "/run/mrjam-worker-credential-adaptation";
    serviceConfig = {
      Type = "oneshot";
      User = "root";
      Group = "root";
      ExecStart = "${package}/bin/mrjam-worker-credentials-adapt";
      StateDirectory = "mrjam-worker-credentials";
      StateDirectoryMode = "0700";
      BindReadOnlyPaths = [ "/run/mrjam-worker-credential-adaptation" ];
      ReadWritePaths = [ "/var/lib/mrjam-worker-credentials" ];
      InaccessiblePaths = [ "-/var/lib/mrjam-identite" "-/var/lib/mrjam-metier"
        "-/var/lib/forgejo" "-/var/lib/kanidm" "-/var/lib/nextcloud" "-/var/lib/postgresql"
        "-/var/backup" "-/var/backups" "-/run/postgresql" "-/run/nix" ];
      UMask = "0077";
      LimitCORE = 0;
      NoNewPrivileges = true;
      CapabilityBoundingSet = "";
      AmbientCapabilities = "";
      ProtectSystem = "strict";
      ProtectHome = true;
      PrivateNetwork = true;
      PrivateTmp = true;
      PrivateDevices = true;
      ProtectKernelTunables = true;
      ProtectKernelModules = true;
      ProtectKernelLogs = true;
      ProtectControlGroups = true;
      ProtectProc = "invisible";
      ProcSubset = "pid";
      RestrictAddressFamilies = [ "AF_UNIX" ];
      RestrictNamespaces = true;
      RestrictSUIDSGID = true;
      RestrictRealtime = true;
      LockPersonality = true;
      MemoryDenyWriteExecute = true;
      StandardOutput = "null";
      StandardError = "null";
      TimeoutStartSec = 60;
      MemoryMax = "128M";
      TasksMax = 16;
    };
  };
}
