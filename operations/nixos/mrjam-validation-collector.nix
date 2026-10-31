{ config, lib, pkgs, ... }:
let cfg = config.services.mrjamValidationCollector;
in {
  options.services.mrjamValidationCollector = {
    enable = lib.mkEnableOption "separate identity for collecting and retaining validated code artifacts";
    rulesRevision = lib.mkOption { type = lib.types.strMatching "[0-9a-f]{40}"; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = config.services.mrjamValidationWorker.enable && config.services.mrjamValidationWorker.rulesRevision == cfg.rulesRevision;
        message = "mrjamValidationCollector: the worker must pin the same independent rules revision."; }
    ];
    users.groups.mrjam-validation-collector = { };
    users.groups.mrjam-validation-requesters = { };
    users.users.mrjam-validation-collector = {
      isSystemUser = true;
      group = "mrjam-validation-collector";
      extraGroups = [ "mrjam-validation-submitters" ];
      hashedPassword = "!";
      home = "/var/empty";
      createHome = false;
    };
    environment.etc."mrjam-validation-submit/policy.json" = { text = builtins.toJSON { rules_revision = cfg.rulesRevision; }; mode = "0444"; };
    systemd.tmpfiles.rules = [
      "d /run/mrjam-validation-collector 0750 root mrjam-validation-requesters -"
      "d /var/lib/mrjam-validation-collector/artifacts 0700 mrjam-validation-collector mrjam-validation-collector -"
    ];
    systemd.sockets.mrjam-validation-collector = {
      listenStreams = [ "/run/mrjam-validation-collector/request.sock" ];
      socketConfig = {
        Accept = true;
        MaxConnections = 1;
        Backlog = 1;
        SocketUser = "root";
        SocketGroup = "mrjam-validation-requesters";
        SocketMode = "0660";
        RemoveOnStop = true;
        # Accept=yes instantiates the matching service template automatically.
      };
    };
    systemd.services."mrjam-validation-collector@" = {
      description = "MRJ.am bounded isolated artifact collector";
      after = [ "mrjam-validation-worker.socket" ];
      requires = [ "mrjam-validation-worker.socket" ];
      restartIfChanged = false;
      serviceConfig = {
        Type = "exec";
        ExecStart = "${pkgs.python3}/bin/python3 -I -S ${../forgejo/submit.py}";
        User = "mrjam-validation-collector";
        Group = "mrjam-validation-collector";
        SupplementaryGroups = [ "mrjam-validation-submitters" ];
        StateDirectory = "mrjam-validation-collector";
        StateDirectoryMode = "0700";
        StandardInput = "socket";
        StandardOutput = "socket";
        StandardError = "null";
        NoNewPrivileges = true;
        CapabilityBoundingSet = "";
        AmbientCapabilities = "";
        UMask = "0077";
        ProtectSystem = "strict";
        ProtectHome = true;
        PrivateTmp = true;
        PrivateDevices = true;
        PrivateNetwork = true;
        ProtectProc = "invisible";
        ProcSubset = "pid";
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectKernelLogs = true;
        ProtectControlGroups = true;
        RestrictNamespaces = true;
        RestrictSUIDSGID = true;
        LockPersonality = true;
        RestrictRealtime = true;
        RestrictAddressFamilies = [ "AF_UNIX" ];
        InaccessiblePaths = [ "-/run/credentials" "-/var/lib/mrjam-forgejo-runner" "-/var/lib/forgejo" "-/var/lib/postgresql" "-/var/lib/kanidm" "-/var/lib/nextcloud" "-/var/backup" "-/var/backups" "-/var/run/docker.sock" ];
        ReadWritePaths = [ "/var/lib/mrjam-validation-collector" ];
        MemoryMax = "128M";
        TasksMax = 8;
        RuntimeMaxSec = 1860;
        TimeoutStartSec = 1865;
        KillMode = "control-group";
        LimitCORE = 0;
        LimitFSIZE = 67108864;
      };
    };
  };
}
