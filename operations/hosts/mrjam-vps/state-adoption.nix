# Explicit one-shot publication from sealed synthetic-qualified SQLite images.
# Preparing the images and stopping the old writers belong to the cutover backend.
{ lib, ... }:
let
  admission = "/nix/store/9dn05bap085d5c7bjzilqs4bwd4ql4gg-mrjam-admission-native-adoption-1";
  mail = "/nix/store/8x4pybgyhkz01jqd41363wfs5rz0fm8i-mrjam-mail-native-adoption-3";
  adopt = { user, source, binary, state, conflicts, memory }: {
    description = "Explicit publication of adopted ${state} SQLite state";
    wantedBy = [ ];
    inherit conflicts;
    restartIfChanged = false;
    stopIfChanged = false;
    unitConfig.AssertPathIsDirectory = source;
    serviceConfig = {
      Type = "oneshot";
      User = user;
      Group = user;
      ExecStart = binary;
      StateDirectory = state;
      StateDirectoryMode = "0700";
      BindReadOnlyPaths = [ source ];
      ReadWritePaths = [ "/var/lib/${state}" ];
      UMask = "0077";
      NoNewPrivileges = true;
      CapabilityBoundingSet = "";
      AmbientCapabilities = "";
      ProtectSystem = "strict";
      ProtectHome = true;
      PrivateNetwork = true;
      PrivateTmp = true;
      PrivateDevices = true;
      PrivateIPC = true;
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
      InaccessiblePaths = [ "-/var/lib/mrjam-metier" "-/var/lib/mrjam-identite"
        "-/var/lib/forgejo" "-/var/lib/kanidm" "-/var/lib/nextcloud"
        "-/var/lib/postgresql" "-/var/backup" "-/var/backups"
        "-/run/postgresql" "-/run/nix" "-/run/docker.sock" ];
      StandardInput = "null";
      StandardOutput = "null";
      StandardError = "null";
      LimitCORE = 0;
      TimeoutStartSec = 90;
      TimeoutStopSec = 30;
      KillMode = "control-group";
      MemoryMax = memory;
      CPUQuota = "100%";
      TasksMax = 16;
    };
  };
in {
  system.extraDependencies = map builtins.storePath [ admission mail ];
  systemd.services = {
    mrjam-admission-native-adopt = adopt {
      user = "mrjam-vision-admission";
      source = "/run/mrjam-admission-adoption";
      binary = "${admission}/bin/mrjam-admission-adopt";
      state = "mrjam-vision-admission";
      conflicts = [ "mrjam-vision-admission.service" "mrjam-vision-admission-initialize.service" ];
      memory = "512M";
    };
    mrjam-cycle-mail-adopt = adopt {
      user = "mrjam-vision-cycle";
      source = "/run/mrjam-cycle-mail-adoption";
      binary = "${mail}/bin/mrjam-cycle-mail-adopt";
      state = "mrjam-vision-cycle";
      conflicts = [ "mrjam-vision-cycle.service" "mrjam-vision-cycle-initialize.service" ];
      memory = "512M";
    };
    mrjam-archive-mail-adopt = adopt {
      user = "mrjam-vision-archive";
      source = "/run/mrjam-archive-mail-adoption";
      binary = "${mail}/bin/mrjam-archive-mail-adopt";
      state = "mrjam-vision-archive";
      conflicts = [ "mrjam-vision-archive.service" "mrjam-vision-archive-initialize.service" ];
      memory = "768M";
    };
  };
}
