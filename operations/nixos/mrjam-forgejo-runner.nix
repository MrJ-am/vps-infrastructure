{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamForgejoRunner;
  nftUid = value: if value == null then throw "mrjamForgejoRunner: explicit service UIDs required before building firewall rules" else toString value;
  boundedRunner = pkgs.callPackage ../forgejo/runner-admission.nix { };
  admissionPolicy = pkgs.writeText "mrjam-runner-admission.json" (builtins.toJSON {
    schema_version = 1;
    rules_revision = cfg.rulesRevision;
  });
  clientSources = pkgs.runCommand "mrjam-workflow-client" { } ''
    mkdir -p "$out"
    cp ${../forgejo/request_validation.py} "$out/request_validation.py"
    cp ${../forgejo/submit.py} "$out/submit.py"
  '';
  client = pkgs.writeShellScriptBin "mrjam-submit-validation" ''
    exec ${pkgs.python3}/bin/python3 -I -S ${clientSources}/request_validation.py
  '';
  registration = pkgs.runCommand "mrjam-forgejo-registration" { } ''
    mkdir -p "$out"
    cp ${../forgejo/register_runner.py} "$out/register_runner.py"
    cp ${../forgejo/reconcile.py} "$out/reconcile.py"
  '';
  runtime = pkgs.buildEnv {
    name = "mrjam-forgejo-coordinator-runtime";
    paths = [ boundedRunner pkgs.bash pkgs.coreutils pkgs.gitMinimal client ];
  };
  closure = pkgs.closureInfo { rootPaths = [ runtime ]; };
  # A private root containing only the coordinator's public executable closure.
  # No bind of the host /nix/store, /etc, /proc or persistent applications.
  # Copying the closure costs space; it deliberately avoids a host-store mount
  # which could expose machine configuration or unrelated confidential sources.
  root = pkgs.runCommand "mrjam-forgejo-coordinator-root" { } ''
    mkdir -p "$out/nix/store" "$out/bin" "$out/usr/bin" "$out/etc" \
      "$out/proc" "$out/sys/fs/cgroup" "$out/dev" "$out/tmp" "$out/run/mrjam-validation-collector" \
      "$out/var/tmp" "$out/home" "$out/root" "$out/run/user" \
      "$out/run/credentials/mrjam-forgejo-runner.service" \
      "$out/var/lib/mrjam-forgejo-runner" "$out/etc/mrjam-forgejo-runner"
    while IFS= read -r path; do
      cp -a --reflink=auto "$path" "$out/nix/store/"
    done < ${closure}/store-paths
    ln -s ${pkgs.bash}/bin/bash "$out/bin/sh"
    ln -s ${pkgs.coreutils}/bin/env "$out/usr/bin/env"
    touch "$out/run/mrjam-validation-collector/request.sock"
    # Nix deduplication may hardlink store files. Mount the explicit root-owned
    # /etc copy below; keep the runner's single-link policy check unchanged.
    touch "$out/etc/mrjam-forgejo-runner/admission.json"
    printf '%s\n' 'root:x:0:0:root:/var/empty:/bin/sh' > "$out/etc/passwd"
    printf '%s\n' 'root:x:0:' > "$out/etc/group"
  '';
  guarded = {
    UMask = "0077";
    NoNewPrivileges = true;
    CapabilityBoundingSet = "";
    AmbientCapabilities = "";
    ProtectSystem = "strict";
    ProtectHome = true;
    PrivateTmp = true;
    PrivateDevices = true;
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
    SystemCallArchitectures = "native";
    RestrictAddressFamilies = [ "AF_INET" "AF_UNIX" ];
    IPAddressDeny = "any";
    IPAddressAllow = "localhost";
    SocketBindDeny = "any";
    StandardError = "null";
  };
in {
  options.services.mrjamForgejoRunner = {
    enable = lib.mkEnableOption "repository-scoped Forgejo coordinator with a distinct isolated validation worker";
    rulesRevision = lib.mkOption { type = lib.types.strMatching "[0-9a-f]{40}"; };
    coordinatorUid = lib.mkOption {
      type = lib.types.nullOr (lib.types.ints.between 1 4294967294); default = null;
      description = "Explicit existing or reserved UID, reconciled before adoption; shared with the nftables policy.";
    };
    registrarUid = lib.mkOption {
      type = lib.types.nullOr (lib.types.ints.between 1 4294967294); default = null;
      description = "Distinct existing or reserved registration UID, reconciled before adoption.";
    };
    registrationTokenFile = lib.mkOption {
      type = lib.types.strMatching "/(run|var/lib)/[A-Za-z0-9_./-]+";
      description = "Existing local API credential reference for the separate registrar. Never visible to the daemon or worker.";
    };
    coordinatorRoot = lib.mkOption { type = lib.types.package; readOnly = true; default = root; };
    coordinatorPackage = lib.mkOption { type = lib.types.package; readOnly = true; default = boundedRunner; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = cfg.coordinatorUid != null && cfg.registrarUid != null && cfg.coordinatorUid != cfg.registrarUid;
        message = "mrjamForgejoRunner: two distinct explicit service UIDs are required; never infer them from the build host."; }
      { assertion = config.services.mrjamValidationWorker.enable;
        message = "mrjamForgejoRunner: the distinct validation worker must be configured."; }
      { assertion = config.services.mrjamValidationWorker.rulesRevision == cfg.rulesRevision;
        message = "mrjamForgejoRunner: coordinator and worker must pin the same protected rules revision."; }
      { assertion = config.services.mrjamValidationCollector.enable && config.services.mrjamValidationCollector.rulesRevision == cfg.rulesRevision;
        message = "mrjamForgejoRunner: a distinct artifact collector with the same rules is required."; }
      { assertion = config.networking.nftables.enable;
        message = "mrjamForgejoRunner: nftables must already be selected to enforce the coordinator's fixed loopback destination."; }
      { assertion = !(lib.hasInfix "/../" cfg.registrationTokenFile) && !(lib.hasSuffix "/.." cfg.registrationTokenFile);
        message = "mrjamForgejoRunner: credential references cannot contain parent traversal."; }
      { assertion = pkgs.forgejo-runner.version == "13.2.0" && pkgs.forgejo.version == "17.0.1";
        message = "mrjamForgejoRunner: runner/API version changes require a new qualification."; }
    ];
    users.groups.mrjam-forgejo-registration = { };
    users.groups.mrjam-forgejo-runner = { };
    users.users.mrjam-forgejo-registration = {
      isSystemUser = true;
      uid = cfg.registrarUid;
      group = "mrjam-forgejo-registration";
      home = "/var/empty";
    };
    users.users.mrjam-forgejo-runner = {
      isSystemUser = true;
      uid = cfg.coordinatorUid;
      group = "mrjam-forgejo-runner";
      extraGroups = [ "mrjam-validation-requesters" ];
      home = "/var/empty";
    };
    environment.etc."mrjam-forgejo-registration/policy.json" = {
      text = builtins.toJSON { rules_revision = cfg.rulesRevision; };
      mode = "0444";
    };
    environment.etc."mrjam-forgejo-runner/admission.json" = {
      source = admissionPolicy;
      mode = "0444"; # NixOS copies this file instead of creating a store symlink.
    };
    systemd.tmpfiles.rules = [
      "d /var/lib/mrjam-forgejo-runner/work 0700 mrjam-forgejo-runner mrjam-forgejo-runner -"
    ];
    networking.nftables.tables.mrjam-forgejo-coordinator = {
      family = "inet";
      content = ''
        chain bounded_output {
          type filter hook output priority 10; policy accept;
          meta skuid ${nftUid cfg.coordinatorUid} ip daddr 127.0.0.1 tcp dport 3004 accept
          meta skuid ${nftUid cfg.coordinatorUid} reject
          meta skuid ${nftUid cfg.registrarUid} ip daddr 127.0.0.1 tcp dport 3004 accept
          meta skuid ${nftUid cfg.registrarUid} reject
        }
      '';
    };
    systemd.services.mrjam-forgejo-registration = {
      description = "MRJ.am bounded repository-scoped runner registration";
      restartIfChanged = false;
      stopIfChanged = false;
      after = [ "nftables.service" ];
      requires = [ "nftables.service" ];
      serviceConfig = guarded // {
        Type = "oneshot";
        ExecStart = "${pkgs.python3}/bin/python3 -I -S ${registration}/register_runner.py";
        User = "mrjam-forgejo-registration";
        Group = "mrjam-forgejo-registration";
        StateDirectory = "mrjam-forgejo-registration";
        StateDirectoryMode = "0700";
        WorkingDirectory = "/var/lib/mrjam-forgejo-registration";
        LoadCredential = [ "forgejo-token:${cfg.registrationTokenFile}" ];
        InaccessiblePaths = [ "-/var/lib/forgejo" "-/var/lib/postgresql" "-/var/lib/kanidm" "-/var/lib/nextcloud" "-/var/backup" "-/var/backups" ];
        ReadWritePaths = [ "/var/lib/mrjam-forgejo-registration" ];
        MemoryMax = "128M";
        TasksMax = 8;
        TimeoutStartSec = 125;
        StandardOutput = "journal"; # Closed metadata only, never the generated token.
      };
    };
    systemd.services.mrjam-forgejo-runner = {
      description = "MRJ.am protected-workflow coordinator";
      # Starting the reviewed service is a separate bounded operation. An import
      # or generation switch does not register/start a runner automatically.
      restartIfChanged = false;
      stopIfChanged = false;
      after = [ "nftables.service" "mrjam-validation-collector.socket" ];
      requires = [ "nftables.service" "mrjam-validation-collector.socket" ];
      environment = {
        # NixOS also defines PATH from service.path. This private root contains
        # only the coordinator runtime; force that exact path, no host fallback.
        PATH = lib.mkForce "${runtime}/bin";
        HOME = "/var/lib/mrjam-forgejo-runner";
        USER = "mrjam-forgejo-runner";
      };
      unitConfig.ConditionPathExists = "/var/lib/mrjam-forgejo-registration/registration/identity.json";
      serviceConfig = guarded // {
        ExecStart = "${boundedRunner}/bin/forgejo-runner daemon --config %d/runner-config";
        User = "mrjam-forgejo-runner";
        Group = "mrjam-forgejo-runner";
        SupplementaryGroups = [ "mrjam-validation-requesters" ];
        RootDirectory = root;
        MountAPIVFS = true;
        BindReadOnlyPaths = [ "/run/mrjam-validation-collector/request.sock" "/etc/mrjam-forgejo-runner/admission.json" ];
        StateDirectory = "mrjam-forgejo-runner";
        StateDirectoryMode = "0700";
        WorkingDirectory = "/var/lib/mrjam-forgejo-runner";
        LoadCredential = [
          "runner-token:/var/lib/mrjam-forgejo-registration/registration/runner-token"
          "runner-config:/var/lib/mrjam-forgejo-registration/registration/connection.json"
        ];
        ReadWritePaths = [ "/var/lib/mrjam-forgejo-runner" ];
        MemoryMax = "512M";
        CPUQuota = "25%";
        TasksMax = 64;
        LimitNOFILE = 512;
        Restart = "no";
        KillMode = "control-group";
        TimeoutStopSec = 1950;
        StandardOutput = "null"; # No raw workflow or API output exported from production.
      };
    };
  };
}
