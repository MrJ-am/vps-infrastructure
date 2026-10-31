{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamValidationWorker;
  closure = pkgs.closureInfo { rootPaths = [ cfg.validator ]; };
  policy = {
    schema_version = 1;
    rules_revision = cfg.rulesRevision;
    validator_store = toString cfg.validator;
    bubblewrap_store = toString pkgs.bubblewrap;
    closure_file = "${closure}/store-paths";
  };
in {
  options.services.mrjamValidationWorker = {
    enable = lib.mkEnableOption "isolated source-only validation worker";
    validator = lib.mkOption {
      type = lib.types.package;
      description = "Independently pinned rules package with bin/mrjam-validate. Never selected by a candidate or request.";
    };
    rulesRevision = lib.mkOption { type = lib.types.strMatching "[0-9a-f]{40}"; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [{
      assertion = pkgs.bubblewrap.version == "0.12.0";
      message = "mrjamValidationWorker: bubblewrap version changed; requalify namespace boundaries.";
    }];
    users.groups.mrjam-validation-worker = { };
    users.groups.mrjam-validation-submitters = { };
    users.users.mrjam-validation-worker = {
      isSystemUser = true;
      group = "mrjam-validation-worker";
      extraGroups = [ ];
      hashedPassword = "!";
      createHome = false;
      home = "/var/empty";
    };
    environment.etc."mrjam-validation-worker/policy.json" = { text = builtins.toJSON policy; mode = "0444"; };
    systemd.tmpfiles.rules = [
      "d /var/lib/mrjam-validation-input 0555 root root -"
      "d /run/mrjam-validation-worker 0750 root mrjam-validation-worker -"
      "f /run/mrjam-validation-worker/operation.lock 0440 root mrjam-validation-worker -"
      "d /run/mrjam-validation 0750 root mrjam-validation-submitters -"
    ];
    systemd.sockets.mrjam-validation-worker = {
      # Operator-controlled initial start; no WantedBy is introduced here.
      listenStreams = [ "/run/mrjam-validation/request.sock" ];
      socketConfig = {
        Accept = true;
        MaxConnections = 1;
        Backlog = 1;
        SocketUser = "root";
        SocketGroup = "mrjam-validation-submitters";
        SocketMode = "0660";
        RemoveOnStop = true;
        # Accept=yes selects the matching instantiated template automatically.
        # A bare @.service in Service= is rejected by systemd 260.
      };
    };
    systemd.services."mrjam-validation-worker@" = {
      description = "MRJ.am isolated source validation";
      restartIfChanged = false;
      serviceConfig = {
        Type = "exec";
        ExecStart = "${pkgs.python3}/bin/python3 -I -S ${../forgejo/worker.py}";
        User = "mrjam-validation-worker";
        Group = "mrjam-validation-worker";
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
        IPAddressDeny = "any";
        IPAddressAllow = "localhost";
        # Isolate the trusted worker itself before either Bubblewrap layer.
        # Masked submounts/hidepid on proc forbid an unprivileged fresh proc
        # mount (kernel mount_too_revealing). Do not combine those mechanisms.
        PrivatePIDs = true;
        ProtectProc = "default";
        ProcSubset = "all";
        # No root identity, host capabilities or writable host sysctl exists.
        # Explicit negative VM tests cover kernel writes and log access.
        ProtectKernelTunables = false;
        ProtectKernelModules = true;
        ProtectKernelLogs = false;
        ProtectControlGroups = true;
        RestrictSUIDSGID = true;
        LockPersonality = true;
        RestrictRealtime = true;
        RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" "AF_NETLINK" ];
        # Bubblewrap itself must create unprivileged namespaces and mounts.
        # No broad syscall deny-list is advertised as qualified before VM tests.
        InaccessiblePaths = [ "-/run/credentials" "-/var/lib/forgejo" "-/var/lib/postgresql" "-/var/lib/kanidm" "-/var/lib/nextcloud" "-/var/backup" "-/var/backups" "-/var/run/docker.sock" ];
        ReadOnlyPaths = [ "/var/lib/mrjam-validation-input" ];
        MemoryMax = "2G";
        CPUQuota = "100%";
        TasksMax = 256;
        RuntimeMaxSec = 1830;
        TimeoutStartSec = 1835;
        KillMode = "control-group";
        LimitCORE = 0;
      };
    };
  };
}
