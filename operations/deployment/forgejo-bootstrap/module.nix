{ config, lib, pkgs, ... }:
let
  package = pkgs.callPackage ./package.nix {
    forgejoUid = config.services.mrjamForgejoHost.uid;
    forgejoGid = config.services.mrjamForgejoHost.gid;
  };
  unit = operation: {
    description = "MRJ.am closed Forgejo technical ${operation}";
    wantedBy = [ ]; restartIfChanged = false; stopIfChanged = false;
    after = [ "forgejo.service" ]; requires = [ "forgejo.service" ];
    serviceConfig = {
      Type = "oneshot"; User = "root"; Group = "root";
      ExecStart = "${package}/bin/mrjam-forgejo-${operation}";
      ExecStopPost = "${package}/bin/mrjam-forgejo-cleanup";
      StateDirectory = "mrjam-forgejo-bootstrap"; StateDirectoryMode = "0700";
      UMask = "0077"; StandardInput = "null"; StandardOutput = "journal"; StandardError = "null";
      NoNewPrivileges = true; ProtectSystem = "strict"; ProtectHome = true;
      CapabilityBoundingSet = [ "CAP_SETUID" "CAP_SETGID" "CAP_DAC_READ_SEARCH" "CAP_SYS_PTRACE" ];
      # systemd260 drops SETUID while retaining seccomp setup capabilities unless
      # explicitly requested here. The child clears it on demotion to Forgejo.
      AmbientCapabilities = [ "CAP_SETUID" ];
      PrivateTmp = true; PrivateDevices = true; PrivateIPC = true;
      ProtectKernelTunables = true; ProtectKernelModules = true; ProtectKernelLogs = true; ProtectControlGroups = true;
      ProtectProc = "invisible"; ProcSubset = "pid"; RestrictNamespaces = true; RestrictSUIDSGID = true;
      RestrictRealtime = true; LockPersonality = true; MemoryDenyWriteExecute = true;
      RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" ];
      IPAddressDeny = "any"; IPAddressAllow = "localhost"; SocketBindDeny = "any";
      ReadWritePaths = [ "/var/lib/mrjam-forgejo-bootstrap" "/var/lib/forgejo" ];
      InaccessiblePaths = [ "-/var/lib/kanidm" "-/var/lib/nextcloud" "-/var/lib/mrjam-metier" "-/var/backup" "-/var/backups" ];
      TimeoutStartSec = 200; TimeoutStopSec = 60; KillMode = "control-group";
      MemoryMax = "512M"; CPUQuota = "100%"; TasksMax = 48; LimitCORE = 0;
    };
  };
in {
  assertions = [{ assertion = config.services.mrjamForgejoHost.enable
      && config.services.mrjamForgejoHost.uid != null && config.services.mrjamForgejoHost.gid != null;
    message = "Forgejo bootstrap must bind its immutable package to the adopted Forgejo UID/GID."; }];
  systemd.services.mrjam-forgejo-probe = unit "probe";
  systemd.services.mrjam-forgejo-bootstrap = unit "bootstrap";
}
