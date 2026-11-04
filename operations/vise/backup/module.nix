# Optional until the real SQL/systemd recovery fixture and host return pass.
{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamViseCoherentBackup;
  package = import ./package.nix { inherit pkgs; };
  common = {
    Type = "oneshot"; User = "root"; Group = "root";
    UMask = "0077"; NoNewPrivileges = true;
    ProtectSystem = "strict"; ProtectHome = true;
    PrivateTmp = true; PrivateDevices = true;
    StateDirectory = "mrjam-vise-backup"; StateDirectoryMode = "0700";
    ReadWritePaths = [ "/var/backup/mrjam/vise-v1" "/var/lib/mrjam-cutover/first-deployment" ];
    CapabilityBoundingSet = [ "CAP_DAC_READ_SEARCH" "CAP_SETUID" "CAP_SETGID" ];
    # Keep precisely the declared identity-drop capabilities through the
    # wrapper/interpreter exec chain under NoNewPrivileges.
    AmbientCapabilities = [ "CAP_DAC_READ_SEARCH" "CAP_SETUID" "CAP_SETGID" ];
    RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" ];
    IPAddressDeny = "any"; IPAddressAllow = "localhost";
    MemoryMax = "512M"; TasksMax = 32; CPUQuota = "50%";
    LimitCORE = 0; LimitFSIZE = "10G";
    StandardInput = "null"; StandardOutput = "journal"; StandardError = "null";
    TimeoutStartSec = "20min"; TimeoutStopSec = "4min";
    KillMode = "control-group";
  };
in {
  options.services.mrjamViseCoherentBackup = {
    enable = lib.mkEnableOption "coherent encrypted ViSe backup and restart recovery";
    promote = lib.mkEnableOption "periodic ViSe backup after qualification";
    credentialFile = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/mrjam-worker-credentials/v1/archive.json";
      description = "Private existing archive configuration; only its age recipient is consumed.";
    };
  };
  config = lib.mkIf cfg.enable {
    assertions = [{
      assertion = config.services.mrjamVise.enable && config.services.postgresql.enable;
      message = "ViSe coherent backup requires the separately adopted ViSe and PostgreSQL services.";
    }];
    systemd.tmpfiles.rules = [ "d /var/backup/mrjam/vise-v1 0700 root root -" ];
    systemd.services.mrjam-vise-backup = {
      description = "Private coherent encrypted ViSe database and deletion ledger backup";
      # A cgroup-wide kill can also kill ExecStopPost. Recover in a separate
      # unit after the failed capture has fully released its processes/lock.
      onFailure = [ "mrjam-vise-backup-recovery.service" ];
      after = [ "postgresql.service" "vise.service" ]; requires = [ "postgresql.service" ];
      restartIfChanged = false; stopIfChanged = false;
      serviceConfig = common // {
        ExecStart = "${package}/bin/mrjam-vise-backup-capture";
        ExecStopPost = "${package}/bin/mrjam-vise-backup-recover";
        LoadCredential = [ "archive-configuration:${cfg.credentialFile}" ];
      };
    };
    systemd.services.mrjam-vise-backup-recovery = {
      description = "Recover ViSe availability after an interrupted backup";
      after = [ "postgresql.service" "vise.service" ]; requires = [ "postgresql.service" ];
      wantedBy = lib.optional cfg.promote "multi-user.target";
      restartIfChanged = false; stopIfChanged = false;
      serviceConfig = common // {
        ExecStart = "${package}/bin/mrjam-vise-backup-recover";
        TimeoutStartSec = "6min";
      };
    };
    systemd.timers.mrjam-vise-backup = {
      wantedBy = lib.optional cfg.promote "timers.target";
      timerConfig = { OnCalendar = "*-*-* 02:30:00 UTC"; RandomizedDelaySec = "10min"; Persistent = true; };
    };
    systemd.timers.mrjam-vise-backup-recovery = {
      wantedBy = lib.optional cfg.promote "timers.target";
      timerConfig = { OnBootSec = "2min"; OnUnitInactiveSec = "60s"; };
    };
  };
}
