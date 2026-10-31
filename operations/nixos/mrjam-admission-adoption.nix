{ config, lib, ... }:
let
  cfg = config.services.mrjamAdmissionAdoption;
  name = "mrjam-admission-adoption";
  owner = "mrjam-vision-admission";
in {
  imports = [ ./mrjam-vision-admission.nix ];
  options.services.mrjamAdmissionAdoption = {
    enable = lib.mkEnableOption "explicit offline adoption of sealed historical admission state";
    artifactStorePath = lib.mkOption {
      type = lib.types.strMatching "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+";
      description = "Previously built and separately qualified mrjam-admission-adopt package.";
    };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = !(builtins.hasContext cfg.artifactStorePath);
        message = "Admission adoption requires an already qualified artifact without build context."; }
      { assertion = config.services.mrjamVisionAdmission.enable && !config.services.mrjamVisionAdmission.admissionsOpen;
        message = "Adoption requires the declared admission identity and closed public admissions."; }
    ];
    # Empty sealed staging only. Snapshot acquisition and retention are separate
    # bounded operator/controller operations, never an agent-readable input API.
    systemd.tmpfiles.rules = [ "d /var/lib/mrjam-admission-adoption-input 0700 root root -" ];
    systemd.services.${name} = {
      description = "MRJ.am explicit offline adoption of private admission snapshots";
      conflicts = [ "mrjam-vision-admission.service" "mrjam-vision-admission-initialize.service" ];
      after = [ "mrjam-vision-admission.service" "mrjam-vision-admission-initialize.service" ];
      restartIfChanged = false;
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${cfg.artifactStorePath}/bin/mrjam-admission-adopt";
        User = owner; Group = owner; Restart = "no";
        StateDirectory = owner; StateDirectoryMode = "0700";
        RuntimeDirectory = name; RuntimeDirectoryMode = "0700";
        BindReadOnlyPaths = [
          "/var/lib/mrjam-admission-adoption-input/requests.sqlite:/run/${name}/requests.sqlite"
          "/var/lib/mrjam-admission-adoption-input/mail.sqlite:/run/${name}/mail.sqlite"
        ];
        UMask = "0077"; StandardInput = "null"; StandardOutput = "journal"; StandardError = "journal";
        NoNewPrivileges = true; CapabilityBoundingSet = ""; AmbientCapabilities = "";
        ProtectSystem = "strict"; ProtectHome = true; PrivateTmp = true; PrivateDevices = true;
        PrivateNetwork = true; IPAddressDeny = "any"; RestrictAddressFamilies = [ "AF_UNIX" ];
        PrivateIPC = true; ProtectKernelTunables = true; ProtectKernelModules = true;
        ProtectKernelLogs = true; ProtectControlGroups = true; ProtectProc = "invisible";
        ProcSubset = "pid"; RestrictSUIDSGID = true; RestrictRealtime = true;
        RestrictNamespaces = true; LockPersonality = true; MemoryDenyWriteExecute = true;
        InaccessiblePaths = [ "-/run/postgresql" "-/var/lib/forgejo" "-/var/lib/postgresql"
          "-/var/lib/kanidm" "-/var/lib/nextcloud" "-/var/lib/mrjam-admission"
          "-/var/backup" "-/var/backups" "-/var/run/docker.sock" ];
        MemoryAccounting = true; MemoryMax = "512M"; CPUQuota = "20%"; TasksMax = 8;
        TimeoutStartSec = 90; TimeoutStopSec = 15; KillMode = "control-group"; LimitCORE = 0;
      };
    };
  };
}
